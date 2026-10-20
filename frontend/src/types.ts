// Mengikuti schema backend (backend/app/schemas/schemas.py)

export type Role = "PIC_KLIEN" | "INTAKE_SUPPORT" | "FINANCE_REVIEWER" | "SERVICE_LEAD" | "SYSTEM_ADMIN";

export type DocStatus =
  | "QUEUED" | "PROCESSING" | "DRAFT" | "READY_FOR_REVIEW" | "EXCEPTION" | "AMIGA_REVIEWED" | "SENT_TO_CLIENT" | "CANCELLED";

export type IssueCode =
  | "MISSING_EVIDENCE" | "CALCULATION_DISCREPANCY" | "POSSIBLE_DUPLICATE" | "EXTRACTION_FAILED"
  | "RETURNED_BY_REVIEWER" | "VENDOR_MISMATCH" | "NOT_AN_INVOICE"
  | "RECEIPT_NOT_INVOICE" | "NEEDS_MANUAL_REVIEW" | "ACCOUNT_MISMATCH";

/** Klasifikasi AI: invoice resmi, struk/nota (draft), tidak relevan (ditolak), meragukan (cek manual). */
export type DocClass = "INVOICE" | "RECEIPT" | "IRRELEVANT" | "UNCERTAIN";
export interface Classification {
  doc_class: DocClass;
  files: { file: string; doc_class: DocClass; document_type: string | null; reason: string | null }[];
  decision: { decision: "INVOICE" | "RECEIPT_ACCEPTED" | "IRRELEVANT"; by: string; at: string; reason: string } | null;
}
/** Pemeriksaan rekening terhadap data vendor yang diverifikasi Finance Reviewer. */
export interface AccountCheck {
  state: "VERIFIED" | "MISMATCH" | "UNVERIFIED" | "MISSING" | "NOT_APPLICABLE";
  message: string; source: "AI" | "PIC"; vendor: string | null; verified_by: string | null;
}

export interface ClientRef { id: string; name: string; logo_updated_at?: string | null }
export interface ClientOverview extends ClientRef { created_at: string; pics: string[]; intakes: string[] }

export interface Me {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  /** Perusahaan yang datanya bisa dilihat (Finance Reviewer: semua perusahaan). */
  clients: ClientRef[];
  /** Perusahaan yang boleh diajukan (penugasan System Admin; PIC Klien / Intake Support). */
  upload_clients?: ClientRef[];
  /** Spesimen tanda tangan elektronik (PIC Klien), null bila belum ada. */
  signature_updated_at?: string | null;
}

export interface AdminUser extends Me { is_active: boolean }

export interface DocumentSummary {
  id: string;
  request_id: string;
  client: ClientRef;
  status: DocStatus;
  request_type: string | null;
  channel: string | null;
  submitted_date: string | null;
  due_date: string | null;
  original_filename: string;
  page_count: number;
  uploaded_by: string;
  on_behalf_of: string | null;
  assigned_reviewer: string | null;
  vendor_name: string | null;
  total: string | null;
  created_at: string;
  updated_at: string;
}

export interface Issue { code: IssueCode; field: string | null; message: string; created_at: string }

export interface LineItem {
  position: number;
  description: string | null;
  qty: string | null;
  unit_price: string | null;
  subtotal: string | null;
}

export interface Extraction {
  vendor_name: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  total: string | null;
  bank_name: string | null;
  account_no: string | null;
  account_name: string | null;
  line_items: LineItem[];
  extracted_at: string | null;
  duration_ms: number | null;
}

export interface FileData {
  vendor_name: string | null; invoice_no: string | null; invoice_date: string | null; total: string | null;
  bank_name: string | null; account_no: string | null; account_name: string | null;
  line_items: FileLine[];
  /** Pilihan pajak PIC (Tahap 4); tarif disalin saat dipilih. */
  tax?: TaxChoice | null;
  /** Saran PPh tiap baris (aturan kata kunci, atau AI bila diminta PIC); null untuk baris PPN. */
  line_suggestions?: (LineSuggestion | null)[];
  tax_suggestion?: { code: string; name: string; reason: string; source: "ai" | "aturan" } | null;
  /** NPWP vendor menurut data referensi: null = vendor belum terdaftar. */
  npwp_known?: boolean | null;
  /** true = invoice ini belum terbaca AI (dimatikan/bermasalah), datanya diisi PIC secara manual. */
  manual?: boolean;
}

