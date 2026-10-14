"""Endpoint lihat isi database (/db/*): hanya baca, tanpa data sensitif."""
from tests.test_ask import client, session_id  # noqa: F401  (fixture)


def test_summary_lists_tables_with_row_counts(client):
    body = client.get("/db/summary").json()
    tables = {t["table"]: t["rows"] for t in body}
    assert {"users", "clients", "qa_memory", "conversation_messages", "audit_logs"} <= tables.keys()
    assert "alembic_version" not in tables
    assert tables["clients"] >= 2


def test_qa_memory_shows_stored_answer_and_active_flag(client, session_id):
    r = client.post("/ask-agent", json={"question": "Apa itu QUEUED?", "session_id": session_id})
    answer_id = r.json()["answer_id"]

    items = client.get("/db/qa-memory").json()
    item = next(i for i in items if i["id"] == answer_id)
    assert item["question"] == "Apa itu QUEUED?"
    assert item["active"] is True
    assert "embedding" not in item


def test_conversation_list_and_detail(client, session_id):
    client.post("/ask", json={"question": "Apa itu QUEUED?", "session_id": session_id})

    sessions = {s["session_id"]: s["messages"] for s in client.get("/db/conversations").json()}
    assert sessions[session_id] == 2

    messages = client.get(f"/db/conversations/{session_id}").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Apa itu QUEUED?"


def test_unknown_conversation_returns_404(client):
    assert client.get("/db/conversations/tidak-ada-sesi-ini").status_code == 404


def test_users_never_expose_password(client):
    r = client.get("/db/users")
    users = {u["email"]: u for u in r.json()}
    assert users["pic.alpha@amiga.test"]["clients"] == ["PT Klien Alpha"]
    assert users["admin@amiga.test"]["role"] == "SYSTEM_ADMIN"
    assert "password" not in r.text.lower()
