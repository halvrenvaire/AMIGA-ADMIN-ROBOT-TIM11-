"""Riwayat percakapan /ask per session_id, disimpan di PostgreSQL."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ConversationMessage


class HistoryService:
    def __init__(self, db: Session):
        self.db = db

    def add_turn(self, session_id: str, question: str, answer: str) -> None:
        self.db.add_all([
            ConversationMessage(session_id=session_id, role="user", content=question),
            ConversationMessage(session_id=session_id, role="assistant", content=answer),
        ])
        self.db.commit()

    def get_history(self, session_id: str, last_n: int = 6) -> list[dict]:
        """N pesan terakhir, urut dari yang paling lama."""
        rows = self.db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.id.desc())
            .limit(last_n)
        ).all()
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def clear_session(self, session_id: str) -> int:
        result = self.db.execute(
            delete(ConversationMessage).where(ConversationMessage.session_id == session_id)
        )
        self.db.commit()
        return result.rowcount
