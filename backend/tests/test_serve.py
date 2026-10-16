"""Mode produksi (app.serve): dashboard dan API dari satu port."""
import pytest
from fastapi.testclient import TestClient

from app import serve


@pytest.fixture
def client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>AMIGA</html>")
    (dist / "assets" / "app.js").write_text("console.log('amiga')")
    (tmp_path / "rahasia.env").write_text("JWT_SECRET=bocor")
    monkeypatch.setattr(serve, "DIST", dist)
    with TestClient(serve.app) as c:
        yield c


def test_api_is_served_under_api_prefix(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/", follow_redirects=False).headers["location"] == "/api/docs"


def test_frontend_files_and_spa_routes(client):
    assert client.get("/assets/app.js").text == "console.log('amiga')"
    for path in ("/", "/dokumen/123", "/akun"):
        r = client.get(path)
        assert r.status_code == 200 and "AMIGA" in r.text
    assert client.get("/assets/tidak-ada.js").status_code == 404


def test_files_outside_dist_are_never_served(client):
    for path in ("/../rahasia.env", "/%2e%2e/rahasia.env", "/..%2frahasia.env"):
        assert "bocor" not in client.get(path).text


def test_login_works_through_api_prefix(client):
    r = client.post("/api/auth/login", data={"username": "pic.alpha@amiga.test", "password": "salah"})
    assert r.status_code == 401
