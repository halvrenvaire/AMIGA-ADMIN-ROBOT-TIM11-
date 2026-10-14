"""Pengaturan akun: ubah profil, ganti password, reset password oleh admin.

Berjalan di dalam transaksi yang di-rollback (fixture tx), karena jejak audit append-only
mencegah akun test dihapus setelah ada catatan audit atas namanya.
"""
import uuid

from sqlalchemy import select

from app import db as db_module
from app.auth import create_access_token
from app.models import AuditLog, User, UserRole, Role
from app.security import hash_password
from tests.test_documents import DrainingClient, tx  # noqa: F401
from app.main import app

PASSWORD = "lama-12345"


def new_user(email=None):
    with db_module.SessionLocal() as db:
        user = User(email=email or f"akun-{uuid.uuid4().hex[:8]}@amiga.test", full_name="Akun Uji",
                    password_hash=hash_password(PASSWORD), role_links=[UserRole(role=Role.FINANCE_REVIEWER)])
        db.add(user)
        db.commit()
        return user, create_access_token(user)


def client(token):
    return DrainingClient(app, headers={"Authorization": f"Bearer {token}"})


def login(email, password):
    return DrainingClient(app).post("/auth/login", data={"username": email, "password": password})


def test_update_display_name(tx):
    user, token = new_user()
    r = client(token).patch("/auth/me", json={"full_name": "Nama Baru"})
    assert r.status_code == 200 and r.json()["full_name"] == "Nama Baru"
    with db_module.SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.actor_id == user.id, AuditLog.action == "PROFILE_UPDATED"))
    assert (log.field, log.old_value, log.new_value) == ("full_name", "Akun Uji", "Nama Baru")


def test_change_email_requires_current_password(tx):
    user, token = new_user()
    api = client(token)
    new_email = f"baru-{uuid.uuid4().hex[:6]}@amiga.test"
    assert api.patch("/auth/me", json={"email": new_email}).status_code == 403
    assert api.patch("/auth/me", json={"email": new_email, "current_password": "salah"}).status_code == 403
    r = api.patch("/auth/me", json={"email": new_email.upper(), "current_password": PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == new_email
    assert login(new_email, PASSWORD).status_code == 200


def test_email_must_be_unique_and_valid(tx):
    _, token = new_user()
    api = client(token)
    assert api.patch("/auth/me", json={"email": "reviewer2@amiga.test", "current_password": PASSWORD}).status_code == 409
    assert api.patch("/auth/me", json={"email": "bukan-email", "current_password": PASSWORD}).status_code == 422


def test_change_password_logs_out_other_sessions(tx):
    user, old_token = new_user()
    other_session = client(old_token)
    r = client(old_token).post("/auth/me/password", json={"current_password": PASSWORD, "new_password": "baru-67890"})
    assert r.status_code == 200
    new_token = r.json()["access_token"]
    assert other_session.get("/auth/me").status_code == 401   # sesi lama keluar
    assert client(new_token).get("/auth/me").status_code == 200  # sesi ini tetap
    assert login(user.email, PASSWORD).status_code == 401
    assert login(user.email, "baru-67890").status_code == 200
    with db_module.SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.actor_id == user.id, AuditLog.action == "PASSWORD_CHANGED"))
    assert log is not None and "baru-67890" not in (log.note or "")


def test_password_rules(tx):
    user, token = new_user()
    api = client(token)
    bad = [("salah", "baru-67890", 403, "Password saat ini salah"),
           (PASSWORD, PASSWORD, 422, "berbeda"),
           (PASSWORD, "pendek1", 422, None),
           (PASSWORD, "hanyahuruf", 422, "huruf dan angka"),
           (PASSWORD, user.email, 422, None)]
    for current, new, code, msg in bad:
        r = api.post("/auth/me/password", json={"current_password": current, "new_password": new})
        assert r.status_code == code, (new, r.text)
        if msg:
            assert msg in r.text


def test_admin_resets_password(tx):
    user, old_token = new_user()
    admin = DrainingClient(app, headers={"Authorization": f"Bearer {admin_token()}"})
    assert admin.post(f"/admin/users/{user.id}/password", json={"new_password": "reset-2468"}).status_code == 204
    assert client(old_token).get("/auth/me").status_code == 401
    assert login(user.email, "reset-2468").status_code == 200
    me = admin.get("/auth/me").json()
    assert admin.post(f"/admin/users/{me['id']}/password", json={"new_password": "reset-2468"}).status_code == 403
    reviewer = client(new_user()[1])
    assert reviewer.post(f"/admin/users/{user.id}/password", json={"new_password": "reset-2468"}).status_code == 403


def admin_token():
    with db_module.SessionLocal() as db:
        return create_access_token(db.scalar(select(User).where(User.email == "admin@amiga.test")))
