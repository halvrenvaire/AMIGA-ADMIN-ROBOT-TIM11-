"""Token login untuk akun hasil seed.py (tanpa perlu password)."""
from sqlalchemy import select

from app.auth import create_access_token
from app.db import SessionLocal
from app.models import User


def auth_header(email: str) -> dict[str, str]:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None, f"{email} belum ada: jalankan seed.py"
        return {"Authorization": f"Bearer {create_access_token(user)}"}
