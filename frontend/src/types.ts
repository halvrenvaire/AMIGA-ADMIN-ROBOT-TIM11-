// Mengikuti schema backend (backend/app/schemas/schemas.py)

export type Role = "PIC_KLIEN" | "INTAKE_SUPPORT" | "FINANCE_REVIEWER" | "SERVICE_LEAD" | "SYSTEM_ADMIN";

export type DocStatus =
  | "QUEUED" | "PROCESSING" | "READY_FOR_REVIEW" | "EXCEPTION" | "AMIGA_REVIEWED" | "SENT_TO_CLIENT";

export type IssueCode =
  | "MISSING_EVIDENCE" | "CALCULATION_DISCREPANCY" | "POSSIBLE_DUPLICATE" | "EXTRACTION_FAILED"
  | "RETURNED_BY_REVIEWER";

export interface ClientRef { id: string; name: string }

export interface Me {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  clients: ClientRef[];
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

export interface AskAgentResponse {
  answer: string;
  session_id: string;
  answer_id: number | null;
  memory_note: string;
  used_queue_data: boolean;
  sources: { source: string; score: number; preview: string }[];
}
