import { useState } from "react";
import { AlertTriangle, Ban, CheckCircle2, FileQuestion, Receipt, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { api } from "../api";
import { FIELD_LABEL, ISSUE_LABEL, rupiah, tanggal } from "../format";
import type { AccountCheck, DocClass, DocumentDetail } from "../types";
import { Alert, Modal } from "./ui";

export const CLASS_LABEL: Record<DocClass, string> = {
  INVOICE: "Invoice vendor",
  RECEIPT: "Struk / nota pembelian",
  IRRELEVANT: "Tidak relevan",
  UNCERTAIN: "Meragukan",
};
const CLASS_TONE: Record<DocClass, string> = { INVOICE: "ok", RECEIPT: "warn", IRRELEVANT: "bad", UNCERTAIN: "warn" };

const DRAFT_FIELDS = ["vendor_name", "invoice_no", "invoice_date", "total", "bank_name", "account_no", "account_name"] as const;

/** Status rekening tujuan dibanding data vendor yang diverifikasi Finance Reviewer. */
export function AccountCheckBox({ check }: { check: AccountCheck }) {
  const meta = {
    VERIFIED: { icon: ShieldCheck, tone: "ok", title: "Rekening terverifikasi" },
    MISMATCH: { icon: ShieldAlert, tone: "bad", title: "Rekening tidak cocok dengan data terverifikasi" },
    UNVERIFIED: { icon: ShieldQuestion, tone: "warn", title: "Rekening belum terverifikasi" },
    MISSING: { icon: ShieldQuestion, tone: "gray", title: "Rekening belum ada" },
  }[check.state as string];
  // Reimburse (NOT_APPLICABLE) tidak dicek rekeningnya; status yang tidak dikenal juga tidak ditampilkan
  if (!meta) return null;
  const Icon = meta.icon;
  return (
    <div className={`account-check ${meta.tone}`}>
      <Icon />
      <div>
        <b>{meta.title}</b>
        <span>{check.message}</span>
        <small>Sumber nomor rekening: {check.source === "PIC" ? "diisi PIC" : "dibaca AI dari dokumen"}</small>
      </div>
    </div>
  );
}

/** Panel Preview hasil klasifikasi AI: draft data, data yang belum lengkap, peringatan validasi, dan keputusan
 *  manual Finance Reviewer. Tidak tampil untuk invoice biasa yang tidak pernah diputuskan manual. */
export function ClassificationPanel({ doc, canDecide, onDecided }: {
  doc: DocumentDetail; canDecide: boolean; onDecided: (next: DocumentDetail, text: string) => void;
}) {
  const [deciding, setDeciding] = useState<null | "INVOICE" | "RECEIPT_ACCEPTED" | "IRRELEVANT">(null);
  const info = doc.classification;
  if (!info || (info.doc_class === "INVOICE" && !info.decision)) return null;

  const ex = doc.extraction;
  const codes = new Set(doc.issues.map((i) => i.code));
  const missing = doc.issues.filter((i) => i.code === "MISSING_EVIDENCE");
  const warnings = doc.issues.filter((i) => !["MISSING_EVIDENCE", "RECEIPT_NOT_INVOICE", "NEEDS_MANUAL_REVIEW", "NOT_AN_INVOICE"].includes(i.code));
  const open = codes.has("RECEIPT_NOT_INVOICE") || codes.has("NEEDS_MANUAL_REVIEW");
  const isReceipt = info.doc_class === "RECEIPT";
  const Icon = info.doc_class === "IRRELEVANT" ? Ban : isReceipt ? Receipt : FileQuestion;
  const title = {
    INVOICE: "Diklasifikasikan manual sebagai invoice",
    RECEIPT: "Preview Draft dari struk / nota",
    IRRELEVANT: "Dokumen ditolak: tidak relevan",
    UNCERTAIN: "Dokumen perlu pemeriksaan manual",
  }[info.doc_class];
  const receiptReady = open && codes.size === 1 && codes.has("RECEIPT_NOT_INVOICE") && doc.account_check?.state === "VERIFIED";

  return (
    <section className={`card panel preview-panel ${CLASS_TONE[info.doc_class]}`}>
      <div className="panel-head">
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <span className={`stat-ic ${info.doc_class === "IRRELEVANT" ? "red" : info.doc_class === "INVOICE" ? "teal" : "amber"}`}><Icon /></span>
          <div>
            <h2>{title}</h2>
            <p>Klasifikasi AI: <b>{CLASS_LABEL[info.doc_class]}</b>
              {isReceipt && " · bukan invoice resmi vendor, voucher tidak terbit otomatis"}</p>
          </div>
        </div>
      </div>

      {info.files.length > 0 && (
        <ul className="preview-files">
          {info.files.map((f) => (
            <li key={f.file}>
              <span className={`chip ${f.doc_class === "INVOICE" ? "ok" : f.doc_class === "IRRELEVANT" ? "bad" : "warn"}`}>{CLASS_LABEL[f.doc_class]}</span>
              <span><b>{f.file}</b>{f.document_type && <> · terbaca sebagai {f.document_type}</>}
                {f.reason && <span className="muted"> · {f.reason}</span>}</span>
            </li>
          ))}
        </ul>
      )}

      {ex && info.doc_class !== "IRRELEVANT" && (
        <>
          <div className="section-title">{isReceipt ? "Draft pengajuan (hasil ekstraksi AI)" : "Data yang terbaca"}</div>
          <dl className="meta preview-data">
            {DRAFT_FIELDS.map((k) => {
              const value = k === "total" ? (ex.total != null ? rupiah(ex.total) : null) : k === "invoice_date" ? (ex.invoice_date ? tanggal(ex.invoice_date) : null) : ex[k];
              return (
                <div key={k} className={value ? undefined : "missing"} style={{ display: "contents" }}>
                  <dt>{FIELD_LABEL[k]}</dt>
                  <dd>{value ?? <span className="chip warn">Belum ada</span>}</dd>
                </div>
              );
            })}
            <dt>Rincian barang</dt><dd>{ex.line_items.length} baris</dd>
          </dl>
          <small className="muted">AI hanya menyalin data yang tertulis di dokumen; data yang tidak ada dibiarkan kosong, tidak ditebak.</small>
        </>
      )}

      {missing.length > 0 && (
        <div>
          <div className="section-title">Data yang belum lengkap ({missing.length})</div>
          <ul className="preview-list">{missing.map((i, n) => <li key={n}>{i.field ? FIELD_LABEL[i.field] ?? i.field : "Rincian"}: {i.message}</li>)}</ul>
        </div>
      )}
      {warnings.length > 0 && (
        <div>
          <div className="section-title">Peringatan validasi ({warnings.length})</div>
          <ul className="preview-list warn">{warnings.map((i, n) => <li key={n}><b>{ISSUE_LABEL[i.code]}</b>: {i.message}</li>)}</ul>
        </div>
      )}
      {doc.account_check && info.doc_class !== "IRRELEVANT" && <AccountCheckBox check={doc.account_check} />}

      {info.decision && (
        <Alert kind="info">
          Keputusan manual <b>{info.decision.decision === "RECEIPT_ACCEPTED" ? "struk diterima sebagai dasar pembayaran"
            : info.decision.decision === "INVOICE" ? "diproses sebagai invoice" : "ditolak sebagai tidak relevan"}</b> oleh{" "}
          {info.decision.by}: {info.decision.reason}
        </Alert>
      )}
      {isReceipt && open && (
        <Alert kind="warn">
          Struk/nota tidak otomatis menjadi invoice resmi. Pilihannya: minta invoice resmi ke vendor lalu ajukan ulang,
          atau Finance Reviewer menerimanya sebagai dasar pembayaran setelah data wajib lengkap dan rekening terverifikasi.
          Persetujuan Finance Reviewer tetap diperlukan sebelum voucher terbit.
        </Alert>
      )}

      {canDecide && open && (
        <div className="actions">
          {isReceipt ? (
            <button className="btn primary" disabled={!receiptReady} onClick={() => setDeciding("RECEIPT_ACCEPTED")}
                    title={receiptReady ? undefined : "Data wajib harus lengkap dan rekening terverifikasi lebih dulu"}>
              <CheckCircle2 /> Terima sebagai dasar pembayaran
            </button>
          ) : (
            <button className="btn primary" onClick={() => setDeciding("INVOICE")}><CheckCircle2 /> Proses sebagai invoice</button>
          )}
          <button className="btn danger" onClick={() => setDeciding("IRRELEVANT")}><Ban /> Tolak: tidak relevan</button>
          {isReceipt && !receiptReady && (
            <small className="muted" style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <AlertTriangle size={14} /> Bisa diterima setelah data wajib lengkap dan rekening vendor terverifikasi.
            </small>
          )}
        </div>
      )}
      {deciding && <DecisionModal doc={doc} decision={deciding} onClose={() => setDeciding(null)}
                                  onDone={(next, text) => { setDeciding(null); onDecided(next, text); }} />}
    </section>
  );
}

function DecisionModal({ doc, decision, onClose, onDone }: {
  doc: DocumentDetail; decision: "INVOICE" | "RECEIPT_ACCEPTED" | "IRRELEVANT";
  onClose: () => void; onDone: (next: DocumentDetail, text: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const meta = {
    RECEIPT_ACCEPTED: ["Terima struk sebagai dasar pembayaran", "mis. Reimbursement sesuai kebijakan klien; vendor tidak menerbitkan invoice.",
      "Struk diterima. Dokumen masuk antrean Finance Reviewer untuk disetujui."],
    INVOICE: ["Proses sebagai invoice", "mis. Dicek manual: dokumen adalah invoice resmi vendor.", "Dokumen diverifikasi ulang sebagai invoice."],
    IRRELEVANT: ["Tolak dokumen", "mis. Dokumen ini surat penawaran, bukan tagihan.", "Dokumen ditolak sebagai tidak relevan."],
  }[decision];

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      onDone(await api.post<DocumentDetail>(`/documents/${doc.id}/classification`, { decision, reason }), meta[2]);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={meta[0]} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <div className="field">
        <label htmlFor="cls-reason">Alasan (wajib, tercatat di jejak audit)</label>
        <textarea id="cls-reason" className="input" value={reason} placeholder={meta[1]} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className={`btn ${decision === "IRRELEVANT" ? "danger" : "primary"}`} disabled={busy || reason.trim().length < 5}
                onClick={submit}>{meta[0]}</button>
      </div>
    </Modal>
  );
}
