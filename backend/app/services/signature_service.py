"""Spesimen tanda tangan elektronik untuk voucher.

PIC Klien menggoreskan (canvas) atau mengunggah gambar tanda tangan: miliknya sendiri untuk kotak
"Diajukan oleh", dan milik pemberi persetujuan untuk kotak "Disetujui oleh". Saat voucher terbit,
sistem menempelkan spesimen ini ke kotak yang sesuai. Kotak tanpa spesimen tetap kosong untuk
tanda tangan basah.

Gambar selalu diproses ulang di server (bukan disimpan apa adanya): dibuka dengan Pillow, latar
putih dijadikan transparan, dipotong ke goresan, dan disimpan ulang sebagai PNG kecil.
"""
import base64
import binascii
import io
import uuid

from fastapi import HTTPException, status
from PIL import Image, ImageChops, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Signatory, User

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_SIZE = (900, 300)  # px; cukup tajam untuk kotak ±55 x 17 mm di PDF
WHITE_CUTOFF = 235  # piksel lebih terang dari ini dianggap latar (untuk foto/scan tanda tangan)


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def normalize(image: str) -> bytes:
    """Data URL / base64 (PNG atau JPEG) → PNG transparan yang dipotong ke goresan tanda tangan."""
    raw = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise _bad("Gambar tanda tangan tidak valid.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise _bad("Gambar tanda tangan maksimal 2 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("PNG", "JPEG"):
            raise _bad("Gunakan gambar PNG atau JPG.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise _bad("Gambar tanda tangan tidak bisa dibaca. Gunakan PNG atau JPG.")

    img = img.convert("RGBA")
    # Latar terang menjadi transparan, supaya foto tanda tangan di kertas putih juga rapi di voucher
    ink = img.convert("L").point(lambda v: 0 if v > WHITE_CUTOFF else 255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), ink))
    box = img.getbbox()
    if box is None:
        raise _bad("Tanda tangan masih kosong. Goreskan atau unggah tanda tangan terlebih dahulu.")
    img = img.crop(box)
    if img.width < 20 or img.height < 8:
        raise _bad("Goresan tanda tangan terlalu kecil.")
    img.thumbnail(MAX_SIZE)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def for_signers(db: Session, signers: list[dict]) -> list[bytes | None]:
    """Spesimen untuk tiap penanda tangan di salinan dokumen (urutan sama). Salinan lama tanpa id → None."""
    user_ids = {uuid.UUID(s["user_id"]) for s in signers if s.get("user_id")}
    sig_ids = {uuid.UUID(s["signatory_id"]) for s in signers if s.get("signatory_id")}
    users = dict(db.execute(select(User.id, User.signature_png).where(User.id.in_(user_ids))).tuples().all()) \
        if user_ids else {}
    sigs = dict(db.execute(select(Signatory.id, Signatory.signature_png)
                           .where(Signatory.id.in_(sig_ids))).tuples().all()) if sig_ids else {}
    return [users.get(uuid.UUID(s["user_id"])) if s.get("user_id")
            else sigs.get(uuid.UUID(s["signatory_id"])) if s.get("signatory_id") else None
            for s in signers]
