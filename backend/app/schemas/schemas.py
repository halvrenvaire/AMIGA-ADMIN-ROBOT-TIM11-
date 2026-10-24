import uuid
from datetime import date, datetime
from typing import Literal
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


class DataTableOut(BaseModel):
    """Hasil query data Asisten (text-to-query), ditampilkan sebagai tabel di chat."""
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str | None = None
    links: list[dict] = []  # tombol ke halaman terkait: {label, href}
    row_links: list[str | None] = []  # tautan per baris, mis. ke detail dokumen


class DocCardOut(BaseModel):
    """Kartu dokumen interaktif di jawaban Asisten: progres, detail, riwayat, saran, dan tautan."""
    request_id: str
    href: str
    status: str
    status_label: str
    subtitle: str
    fields: list[list[str]]
    steps: list[dict]
    history: list[dict]
    links: list[dict]
    hint: str | None = None


class AssistantSession(BaseModel):
    """Satu percakapan Asisten milik pengguna; judulnya pertanyaan pertama."""
    session_id: str
    title: str
    last_activity: datetime
    messages: int


class AssistantMessage(BaseModel):
    role: str
    content: str
    created_at: datetime
    query_label: str | None = None
    data_tables: list[DataTableOut] = []
    cards: list[DocCardOut] = []


class AskAgentResponse(AskResponse):
    # ID untuk memberi 👍/👎; None bila jawaban tidak disimpan ke memori
    answer_id: int | None
    # Alasan jawaban disimpan / tidak disimpan ke memori
    memory_note: str
    memory_refs: list[MemoryRef]
    # True bila jawaban memakai data antrean (sesuai hak akses pengguna)
    used_queue_data: bool = False
    # Text-to-query: interpretasi pertanyaan dan tabel hasilnya (kosong bila menjawab dari SOP)
    query_label: str | None = None
    data_tables: list[DataTableOut] = []
    cards: list[DocCardOut] = []  # kartu dokumen interaktif (progres, riwayat, tautan)


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
    logo_updated_at: datetime | None = None  # ada logo klien untuk kop voucher bila terisi


