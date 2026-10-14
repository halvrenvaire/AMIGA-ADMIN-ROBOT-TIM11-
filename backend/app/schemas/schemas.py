from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=100)


class SourceItem(BaseModel):
    source: str
    origin: str
    chunk_index: int
    score: float
    preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    session_id: str


class MemoryRef(BaseModel):
    """Tanya-jawab lama yang mirip dan dipakai sebagai referensi."""
    question: str
    score: float
    feedback: int | None


class AskAgentResponse(AskResponse):
    # ID untuk memberi 👍/👎; None bila jawaban tidak disimpan ke memori
    answer_id: int | None
    # Alasan jawaban disimpan / tidak disimpan ke memori
    memory_note: str
    memory_refs: list[MemoryRef]


class FeedbackRequest(BaseModel):
    answer_id: int
    helpful: bool


class FeedbackResponse(BaseModel):
    answer_id: int
    feedback: int


class IndexStatus(BaseModel):
    indexed: bool
    total_chunks: int
    sources: list[str]
    last_indexed_at: str | None


class ReindexResponse(IndexStatus):
    status: str
    duration_seconds: float


class HealthResponse(BaseModel):
    status: str
    database: str
    rag: IndexStatus
    llm_model: str
    embed_model: str


# --- Lihat isi database (hanya baca) ---

class TableCount(BaseModel):
    table: str
    rows: int


class QAMemoryItem(BaseModel):
    id: int
    session_id: str
    question: str
    answer: str
    feedback: int | None
    # True bila dibuat dari index SOP yang sedang aktif (bisa dipakai sebagai referensi)
    active: bool
    created_at: datetime


class SessionSummary(BaseModel):
    session_id: str
    messages: int
    last_activity: datetime


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class UserItem(BaseModel):
    email: str
    full_name: str
    role: str
    is_active: bool
    clients: list[str]
