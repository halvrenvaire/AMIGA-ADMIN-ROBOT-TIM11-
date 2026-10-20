import { type ReactNode } from "react";
import { AlertTriangle, Check, CheckCircle2, Cpu, FileSearch, Inbox, Loader2, ScanText, ShieldCheck, UserCheck, X } from "lucide-react";
import { rupiah } from "../format";
import type { DocumentDetail, IssueCode } from "../types";

type StepState = "done" | "active" | "todo";

/** Kartu proses AI selama QUEUED/PROCESSING. Tahap dan progres per file diambil dari data server, bukan simulasi. */
export function AiProcessingCard({ doc }: { doc: DocumentDetail }) {
  const files = doc.files.length ? doc.files : [{ position: 1, original_filename: doc.original_filename, page_count: doc.page_count, read_at: null }];
  const read = files.filter((f) => f.read_at).length;
  const current = files.find((f) => !f.read_at);
  const queued = doc.status === "QUEUED";
  const allRead = read === files.length;

  const steps: { icon: typeof Inbox; title: string; detail: ReactNode; state: StepState }[] = [
    { icon: Inbox, title: "Diterima sistem", detail: `${files.length} file · ${doc.page_count} halaman`, state: queued ? "active" : "done" },
    {
      icon: ScanText, title: "AI membaca invoice",
      detail: queued ? "Menunggu giliran" : allRead ? `${files.length} file selesai dibaca` : (
        <>File {read + 1} dari {files.length}: <b>{current?.original_filename}</b></>
      ),
      state: queued ? "todo" : allRead ? "done" : "active",
    },
    { icon: ShieldCheck, title: "Verifikasi sistem", detail: "Hitungan, kelengkapan, duplikasi, rekening penerima", state: allRead && !queued ? "active" : "todo" },
    { icon: UserCheck, title: "Siap ditinjau", detail: "Ditugaskan ke Finance Reviewer", state: "todo" },
  ];

  return (
    <section className="card ai-card" aria-live="polite">
      <div className="ai-card-head">
        <span className="ai-orb" aria-hidden="true"><Cpu /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="ai-eyebrow">AMIGA AI Engine</span>
          <h2>{queued ? "Invoice masuk antrean AI" : "AI sedang memproses invoice Anda"}</h2>
        </div>
      </div>

      {files.length > 1 && (
        <div className="ai-progress" role="progressbar" aria-valuemin={0} aria-valuemax={files.length} aria-valuenow={read}
             aria-label="File selesai dibaca">
          <i style={{ width: `${(read / files.length) * 100}%` }} />
        </div>
      )}

      <ol className="ai-steps">
        {steps.map(({ icon: Icon, title, detail, state }) => (
          <li key={title} className={state}>
            <span className="ai-step-ic">{state === "done" ? <Check /> : state === "active" ? <Loader2 className="spin" /> : <Icon />}</span>
            <div><b>{title}</b><small>{detail}</small></div>
          </li>
        ))}
      </ol>

      <small className="muted">Halaman diperbarui otomatis. Anda boleh meninggalkan halaman ini; prosesnya tetap berjalan.</small>
    </section>
  );
}

const CHECKS: { code: IssueCode; label: string }[] = [
  { code: "NOT_AN_INVOICE", label: "Dokumen adalah invoice vendor" },
  { code: "MISSING_EVIDENCE", label: "Data wajib lengkap (vendor, nomor, rekening)" },
  { code: "CALCULATION_DISCREPANCY", label: "Total cocok dengan rincian barang" },
  { code: "POSSIBLE_DUPLICATE", label: "Bukan invoice yang pernah diajukan" },
  { code: "VENDOR_MISMATCH", label: "Satu vendor dan satu rekening tujuan (atau dikonfirmasi PIC)" },
];

/** Ringkasan hasil kerja AI dan verifikasi sistem setelah selesai. */
/** `onJump`: pemeriksaan yang gagal bisa diklik untuk langsung ke bagian yang perlu diperbaiki
 *  ("ACCOUNT" untuk pemeriksaan rekening). */
