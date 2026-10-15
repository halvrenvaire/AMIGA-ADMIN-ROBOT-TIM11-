"""Login, profil, pengecekan peran di server, dan isolasi klien (F7, UAT 6)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import create_access_token
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Client, Role
from tests.auth_helpers import auth_header
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def api():
    # Tanpa `with`: startup (index Asisten) tidak perlu untuk test login
    return TestClient(app)


def _client_id(name):
    with SessionLocal() as db:
        return db.scalar(select(Client.id).where(Client.name == name))


def test_login_returns_token_and_profile(api, make_user):
    user = make_user(Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER)
    r = api.post("/auth/login", data={"username": user.email.upper(), "password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["roles"] == ["FINANCE_REVIEWER", "INTAKE_SUPPORT"]

    me = api.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == user.email


def test_wrong_password_is_rejected(api, make_user):
    user = make_user(Role.PIC_KLIEN)
    r = api.post("/auth/login", data={"username": user.email, "password": "salah"})
    assert r.status_code == 401
    assert "password salah" in r.json()["detail"]


def test_inactive_user_cannot_login_or_use_old_token(api, make_user):
    user = make_user(Role.SERVICE_LEAD, is_active=False)
    r = api.post("/auth/login", data={"username": user.email, "password": TEST_PASSWORD})
    assert r.status_code == 403
    old_token = create_access_token(user)
    assert api.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401


def test_missing_or_invalid_token_is_rejected(api):
    assert api.get("/auth/me").status_code == 401
    assert api.get("/auth/me", headers={"Authorization": "Bearer bukan-token"}).status_code == 401


def test_me_lists_only_assigned_clients(api):
    me = api.get("/auth/me", headers=auth_header("pic.alpha@amiga.test")).json()
    assert [c["name"] for c in me["clients"]] == ["PT Klien Alpha"]


def test_client_lists_are_isolated(api):
    names = [c["name"] for c in api.get("/clients", headers=auth_header("pic.beta@amiga.test")).json()]
    assert names == ["PT Klien Beta"]


def test_uat6_user_of_client_a_cannot_open_client_b_and_it_is_logged(api):
    beta_id = _client_id("PT Klien Beta")
    with SessionLocal() as db:
        before = db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)) or 0

    r = api.get(f"/clients/{beta_id}", headers=auth_header("pic.alpha@amiga.test"))
    assert r.status_code == 403
    assert "Akses ditolak" in r.json()["detail"]

    with SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.id > before, AuditLog.action == "ACCESS_DENIED"))
    assert log is not None
    assert log.client_id == beta_id
    assert "pic.alpha@amiga.test" in log.actor_label


def test_assigned_client_can_be_opened(api):
    alpha_id = _client_id("PT Klien Alpha")
    r = api.get(f"/clients/{alpha_id}", headers=auth_header("reviewer1@amiga.test"))
    assert r.status_code == 200
    assert r.json()["name"] == "PT Klien Alpha"
