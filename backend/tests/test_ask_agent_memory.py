"""Memori tanya-jawab /ask-agent (fitur yang membedakannya dari /ask)."""
from app.main import app
from tests.test_ask import FakeBedrock, client, session_id  # noqa: F401  (fixture)

ASK = "/ask-agent"


def _ask(client, question, sid):
    r = client.post(ASK, json={"question": question, "session_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


def test_first_question_is_stored_without_references(client, session_id):
    body = _ask(client, "Apa itu QUEUED?", session_id)
    assert body["answer_id"] is not None
    assert body["memory_note"].startswith("Disimpan ke memori")
    assert body["memory_refs"] == []


def test_similar_question_from_other_session_uses_old_answer_as_reference(client, session_id):
    _ask(client, "Apa itu QUEUED?", f"{session_id}-a")
    body = _ask(client, "QUEUED itu artinya apa?", f"{session_id}-b")

    assert [m["question"] for m in body["memory_refs"]] == ["Apa itu QUEUED?"]
    assert body["memory_refs"][0]["score"] >= 0.70
    system = app.state.bedrock.last_system
    assert "Tanya-jawab sebelumnya yang mirip" in system
    assert "jawaban untuk: Apa itu QUEUED?" in system


def test_unrelated_question_gets_no_reference(client, session_id):
    _ask(client, "Apa itu QUEUED?", f"{session_id}-a")
    body = _ask(client, "Apakah voucher sama dengan persetujuan bayar?", f"{session_id}-b")
    assert body["memory_refs"] == []
    assert "Tanya-jawab sebelumnya" not in app.state.bedrock.last_system


def test_follow_up_question_is_not_stored_or_matched(client, session_id):
    _ask(client, "Apa itu QUEUED?", session_id)
    body = _ask(client, "Kalau QUEUED lama, bagaimana?", session_id)  # lanjutan di sesi sama
    assert body["answer_id"] is None
    assert "pertanyaan lanjutan" in body["memory_note"]
    assert body["memory_refs"] == []


def test_not_found_answer_is_not_stored(client, session_id):
    class NotFoundBedrock(FakeBedrock):
        def generate(self, system_prompt, messages, **kw):
            return "Informasi tersebut tidak ada di dokumen SOP."

    app.state.bedrock = NotFoundBedrock()
    body = _ask(client, "Berapa harga saham QUEUED?", session_id)
    assert body["answer_id"] is None
    assert "tidak ditemukan di dokumen SOP" in body["memory_note"]


def test_thumbs_down_is_excluded_and_thumbs_up_is_prioritized(client, session_id):
    first = _ask(client, "Apa itu QUEUED?", f"{session_id}-a")["answer_id"]
    second = _ask(client, "Status QUEUED maksudnya?", f"{session_id}-b")["answer_id"]

    assert client.post(f"{ASK}/feedback", json={"answer_id": second, "helpful": True}).json() == {
        "answer_id": second, "feedback": 1,
    }
    refs = _ask(client, "QUEUED itu apa?", f"{session_id}-c")["memory_refs"]
    assert [m["question"] for m in refs][:2] == ["Status QUEUED maksudnya?", "Apa itu QUEUED?"]

    client.post(f"{ASK}/feedback", json={"answer_id": first, "helpful": False})
    refs = _ask(client, "QUEUED artinya?", f"{session_id}-d")["memory_refs"]
    assert "Apa itu QUEUED?" not in [m["question"] for m in refs]


def test_memory_from_old_index_is_ignored_after_reindex(client, session_id):
    _ask(client, "Apa itu QUEUED?", f"{session_id}-a")
    app.state.indexing.version = "versi-index-baru"  # efek /reindex
    body = _ask(client, "QUEUED itu artinya apa?", f"{session_id}-b")
    assert body["memory_refs"] == []


def test_ask_endpoint_does_not_write_memory(client, session_id):
    client.post("/ask", json={"question": "Apa itu QUEUED?", "session_id": f"{session_id}-a"})
    body = _ask(client, "QUEUED itu artinya apa?", f"{session_id}-b")
    assert body["memory_refs"] == []


def test_feedback_for_unknown_answer_returns_404(client):
    r = client.post(f"{ASK}/feedback", json={"answer_id": 999_999_999, "helpful": True})
    assert r.status_code == 404
