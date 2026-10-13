import uuid

import pytest

from app.db import SessionLocal
from app.services.history_service import HistoryService


@pytest.fixture
def history():
    db = SessionLocal()
    service = HistoryService(db)
    session_id = f"test-{uuid.uuid4()}"
    yield service, session_id
    service.clear_session(session_id)
    db.close()


def test_add_three_turns_returns_six_messages_in_order(history):
    service, sid = history
    for i in range(1, 4):
        service.add_turn(sid, f"tanya {i}", f"jawab {i}")
    msgs = service.get_history(sid, last_n=6)
    assert [m["content"] for m in msgs] == [
        "tanya 1", "jawab 1", "tanya 2", "jawab 2", "tanya 3", "jawab 3"
    ]
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 3


def test_last_n_keeps_most_recent(history):
    service, sid = history
    for i in range(1, 4):
        service.add_turn(sid, f"tanya {i}", f"jawab {i}")
    assert [m["content"] for m in service.get_history(sid, last_n=2)] == ["tanya 3", "jawab 3"]


def test_sessions_are_isolated(history):
    service, sid = history
    service.add_turn(sid, "tanya", "jawab")
    assert service.get_history(f"{sid}-lain") == []


def test_clear_session_removes_everything(history):
    service, sid = history
    service.add_turn(sid, "tanya", "jawab")
    assert service.clear_session(sid) == 2
    assert service.get_history(sid) == []
