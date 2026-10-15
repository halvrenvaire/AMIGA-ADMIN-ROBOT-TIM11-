"""System Admin: kelola akun, peran, dan penugasan klien (FR-7.1).

Setiap perubahan dicatat di jejak audit. System Admin tidak boleh mengubah peran,
penugasan, atau status akunnya sendiri.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import Client, Role, User, UserClientAssignment, UserRole
from app.schemas.schemas import (
    ActiveUpdate, AdminUser, ClientCreate, ClientOverview, ClientRef, ClientsUpdate, PasswordReset, RolesUpdate, UserCreate,
)
from app.security import hash_password, password_problem
from app.services import audit_service
from app.services.access_rules import RoleCombinationError, validate_role_combination

router = APIRouter(prefix="/admin", tags=["System Admin"])

admin_only = require_roles(Role.SYSTEM_ADMIN)


def _admin_user(db: Session, user: User) -> AdminUser:
    clients = db.scalars(
        select(Client).join(UserClientAssignment, UserClientAssignment.client_id == Client.id)
        .where(UserClientAssignment.user_id == user.id).order_by(Client.name)
    ).all()
    return AdminUser(
        id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active,
        roles=sorted(user.roles, key=lambda r: r.value),
        clients=[ClientRef(id=c.id, name=c.name) for c in clients],
    )


def _get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Pengguna tidak ditemukan.")
    return user


def _not_self(admin: User, target: User) -> None:
    if admin.id == target.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "System Admin tidak boleh mengubah peran, penugasan, atau status akunnya sendiri.")


def _check_roles(roles: set[Role]) -> None:
    try:
        validate_role_combination(roles)
    except RoleCombinationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


def _check_clients(db: Session, client_ids: set[uuid.UUID]) -> None:
    found = set(db.scalars(select(Client.id).where(Client.id.in_(client_ids))))
    if found != client_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ada klien yang tidak ditemukan.")


def _role_text(roles) -> str:
    return ", ".join(sorted(r.value for r in roles)) or "-"


@router.get("/users", response_model=list[AdminUser])
def list_users(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [_admin_user(db, u) for u in db.scalars(select(User).order_by(User.email))]


@router.post("/users", response_model=AdminUser, status_code=201)
def create_user(body: UserCreate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    roles, client_ids = set(body.roles), set(body.client_ids)
    _check_roles(roles)
    _check_clients(db, client_ids)
    email = body.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah terdaftar.")

    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password),
                role_links=[UserRole(role=r) for r in roles])
    db.add(user)
    db.flush()
    for cid in client_ids:
        db.add(UserClientAssignment(user_id=user.id, client_id=cid))
    audit_service.record(db, admin, "USER_CREATED", new_value=_role_text(roles),
                         note=f"Akun {email} dibuat")
    db.commit()
    return _admin_user(db, user)


@router.put("/users/{user_id}/roles", response_model=AdminUser)
def set_roles(user_id: uuid.UUID, body: RolesUpdate, admin: User = Depends(admin_only),
              db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    _not_self(admin, user)
    roles = set(body.roles)
    _check_roles(roles)

    old = user.roles
    if roles != old:
        user.role_links = [link for link in user.role_links if link.role in roles] + [
            UserRole(role=r) for r in roles - old
        ]
        audit_service.record(db, admin, "USER_ROLES_CHANGED", field="roles",
                             old_value=_role_text(old), new_value=_role_text(roles),
                             note=f"Peran {user.email} diubah")
        db.commit()
    return _admin_user(db, user)


@router.put("/users/{user_id}/clients", response_model=AdminUser)
def set_clients(user_id: uuid.UUID, body: ClientsUpdate, admin: User = Depends(admin_only),
                db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    _not_self(admin, user)
    new_ids = set(body.client_ids)
    _check_clients(db, new_ids)

    old_ids = set(db.scalars(select(UserClientAssignment.client_id)
                             .where(UserClientAssignment.user_id == user.id)))
    if new_ids != old_ids:
        db.execute(delete(UserClientAssignment).where(
            UserClientAssignment.user_id == user.id,
            UserClientAssignment.client_id.in_(old_ids - new_ids),
        ))
        for cid in new_ids - old_ids:
            db.add(UserClientAssignment(user_id=user.id, client_id=cid))
        names = dict(db.execute(select(Client.id, Client.name)
                                .where(Client.id.in_(old_ids | new_ids))).tuples().all())
        audit_service.record(db, admin, "USER_CLIENTS_CHANGED", field="clients",
                             old_value=", ".join(sorted(names[i] for i in old_ids)) or "-",
                             new_value=", ".join(sorted(names[i] for i in new_ids)) or "-",
                             note=f"Penugasan klien {user.email} diubah")
        db.commit()
    return _admin_user(db, user)


@router.patch("/users/{user_id}/active", response_model=AdminUser)
def set_active(user_id: uuid.UUID, body: ActiveUpdate, admin: User = Depends(admin_only),
               db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    _not_self(admin, user)
    if user.is_active != body.is_active:
        audit_service.record(db, admin, "USER_ACTIVATED" if body.is_active else "USER_DEACTIVATED",
                             field="is_active", old_value=str(user.is_active),
                             new_value=str(body.is_active), note=f"Status akun {user.email} diubah")
        user.is_active = body.is_active
        db.commit()
    return _admin_user(db, user)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(user_id: uuid.UUID, body: PasswordReset, admin: User = Depends(admin_only),
                   db: Session = Depends(get_db)):
    """Atur password baru untuk pengguna lain (mis. lupa password). Semua sesi pengguna itu keluar."""
    user = _get_user(db, user_id)
    _not_self(admin, user)
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    audit_service.record(db, admin, "PASSWORD_RESET_BY_ADMIN", note=f"Password {user.email} diatur ulang")
    db.commit()


@router.get("/clients", response_model=list[ClientRef])
def list_all_clients(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return db.scalars(select(Client).order_by(Client.name)).all()


@router.get("/clients/overview", response_model=list[ClientOverview])
def clients_overview(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Klien beserta PIC Klien dan Intake Support aktif yang ditugaskan, untuk memeriksa klien tanpa PIC."""
    people: dict[uuid.UUID, dict[Role, list[str]]] = {}
    for cid, name, role in db.execute(
        select(UserClientAssignment.client_id, User.full_name, UserRole.role)
        .join(User, User.id == UserClientAssignment.user_id)
        .join(UserRole, UserRole.user_id == User.id)
        .where(User.is_active.is_(True), UserRole.role.in_([Role.PIC_KLIEN, Role.INTAKE_SUPPORT]))
        .order_by(User.full_name)
    ):
        people.setdefault(cid, {}).setdefault(role, []).append(name)
    return [
        ClientOverview(id=c.id, name=c.name, created_at=c.created_at,
                       pics=people.get(c.id, {}).get(Role.PIC_KLIEN, []),
                       intakes=people.get(c.id, {}).get(Role.INTAKE_SUPPORT, []))
        for c in db.scalars(select(Client).order_by(Client.name))
    ]


@router.post("/clients", response_model=ClientRef, status_code=201)
def create_client(body: ClientCreate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    name = body.name.strip()
    if db.scalar(select(Client).where(func.lower(Client.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nama klien sudah terdaftar.")
    client = Client(name=name)
    db.add(client)
    db.flush()
    audit_service.record(db, admin, "CLIENT_CREATED", client_id=client.id, note=f"Klien {name} dibuat")
    db.commit()
    return client