/** Satu baris rincian; pph/vat/kind diatur di panel pajak. */
export interface FileLine {
  description: string | null; qty: string | null; unit_price: string | null; subtotal: string | null;
  /** Jenis PPh baris ini (mode PPh per baris). */
  pph?: string | null;
  /** false = baris tidak kena PPN. */
  vat?: boolean | null;
  /** Koreksi PIC atas tebakan sistem: baris barang/jasa atau baris PPN. */
  kind?: "item" | "vat" | null;
}

export interface LineSuggestion { code: string; reason: string; source: "ai" | "aturan" }

export type VatMode = "separate" | "included" | "none";
export interface VatSetting { mode: VatMode; rate: string; show: boolean }

export interface TaxGroup { code: string; name: string; rate: string; base: string; amount: string; lines: number[] }

export interface TaxChoice {
  /** "invoice": satu jenis PPh untuk seluruh invoice; "line": PPh dipilih per baris (lihat groups). */
  mode?: "invoice" | "line";
  code: string; name: string; npwp: boolean; rate?: string; base?: string | null; base_auto?: boolean; amount: string;
  source: "ai" | "aturan" | "pic";
  groups?: TaxGroup[];
  vat?: VatSetting;
}

export interface TaxRate {
  code: string; name: string; description: string | null; rate_npwp: string; rate_no_npwp: string;
  is_active: boolean; needs_confirmation: boolean; updated_at: string | null;
}

export interface TaxSummary {
  gross: string | null; tax_total: string; net: string | null;
  lines: { invoice_no: string | null; name: string; rate: string; npwp: boolean; base: string; amount: string; detail?: string | null }[];
  vat?: { invoice_no: string | null; mode: VatMode; rate: string; amount: string; show: boolean; warning: string | null }[];
}

export interface DocumentDetail extends DocumentSummary {
  issues: Issue[];
  extraction: Extraction | null;
  pic_overrides: Record<string, string>;
  voucher: { voucher_no: string; generated_at: string } | null;
  vendor: ClientRef | null;
  signers: Signer[];
  /** source_format: "jpg"/"png"/"webp" bila diunggah sebagai foto lalu dikonversi ke PDF. */
  files: { position: number; original_filename: string; page_count: number; read_at: string | null; source_format?: string | null;
    /** Data per invoice yang diedit PIC saat DRAFT/EXCEPTION. */
    data?: FileData | null }[];
  cancellation?: { by: string; at: string; reason: string } | null;
  classification?: Classification | null;
  account_check?: AccountCheck | null;
  tax_summary?: TaxSummary | null;
  /** Isi manual: AI dimatikan atau gagal membaca sebagian/semua invoice. */
  ai_manual?: { status: "off" | "failed"; files: string[]; message: string } | null;
  ai_enabled?: boolean;
  /** Rekening tujuan per vendor (invoice dengan vendor + rekening sama digabung). */
  payees?: Payee[];
  /** Peringatan yang sudah dikonfirmasi PIC dan masih berlaku, per kode kendala. */
  acknowledgements?: Record<string, { reason: string; by: string; at: string }>;
}

export interface Payee {
  vendor_name: string | null; bank_name: string | null; account_no: string | null; account_name: string | null;
  invoices: number[]; gross: string; net: string;
  state: AccountCheck["state"]; message: string; source: "AI" | "PIC";
  vendor_id: string | null; vendor_verified: boolean;
  /** Rekening di Data Referensi sama dengan rekening invoice. */
  reference_matches: boolean;
}

export interface AuditItem {
  id: number;
  created_at: string;
  actor_label: string;
  action: string;
  status_before: string | null;
  status_after: string | null;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  note: string | null;
}

