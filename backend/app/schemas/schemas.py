import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role


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
    roles: list[str]
    is_active: bool
    clients: list[str]


# --- Login dan hak akses (F7) ---

class ClientRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[Role]
    clients: list[ClientRef]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeResponse


# --- System Admin: kelola akun, peran, penugasan klien (FR-7.1) ---

class AdminUser(MeResponse):
    is_active: bool


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    roles: list[Role] = Field(min_length=1)
    client_ids: list[uuid.UUID] = []


class RolesUpdate(BaseModel):
    roles: list[Role] = Field(min_length=1)


class ClientsUpdate(BaseModel):
    client_ids: list[uuid.UUID]


class ActiveUpdate(BaseModel):
    is_active: bool


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
