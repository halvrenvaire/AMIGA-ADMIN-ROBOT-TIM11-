"""Riwayat percakapan /ask dan /ask-agent per session_id, disimpan di PostgreSQL."""
import json
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ConversationMessage

# Batas teks data yang ikut dikirim ke model sebagai konteks pertanyaan lanjutan
DATA_CONTEXT_CHARS = 2500


def _with_data(content: str, data: dict | None) -> str:
    """Jawaban berbasis data dikirim ke model beserta rencana query dan isi tabelnya, supaya pertanyaan
    lanjutan ("tampilkan detail dokumen tersebut") bisa merujuk ke hasil sebelumnya."""
    if not data:
        return content
    note = f"\n\n[Rencana query jawaban ini: {json.dumps(data.get('plan', {}), ensure_ascii=False)}]"
    tables = data.get("text") or ""
    if len(tables) > DATA_CONTEXT_CHARS:
        tables = tables[:DATA_CONTEXT_CHARS] + "\n…(dipotong)"
    return content + note + (f"\n[Data yang ditampilkan]\n{tables}" if tables else "")


class HistoryService:
    def __init__(self, db: Session):
        self.db = db

    def add_turn(self, session_id: str, question: str, answer: str,
                 user_id: uuid.UUID | None = None, data: dict | None = None) -> None:
        self.db.add_all([
            ConversationMessage(session_id=session_id, user_id=user_id, role="user", content=question),
            ConversationMessage(session_id=session_id, user_id=user_id, role="assistant", content=answer, data=data),
        ])
        self.db.commit()

    def get_history(self, session_id: str, last_n: int = 6, user_id: uuid.UUID | None = None) -> list[dict]:
        """N pesan terakhir, urut dari yang paling lama. Dengan `user_id`, hanya pesan milik pengguna itu."""
        stmt = select(ConversationMessage).where(ConversationMessage.session_id == session_id)
        if user_id is not None:
            stmt = stmt.where(ConversationMessage.user_id == user_id)
        rows = self.db.scalars(stmt.order_by(ConversationMessage.id.desc()).limit(last_n)).all()
        return [{"role": r.role, "content": _with_data(r.content, r.data)} for r in reversed(rows)]

    def list_sessions(self, user_id: uuid.UUID, limit: int = 50) -> list[dict]:
        """Percakapan milik pengguna, terbaru di atas. Judulnya pertanyaan pertama."""
        first = (select(ConversationMessage.session_id, func.min(ConversationMessage.id).label("first_id"),
                        func.max(ConversationMessage.created_at).label("last_activity"),
                        func.count().label("messages"))
                 .where(ConversationMessage.user_id == user_id)
                 .group_by(ConversationMessage.session_id).subquery())
        rows = self.db.execute(
            select(first.c.session_id, ConversationMessage.content, first.c.last_activity, first.c.messages)
            .join(ConversationMessage, ConversationMessage.id == first.c.first_id)
            .order_by(first.c.last_activity.desc()).limit(limit)
        ).all()
        return [{"session_id": sid, "title": title[:120], "last_activity": last, "messages": n}
                for sid, title, last, n in rows]

    def get_messages(self, user_id: uuid.UUID, session_id: str) -> list[ConversationMessage]:
        return list(self.db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id, ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.id)
        ))

    def clear_session(self, session_id: str, user_id: uuid.UUID | None = None) -> int:
        stmt = delete(ConversationMessage).where(ConversationMessage.session_id == session_id)
        if user_id is not None:
            stmt = stmt.where(ConversationMessage.user_id == user_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount
