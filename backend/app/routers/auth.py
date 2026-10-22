from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.db import get_db
from app.models import Client, Role, User
from app.schemas.schemas import (
    ClientRef, LoginResponse, MeResponse, PasswordChange, ProfileUpdate, SignatureIn, TokenResponse,
)
from app.security import hash_password, password_problem, verify_password
from app.services import audit_service, login_guard, signature_service
from app.services.access_rules import accessible_client_ids, assigned_client_ids

router = APIRouter(prefix="/auth", tags=["Login"])


def user_profile(db: Session, user: User) -> MeResponse:
    client_ids = accessible_client_ids(db, user)
    clients = db.scalars(select(Client).where(Client.id.in_(client_ids)).order_by(Client.name)).all()
    upload_ids = assigned_client_ids(db, user) if user.roles & {Role.PIC_KLIEN, Role.INTAKE_SUPPORT} else set()
    return MeResponse(
        id=user.id, email=user.email, full_name=user.full_name,
        roles=sorted(user.roles, key=lambda r: r.value),
        clients=[ClientRef(id=c.id, name=c.name) for c in clients],
        upload_clients=[ClientRef(id=c.id, name=c.name) for c in clients if c.id in upload_ids],
        signature_updated_at=user.signature_updated_at,
        submitter_profile=user.submitter_profile or {},
    )


@router.post("/login", response_model=LoginResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login dengan email (isi di kolom `username`) dan password. Terlalu banyak salah -> dikunci sementara."""
    email = form.username.strip().lower()
    ip = request.client.host if request.client else "-"
    wait = login_guard.retry_after(ip, email)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Terlalu banyak percobaan login yang salah. Coba lagi dalam {(wait + 59) // 60} menit.",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(form.password, user.password_hash):
        login_guard.record_failure(ip, email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau password salah.")
    login_guard.record_success(email)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun Anda dinonaktifkan. Hubungi System Admin.")
    return LoginResponse(access_token=create_access_token(user), user=user_profile(db, user))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Profil, peran, dan klien yang ditugaskan kepada pengguna yang sedang login."""
    return user_profile(db, user)


@router.patch("/me", response_model=MeResponse)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ubah nama tampilan dan/atau email. Mengganti email (dipakai untuk login) wajib dengan password saat ini."""
    if body.full_name is not None and body.full_name.strip() != user.full_name:
        audit_service.record(db, user, "PROFILE_UPDATED", field="full_name",
                             old_value=user.full_name, new_value=body.full_name.strip())
        user.full_name = body.full_name.strip()
    if body.email is not None and body.email.strip().lower() != user.email:
        email = body.email.strip().lower()
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password saat ini salah. Email tidak diubah.")
        if db.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah dipakai akun lain.")
        audit_service.record(db, user, "PROFILE_UPDATED", field="email", old_value=user.email, new_value=email)
        user.email = email
    db.commit()
    return user_profile(db, user)


@router.get("/me/signature")
def my_signature(user: User = Depends(get_current_user)):
    """Spesimen tanda tangan elektronik milik sendiri (PNG)."""
    if user.signature_png is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Belum ada tanda tangan elektronik.")
    return Response(user.signature_png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.put("/me/signature", response_model=MeResponse)
def set_my_signature(body: SignatureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PIC Klien mendaftarkan tanda tangan elektroniknya untuk kotak "Diajukan oleh" di voucher."""
    if Role.PIC_KLIEN not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tanda tangan elektronik di kotak \"Diajukan oleh\" hanya untuk PIC Klien.")
    replaced = user.signature_png is not None
    user.signature_png = signature_service.normalize(body.image)
    user.signature_updated_at = datetime.now(timezone.utc)
    audit_service.record(db, user, "SIGNATURE_UPDATED", field="signature",
                         note="Tanda tangan elektronik " + ("diganti" if replaced else "didaftarkan"))
    db.commit()
    return user_profile(db, user)


@router.delete("/me/signature", response_model=MeResponse)
def delete_my_signature(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.signature_png is not None:
        user.signature_png, user.signature_updated_at = None, None
        audit_service.record(db, user, "SIGNATURE_REMOVED", field="signature", note="Tanda tangan elektronik dihapus")
        db.commit()
    return user_profile(db, user)


@router.post("/me/password", response_model=TokenResponse)
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ganti password. Semua sesi lain keluar; sesi ini mendapat token baru."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password saat ini salah.")
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password baru harus berbeda dari password lama.")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    audit_service.record(db, user, "PASSWORD_CHANGED", note="Password diganti oleh pemilik akun; sesi lain dikeluarkan")
    db.commit()
    return TokenResponse(access_token=create_access_token(user))
