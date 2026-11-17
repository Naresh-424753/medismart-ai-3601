"""Photo upload for doctor profile photos, patient profile/emergency-card photos and the hospital website gallery.

Images are decoded with Pillow (so anything that is not a real raster image is rejected, SVG included), EXIF/GPS metadata is
dropped by re-encoding, the picture is shrunk to max 900 px and stored in MongoDB (Render's disk is wiped on every deploy).
They are served publicly at GET /media/{id}: only upload pictures that are meant to be public."""
import base64
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ..common import audit, new_id, now
from ..config import settings
from ..db import get_db
from ..deps import require_roles

router = APIRouter(prefix="/media", tags=["media"])
log = logging.getLogger("medismart.media")
uploader = require_roles("doctor", "admin", "patient")  # super_admin passes automatically
MAX_UPLOAD = 6 * 1024 * 1024
MAX_SIDE = 900


def _shrink(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise HTTPException(400, "This file is not a valid photo. Upload a JPG, PNG or WebP image.")
    if im.format not in {"JPEG", "PNG", "WEBP", "GIF", "MPO"}:
        raise HTTPException(400, "Upload a JPG, PNG or WebP image.")
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, "white")
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85, optimize=True)  # new file: no EXIF/GPS carried over
    return out.getvalue()


def _public_base(request: Request) -> str:
    base = (settings.PUBLIC_API_URL or str(request.base_url)).rstrip("/")
    if base.startswith("http://") and not any(h in base for h in ("localhost", "127.0.0.1")):
        base = "https://" + base[len("http://"):]
    return base


@router.post("/upload", status_code=201)
async def upload(request: Request, file: UploadFile = File(...), user: dict = Depends(uploader)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo too large (max 6 MB)")
    jpg = _shrink(data)
    db = get_db()
    if user["role"] != "admin" and await db.media.count_documents({"owner": user["id"]}) >= (12 if user["role"] == "patient" else 60):
        raise HTTPException(429, "Photo limit reached.")
    mid = new_id().replace("-", "")
    await db.media.insert_one({"id": mid, "owner": user["id"], "owner_role": user["role"], "size": len(jpg), "data": base64.b64encode(jpg).decode(), "created_at": now()})
    await audit(db, user["id"], "media_upload", mid, role=user["role"])
    return {"id": mid, "url": f"{_public_base(request)}/media/{mid}", "size": len(jpg)}


@router.get("/{mid}")
async def get_media(mid: str):
    if not mid.isalnum() or len(mid) > 64:
        raise HTTPException(404, "Not found")
    m = await get_db().media.find_one({"id": mid}, {"_id": 0, "data": 1})
    if not m:
        raise HTTPException(404, "Not found")
    return Response(base64.b64decode(m["data"]), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400", "Cross-Origin-Resource-Policy": "cross-origin"})
