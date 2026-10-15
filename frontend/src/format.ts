import type { DocStatus, IssueCode, Role } from "./types";

export const ROLE_LABEL: Record<Role, string> = {
  PIC_KLIEN: "PIC Klien",
  INTAKE_SUPPORT: "Intake Support",
  FINANCE_REVIEWER: "Finance Reviewer",
  SERVICE_LEAD: "Service Lead",
  SYSTEM_ADMIN: "System Admin",
};

export const STATUS_LABEL: Record<DocStatus, string> = {
  QUEUED: "Antre",
  PROCESSING: "Diproses AI",
  READY_FOR_REVIEW: "Siap ditinjau",
  EXCEPTION: "Ada kendala",
  AMIGA_REVIEWED: "Disetujui",
  SENT_TO_CLIENT: "Diserahkan",
  CANCELLED: "Dibatalkan",
};

export const STATUS_ORDER: DocStatus[] = [
  "QUEUED", "PROCESSING", "READY_FOR_REVIEW", "EXCEPTION", "AMIGA_REVIEWED", "SENT_TO_CLIENT", "CANCELLED",
];

export const ISSUE_LABEL: Record<IssueCode, string> = {
  MISSING_EVIDENCE: "Data belum lengkap",
  CALCULATION_DISCREPANCY: "Selisih hitungan",
  POSSIBLE_DUPLICATE: "Kemungkinan duplikat",
  EXTRACTION_FAILED: "AI gagal membaca",
  RETURNED_BY_REVIEWER: "Dikembalikan reviewer",
  VENDOR_MISMATCH: "Vendor/rekening berbeda",
  NOT_AN_INVOICE: "Bukan invoice",
};

export const FIELD_LABEL: Record<string, string> = {
  vendor_name: "Nama vendor",
  invoice_no: "Nomor invoice",
  invoice_date: "Tanggal invoice",
  total: "Total invoice",
  bank_name: "Nama bank",
  account_no: "Nomor rekening",
  account_name: "Nama penerima",
  line_items: "Rincian barang/jasa",
  assigned_reviewer: "Reviewer",
  roles: "Peran",
  clients: "Klien",
  is_active: "Status akun",
};

const rupiahFmt = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
export const rupiah = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "-" : `Rp ${rupiahFmt.format(Number(v))}`;

const dateFmt = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("id-ID", {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

/** Tanggal "YYYY-MM-DD" (tanpa zona) atau timestamp ISO. */
export function tanggal(value: string | null | undefined): string {
  if (!value) return "-";
  return dateFmt.format(value.length === 10 ? new Date(`${value}T00:00:00`) : new Date(value));
}

export const waktu = (value: string | null | undefined) => (value ? dateTimeFmt.format(new Date(value)) : "-");

/** Sisa hari ke tenggat; negatif = lewat. */
export function daysUntil(due: string | null): number | null {
  if (!due) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${due}T00:00:00`).getTime() - today.getTime()) / 86_400_000);
}

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Angka untuk input: "900000.00" → "900000". */
export const plainNumber = (v: string | null) => (v === null ? "" : String(Number(v)));
