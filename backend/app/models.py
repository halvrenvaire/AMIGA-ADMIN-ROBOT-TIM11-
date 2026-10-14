"""Model data AMIGA Robot Admin (PRD bagian 2, 3, 6, dan F8)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, REAL, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    PIC_KLIEN = "PIC_KLIEN"
    INTAKE_SUPPORT = "INTAKE_SUPPORT"
    FINANCE_REVIEWER = "FINANCE_REVIEWER"
    SERVICE_LEAD = "SERVICE_LEAD"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class DocStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    EXCEPTION = "EXCEPTION"
    AMIGA_REVIEWED = "AMIGA_REVIEWED"
    SENT_TO_CLIENT = "SENT_TO_CLIENT"


class IssueCode(str, enum.Enum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CALCULATION_DISCREPANCY = "CALCULATION_DISCREPANCY"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    RETURNED_BY_REVIEWER = "RETURNED_BY_REVIEWER"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assignments: Mapped[list["UserClientAssignment"]] = relationship(
        back_populates="user", foreign_keys="UserClientAssignment.user_id"
    )


class UserClientAssignment(Base):
    """Penugasan klien (isolasi klien, F7) dan delegasi Intake Support (FR-1.4)."""
    __tablename__ = "user_client_assignments"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    # Diisi bila penugasan ini adalah delegasi dari PIC Klien ke Intake Support
    delegated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="assignments", foreign_keys=[user_id])
    client: Mapped[Client] = relationship()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # PIC Klien yang diwakili bila diunggah oleh Intake Support
    on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    request_type: Mapped[str | None] = mapped_column(String(100))
    submitted_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus, name="doc_status"), index=True)
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    file_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(300))
    page_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Client] = relationship()
    extraction: Mapped["Extraction | None"] = relationship(back_populates="document", uselist=False)
    issues: Mapped[list["ValidationIssue"]] = relationship(back_populates="document")
    voucher: Mapped["Voucher | None"] = relationship(back_populates="document", uselist=False)


class Extraction(Base):
    """Data hasil ekstraksi AI, bisa dikoreksi Finance Reviewer (PRD bagian 6)."""
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    vendor_name: Mapped[str | None] = mapped_column(String(300))
    invoice_no: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    account_no: Mapped[str | None] = mapped_column(String(50))
    account_name: Mapped[str | None] = mapped_column(String(200))
    # Hasil normalisasi untuk deteksi duplikat (huruf kecil, tanpa spasi/tanda baca)
    vendor_norm: Mapped[str | None] = mapped_column(String(300), index=True)
    invoice_no_norm: Mapped[str | None] = mapped_column(String(100), index=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="extraction")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="extraction", order_by="LineItem.position", cascade="all, delete-orphan"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"))
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    extraction: Mapped[Extraction] = relationship(back_populates="line_items")


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    code: Mapped[IssueCode] = mapped_column(Enum(IssueCode, name="issue_code"))
    field: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="issues")


class Voucher(Base):
    __tablename__ = "vouchers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    voucher_no: Mapped[str] = mapped_column(String(60), unique=True)
    file_key: Mapped[str] = mapped_column(String(500))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    document: Mapped[Document] = relationship(back_populates="voucher")


class AuditLog(Base):
    """Jejak audit append-only (F8). UPDATE/DELETE ditolak trigger di database."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None = sistem/AI
    actor_label: Mapped[str] = mapped_column(String(200))
    on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))
    status_before: Mapped[str | None] = mapped_column(String(40))
    status_after: Mapped[str | None] = mapped_column(String(40))
    field: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    """Riwayat percakapan endpoint /ask (asisten SOP), dikelompokkan per session_id."""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QAMemory(Base):
    """Memori tanya-jawab /ask-agent: pertanyaan lama yang mirip dipakai sebagai referensi."""
    __tablename__ = "qa_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(REAL))
    # Waktu index SOP saat jawaban dibuat; memori dari index lama diabaikan setelah /reindex
    index_version: Mapped[str] = mapped_column(String(64), index=True)
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # 1 = 👍, -1 = 👎, None = belum dinilai
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
