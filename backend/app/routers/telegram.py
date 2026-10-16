"""Menghubungkan akun dengan bot Telegram dari halaman Pengaturan akun."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import User
from app.schemas.schemas import TelegramLinkCodeOut, TelegramStatus
from app.services import telegram_service

router = APIRouter(prefix="/auth/me/telegram", tags=["Telegram"])


def _bot_url() -> str:
    return f"https://t.me/{settings.telegram_bot_username}"


@router.get("", response_model=TelegramStatus)
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Apakah akun ini sudah terhubung ke bot Telegram."""
    link = telegram_service.get_link_for_user(db, user)
    return TelegramStatus(
        configured=bool(settings.telegram_bot_token), linked=link is not None,
        telegram_username=link.telegram_username if link else None,
        linked_at=link.linked_at if link else None,
        bot_username=settings.telegram_bot_username, bot_url=_bot_url(),
    )


@router.post("/link-code", response_model=TelegramLinkCodeOut)
def link_code(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kode sekali pakai untuk dikirim ke bot: `/login <kode>`. Kode lama yang belum dipakai dibatalkan."""
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Bot Telegram belum dikonfigurasi di server (TELEGRAM_BOT_TOKEN).")
    code, expires_at = telegram_service.create_link_code(db, user)
    return TelegramLinkCodeOut(code=code, expires_at=expires_at, bot_username=settings.telegram_bot_username,
                               deep_link=f"{_bot_url()}?start={code}")


@router.delete("", status_code=204)
def unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Putuskan Telegram dari akun ini. Bot tidak lagi bisa dipakai sampai dihubungkan ulang."""
    link = telegram_service.get_link_for_user(db, user)
    if link is None:
        raise HTTPException(404, "Akun ini belum terhubung ke Telegram.")
    telegram_service.unlink(db, link, via="dashboard")
