import base64
import binascii
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.auth import ensure_client_access, get_current_user, require_roles
from app.db import get_db
from app.models import Client, Role, User
from app.schemas.schemas import ClientRef, SignatureIn
from app.services import audit_service
from app.services.access_rules import accessible_client_ids

router = APIRouter(prefix="/clients", tags=["Klien"])


@router.get("", response_model=list[ClientRef])
def list_clients(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Klien yang ditugaskan kepada pengguna (mis. pilihan klien di formulir unggah)."""
    ids = accessible_client_ids(db, user)
    return db.scalars(select(Client).where(Client.id.in_(ids)).order_by(Client.name)).all()


@router.get("/{client_id}", response_model=ClientRef)
def get_client(client_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detail satu klien. Klien yang tidak ditugaskan ditolak dan dicatat di jejak audit."""
    ensure_client_access(db, user, client_id)
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(404, "Klien tidak ditemukan.")
    return client


# --- Logo klien di kop Voucher Pengeluaran (feedback owner 19 Okt 2026) ---
logo_editors = require_roles(Role.PIC_KLIEN, Role.SYSTEM_ADMIN)
LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_MAX_SIZE = (1200, 400)  # px; kop voucher tinggi ±13 mm


def normalize_logo(image: str) -> bytes:
    """Data URL / base64 (PNG, JPEG, atau WEBP) → PNG, tepi transparan dipotong, ukuran dibatasi."""
    raw = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Gambar logo tidak valid.")
    if len(data) > LOGO_MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Logo maksimal 2 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Gunakan logo PNG, JPG, atau WEBP.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Logo tidak bisa dibaca. Gunakan PNG, JPG, atau WEBP.")
    img = img.convert("RGBA")
    box = img.getchannel("A").getbbox()
    if box is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Logo kosong.")
    img = img.crop(box)
    img.thumbnail(LOGO_MAX_SIZE)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _editable_client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    # System Admin mengelola semua klien; PIC Klien hanya klien yang ditugaskan
    if Role.SYSTEM_ADMIN not in user.roles:
        ensure_client_access(db, user, client_id)
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(404, "Klien tidak ditemukan.")
    return client


@router.get("/{client_id}/logo", response_class=Response)
def get_logo(client_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if Role.SYSTEM_ADMIN not in user.roles:
        ensure_client_access(db, user, client_id)
    client = db.scalar(select(Client).where(Client.id == client_id).options(undefer(Client.logo_png)))
    if client is None or not client.logo_png:
        raise HTTPException(404, "Klien belum punya logo.")
    return Response(client.logo_png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.put("/{client_id}/logo", response_model=ClientRef)
def set_logo(client_id: uuid.UUID, body: SignatureIn, user: User = Depends(logo_editors), db: Session = Depends(get_db)):
    """Unggah logo klien untuk kop Voucher Pengeluaran. Berlaku untuk voucher yang terbit setelahnya."""
    client = _editable_client(db, user, client_id)
    client.logo_png = normalize_logo(body.image)
    client.logo_updated_at = datetime.now(timezone.utc)
    audit_service.record(db, user, "CLIENT_LOGO_CHANGED", client_id=client.id, note=f"Logo {client.name} diperbarui")
    db.commit()
    return client


@router.delete("/{client_id}/logo", response_model=ClientRef)
def delete_logo(client_id: uuid.UUID, user: User = Depends(logo_editors), db: Session = Depends(get_db)):
    client = _editable_client(db, user, client_id)
    client.logo_png = None
    client.logo_updated_at = None
    audit_service.record(db, user, "CLIENT_LOGO_CHANGED", client_id=client.id, note=f"Logo {client.name} dihapus")
    db.commit()
    return client
