"""Model data AMIGA Robot Admin (PRD bagian 2, 3, 6, dan F8)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Enum, ForeignKey, Integer, LargeBinary, Numeric, SmallInteger, String, Text,
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


# Kategori pengajuan (feedback owner 19 Okt 2026): hanya untuk filter dashboard, tidak dicetak di voucher
REQUEST_CATEGORIES = ("Voucher Pengeluaran Vendor", "Voucher Pengeluaran Reimburse", "Lainnya")
CATEGORY_VENDOR, CATEGORY_REIMBURSE, CATEGORY_OTHER = REQUEST_CATEGORIES


class DocStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    # AI selesai membaca; PIC memeriksa/mengedit per invoice lalu mengirim ke reviewer (feedback owner)
    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    EXCEPTION = "EXCEPTION"
    AMIGA_REVIEWED = "AMIGA_REVIEWED"
    SENT_TO_CLIENT = "SENT_TO_CLIENT"
    # Dibatalkan pengaju sebelum disetujui (mis. salah unggah). Data dan jejak audit tetap tersimpan.
    CANCELLED = "CANCELLED"


class IssueCode(str, enum.Enum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CALCULATION_DISCREPANCY = "CALCULATION_DISCREPANCY"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    RETURNED_BY_REVIEWER = "RETURNED_BY_REVIEWER"
    # Beberapa invoice dalam satu voucher harus untuk satu vendor dan satu rekening tujuan
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    # AI (Invoice Verification Officer) menilai PDF bukan invoice dan tidak relevan: ditolak
    NOT_AN_INVOICE = "NOT_AN_INVOICE"
    # Struk/bon/nota pembelian: data diekstrak sebagai draft, tetapi bukan invoice resmi vendor
    RECEIPT_NOT_INVOICE = "RECEIPT_NOT_INVOICE"
    # Jenis dokumen meragukan atau datanya terlalu sedikit: Finance Reviewer memeriksa manual
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    # Rekening berbeda dengan rekening vendor yang sudah diverifikasi Finance Reviewer
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"


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
    # Token yang diterbitkan sebelum waktu ini ditolak (logout semua sesi setelah ganti/reset password)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Spesimen tanda tangan elektronik PIC Klien (PNG transparan) untuk kotak "Diajukan oleh"
    signature_png: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    signature_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignments: Mapped[list["UserClientAssignment"]] = relationship(
        back_populates="user", foreign_keys="UserClientAssignment.user_id"
    )
    role_links: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def roles(self) -> set[Role]:
        return {link.role for link in self.role_links}


class UserRole(Base):
    """Peran pengguna. Satu pengguna boleh punya lebih dari satu peran internal."""
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), primary_key=True)

    user: Mapped[User] = relationship(back_populates="role_links")


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


class Vendor(Base):
    """Data referensi vendor milik satu klien, didaftarkan PIC Klien. Nama unik per klien (dinormalisasi)."""
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("client_id", "name_norm"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    name_norm: Mapped[str] = mapped_column(String(300))
    npwp: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    account_no: Mapped[str | None] = mapped_column(String(50))
    account_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Data referensi tepercaya: rekening vendor diverifikasi Finance Reviewer (bukan pendaftarnya).
    # Direset otomatis bila data bank vendor diubah.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Siapa yang terakhir mengisi/mengubah data bank; tidak boleh memverifikasinya sendiri (SoD)
    bank_updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Client] = relationship()


class SignatoryKind(str, enum.Enum):
    PENGAJU = "PENGAJU"      # kotak "Diajukan oleh" (pihak PIC Klien)
    PENYETUJU = "PENYETUJU"  # kotak "Disetujui oleh" (direktur, bendahara, dll.)


class Signatory(Base):
    """Penanda tangan voucher milik satu klien, didaftarkan PIC Klien."""
    __tablename__ = "signatories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    kind: Mapped[SignatoryKind] = mapped_column(Enum(SignatoryKind, name="signatory_kind"))
    full_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Spesimen tanda tangan elektronik (PNG transparan), ditempel di kotak "Disetujui oleh" saat voucher terbit
    signature_png: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    signature_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxRate(Base):
    """Tarif potongan pajak yang bisa dipilih PIC per invoice (Tahap 4 feedback owner).
    Berlaku untuk semua klien; diubah Service Lead / System Admin. `needs_confirmation` = isi awal
    memakai aturan umum dan belum dikonfirmasi konsultan pajak."""
    __tablename__ = "tax_rates"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Persen, mis. 2 = 2%. Vendor tanpa NPWP memakai rate_no_npwp
    rate_npwp: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    rate_no_npwp: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # PIC Klien yang diwakili bila diunggah oleh Intake Support
    on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    request_type: Mapped[str | None] = mapped_column(String(100))
    # Asal pengajuan (FR-1.2), mis. Email atau WhatsApp; wajib diisi lewat formulir unggah
    channel: Mapped[str | None] = mapped_column(String(30))
    # Field yang diisi/diperbaiki PIC; didahulukan atas hasil ekstraksi ulang AI (UAT 8)
    pic_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Vendor di data referensi klien yang cocok dengan hasil ekstraksi (nama dinormalisasi)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    # Salinan penanda tangan voucher saat dipilih: [{"kind": "PENGAJU"|"PENYETUJU", "name", "position"}].
    # Disalin (bukan dirujuk) supaya voucher lama tidak berubah bila daftar penanda tangan diedit.
    signers: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
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
    vendor: Mapped["Vendor | None"] = relationship()
    extraction: Mapped["Extraction | None"] = relationship(back_populates="document", uselist=False)
    issues: Mapped[list["ValidationIssue"]] = relationship(back_populates="document")
    voucher: Mapped["Voucher | None"] = relationship(back_populates="document", uselist=False)
    files: Mapped[list["DocumentFile"]] = relationship(back_populates="document", order_by="DocumentFile.position")


class DocumentFile(Base):
    """Satu file invoice PDF dalam pengajuan. Satu voucher bisa menggabungkan 1–10 invoice;
    `documents.file_key` menunjuk PDF gabungan untuk layar peninjauan."""
    __tablename__ = "document_files"
    __table_args__ = (UniqueConstraint("document_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    file_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(300))
    page_count: Mapped[int] = mapped_column(Integer)
    # Nomor invoice file ini (dinormalisasi) untuk cek duplikasi per invoice
    invoice_no_norm: Mapped[str | None] = mapped_column(String(500), index=True)
    # Kapan AI selesai membaca file ini pada proses terakhir (progres per file di layar detail)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # File asli bila diunggah sebagai foto (JPG/PNG/WEBP) lalu dikonversi ke PDF di file_key
    source_file_key: Mapped[str | None] = mapped_column(String(500))
    source_format: Mapped[str | None] = mapped_column(String(10))
    # Data invoice file ini (hasil AI, lalu dilengkapi/diedit PIC per invoice). Data gabungan voucher
    # di tabel extractions disusun ulang dari data semua file setiap kali PIC menyimpan.
    data: Mapped[dict | None] = mapped_column(JSONB)

    document: Mapped[Document] = relationship(back_populates="files")


class Extraction(Base):
    """Data hasil ekstraksi AI, bisa dikoreksi Finance Reviewer (PRD bagian 6)."""
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    vendor_name: Mapped[str | None] = mapped_column(String(300))
    # Beberapa invoice digabung dengan koma, mis. "INV-001, INV-002"
    invoice_no: Mapped[str | None] = mapped_column(String(500))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    account_no: Mapped[str | None] = mapped_column(String(50))
    account_name: Mapped[str | None] = mapped_column(String(200))
    # Hasil normalisasi untuk deteksi duplikat (huruf kecil, tanpa spasi/tanda baca)
    vendor_norm: Mapped[str | None] = mapped_column(String(300), index=True)
    invoice_no_norm: Mapped[str | None] = mapped_column(String(500), index=True)
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
    """Riwayat percakapan /ask dan /ask-agent, dikelompokkan per session_id."""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    # Pemilik percakapan (layar Asisten menampilkan riwayat milik pengguna sendiri); None = data lama / API
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Jawaban berbasis data: rencana query, label, dan tabel hasilnya (untuk ditampilkan ulang dan pertanyaan lanjutan)
    data: Mapped[dict | None] = mapped_column(JSONB)
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


class TelegramLink(Base):
    """Chat Telegram pribadi yang terhubung ke akun AMIGA (bot @amiga_ro_bot).

    Satu akun hanya terhubung ke satu chat, dan satu chat ke satu akun. Bot memanggil API atas nama
    akun ini, jadi hak akses dan isolasi klien sama persis dengan dashboard.
    """
    __tablename__ = "telegram_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    # Percakapan Asisten yang sedang dipakai di Telegram; /reset membuat yang baru
    session_id: Mapped[str] = mapped_column(String(100))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()


class TelegramLinkCode(Base):
    """Kode sekali pakai dari dashboard untuk menghubungkan Telegram, supaya password tidak pernah
    diketik di chat. Yang disimpan hanya hash kodenya."""
    __tablename__ = "telegram_link_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
