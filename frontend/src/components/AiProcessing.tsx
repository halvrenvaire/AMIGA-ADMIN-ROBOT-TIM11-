import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Check, CheckCircle2, Cpu, FileSearch, Inbox, ScanText, ShieldCheck, Sparkles, UserCheck, X } from "lucide-react";
import { rupiah } from "../format";
import type { DocumentDetail, IssueCode } from "../types";

const LOOKING_FOR = ["Nama vendor", "Nomor invoice", "Tanggal", "Rincian barang", "Total tagihan", "Rekening tujuan"];

type StepState = "done" | "active" | "todo";

/** Detik berjalan sejak `since` (jam server bisa sedikit berbeda, jadi tidak pernah negatif). */
function useElapsed(since: string) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);
  return Math.max(0, (now - new Date(since).getTime()) / 1000);
}

/** Kartu proses AI selama QUEUED/PROCESSING. Tahap dan progres per file diambil dari data server, bukan simulasi. */
export function AiProcessingCard({ doc }: { doc: DocumentDetail }) {
  const elapsed = useElapsed(doc.updated_at);
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
    { icon: ShieldCheck, title: "Verifikasi sistem", detail: "Hitungan, kelengkapan, duplikasi, satu penerima", state: allRead && !queued ? "active" : "todo" },
    { icon: UserCheck, title: "Siap ditinjau", detail: "Ditugaskan ke Finance Reviewer", state: "todo" },
  ];

  return (
    <section className="card ai-card" aria-live="polite">
      <div className="ai-card-head">
        <span className="ai-orb" aria-hidden="true"><Cpu /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="ai-eyebrow"><Sparkles size={12} /> AMIGA AI Engine</span>
          <h2>{queued ? "Invoice masuk antrean AI" : "AI sedang memproses invoice Anda"}</h2>
        </div>
        <span className="ai-timer" title="Waktu berjalan">{elapsed.toFixed(1)} dtk</span>
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
            <span className="ai-step-ic">{state === "done" ? <Check /> : <Icon />}</span>
            <div><b>{title}</b><small>{detail}</small></div>
          </li>
        ))}
      </ol>

      {!queued && !allRead && (
        <div className="ai-looking">
          <span className="muted">Yang dicari AI</span>
          <div>{LOOKING_FOR.map((f, i) => <span key={f} className="ai-chip" style={{ animationDelay: `${i * 0.25}s` }}>{f}</span>)}</div>
        </div>
      )}
      <small className="muted">Halaman diperbarui otomatis. Anda boleh meninggalkan halaman ini; prosesnya tetap berjalan.</small>
    </section>
  );
}

const CHECKS: { code: IssueCode; label: string }[] = [
  { code: "NOT_AN_INVOICE", label: "Dokumen adalah invoice vendor" },
  { code: "MISSING_EVIDENCE", label: "Data wajib lengkap (vendor, nomor, rekening)" },
  { code: "CALCULATION_DISCREPANCY", label: "Total cocok dengan rincian barang" },
  { code: "POSSIBLE_DUPLICATE", label: "Bukan invoice yang pernah diajukan" },
  { code: "VENDOR_MISMATCH", label: "Satu vendor dan satu rekening tujuan" },
];

/** Ringkasan hasil kerja AI dan verifikasi sistem setelah selesai. `fresh` = baru selesai saat halaman dibuka (animasi masuk). */
export function AiResultCard({ doc, fresh, onClose }: { doc: DocumentDetail; fresh: boolean; onClose?: () => void }) {
  const ex = doc.extraction;
  if (!ex) return null;
  const codes = new Set(doc.issues.map((i) => i.code));
  const notInvoice = codes.has("NOT_AN_INVOICE");
  const passed = !doc.issues.length && doc.status !== "EXCEPTION";
  const seconds = ex.duration_ms != null ? (ex.duration_ms / 1000).toFixed(1) : null;

  return (
    <section className={`card ai-card result${fresh ? " fresh" : ""}`}>
      <div className="ai-card-head">
        <span className={`ai-orb ${passed ? "ok" : "warn"}`} aria-hidden="true">{passed ? <CheckCircle2 /> : <AlertTriangle />}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="ai-eyebrow"><Sparkles size={12} /> Hasil AMIGA AI Engine</span>
          <h2>{passed ? "Lolos semua pemeriksaan" : `${doc.issues.length} kendala perlu ditindaklanjuti`}</h2>
        </div>
        {onClose && <button className="btn ghost sm" onClick={onClose} aria-label="Tutup ringkasan"><X /></button>}
      </div>

      <div className="ai-stats">
        <div><b>{seconds ?? "-"}<small> dtk</small></b><span>waktu baca AI</span></div>
        <div><b>{ex.line_items.length}</b><span>baris barang</span></div>
        <div><b>{doc.files.length || 1}</b><span>file dibaca</span></div>
        <div><b className="ai-money">{rupiah(ex.total)}</b><span>total tagihan</span></div>
      </div>
      {ex.vendor_name && <p className="ai-found"><FileSearch size={14} /> Vendor terbaca: <b>{ex.vendor_name}</b>{ex.invoice_no && <> · No. {ex.invoice_no}</>}</p>}

      <ul className="ai-checks">
        {CHECKS.map(({ code, label }, i) => {
          const failed = codes.has(code);
          const skipped = notInvoice && code !== "NOT_AN_INVOICE";
          return (
            <li key={code} className={failed ? "fail" : skipped ? "skip" : "pass"} style={{ animationDelay: `${0.15 + i * 0.12}s` }}>
              <span>{failed ? <X /> : skipped ? "–" : <Check />}</span>{label}
              {skipped && <small className="muted"> · dilewati</small>}
            </li>
          );
        })}
      </ul>
      {passed && doc.assigned_reviewer && (
        <p className="ai-found"><UserCheck size={14} /> Ditugaskan ke <b>{doc.assigned_reviewer}</b> untuk ditinjau.</p>
      )}
    </section>
  );
}

/** Garis pindai di atas pratinjau PDF selama AI membaca. */
export function AiScanOverlay({ label }: { label: string }) {
  return (
    <div className="ai-scan" aria-hidden="true">
      <span className="ai-scan-beam" />
      <span className="ai-scan-label"><Sparkles size={12} /> {label}</span>
    </div>
  );
}