class ClientOverview(ClientRef):
    """Klien beserta pengguna pengaju yang ditugaskan (layar Klien System Admin)."""
    created_at: datetime
    pics: list[str]
    intakes: list[str]


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    roles: list[Role]
    clients: list[ClientRef]  # perusahaan yang datanya bisa dilihat (Finance Reviewer: semua)
    upload_clients: list[ClientRef] = []  # perusahaan yang boleh diajukan (penugasan System Admin)
    signature_updated_at: datetime | None = None  # spesimen tanda tangan elektronik (PIC Klien)
    # Profil "Diajukan oleh" terakhir: {"name", "position", "companies": {client_id: perusahaan/unit}}
    submitter_profile: dict = {}


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    email: str | None = Field(None, min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    # Wajib bila email diganti
    current_password: str | None = Field(None, max_length=200)
    # Profil "Diajukan oleh" mode PIC (Tahap 15); kosong = "PIC Klien" / nama perusahaan klien
    submitter_position: str | None = Field(None, max_length=120)
    submitter_company: str | None = Field(None, max_length=200)


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
    extraction_mode: Literal["TOTAL_ONLY", "ITEMIZED"] = "ITEMIZED"
    include_account: bool = False  # rekening tujuan diisi, dicek, dan dicetak di voucher
    auto_tax: bool = True  # otomatis terapkan saran pajak per invoice


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
    read_at: datetime | None = None  # selesai dibaca AI pada proses terakhir
    source_format: str | None = None  # "jpg"/"png"/"webp" bila diunggah sebagai foto lalu dikonversi ke PDF
    data: dict | None = None  # data invoice file ini (diedit PIC per invoice)
    # Tahap 15: bukti = halaman page_from..page_to dari PDF unggahan (upload_pages halaman). None = seluruh file
    page_from: int | None = None
    page_to: int | None = None
    upload_pages: int | None = None
    upload_name: str | None = None  # nama file unggahan (tanpa keterangan halaman)


class FilePagesUpdate(BaseModel):
    """Rentang halaman satu bukti dari PDF unggahannya (Tahap 15)."""
    page_from: int = Field(ge=1, le=10000)
    page_to: int = Field(ge=1, le=10000)


class FileAdd(FilePagesUpdate):
    """Tambah bukti dari halaman PDF unggahan bukti lain (mis. invoice yang terlewat AI)."""
    source_position: int = Field(ge=1)
    read_ai: bool = True  # AI membaca bukti baru; False = diisi manual oleh PIC


class CancellationOut(BaseModel):
    by: str
    at: datetime
    reason: str


class DocumentDetail(DocumentSummary):
    # Kendala yang masih terbuka: kode + alasan berbahasa sederhana (FR-3.3)
    issues: list[IssueItem]
    extraction: ExtractionOut | None
    # Field yang sudah diisi/diperbaiki PIC (didahulukan atas hasil AI)
    pic_overrides: dict[str, str]
    voucher: VoucherOut | None
    vendor: ClientRef | None = None  # vendor di data referensi (id, name) bila cocok
    signers: list["Signer"] = []
    files: list[DocumentFileOut] = []  # file invoice yang digabung dalam voucher ini
    cancellation: CancellationOut | None = None  # siapa, kapan, dan alasan bila dibatalkan
    # Klasifikasi AI (invoice / struk / tidak relevan / meragukan) dan pemeriksaan rekening
    classification: dict | None = None
    account_check: dict | None = None
    # Total tagihan, potongan pajak, dan nilai bersih yang dibayarkan voucher (Tahap 4)
    tax_summary: "TaxSummaryOut | None" = None
    # Isi manual: AI dimatikan/gagal membaca sebagian atau semua invoice ({status, files, message})
    ai_manual: dict | None = None
    # Tahap 15: invoice dalam PDF melebihi batas per voucher: {"limit", "files": [{"file", "skipped"}]}
    invoice_limit: dict | None = None
    ai_enabled: bool = True  # AI_EXTRACTION_ENABLED; false = tombol baca ulang dengan AI disembunyikan
    # Rekening tujuan per vendor (beberapa invoice dengan vendor+rekening sama digabung)
    payees: list["PayeeOut"] = []
    # Peringatan yang sudah dikonfirmasi PIC dan masih berlaku: {kode: {reason, by, at}}
    acknowledgements: dict[str, dict] = {}
    # Ada spesimen tanda tangan "Diajukan oleh" yang tersimpan di pengajuan ini
    submitter_signature: bool = False


class PayeeOut(BaseModel):
    vendor_name: str | None
    bank_name: str | None
    account_no: str | None
    account_name: str | None
    invoices: list[int]
    gross: Decimal
    net: Decimal
    state: str
    message: str
    source: str
    vendor_id: str | None = None
    vendor_verified: bool = False
    reference_matches: bool = False


class TaxLineOut(BaseModel):
    invoice_no: str | None
    name: str
    rate: Decimal
    npwp: bool
    base: Decimal
    amount: Decimal
    detail: str | None = None  # PPh per baris: uraian baris yang dipotong


class VatLineOut(BaseModel):
    invoice_no: str | None
    mode: Literal["excluded", "included", "none"]
    rate: Decimal
    amount: Decimal  # PPN yang termasuk di total tagihan
    show: bool  # rincian PPN dicetak di voucher
    warning: str | None = None  # PPN invoice berbeda dengan hitungan sistem (tidak memblokir)


class TaxSummaryOut(BaseModel):
    gross: Decimal | None
    tax_total: Decimal
    net: Decimal | None
    lines: list[TaxLineOut] = []
    vat: list[VatLineOut] = []


class TaxLineChoice(BaseModel):
    """Pengaturan pajak satu baris rincian (indeks mulai 0)."""
    index: int = Field(ge=0, lt=300)
    pph: str | None = Field(None, max_length=20)  # mode per baris; kosong/NONE = tidak dipotong
    vat: bool | None = None  # baris kena PPN
    kind: Literal["item", "vat"] | None = None  # jenis baris bila PIC mengoreksi tebakan sistem


class VatChoice(BaseModel):
    """PPN satu invoice: harga belum termasuk PPN (ditambahkan), sudah termasuk PPN, atau tidak ada."""
    mode: Literal["excluded", "included", "none", "separate"]  # "separate" = PPN terpisah (format lama) = "excluded"
    rate: Decimal = Field(Decimal(11), gt=0, le=100)
    show: bool = False  # cetak rincian PPN di voucher (bawaan: PPN dilebur ke nilai barang)


class TaxChoice(BaseModel):
    """Pilihan pajak PIC untuk satu invoice. `base` kosong = DPP otomatis dari rincian (tanpa baris PPN).
    `mode` "line": PPh dipilih per baris lewat `lines` (DPP otomatis per baris; `code` dan `base` diabaikan)."""
    code: str = Field("NONE", max_length=20)
    npwp: bool = True
    base: Decimal | None = Field(None, ge=0)
    mode: Literal["invoice", "line"] = "invoice"
    lines: list[TaxLineChoice] = Field(default_factory=list, max_length=300)
    vat: VatChoice | None = None
    # Hitung pajak otomatis (bawaan). False: DPP (`base`), PPN (`vat_amount`), dan potongan PPh (`amount`) diisi manual
    calc: bool = True
    vat_amount: Decimal | None = Field(None, ge=0)
    amount: Decimal | None = Field(None, ge=0)


class OptionsUpdate(BaseModel):
    """Pengaturan pengajuan di halaman detail (Tahap 14); field yang tidak dikirim = tetap."""
    extraction_mode: Literal["TOTAL_ONLY", "ITEMIZED"] | None = None
    include_account: bool | None = None
    auto_tax: bool | None = None


class TaxRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str | None
    rate_npwp: Decimal
    rate_no_npwp: Decimal
    is_active: bool
    needs_confirmation: bool
    updated_at: datetime | None = None


class TaxRateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    rate_npwp: Decimal | None = Field(None, ge=0, le=100)
    rate_no_npwp: Decimal | None = Field(None, ge=0, le=100)
    is_active: bool | None = None
    needs_confirmation: bool | None = None


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
    # Pengaturan pajak baris (diatur di panel pajak; ikut dikirim ulang saat data invoice disimpan)
    pph: str | None = Field(None, max_length=20)
    vat: bool | None = None
    kind: Literal["item", "vat"] | None = None


class FileDataUpdate(BaseModel):
    description: str | None = Field(None, max_length=500)  # uraian transaksi (mode total saja: 1 baris voucher)
    """Data satu invoice yang diedit PIC (feedback owner: edit per invoice). Menggantikan data file itu."""
    vendor_name: str | None = Field(None, max_length=300)
    invoice_no: str | None = Field(None, max_length=100)
    invoice_date: date | None = None
    total: Decimal | None = None
    bank_name: str | None = Field(None, max_length=100)
    account_no: str | None = Field(None, max_length=50)
    account_name: str | None = Field(None, max_length=200)
    line_items: list[LineItemIn] = Field(default_factory=list, max_length=300)


class ReviewUpdate(BaseModel):
    """Koreksi data hasil ekstraksi oleh Finance Reviewer. Field yang tidak dikirim tidak berubah;
    `line_items` bila dikirim menggantikan seluruh rincian."""
    fields: dict[str, str | None] = {}
    line_items: list[LineItemIn] | None = None


class ApproveRequest(BaseModel):
    """Rekening yang belum terverifikasi terhadap data referensi wajib dikonfirmasi reviewer."""
    account_confirmed: bool = False
    account_note: str | None = Field(None, max_length=500)


class ClassificationDecision(BaseModel):
    """Keputusan manual Finance Reviewer atas dokumen struk/nota atau meragukan."""
    decision: Literal["INVOICE", "RECEIPT_ACCEPTED", "IRRELEVANT"]
    reason: str = Field(min_length=5, max_length=1000)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class AcknowledgeRequest(ReasonRequest):
    code: IssueCode  # peringatan yang dikonfirmasi, mis. VENDOR_MISMATCH


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
    # Rekening diverifikasi Finance Reviewer (data referensi tepercaya); None = belum
    verified_at: datetime | None = None
    verified_by: str | None = None


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
    # Terisi bila spesimen tanda tangan elektronik sudah didaftarkan
    signature_updated_at: datetime | None = None


class SignatureIn(BaseModel):
    """Gambar tanda tangan: data URL atau base64 PNG/JPEG/WEBP (hasil canvas atau unggahan)."""
    image: str = Field(min_length=20, max_length=3_000_000)


class Signer(BaseModel):
    """Salinan penanda tangan pada dokumen/voucher."""
    kind: SignatoryKind
    name: str
    position: str
    company: str | None = None  # profil pengaju (Tahap 14): perusahaan/unit
    signature: bool = False  # kotak "Diajukan oleh" memakai spesimen yang tersimpan di dokumen
    source: Literal["PIC", "MANUAL"] | None = None  # Tahap 15: sumber kotak "Diajukan oleh"; None = data lama


class SignersUpdate(BaseModel):
    signatory_ids: list[uuid.UUID]
    # Sumber "Diajukan oleh" (Tahap 15): PIC = profil akun PIC Klien (dikunci), MANUAL = diisi manual
    submitter_source: Literal["PIC", "MANUAL"] | None = None
    # Profil "Diajukan oleh" (Tahap 14); tidak dikirim = tetap
    submitter_position: str | None = Field(None, max_length=120)
    submitter_company: str | None = Field(None, max_length=200)
    # Nama di kotak "Diajukan oleh"; None = tidak diubah, "" = kembali ke PIC pengaju
    submitter_name: str | None = Field(None, max_length=200)


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
    total: Decimal | None  # nilai yang dibayarkan (setelah potongan pajak)
    gross: Decimal | None = None  # total tagihan sebelum potongan
    tax_total: Decimal = Decimal(0)
    status: DocStatus
    approved_by: str
    pic_name: str | None = None  # PIC Klien pengaju: pengunggah, atau PIC yang diwakili Intake Support
    request_type: str | None = None  # kategori pengajuan


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


# --- Telegram (bot @amiga_ro_bot) ---

class TelegramStatus(BaseModel):
    configured: bool  # token bot sudah diisi di server
    linked: bool
    telegram_username: str | None
    linked_at: datetime | None
    bot_username: str
    bot_url: str


class TelegramLinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    bot_username: str
    # Membuka chat bot dan langsung mengirim kode (tautan t.me dengan parameter start)
    deep_link: str
