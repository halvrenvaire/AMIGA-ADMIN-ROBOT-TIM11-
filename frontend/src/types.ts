// Mengikuti schema backend (backend/app/schemas/schemas.py)

export type Role = "PIC_KLIEN" | "INTAKE_SUPPORT" | "FINANCE_REVIEWER" | "SERVICE_LEAD" | "SYSTEM_ADMIN";

export type DocStatus =
  | "QUEUED" | "PROCESSING" | "READY_FOR_REVIEW" | "EXCEPTION" | "AMIGA_REVIEWED" | "SENT_TO_CLIENT" | "CANCELLED";

export type IssueCode =
  | "MISSING_EVIDENCE" | "CALCULATION_DISCREPANCY" | "POSSIBLE_DUPLICATE" | "EXTRACTION_FAILED"
  | "RETURNED_BY_REVIEWER" | "VENDOR_MISMATCH" | "NOT_AN_INVOICE";

export interface ClientRef { id: string; name: string }
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

export interface DocumentDetail extends DocumentSummary {
  issues: Issue[];
  extraction: Extraction | null;
  pic_overrides: Record<string, string>;
  voucher: { voucher_no: string; generated_at: string } | null;
  vendor: ClientRef | null;
  signers: Signer[];
  files: { position: number; original_filename: string; page_count: number }[];
  cancellation?: { by: string; at: string; reason: string } | null;
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

export interface DataTable { title: string; columns: string[]; rows: string[][]; note: string | null }

export interface AssistantSession { session_id: string; title: string; last_activity: string; messages: number }
export interface AssistantMessage {
  role: "user" | "assistant"; content: string; created_at: string; query_label: string | null; data_tables: DataTable[];
}

export interface AskAgentResponse {
  answer: string;
  session_id: string;
  answer_id: number | null;
  memory_note: string;
  used_queue_data: boolean;
  query_label: string | null;
  data_tables: DataTable[];
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
  total: string | null;
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
