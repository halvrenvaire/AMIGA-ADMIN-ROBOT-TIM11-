from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.db import get_db
from app.models import Client, User
from app.schemas.schemas import ClientRef, LoginResponse, MeResponse
from app.security import verify_password
from app.services.access_rules import accessible_client_ids

router = APIRouter(prefix="/auth", tags=["Login"])


def user_profile(db: Session, user: User) -> MeResponse:
    client_ids = accessible_client_ids(db, user)
    clients = db.scalars(select(Client).where(Client.id.in_(client_ids)).order_by(Client.name)).all()
    return MeResponse(
        id=user.id, email=user.email, full_name=user.full_name,
        roles=sorted(user.roles, key=lambda r: r.value),
        clients=[ClientRef(id=c.id, name=c.name) for c in clients],
    )


@router.post("/login", response_model=LoginResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login dengan email (isi di kolom `username`) dan password."""
    user = db.scalar(select(User).where(func.lower(User.email) == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau password salah.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun Anda dinonaktifkan. Hubungi System Admin.")
    return LoginResponse(access_token=create_access_token(user), user=user_profile(db, user))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Profil, peran, dan klien yang ditugaskan kepada pengguna yang sedang login."""
    return user_profile(db, user)
