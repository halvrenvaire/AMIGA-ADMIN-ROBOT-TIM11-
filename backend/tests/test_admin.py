"""System Admin: kelola akun, peran, penugasan klien (FR-7.1) dan batasannya."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import create_access_token
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Client, Role, User, UserClientAssignment
from tests.auth_helpers import auth_header


@pytest.fixture
def admin():
    return TestClient(app, headers=auth_header("admin@amiga.test"))


@pytest.fixture
def new_emails():
    """Email untuk akun yang dibuat lewat API; akunnya dihapus setelah test."""
    emails: list[str] = []

    def factory() -> str:
        emails.append(f"test-{uuid.uuid4().hex[:10]}@amiga.test")
        return emails[-1]

    yield factory
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.email.in_(emails))))
        db.execute(delete(UserClientAssignment).where(UserClientAssignment.user_id.in_(ids)))
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()


def _client_ids():
    with SessionLocal() as db:
        return {name: str(cid) for cid, name in db.execute(select(Client.id, Client.name))}


def _create(admin, email, roles, clients=()):
    ids = _client_ids()
    return admin.post("/admin/users", json={
        "email": email, "full_name": "Akun Baru", "password": "password-baru-1",
        "roles": roles, "client_ids": [ids[c] for c in clients],
    })


def test_admin_creates_multi_role_user_with_clients(admin, new_emails):
    r = _create(admin, new_emails(), ["INTAKE_SUPPORT", "FINANCE_REVIEWER"], ["PT Klien Alpha"])
    assert r.status_code == 201
    body = r.json()
    assert body["roles"] == ["FINANCE_REVIEWER", "INTAKE_SUPPORT"]
    assert [c["name"] for c in body["clients"]] == ["PT Klien Alpha"]

    login = TestClient(app).post("/auth/login", data={"username": body["email"], "password": "password-baru-1"})
    assert login.status_code == 200


@pytest.mark.parametrize("roles", [["PIC_KLIEN", "INTAKE_SUPPORT"], ["SYSTEM_ADMIN", "FINANCE_REVIEWER"]])
def test_forbidden_role_combination_is_rejected(admin, new_emails, roles):
    r = _create(admin, new_emails(), roles)
    assert r.status_code == 422


def test_duplicate_email_is_rejected(admin):
    assert _create(admin, "reviewer1@amiga.test", ["FINANCE_REVIEWER"]).status_code == 409


def test_role_change_applies_immediately_and_is_audited(admin, new_emails):
    user = _create(admin, new_emails(), ["SERVICE_LEAD"], ["PT Klien Alpha"]).json()
    with SessionLocal() as db:
        token = create_access_token(db.get(User, uuid.UUID(user["id"])))
    as_user = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert as_user.get("/auth/me").json()["roles"] == ["SERVICE_LEAD"]

    r = admin.put(f"/admin/users/{user['id']}/roles", json={"roles": ["SERVICE_LEAD", "FINANCE_REVIEWER"]})
    assert r.status_code == 200
    # Token lama langsung membawa peran baru karena peran dibaca dari database
    assert as_user.get("/auth/me").json()["roles"] == ["FINANCE_REVIEWER", "SERVICE_LEAD"]

    with SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.action == "USER_ROLES_CHANGED")
                        .order_by(AuditLog.id.desc()).limit(1))
    assert (log.old_value, log.new_value) == ("SERVICE_LEAD", "FINANCE_REVIEWER, SERVICE_LEAD")
    assert user["email"] in log.note


def test_client_assignment_change(admin, new_emails):
    user = _create(admin, new_emails(), ["FINANCE_REVIEWER"], ["PT Klien Alpha"]).json()
    ids = _client_ids()
    r = admin.put(f"/admin/users/{user['id']}/clients", json={"client_ids": [ids["PT Klien Beta"]]})
    assert [c["name"] for c in r.json()["clients"]] == ["PT Klien Beta"]


def test_deactivated_user_loses_access(admin, new_emails):
    user = _create(admin, new_emails(), ["SERVICE_LEAD"]).json()
    with SessionLocal() as db:
        token = create_access_token(db.get(User, uuid.UUID(user["id"])))
    assert admin.patch(f"/admin/users/{user['id']}/active", json={"is_active": False}).status_code == 200
    assert TestClient(app).get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_admin_cannot_change_own_roles_clients_or_status(admin):
    me = admin.get("/auth/me").json()
    ids = _client_ids()
    assert admin.put(f"/admin/users/{me['id']}/roles",
                     json={"roles": ["SYSTEM_ADMIN", "SERVICE_LEAD"]}).status_code == 403
    assert admin.put(f"/admin/users/{me['id']}/clients",
                     json={"client_ids": [ids["PT Klien Alpha"]]}).status_code == 403
    assert admin.patch(f"/admin/users/{me['id']}/active", json={"is_active": False}).status_code == 403


@pytest.mark.parametrize("email", ["reviewer1@amiga.test", "lead@amiga.test", "pic.alpha@amiga.test"])
def test_admin_endpoints_reject_other_roles(email):
    api = TestClient(app, headers=auth_header(email))
    assert api.get("/admin/users").status_code == 403
    assert api.post("/admin/clients", json={"name": "PT Klien Gamma"}).status_code == 403


def test_duplicate_client_name_is_rejected(admin):
    assert admin.post("/admin/clients", json={"name": "pt klien alpha"}).status_code == 409
