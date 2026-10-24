"""Konfigurasi pytest.

Test berjalan di database TERPISAH (<nama dev>_test, sama dengan yang dipakai E2E), bukan database
dev, supaya data yang diubah saat mencoba aplikasi tidak membuat test gagal. DATABASE_URL harus
di-set sebelum modul app diimpor, jadi bagian ini ada di paling atas.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    dev = next(line.split("=", 1)[1].strip() for line in (BACKEND / ".env").read_text().splitlines()
               if line.startswith("DATABASE_URL="))
    base, name = dev.rsplit("/", 1)
    return f"{base}/{name.split('?')[0]}_test"


os.environ["DATABASE_URL"] = _test_database_url()
if not os.environ["DATABASE_URL"].rsplit("/", 1)[1].endswith("_test"):
    raise SystemExit("Menolak: database test harus berakhiran _test")

# Skema terbaru dan akun seed di database test (aman diulang)
for cmd in ([sys.executable, "-m", "alembic", "upgrade", "head"], [sys.executable, "seed.py"]):
    subprocess.run(cmd, cwd=BACKEND, check=True, capture_output=True)

import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User, UserClientAssignment, UserRole  # noqa: E402
from app.security import hash_password  # noqa: E402

TEST_PASSWORD = "rahasia-test-123"


@pytest.fixture
def make_user():
    """Buat pengguna sementara dengan password TEST_PASSWORD; dihapus setelah test."""
    created: list[uuid.UUID] = []

    def factory(*roles, is_active=True) -> User:
        with SessionLocal() as db:
            user = User(email=f"test-{uuid.uuid4().hex[:10]}@amiga.test", full_name="Pengguna Test",
                        password_hash=hash_password(TEST_PASSWORD), is_active=is_active,
                        role_links=[UserRole(role=r) for r in roles])
            db.add(user)
            db.commit()
            created.append(user.id)
            return user

    yield factory
    with SessionLocal() as db:
        db.execute(delete(UserClientAssignment).where(UserClientAssignment.user_id.in_(created)))
        db.execute(delete(User).where(User.id.in_(created)))
        db.commit()


@pytest.fixture(autouse=True)
def _reset_login_guard():
    """Batas percobaan login disimpan di memori proses: kosongkan supaya test tidak saling memengaruhi."""
    from app.services import login_guard
    login_guard.reset()
    yield
    login_guard.reset()
