import uuid

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.models import User, UserClientAssignment, UserRole
from app.security import hash_password

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
