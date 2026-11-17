"""Train the three Image AI classifiers (bone fracture, brain tumor type, pneumonia) and export them exactly the way the server loads them.

Run on YOUR PC / Google Colab (a GPU helps a lot; CPU works for small runs). Not run inside the project generator: no datasets there.

    pip install torch torchvision onnx onnxruntime scikit-learn pillow numpy
    python -m ml.train_image_models --task pneumonia_classification   --data D:/datasets/chest_xray            --epochs 8
    python -m ml.train_image_models --task tumor_classification       --data D:/datasets/brain_tumor_mri       --epochs 10
    python -m ml.train_image_models --task fracture                   --data D:/datasets/bone_fracture         --epochs 10
(run from the backend/ folder)

Output (what app/services/image_ai.py loads, nothing else to configure):
    ml/models/images/<task>.onnx     input  float32 [N,3,224,224]  (RGB, /255, ImageNet mean/std)   output  logits [N,classes]
    ml/models/images/<task>.json     {"labels": [...], metrics...}   <- labels order = model output order

DATASET LAYOUT - either of:
    <data>/train/<class>/*.jpg  (+ <data>/val|valid/<class>, <data>/test/<class>)    <- Kaggle style, used as given
    <data>/<class>/*.jpg                                                                <- split 70/15/15 by this script
Class folder names are matched case-insensitively with the aliases in CLASS_ALIASES below (NORMAL, notumor, fractured, ...).

HONEST WARNINGS
* Public datasets are small, from one or few hospitals, and often contain shortcuts (hospital markers, scanner type, text on film)
  and several images per patient. The held-out numbers printed here come from the SAME dataset, so real-world accuracy will be lower.
  If your folder is flat, this script splits by file and the same patient can land in both train and test: numbers are then optimistic.
* This is a screening aid, NOT a diagnostic device. Validate on your own hospital's images, let a radiologist review the errors and keep the disclaimer.
* Check every dataset's licence before using it in a product.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

SIZE = 224
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)  # must match app/services/image_ai.py::_cnn
EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
OUT_DIR = os.path.join(HERE, "models", "images")  # = what app/services/image_ai.py::MODEL_DIR reads

TASKS = {
    "pneumonia_classification": ["normal", "pneumonia"],
    "tumor_classification": ["no_tumor", "glioma", "meningioma", "pituitary"],
    "fracture": ["no_fracture", "fracture"],
}
CLASS_ALIASES = {
    "pneumonia_classification": {"normal": "normal", "pneumonia": "pneumonia", "pneumonia_bacteria": "pneumonia", "pneumonia_virus": "pneumonia"},
    "tumor_classification": {"notumor": "no_tumor", "no_tumor": "no_tumor", "no tumor": "no_tumor", "normal": "no_tumor", "glioma": "glioma", "glioma_tumor": "glioma",
                             "meningioma": "meningioma", "meningioma_tumor": "meningioma", "pituitary": "pituitary", "pituitary_tumor": "pituitary"},
    "fracture": {"fractured": "fracture", "fracture": "fracture", "abnormal": "fracture", "positive": "fracture",
                 "not fractured": "no_fracture", "not_fractured": "no_fracture", "non_fractured": "no_fracture", "nonfractured": "no_fracture", "no_fracture": "no_fracture",
                 "normal": "no_fracture", "negative": "no_fracture"},
}
SPLIT_NAMES = {"train": "train", "training": "train", "val": "val", "valid": "val", "validation": "val", "test": "test", "testing": "test"}


# ----------------------------------------------------------------------------- dataset discovery (pure python, unit-testable)
def _images(folder: str) -> list[str]:
    out = []
    for root, _, files in os.walk(folder):
        out += [os.path.join(root, f) for f in files if f.lower().endswith(EXTS)]
    return sorted(out)


def _class_dirs(base: str, task: str) -> dict[str, list[str]]:
    """{canonical label: [image paths]} for the class folders directly inside `base`."""
    amap, found = CLASS_ALIASES[task], {}
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d)
        if os.path.isdir(p) and d.lower().strip() in amap:
            found.setdefault(amap[d.lower().strip()], []).extend(_images(p))
    return found


def discover(data: str, task: str, seed: int = 7) -> dict[str, list[tuple[str, int]]]:
    labels = TASKS[task]
    sub = {SPLIT_NAMES[d.lower()]: os.path.join(data, d) for d in os.listdir(data) if d.lower() in SPLIT_NAMES and os.path.isdir(os.path.join(data, d))}
    splits: dict[str, list[tuple[str, int]]] = {"train": [], "val": [], "test": []}
    if "train" in sub:
        for name, base in sub.items():
            for lab, files in _class_dirs(base, task).items():
                splits[name] += [(f, labels.index(lab)) for f in files]
        if not splits["val"]:  # no validation folder: carve 15% out of train
            rnd = random.Random(seed); rnd.shuffle(splits["train"]); k = max(1, len(splits["train"]) // 7)
            splits["val"], splits["train"] = splits["train"][:k], splits["train"][k:]
        # Kaggle pneumonia ships a tiny (16 image) val folder: if it is that small, take 10% of train instead
        if len(splits["val"]) < 50 and len(splits["train"]) > 1000:
            rnd = random.Random(seed); rnd.shuffle(splits["train"]); k = len(splits["train"]) // 10
            splits["val"] += splits["train"][:k]; splits["train"] = splits["train"][k:]
        if not splits["test"]:
            rnd = random.Random(seed + 1); rnd.shuffle(splits["val"]); k = max(1, len(splits["val"]) // 2)
            splits["test"], splits["val"] = splits["val"][:k], splits["val"][k:]
    else:
        found = _class_dirs(data, task)
        for lab, files in found.items():
            rnd = random.Random(seed); files = list(files); rnd.shuffle(files)
            a, b = int(len(files) * .7), int(len(files) * .85)
            i = labels.index(lab)
            splits["train"] += [(f, i) for f in files[:a]]; splits["val"] += [(f, i) for f in files[a:b]]; splits["test"] += [(f, i) for f in files[b:]]
    for name, items in splits.items():
        present = {labels[i] for _, i in items}
        missing = [l for l in labels if l not in present]
        if missing:
            raise SystemExit(f"Split '{name}' has no images for {missing}. Expected class folders matching {sorted(CLASS_ALIASES[task])} inside {data}")
    return splits


def class_metrics(y_true, y_pred, labels, scores=None) -> dict:
    import numpy as np
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    per = {}
    for i, l in enumerate(labels):
        tp = int(((y_true == i) & (y_pred == i)).sum()); fn = int(((y_true == i) & (y_pred != i)).sum())
        fp = int(((y_true != i) & (y_pred == i)).sum()); tn = int(((y_true != i) & (y_pred != i)).sum())
        per[l] = {"n": int((y_true == i).sum()), "sensitivity": round(tp / max(1, tp + fn), 3), "specificity": round(tn / max(1, tn + fp), 3), "precision": round(tp / max(1, tp + fp), 3)}
    conf = [[int(((y_true == i) & (y_pred == j)).sum()) for j in range(len(labels))] for i in range(len(labels))]
    out = {"test_images": int(len(y_true)), "accuracy": round(float((y_true == y_pred).mean()), 3), "per_class": per, "confusion_matrix(rows=true, cols=predicted)": conf}
    if scores is not None and len(labels) == 2:
        try:
            from sklearn.metrics import roc_auc_score
            out["auc"] = round(float(roc_auc_score(y_true, np.asarray(scores)[:, 1])), 3)
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------------- training (needs torch)
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--arch", choices=["mobilenet_v3_large", "resnet18"], default="mobilenet_v3_large", help="mobilenet: ~17 MB onnx, resnet18: ~45 MB")
    ap.add_argument("--max-per-class", type=int, default=0, help="cap training images per class (quick test run)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()

    import numpy as np
    import torch
    import torch.nn as nn
    from PIL import Image
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms as T

    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    labels = TASKS[a.task]
    splits = discover(a.data, a.task, a.seed)
    if a.max_per_class:
        kept, cnt = [], {}
        for f, i in splits["train"]:
            cnt[i] = cnt.get(i, 0) + 1
            if cnt[i] <= a.max_per_class:
                kept.append((f, i))
        splits["train"] = kept
    counts = np.array([sum(1 for _, i in splits["train"] if i == k) for k in range(len(labels))], dtype="float32")
    print({s: len(v) for s, v in splits.items()}, "train images per label:", dict(zip(labels, counts.astype(int))))
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    norm = T.Normalize(MEAN, STD)
    tf_train = T.Compose([T.Resize((SIZE, SIZE)), T.RandomHorizontalFlip(), T.RandomRotation(8), T.ColorJitter(0.15, 0.15), T.ToTensor(), norm])
    tf_eval = T.Compose([T.Resize((SIZE, SIZE)), T.ToTensor(), norm])

    class DS(Dataset):
        def __init__(s, items, tf): s.items, s.tf = items, tf
        def __len__(s): return len(s.items)
        def __getitem__(s, k):
            f, y = s.items[k]
            return s.tf(Image.open(f).convert("RGB")), y  # grayscale X-rays become 3 identical channels, like the server

    mk = lambda items, tf, sh: DataLoader(DS(items, tf), batch_size=a.batch, shuffle=sh, num_workers=min(4, os.cpu_count() or 1))
    tr, va, te = mk(splits["train"], tf_train, True), mk(splits["val"], tf_eval, False), mk(splits["test"], tf_eval, False)

    if a.arch == "resnet18":
        net = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1); net.fc = nn.Linear(net.fc.in_features, len(labels))
    else:
        net = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.IMAGENET1K_V2); net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, len(labels))
    net.to(dev)
    w = torch.tensor(counts.sum() / (len(labels) * np.maximum(counts, 1)), dtype=torch.float32, device=dev)  # rare classes must not be ignored
    loss_fn = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)

    def evaluate(loader):
        net.eval(); ys, ps, loss = [], [], 0.0
        with torch.no_grad():
            for x, y in loader:
                lo = net(x.to(dev)); loss += float(loss_fn(lo, y.to(dev))) * len(y)
                ys += y.tolist(); ps.append(torch.softmax(lo, 1).cpu().numpy())
        p = np.concatenate(ps); return np.array(ys), p, loss / max(1, len(ys))

    best, best_state, bad = 1e9, None, 0
    for ep in range(a.epochs):
        net.train(); tl = 0.0
        for x, y in tr:
            opt.zero_grad(); l = loss_fn(net(x.to(dev)), y.to(dev)); l.backward(); opt.step(); tl += float(l) * len(y)
        sched.step()
        yv, pv, vl = evaluate(va)
        print(f"epoch {ep + 1}/{a.epochs}  train_loss {tl / len(tr.dataset):.4f}  val_loss {vl:.4f}  val_acc {(pv.argmax(1) == yv).mean():.3f}")
        if vl < best - 1e-4:
            best, bad = vl, 0; best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 3:
                print("early stop"); break
    net.load_state_dict(best_state); net.to(dev)
    yt, pt, _ = evaluate(te)
    report = {"labels": labels, "task": a.task, "arch": a.arch, "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "images": {s: len(v) for s, v in splits.items()}, **class_metrics(yt, pt.argmax(1), labels, pt),
              "note": "Held-out split of the SAME dataset. Real-world accuracy will be lower. Screening aid only: validate on local data and have a doctor review."}

    # ---- export + verify: the ONNX file must give the same answer as the PyTorch model, with the server's preprocessing
    os.makedirs(a.out, exist_ok=True)
    net.eval().cpu()
    path = os.path.join(a.out, f"{a.task}.onnx")
    dummy = torch.zeros(1, 3, SIZE, SIZE)
    torch.onnx.export(net, dummy, path, input_names=["input"], output_names=["logits"], opset_version=17, dynamic_axes={"input": {0: "n"}, "logits": {0: "n"}})
    import onnxruntime as ort
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    x = torch.randn(2, 3, SIZE, SIZE)
    diff = float(np.abs(sess.run(None, {"input": x.numpy()})[0] - net(x).detach().numpy()).max())
    if diff > 1e-3:
        sys.exit(f"ONNX export check FAILED (max difference {diff}). The model was not saved for use.")
    report["onnx_check_max_diff"] = diff
    json.dump(report, open(os.path.join(a.out, f"{a.task}.json"), "w"), indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nSaved {path} (+ .json).\nNext: git add backend/ml/models/images/{a.task}.*  &&  commit && push  (and add onnxruntime to the server: already in requirements.txt).")


if __name__ == "__main__":
    main()
