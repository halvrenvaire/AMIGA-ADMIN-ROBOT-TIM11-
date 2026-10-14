import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ConversationMessage, QAMemory
from app.services.bedrock_client import BedrockError
from app.services.vector_store import VectorStore
from tests.auth_helpers import auth_header

CHUNKS = [
    {"content": "QUEUED: invoice sudah diunggah dan menunggu dibaca AI.", "source": "sop.md",
     "origin": "local", "chunk_index": 0},
    {"content": "Voucher bukan persetujuan pembayaran.", "source": "sop.md",
     "origin": "local", "chunk_index": 1},
]


class FakeBedrock:
    def __init__(self, fail=False):
        self.fail = fail
        self.last_messages = None
        self.last_system = None

    def embed(self, text):
        if self.fail:
            raise BedrockError("down")
        return [1.0, 0.0] if "QUEUED" in text else [0.0, 1.0]

    def generate(self, system_prompt, messages, **kw):
        self.last_system, self.last_messages = system_prompt, messages
        return f"jawaban untuk: {messages[-1]['content']}"


class FakeIndexing:
    def __init__(self, store):
        self.store = store
        self.rebuilt = 0
        # Versi index unik per test, supaya memori /ask-agent dari test lain tidak terbawa
        self.version = f"test-{uuid.uuid4()}"

    def get_store(self):
        return self.store

    def build_index(self, force=False):
        self.rebuilt += 1
        return {**self.status(), "duration_seconds": 0.1}

    def status(self):
        return {"indexed": not self.store.is_empty(), "total_chunks": len(self.store.chunks),
                "sources": ["local:sop.md"], "last_indexed_at": self.version}


def _store():
    store = VectorStore()
    store.build(CHUNKS, [[1.0, 0.0], [0.0, 1.0]])
    return store


@pytest.fixture
def client():
    # Asisten hanya untuk peran internal; test memakai akun Finance Reviewer
    with TestClient(app, headers=auth_header("reviewer1@amiga.test")) as c:
        app.state.bedrock = FakeBedrock()
        app.state.indexing = FakeIndexing(_store())
        yield c


@pytest.fixture
def session_id():
    sid = f"test-{uuid.uuid4()}"
    yield sid
    # Termasuk sesi turunan (mis. f"{sid}-a") yang dibuat test memori /ask-agent
    with SessionLocal() as db:
        db.execute(delete(ConversationMessage).where(ConversationMessage.session_id.like(f"{sid}%")))
        db.execute(delete(QAMemory).where(QAMemory.session_id.like(f"{sid}%")))
        db.commit()


@pytest.fixture(params=["/ask", "/ask-agent"])
def endpoint(request):
    """Perilaku dasar /ask juga berlaku untuk /ask-agent (yang menambahkan memori)."""
    return request.param


def test_ask_returns_answer_and_ranked_sources(client, endpoint, session_id):
    r = client.post(endpoint, json={"question": "Apa yang dimaksud QUEUED?", "session_id": session_id})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "jawaban untuk: Apa yang dimaksud QUEUED?"
    assert body["session_id"] == session_id
    assert body["sources"][0]["chunk_index"] == 0
    assert body["sources"][0]["preview"].startswith("QUEUED")
    assert "QUEUED: invoice sudah diunggah" in app.state.bedrock.last_system


def test_second_question_includes_history(client, endpoint, session_id):
    client.post(endpoint, json={"question": "Apa itu QUEUED?", "session_id": session_id})
    client.post(endpoint, json={"question": "Lalu setelah itu?", "session_id": session_id})
    msgs = app.state.bedrock.last_messages
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "Apa itu QUEUED?"
    assert msgs[-1]["content"] == "Lalu setelah itu?"


def test_ask_validation_error(client, endpoint):
    assert client.post(endpoint, json={"question": "", "session_id": "x"}).status_code == 422


def test_ask_when_index_empty_returns_503(client, endpoint, session_id):
    app.state.indexing = FakeIndexing(VectorStore())
    r = client.post(endpoint, json={"question": "Apa itu QUEUED?", "session_id": session_id})
    assert r.status_code == 503


def test_ask_when_bedrock_down_returns_503_without_leaking_detail(client, endpoint, session_id):
    app.state.bedrock = FakeBedrock(fail=True)
    r = client.post(endpoint, json={"question": "Apa itu QUEUED?", "session_id": session_id})
    assert r.status_code == 503
    assert "down" not in r.text


def test_reindex_requires_valid_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "reindex_api_key", "kunci-benar")
    assert client.post("/reindex").status_code == 401
    assert client.post("/reindex", headers={"X-API-Key": "salah"}).status_code == 401
    assert app.state.indexing.rebuilt == 0

    r = client.post("/reindex", headers={"X-API-Key": "kunci-benar"})
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert app.state.indexing.rebuilt == 1


def test_health_reports_index_status(client):
    body = client.get("/health").json()
    assert body["database"] == "ok"
    assert body["rag"]["indexed"] is True
    assert body["rag"]["total_chunks"] == 2
    assert body["status"] == "ok"

    app.state.indexing = FakeIndexing(VectorStore())
    assert client.get("/health").json()["status"] == "degraded"


@pytest.mark.integration
def test_ask_end_to_end_with_real_bedrock(session_id):
    """Skenario plan Task 8: memakai index FAISS sungguhan + Bedrock sungguhan."""
    with TestClient(app, headers=auth_header("reviewer1@amiga.test")) as c:
        r = c.post("/ask", json={"question": "Apa yang dimaksud QUEUED?", "session_id": session_id})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"]
        assert any(s["source"] == "sop.md" for s in body["sources"])
