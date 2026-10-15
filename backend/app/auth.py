"""Login dengan token JWT dan pengecekan hak akses di server (F7).

Token hanya berisi ID pengguna dan waktu terbit. Peran dan status aktif dibaca ulang dari database
di setiap request, sehingga perubahan peran oleh System Admin langsung berlaku. Token yang terbit
sebelum password terakhir diganti ditolak, jadi ganti/reset password mengeluarkan semua sesi lama.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User
from app.services import audit_service
from app.services.access_rules import assigned_client_ids, can_access_client

ALGORITHM = "HS256"

# tokenUrl membuat tombol "Authorize" di /docs bisa login langsung
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Sesi tidak valid atau sudah berakhir. Silakan login lagi.",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    # iat dengan pecahan detik: token lama yang terbit di detik yang sama dengan ganti password tetap tertolak
    return jwt.encode({"sub": str(user.id), "iat": now.timestamp(), "exp": expire},
                      settings.jwt_secret, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    if user.password_changed_at and float(payload.get("iat", 0)) < user.password_changed_at.timestamp():
        raise _UNAUTHORIZED
    return user


def require_roles(*allowed: Role):
    """Dependency: pengguna harus punya minimal satu dari peran `allowed`."""
    allowed_set = set(allowed)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.roles & allowed_set:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Peran Anda tidak diizinkan melakukan aksi ini.")
        return user

    return dependency


def ensure_submit_access(db: Session, user: User, client_id: uuid.UUID) -> None:
    """Sisi pengaju (unggah, perbaikan, penanda tangan): hanya perusahaan yang ditugaskan System Admin.
    Pengguna peran ganda yang juga Finance Reviewer tetap tidak bisa mengajukan untuk perusahaan lain."""
    if client_id in assigned_client_ids(db, user):
        return
    audit_service.record(db, user, "ACCESS_DENIED", client_id=client_id,
                         note="Mencoba mengajukan untuk perusahaan yang tidak ditugaskan")
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak ditugaskan untuk mengajukan atas nama perusahaan ini.")


def ensure_client_access(db: Session, user: User, client_id: uuid.UUID) -> None:
    """Tolak akses ke klien yang tidak ditugaskan, dan catat penolakannya (FR-7.2)."""
    if can_access_client(db, user, client_id):
        return
    audit_service.record(db, user, "ACCESS_DENIED", client_id=client_id,
                         note="Mencoba membuka data klien yang tidak ditugaskan")
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Akses ditolak: klien ini tidak ditugaskan kepada Anda.")
