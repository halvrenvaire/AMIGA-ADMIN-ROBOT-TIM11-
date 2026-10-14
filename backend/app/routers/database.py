"""Melihat isi database dari /docs (hanya baca, untuk pengembangan).

Data sensitif tidak ditampilkan: hash password dan vektor embedding.
Setelah login tersedia (Tahap 3), endpoint ini dibatasi untuk System Admin.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ConversationMessage, QAMemory, User
from app.schemas.schemas import (
    MessageItem, QAMemoryItem, SessionSummary, TableCount, UserItem,
)

router = APIRouter(prefix="/db", tags=["Lihat Database"])


@router.get("/summary", response_model=list[TableCount])
def summary(db: Session = Depends(get_db)):
    """Jumlah baris di setiap tabel."""
    tables = sorted(t for t in inspect(db.get_bind()).get_table_names() if t != "alembic_version")
    # Nama tabel berasal dari skema database sendiri, bukan dari input pengguna
    return [
        TableCount(table=t, rows=db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one())
        for t in tables
    ]


@router.get("/qa-memory", response_model=list[QAMemoryItem])
def qa_memory(request: Request, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Isi memori tanya-jawab /ask-agent, terbaru di atas."""
    current = request.app.state.indexing.status()["last_indexed_at"]
    rows = db.scalars(select(QAMemory).order_by(QAMemory.id.desc()).limit(limit)).all()
    return [
        QAMemoryItem(
            id=r.id, session_id=r.session_id, question=r.question, answer=r.answer,
            feedback=r.feedback, active=r.index_version == current, created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/conversations", response_model=list[SessionSummary])
def conversations(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Daftar sesi chat (/ask dan /ask-agent), aktivitas terbaru di atas."""
    rows = db.execute(
        select(
            ConversationMessage.session_id,
            func.count().label("messages"),
            func.max(ConversationMessage.created_at).label("last_activity"),
        )
        .group_by(ConversationMessage.session_id)
        .order_by(func.max(ConversationMessage.created_at).desc())
        .limit(limit)
    ).all()
    return [SessionSummary(session_id=r.session_id, messages=r.messages, last_activity=r.last_activity)
            for r in rows]


@router.get("/conversations/{session_id}", response_model=list[MessageItem])
def conversation_detail(session_id: str, db: Session = Depends(get_db)):
    """Seluruh pesan dalam satu sesi, urut dari yang paling lama."""
    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.id)
    ).all()
    if not rows:
        raise HTTPException(404, "Sesi tidak ditemukan")
    return [MessageItem(id=r.id, role=r.role, content=r.content, created_at=r.created_at) for r in rows]


@router.get("/users", response_model=list[UserItem])
def users(db: Session = Depends(get_db)):
    """Daftar pengguna beserta klien yang ditugaskan (tanpa password)."""
    rows = db.scalars(select(User).order_by(User.email)).all()
    return [
        UserItem(
            email=u.email, full_name=u.full_name, role=u.role.value, is_active=u.is_active,
            clients=sorted(a.client.name for a in u.assignments),
        )
        for u in rows
    ]