export interface ReviewerLoad { id: string; name: string; pending: number; overloaded: boolean }

export interface DashboardSummary {
  counts: Record<DocStatus, number>;
  problem: number;
  due_soon: number;
  overdue: number;
  reviewers: ReviewerLoad[];
  overload_threshold: number;
  due_soon_days: number;
}

export interface AssistantLink { label: string; href: string; primary?: boolean }
export interface DataTable {
  title: string; columns: string[]; rows: string[][]; note: string | null;
  links?: AssistantLink[]; row_links?: (string | null)[];
}
export interface DocCard {
  request_id: string; href: string; status: DocStatus; status_label: string; subtitle: string;
  fields: string[][];
  steps: { label: string; state: "done" | "active" | "todo" | "bad" | "skip"; at?: string | null; detail?: string | null }[];
  history: { at: string; action: string; actor: string; note: string }[];
  links: AssistantLink[]; hint: string | null;
}

export interface AssistantSession { session_id: string; title: string; last_activity: string; messages: number }
export interface AssistantMessage {
  role: "user" | "assistant"; content: string; created_at: string; query_label: string | null; data_tables: DataTable[];
  cards: DocCard[];
}

export interface AskAgentResponse {
  answer: string;
  session_id: string;
  answer_id: number | null;
  memory_note: string;
  used_queue_data: boolean;
  query_label: string | null;
  data_tables: DataTable[];
  cards: DocCard[];
  sources: { source: string; score: number; preview: string }[];
}

// --- Data referensi, penanda tangan, voucher, metrik (permintaan owner 14 Okt 2026) ---

export interface Vendor {
  id: string;
  client: ClientRef;
  name: string;
  npwp: string | null;
  address: string | null;
  contact_name: string | null;
  phone: string | null;
  email: string | null;
  bank_name: string | null;
  account_no: string | null;
  account_name: string | null;
  notes: string | null;
  is_active: boolean;
  documents: number;
  verified_at: string | null;
  verified_by: string | null;
  created_at: string;
  updated_at: string;
}

export type SignatoryKind = "PENGAJU" | "PENYETUJU";

export interface Signatory {
  id: string;
  client_id: string;
  kind: SignatoryKind;
  full_name: string;
  position: string;
  is_default: boolean;
  is_active: boolean;
  signature_updated_at: string | null;
}

export interface Signer { kind: SignatoryKind; name: string; position: string }

export interface VoucherRow {
  document_id: string;
  voucher_no: string;
  generated_at: string;
  request_id: string;
  client: ClientRef;
  vendor_id: string | null;
  vendor_name: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  /** Nilai yang dibayarkan (setelah potongan pajak). */
  total: string | null;
  gross?: string | null;
  tax_total?: string;
  status: DocStatus;
  approved_by: string;
  /** PIC Klien pengaju (pengunggah, atau PIC yang diwakili Intake Support). */
  pic_name?: string | null;
}

export interface DashboardMetrics {
  period_days: number;
  start: string;
  end: string;
  status_counts: Record<DocStatus, number>;
  received: number;
  received_prev: number;
  approved: number;
  approved_prev: number;
  trend: { date: string; received: number; approved: number; exception: number }[];
  avg_hours_to_voucher: number | null;
  avg_extraction_seconds: number | null;
  sla_on_time: number;
  sla_total: number;
  first_pass: number;
  first_pass_total: number;
  top_issues: { code: IssueCode; count: number }[];
  corrected_docs: number;
  reviewed_docs: number;
  total_value: string;
  total_value_prev: string;
  value_by_client: { client: string; value: string; count: number }[];
  top_vendors: { vendor: string; value: string; count: number }[];
}

/** Status hubungan akun dengan bot Telegram (Pengaturan akun). */
export interface TelegramStatus {
  configured: boolean;
  linked: boolean;
  telegram_username: string | null;
  linked_at: string | null;
  bot_username: string;
  bot_url: string;
}

export interface TelegramLinkCode {
  code: string;
  expires_at: string;
  bot_username: string;
  deep_link: string;
}