export function AiResultCard({ doc, onClose, onJump }: { doc: DocumentDetail; onClose?: () => void; onJump?: (code: string) => void }) {
  const ex = doc.extraction;
  if (!ex) return null;
  const codes = new Set(doc.issues.map((i) => i.code));
  const notInvoice = codes.has("NOT_AN_INVOICE");
  // Struk/nota atau dokumen meragukan juga gagal di pemeriksaan "invoice vendor"
  const notOfficial = codes.has("RECEIPT_NOT_INVOICE") || codes.has("NEEDS_MANUAL_REVIEW");
  const account = doc.account_check;
  const passed = !doc.issues.length && doc.status !== "EXCEPTION";
  const seconds = ex.duration_ms != null ? (ex.duration_ms / 1000).toFixed(1) : null;

  return (
    <section className="card ai-card result">
      <div className="ai-card-head">
        <span className={`ai-orb ${passed ? "ok" : "warn"}`} aria-hidden="true">{passed ? <CheckCircle2 /> : <AlertTriangle />}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="ai-eyebrow">Hasil AMIGA AI Engine</span>
          <h2>{passed ? "Lolos semua pemeriksaan" : `${doc.issues.length} kendala perlu ditindaklanjuti`}</h2>
        </div>
        {onClose && <button className="btn ghost sm" onClick={onClose} aria-label="Tutup ringkasan"><X /></button>}
      </div>

      <div className="ai-stats">
        <div><b>{seconds ?? "-"}<small> dtk</small></b><span>waktu baca AI</span></div>
        <div><b>{ex.line_items.length}</b><span>baris barang</span></div>
        <div><b>{(doc.files.length || 1) - (doc.ai_manual?.files.length ?? 0)}</b><span>file dibaca</span></div>
        <div><b className="ai-money">{rupiah(ex.total)}</b><span>total tagihan</span></div>
      </div>
      {ex.vendor_name && <p className="ai-found"><FileSearch size={14} /> Vendor terbaca: <b>{ex.vendor_name}</b>{ex.invoice_no && <> · No. {ex.invoice_no}</>}</p>}

      <ul className="ai-checks">
        {CHECKS.map(({ code, label }) => {
          const failed = codes.has(code) || (code === "NOT_AN_INVOICE" && notOfficial);
          const skipped = notInvoice && code !== "NOT_AN_INVOICE";
          return (
            <li key={code} className={failed ? "fail" : skipped ? "skip" : "pass"} >
              <span>{failed ? <X /> : skipped ? "–" : <Check />}</span>
              {failed && onJump
                ? <button type="button" className="link-btn" onClick={() => onJump(code)} title="Lihat bagian yang perlu diperbaiki">{label}</button>
                : label}
              {skipped && <small className="muted"> · dilewati</small>}
            </li>
          );
        })}
        {account && account.state !== "NOT_APPLICABLE" && !notInvoice && (
          <li className={account.state === "VERIFIED" ? "pass" : account.state === "MISMATCH" ? "fail" : "skip"}>
            <span>{account.state === "VERIFIED" ? <Check /> : account.state === "MISMATCH" ? <X /> : "?"}</span>
            {account.state !== "VERIFIED" && onJump
              ? <button type="button" className="link-btn" onClick={() => onJump("ACCOUNT")}>Rekening cocok dengan data vendor terverifikasi</button>
              : "Rekening cocok dengan data vendor terverifikasi"}
            {account.state === "UNVERIFIED" && <small className="muted"> · belum terverifikasi</small>}
          </li>
        )}
      </ul>
      {passed && doc.assigned_reviewer && (
        <p className="ai-found"><UserCheck size={14} /> Ditugaskan ke <b>{doc.assigned_reviewer}</b> untuk ditinjau.</p>
      )}
    </section>
  );
}

/** Label kecil di atas pratinjau PDF selama AI membaca. */
export function AiScanOverlay({ label }: { label: string }) {
  return <span className="ai-scan-label" aria-hidden="true"><Loader2 className="spin" size={12} /> {label}</span>;
}
