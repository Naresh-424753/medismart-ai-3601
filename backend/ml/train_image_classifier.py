"""Train an image classifier for one Image AI kind and save it where the server picks it up.

    pip install tensorflow pillow
    python -m ml.train_image_classifier chest-xray --data D:/datasets/chest_xray --epochs 8

--data must contain one sub-folder per label, named EXACTLY like the labels in app/services/imaging.py, e.g. for chest-xray:
    chest_xray/normal/*.jpg   chest_xray/pneumonia/*.jpg   chest_xray/tuberculosis/*.jpg
(Folders for labels you have no data for must still exist; a label with no images makes the script stop.)
Output: models/<kind>.keras (+ models/<kind>.json with the held-out test metrics).

The saved model includes its own preprocessing, because the server feeds raw 0-255 RGB pixels at 224x224.

IMPORTANT - this is a screening aid, not a medical device. Public datasets are small, single-hospital and often have label
noise or shortcuts (hospital markers, scanner type). Before real patients ever see a result: validate on data from your own
hospital, have a radiologist/doctor review errors, and keep the disclaimer. The metrics file shows the numbers on a held-out
test split so you can be honest about performance (look at sensitivity per class, not only accuracy).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from app.services.imaging import KINDS, MODELS_DIR  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=sorted(KINDS))
    ap.add_argument("--data", required=True, help="folder with one sub-folder per label")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--fine-tune-epochs", type=int, default=4, help="extra epochs with the top of the backbone unfrozen (0 = skip)")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    spec = KINDS[a.kind]
    labels, size = spec["labels"], spec["size"]
    missing = [l for l in labels if not os.path.isdir(os.path.join(a.data, l)) or not any(os.scandir(os.path.join(a.data, l)))]
    if missing:
        sys.exit(f"Missing or empty folders for labels: {missing}. Expected sub-folders named exactly: {labels}")

    import numpy as np
    import tensorflow as tf
    from tensorflow import keras
    tf.keras.utils.set_random_seed(a.seed)

    def load(split):
        return keras.utils.image_dataset_from_directory(
            a.data, labels="inferred", label_mode="int", class_names=labels, image_size=(size, size), batch_size=a.batch,
            validation_split=0.3, subset=split, seed=a.seed, shuffle=True)

    train, rest = load("training"), load("validation")
    n_rest = int(rest.cardinality())
    val, test = rest.take(max(1, n_rest // 2)), rest.skip(max(1, n_rest // 2))  # 70% train / 15% val / 15% held-out test (batch-level split)
    train = train.prefetch(tf.data.AUTOTUNE)

    # class weights: rare classes (e.g. tuberculosis) must not be ignored
    counts = np.array([sum(1 for _ in os.scandir(os.path.join(a.data, l))) for l in labels], dtype="float32")
    weights = {i: float(counts.sum() / (len(labels) * c)) for i, c in enumerate(counts)}
    print("images per label:", dict(zip(labels, counts.astype(int))), "class weights:", {labels[i]: round(w, 2) for i, w in weights.items()})

    base = keras.applications.MobileNetV2(input_shape=(size, size, 3), include_top=False, weights="imagenet")
    base.trainable = False
    inp = keras.Input((size, size, 3))
    x = keras.layers.RandomFlip("horizontal")(inp)
    x = keras.layers.RandomRotation(0.05)(x)
    x = keras.layers.RandomZoom(0.1)(x)
    x = keras.layers.Rescaling(1 / 127.5, offset=-1)(x)  # preprocessing lives inside the model (server sends 0-255 pixels)
    x = base(x, training=False)
    x = keras.layers.GlobalAveragePooling2D()(x)
    x = keras.layers.Dropout(0.3)(x)
    out = keras.layers.Dense(len(labels), activation="softmax")(x)
    model = keras.Model(inp, out)
    model.compile(optimizer=keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    cb = [keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True, monitor="val_loss")]
    model.fit(train, validation_data=val, epochs=a.epochs, class_weight=weights, callbacks=cb)
    if a.fine_tune_epochs > 0:
        base.trainable = True
        for layer in base.layers[:-30]:
            layer.trainable = False
        model.compile(optimizer=keras.optimizers.Adam(1e-5), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
        model.fit(train, validation_data=val, epochs=a.fine_tune_epochs, class_weight=weights, callbacks=cb)

    y_true, y_pred = [], []
    for xb, yb in test:
        y_true += yb.numpy().tolist()
        y_pred += np.argmax(model.predict(xb, verbose=0), axis=1).tolist()
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    per = {}
    for i, l in enumerate(labels):
        tp = int(((y_true == i) & (y_pred == i)).sum())
        fn = int(((y_true == i) & (y_pred != i)).sum())
        fp = int(((y_true != i) & (y_pred == i)).sum())
        per[l] = {"n": int((y_true == i).sum()), "sensitivity": round(tp / max(1, tp + fn), 3), "precision": round(tp / max(1, tp + fp), 3)}
    report = {"kind": a.kind, "labels": labels, "test_images": int(len(y_true)), "accuracy": round(float((y_true == y_pred).mean()), 3), "per_class": per,
              "note": "Held-out split of the SAME dataset - real-world accuracy will be lower. Validate locally before clinical use."}
    os.makedirs(MODELS_DIR, exist_ok=True)
    model.save(os.path.join(MODELS_DIR, f"{a.kind}.keras"))
    json.dump(report, open(os.path.join(MODELS_DIR, f"{a.kind}.json"), "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"Saved models/{a.kind}.keras - restart the backend (and make sure tensorflow is installed there).")


if __name__ == "__main__":
    main()
