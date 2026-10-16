"""Batas percobaan login: aplikasi berjalan di IP publik saat deploy."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services import login_guard
from tests.conftest import TEST_PASSWORD


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_five_wrong_passwords_lock_the_account_for_this_ip(make_user):
    user = make_user("PIC_KLIEN")
    client = TestClient(app)
    for _ in range(login_guard.MAX_PER_IP_EMAIL):
        assert _login(client, user.email, "salah-123").status_code == 401
    r = _login(client, user.email, TEST_PASSWORD)  # password benar pun ditolak selama dikunci
    assert r.status_code == 429 and "Coba lagi" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0


def test_success_resets_the_counter(make_user):
    user = make_user("PIC_KLIEN")
    client = TestClient(app)
    for _ in range(login_guard.MAX_PER_IP_EMAIL - 1):
        _login(client, user.email, "salah-123")
    assert _login(client, user.email, TEST_PASSWORD).status_code == 200
    for _ in range(login_guard.MAX_PER_IP_EMAIL - 1):
        assert _login(client, user.email, "salah-123").status_code == 401


def test_email_is_locked_across_ips():
    for i in range(login_guard.MAX_PER_EMAIL):
        login_guard.record_failure(f"10.0.0.{i}", "korban@amiga.test")
    assert login_guard.retry_after("10.9.9.9", "korban@amiga.test") > 0
    assert login_guard.retry_after("10.9.9.9", "lain@amiga.test") == 0


@pytest.mark.parametrize("secret", ["", "dev-secret-ganti", "pendek"])
def test_weak_jwt_secret_is_refused(secret, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()
