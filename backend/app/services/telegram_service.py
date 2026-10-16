"""Menghubungkan chat Telegram dengan akun AMIGA lewat kode sekali pakai.

Alur: pengguna login di dashboard -> Pengaturan akun -> "Hubungkan Telegram" -> mendapat kode 6 digit
(berlaku beberapa menit) -> mengirim `/login <kode>` ke bot, atau membuka tautan t.me yang berisi kode.
Password tidak pernah diketik di chat Telegram.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TelegramLink, TelegramLinkCode, User
from app.services import audit_service

CODE_DIGITS = 6


def _hash(code: str) -> str:
    # Kode dicampur rahasia server, jadi isi tabel saja tidak cukup untuk menebak kodenya
    return hashlib.sha256(f"{settings.jwt_secret}:{code}".encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_session_id() -> str:
    return f"tg-{uuid.uuid4().hex[:16]}"


def normalize_code(text: str) -> str | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits if len(digits) == CODE_DIGITS else None


def create_link_code(db: Session, user: User) -> tuple[str, datetime]:
    """Kode baru membatalkan kode lama milik pengguna yang belum dipakai."""
    now = _now()
    db.execute(update(TelegramLinkCode)
               .where(TelegramLinkCode.user_id == user.id, TelegramLinkCode.used_at.is_(None))
               .values(used_at=now))
    active = set(db.scalars(select(TelegramLinkCode.code_hash).where(
        TelegramLinkCode.used_at.is_(None), TelegramLinkCode.expires_at > now)))
    while True:
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        if _hash(code) not in active:  # kode aktif tidak boleh kembar antar pengguna
            break
    expires_at = now + timedelta(minutes=settings.telegram_link_code_minutes)
    db.add(TelegramLinkCode(user_id=user.id, code_hash=_hash(code), expires_at=expires_at))
    db.commit()
    return code, expires_at


def redeem_code(db: Session, chat_id: int, telegram_username: str | None, code: str) -> User | None:
    """Pakai kode untuk menghubungkan chat ini. None bila kode salah, kedaluwarsa, sudah dipakai,
    atau akunnya nonaktif. Hubungan lama chat ini atau akun ini diganti."""
    now = _now()
    row = db.scalar(select(TelegramLinkCode).where(
        TelegramLinkCode.code_hash == _hash(code),
        TelegramLinkCode.used_at.is_(None),
        TelegramLinkCode.expires_at > now,
    ))
    if row is None:
        return None
    user = db.get(User, row.user_id)
    row.used_at = now
    if user is None or not user.is_active:
        db.commit()
        return None

    for old in db.scalars(select(TelegramLink).where(
            (TelegramLink.chat_id == chat_id) | (TelegramLink.user_id == user.id))):
        db.delete(old)
    db.flush()
    db.add(TelegramLink(user_id=user.id, chat_id=chat_id, telegram_username=telegram_username,
                        session_id=new_session_id()))
    audit_service.record(db, user, "TELEGRAM_LINKED",
                         note=f"Telegram terhubung{f' (@{telegram_username})' if telegram_username else ''}")
    db.commit()
    return user


def get_link_for_chat(db: Session, chat_id: int) -> TelegramLink | None:
    """Hubungan chat ini, hanya bila akunnya masih aktif."""
    link = db.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id))
    if link is None or not link.user.is_active:
        return None
    return link


def get_link_for_user(db: Session, user: User) -> TelegramLink | None:
    return db.scalar(select(TelegramLink).where(TelegramLink.user_id == user.id))


def unlink(db: Session, link: TelegramLink, *, via: str) -> None:
    user = link.user
    db.delete(link)
    audit_service.record(db, user, "TELEGRAM_UNLINKED", note=f"Telegram diputus lewat {via}")
    db.commit()


def reset_session(db: Session, link: TelegramLink) -> None:
    link.session_id = new_session_id()
    db.commit()
