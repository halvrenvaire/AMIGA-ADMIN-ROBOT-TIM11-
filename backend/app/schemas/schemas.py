import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocStatus, IssueCode, Role, SignatoryKind


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
    # True bila jawaban memakai data antrean (sesuai hak akses pengguna)
    used_queue_data: bool = False


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
    clients: list[ClientRef]  # perusahaan yang datanya bisa dilihat (Finance Reviewer: semua)
    upload_clients: list[ClientRef] = []  # perusahaan yang boleh diajukan (penugasan System Admin)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    email: str | None = Field(None, min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    # Wajib bila email diganti
    current_password: str | None = Field(None, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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


# --- Dokumen invoice (F1–F3) ---

class DocumentSummary(BaseModel):
    id: uuid.UUID
    request_id: str
    client: ClientRef
    status: DocStatus
    request_type: str | None
    channel: str | None
    submitted_date: date | None
    due_date: date | None
    original_filename: str
    page_count: int
    uploaded_by: str
    on_behalf_of: str | None
    assigned_reviewer: str | None
    vendor_name: str | None
    total: Decimal | None
    created_at: datetime
    updated_at: datetime


class IssueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: IssueCode
    field: str | None
    message: str
    created_at: datetime


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    description: str | None
    qty: Decimal | None
    unit_price: Decimal | None
    subtotal: Decimal | None


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vendor_name: str | None
    invoice_no: str | None
    invoice_date: date | None
    total: Decimal | None
    bank_name: str | None
    account_no: str | None
    account_name: str | None
    line_items: list[LineItemOut]
    extracted_at: datetime | None
    duration_ms: int | None


class VoucherOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    voucher_no: str
    generated_at: datetime


class DocumentFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    original_filename: str
    page_count: int


class DocumentDetail(DocumentSummary):
    # Kendala yang masih terbuka: kode + alasan berbahasa sederhana (FR-3.3)
    issues: list[IssueItem]
    extraction: ExtractionOut | None
    # Field yang sudah diisi/diperbaiki PIC (didahulukan atas hasil AI)
    pic_overrides: dict[str, str]
    voucher: VoucherOut | None
    vendor: ClientRef | None = None  # vendor di data referensi (id, name) bila cocok
    signers: list[Signer] = []
    files: list[DocumentFileOut] = []  # file invoice yang digabung dalam voucher ini


class FixRequest(BaseModel):
    """Perbaikan oleh PIC Klien / Intake Support saat EXCEPTION (FR-3.4)."""
    fields: dict[str, str] = {}
    note: str | None = Field(None, max_length=1000)


# --- Peninjauan Finance Reviewer, voucher, jejak audit (F4, F5, F8) ---

class LineItemIn(BaseModel):
    description: str | None = Field(None, max_length=1000)
    qty: Decimal | None = None
    unit_price: Decimal | None = None
    subtotal: Decimal | None = None


class ReviewUpdate(BaseModel):
    """Koreksi data hasil ekstraksi oleh Finance Reviewer. Field yang tidak dikirim tidak berubah;
    `line_items` bila dikirim menggantikan seluruh rincian."""
    fields: dict[str, str | None] = {}
    line_items: list[LineItemIn] | None = None


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class AuditItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor_label: str
    action: str
    status_before: str | None
    status_after: str | None
    field: str | None
    old_value: str | None
    new_value: str | None
    note: str | None


# --- Dashboard antrean (F6, Layar 01) ---

class ReviewerLoadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    pending: int
    overloaded: bool


class DashboardSummary(BaseModel):
    counts: dict[str, int]
    problem: int
    due_soon: int
    overdue: int
    reviewers: list[ReviewerLoadOut]
    overload_threshold: int
    due_soon_days: int


class ReassignRequest(BaseModel):
    reviewer_id: uuid.UUID
    reason: str | None = Field(None, max_length=1000)


# --- Data referensi vendor dan penanda tangan (permintaan owner 14 Okt 2026) ---

class VendorIn(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    npwp: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=1000)
    contact_name: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=200)
    bank_name: str | None = Field(None, max_length=100)
    account_no: str | None = Field(None, max_length=50)
    account_name: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=1000)


class VendorCreate(VendorIn):
    client_id: uuid.UUID


class VendorOut(VendorIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client: ClientRef
    is_active: bool
    documents: int = 0
    created_at: datetime
    updated_at: datetime


class VendorCheck(BaseModel):
    exists: bool
    vendor: VendorOut | None


class SignatoryIn(BaseModel):
    kind: SignatoryKind = SignatoryKind.PENYETUJU
    full_name: str = Field(min_length=2, max_length=200)
    position: str = Field(min_length=2, max_length=120)
    is_default: bool = False


class SignatoryCreate(SignatoryIn):
    client_id: uuid.UUID


class SignatoryOut(SignatoryIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    is_active: bool


class Signer(BaseModel):
    """Salinan penanda tangan pada dokumen/voucher."""
    kind: SignatoryKind
    name: str
    position: str


class SignersUpdate(BaseModel):
    signatory_ids: list[uuid.UUID]


class VoucherRow(BaseModel):
    document_id: uuid.UUID
    voucher_no: str
    generated_at: datetime
    request_id: str
    client: ClientRef
    vendor_id: uuid.UUID | None
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: date | None
    total: Decimal | None
    status: DocStatus
    approved_by: str


class TrendPoint(BaseModel):
    date: date
    received: int
    approved: int
    exception: int


class DashboardMetrics(BaseModel):
    period_days: int
    start: date
    end: date
    status_counts: dict[str, int]
    received: int
    received_prev: int
    approved: int
    approved_prev: int
    trend: list[TrendPoint]
    avg_hours_to_voucher: float | None
    avg_extraction_seconds: float | None
    sla_on_time: int
    sla_total: int
    first_pass: int
    first_pass_total: int
    top_issues: list[dict]
    corrected_docs: int
    reviewed_docs: int
    total_value: Decimal
    total_value_prev: Decimal
    value_by_client: list[dict]
    top_vendors: list[dict]


# DocumentDetail merujuk Signer yang didefinisikan di bawahnya
DocumentDetail.model_rebuild()
