"""Endpoint lihat isi database (/db/*): hanya baca, tanpa data sensitif, hanya System Admin."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.auth_helpers import auth_header
from tests.test_ask import client, session_id  # noqa: F401  (fixture)


@pytest.fixture
def admin(client):
    """Login sebagai System Admin, memakai Asisten palsu yang dipasang fixture `client`.

    Tanpa `with`: startup aplikasi tidak dijalankan ulang, jadi Asisten palsu tidak tertimpa.
    """
    return TestClient(app, headers=auth_header("admin@amiga.test"))


def test_db_endpoints_are_admin_only(client):
    # `client` login sebagai Finance Reviewer
    assert client.get("/db/summary").status_code == 403
    assert client.get("/db/users", headers={"Authorization": ""}).status_code == 401


def test_summary_lists_tables_with_row_counts(admin):
    body = admin.get("/db/summary").json()
    tables = {t["table"]: t["rows"] for t in body}
    assert {"users", "clients", "qa_memory", "conversation_messages", "audit_logs"} <= tables.keys()
    assert "alembic_version" not in tables
    assert tables["clients"] >= 2


def test_qa_memory_shows_stored_answer_and_active_flag(client, admin, session_id):
    r = client.post("/ask-agent", json={"question": "Apa itu QUEUED?", "session_id": session_id})
    answer_id = r.json()["answer_id"]

    items = admin.get("/db/qa-memory").json()
    item = next(i for i in items if i["id"] == answer_id)
    assert item["question"] == "Apa itu QUEUED?"
    assert item["active"] is True
    assert "embedding" not in item


def test_conversation_list_and_detail(client, admin, session_id):
    client.post("/ask", json={"question": "Apa itu QUEUED?", "session_id": session_id})

    sessions = {s["session_id"]: s["messages"] for s in admin.get("/db/conversations").json()}
    assert sessions[session_id] == 2

    messages = admin.get(f"/db/conversations/{session_id}").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Apa itu QUEUED?"


def test_unknown_conversation_returns_404(admin):
    assert admin.get("/db/conversations/tidak-ada-sesi-ini").status_code == 404


def test_users_never_expose_password(admin):
    r = admin.get("/db/users")
    users = {u["email"]: u for u in r.json()}
    assert users["pic.alpha@amiga.test"]["clients"] == ["PT Klien Alpha"]
    assert users["admin@amiga.test"]["roles"] == ["SYSTEM_ADMIN"]
    assert users["multi@amiga.test"]["roles"] == ["FINANCE_REVIEWER", "INTAKE_SUPPORT"]
    assert "password" not in r.text.lower()
