import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, FileClock, Loader2, Plus, Receipt, RotateCcw, Save, Trash2, Undo2 } from "lucide-react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { ReassignModal } from "../components/ReassignModal";
import { Alert, Loading, Modal, PdfFrame, StatusBadge, useApi } from "../components/ui";
import { FIELD_LABEL, ISSUE_LABEL, plainNumber, rupiah, tanggal, waktu } from "../format";
import type { DashboardSummary, DocumentDetail, Extraction, Issue } from "../types";

const HEADER_FIELDS = ["vendor_name", "invoice_no", "invoice_date", "total"] as const;
const PAYMENT_FIELDS = ["bank_name", "account_no", "account_name"] as const;
const ALL_FIELDS = [...HEADER_FIELDS, ...PAYMENT_FIELDS];
type Field = (typeof ALL_FIELDS)[number];
type Fields = Record<Field, string>;
interface Line { description: string; qty: string; unit_price: string; subtotal: string }

function toFields(ex: Extraction | null): Fields {
  const f = {} as Fields;
  ALL_FIELDS.forEach((k) => {
    const v = ex?.[k] ?? null;
    f[k] = k === "total" ? plainNumber(v) : v ?? "";
  });
  return f;
}

const toLines = (ex: Extraction | null): Line[] =>
  (ex?.line_items ?? []).map((l) => ({
    description: l.description ?? "", qty: plainNumber(l.qty), unit_price: plainNumber(l.unit_price), subtotal: plainNumber(l.subtotal),
  }));

const flagged = (issues: Issue[]) => new Set(issues.map((i) => i.field).filter(Boolean) as string[]);
const inputType = (k: Field) => (k === "invoice_date" ? "date" : k === "total" ? "number" : "text");

/** Layar 03 — Peninjauan & Verifikasi, sekaligus status dan perbaikan untuk PIC (Layar 02). */
export function DocumentPage() {
  const { id = "" } = useParams();
  const { has } = useAuth();
  const doc = useApi(() => api.get<DocumentDetail>(`/documents/${id}`), [id]);
  const [notice, setNotice] = useState<{ kind: "ok" | "info" | "error" | "warn"; text: string } | null>(null);
  const [reassign, setReassign] = useState<DashboardSummary | null>(null);
  const d = doc.data;

  // Ekstraksi dan verifikasi berjalan di background: muat ulang sampai selesai
  useEffect(() => {
    if (!d || (d.status !== "QUEUED" && d.status !== "PROCESSING")) return;
    const timer = setTimeout(doc.reload, 1500);
    return () => clearTimeout(timer);
  }, [d]); // eslint-disable-line react-hooks/exhaustive-deps

  if (doc.error && !d) return <Alert>{doc.error}</Alert>;
  if (!d) return <Loading />;

  const processing = d.status === "QUEUED" || d.status === "PROCESSING";
  const codes = new Set(d.issues.map((i) => i.code));
  const isReviewer = has("FINANCE_REVIEWER");
  const canReview = isReviewer && d.status === "READY_FOR_REVIEW" && Boolean(d.extraction);
  const canFix = has("PIC_KLIEN", "INTAKE_SUPPORT") && d.status === "EXCEPTION";
  const canReprocess = isReviewer && d.status === "EXCEPTION" && codes.has("EXTRACTION_FAILED");
  const canDismissDup = isReviewer && d.status === "EXCEPTION" && codes.size === 1 && codes.has("POSSIBLE_DUPLICATE");
  const hasVoucher = d.status === "AMIGA_REVIEWED" || d.status === "SENT_TO_CLIENT";

  const update = (next: DocumentDetail, message?: typeof notice) => {
    doc.setData(next);
    setNotice(message ?? null);
  };

  async function reprocess() {
    try {
      update(await api.post<DocumentDetail>(`/documents/${id}/reprocess`), { kind: "info", text: "Dokumen diproses ulang oleh AI." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
  }

  async function openReassign() {
    try { setReassign(await api.get<DashboardSummary>("/dashboard/summary")); }
    catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 19 }}>{d.request_id}</span> <StatusBadge status={d.status} />
          </h1>
          <p>{d.client.name} · {d.request_type ?? "-"} · via {d.channel ?? "-"}</p>
        </div>
        <div className="actions">
          {has("SERVICE_LEAD") && d.status === "READY_FOR_REVIEW" && <button className="btn" onClick={openReassign}>Alihkan reviewer</button>}
          <Link className="btn" to={`/dokumen/${id}/riwayat`}><FileClock /> Riwayat</Link>
          {hasVoucher && !has("SERVICE_LEAD") && <Link className="btn primary" to={`/dokumen/${id}/voucher`}><Receipt /> Voucher</Link>}
        </div>
      </div>

      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}

      <div className="split">
        <section className="card pdf-pane" aria-label="PDF asli">
          <div className="pdf-head">
            <b>PDF asli</b>
            <span className="muted">{d.original_filename} · {d.page_count} hal.</span>
          </div>
          <PdfFrame path={`/documents/${id}/file`} title={`Invoice ${d.request_id}`} />
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          <section className="card panel">
            <dl className="meta">
              <dt>Pengunggah</dt><dd>{d.uploaded_by}{d.on_behalf_of && <> · atas nama {d.on_behalf_of}</>}</dd>
              <dt>Tanggal pengajuan</dt><dd>{tanggal(d.submitted_date)}</dd>
              <dt>Tenggat</dt><dd>{tanggal(d.due_date)}</dd>
              <dt>Finance Reviewer</dt><dd>{d.assigned_reviewer ?? "-"}</dd>
              {d.extraction?.duration_ms != null && <><dt>Dibaca AI</dt><dd>{(d.extraction.duration_ms / 1000).toFixed(1)} detik · {waktu(d.extraction.extracted_at)}</dd></>}
              {d.voucher && <><dt>Voucher</dt><dd className="mono">{d.voucher.voucher_no}</dd></>}
            </dl>
          </section>

          {processing && (
            <Alert kind="info"><span><Loader2 className="spin" size={14} style={{ verticalAlign: "-2px" }} /> AI sedang membaca invoice dan sistem
              memverifikasinya. Halaman ini diperbarui otomatis.</span></Alert>
          )}

          {d.issues.length > 0 && (
            <section className="card panel">
              <div className="section-title">Kendala ({d.issues.length})</div>
              <div className="issues">
                {d.issues.map((i, n) => (
                  <div className="issue" key={n}>
                    <b>{ISSUE_LABEL[i.code]} {i.field && <>· {FIELD_LABEL[i.field] ?? i.field}</>}</b>
                    <span>{i.message}</span>
                    <code>{i.code}</code>
                  </div>
                ))}
              </div>
              {(canReprocess || canDismissDup) && (
                <div className="actions">
                  {canReprocess && <button className="btn primary" onClick={reprocess}><RotateCcw /> Proses ulang</button>}
                  {canDismissDup && <DismissDuplicate id={id} onDone={(n) => update(n, { kind: "ok", text: "Ditandai bukan duplikat; dokumen siap ditinjau." })} />}
                </div>
              )}
            </section>
          )}

          {canFix && <FixForm doc={d} onDone={(n) => update(n, { kind: "info", text: "Perbaikan terkirim. Dokumen kembali ke ekstraksi dengan Request ID yang sama." })} />}

          {d.extraction && (canReview
            ? <ReviewForm doc={d} onChange={update} onNotice={setNotice} />
            : <ReadOnlyData doc={d} />)}
        </div>
      </div>

      {reassign && (
        <ReassignModal doc={d} reviewers={reassign.reviewers} onClose={() => setReassign(null)}
                       onDone={() => { setReassign(null); doc.reload(); setNotice({ kind: "ok", text: "Reviewer dialihkan." }); }} />
      )}
    </>
  );
}

function ReadOnlyData({ doc }: { doc: DocumentDetail }) {
  const ex = doc.extraction!;
  const flags = flagged(doc.issues);
  return (
    <section className="card panel">
      <div className="section-title">Data invoice</div>
      <dl className="meta">
        {ALL_FIELDS.map((k) => (
          <FieldView key={k} label={FIELD_LABEL[k]} flag={flags.has(k)} pic={k in doc.pic_overrides}
                     value={k === "total" ? rupiah(ex.total) : k === "invoice_date" ? tanggal(ex.invoice_date) : ex[k] ?? "-"} />
        ))}
      </dl>
      <LinesTable lines={toLines(ex)} total={ex.total} />
    </section>
  );
}

function FieldView({ label, value, flag, pic }: { label: string; value: string; flag: boolean; pic: boolean }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <span style={flag ? { color: "var(--amber)", fontWeight: 600 } : undefined}>{value || "-"}</span>
        {pic && <> <span className="chip gray">diisi PIC</span></>}
      </dd>
    </>
  );
}

function LinesTable({ lines, total }: { lines: Line[]; total: string | null }) {
  const sum = lines.reduce((s, l) => s + (Number(l.subtotal) || 0), 0);
  const match = total !== null && Math.abs(sum - Number(total)) < 0.005;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table compact">
        <thead><tr><th>#</th><th>Uraian</th><th className="right">Qty</th><th className="right">Harga</th><th className="right">Subtotal</th></tr></thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}>
              <td>{i + 1}</td><td>{l.description || "-"}</td><td className="right num">{l.qty || "-"}</td>
              <td className="right num">{rupiah(l.unit_price)}</td><td className="right num">{rupiah(l.subtotal)}</td>
            </tr>
          ))}
          <tr>
            <td colSpan={4} className="right"><b>Jumlah rincian</b></td>
            <td className="right num"><b>{rupiah(sum)}</b> {total !== null && <span className={`chip ${match ? "ok" : "warn"}`}>{match ? "= total" : "≠ total"}</span>}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** Koreksi oleh Finance Reviewer: Simpan & verifikasi ulang, Kembalikan ke PIC, Setujui (FR-4.1–4.5). */
function ReviewForm({ doc, onChange, onNotice }: {
  doc: DocumentDetail;
  onChange: (d: DocumentDetail, n?: { kind: "ok" | "info" | "error" | "warn"; text: string } | null) => void;
  onNotice: (n: { kind: "ok" | "info" | "error" | "warn"; text: string } | null) => void;
}) {
  const initial = useMemo(() => ({ fields: toFields(doc.extraction), lines: toLines(doc.extraction) }), [doc]);
  const [fields, setFields] = useState(initial.fields);
  const [lines, setLines] = useState(initial.lines);
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState(false);
  useEffect(() => { setFields(initial.fields); setLines(initial.lines); }, [initial]);

  const dirty = JSON.stringify({ fields, lines }) !== JSON.stringify(initial);
  const flags = flagged(doc.issues);
  const setLine = (i: number, k: keyof Line, v: string) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, [k]: v } : l)));

  async function save() {
    const changed = Object.fromEntries(
      ALL_FIELDS.filter((k) => fields[k] !== initial.fields[k]).map((k) => [k, fields[k].trim() || null]),
    );
    const linesChanged = JSON.stringify(lines) !== JSON.stringify(initial.lines);
    setBusy(true);
    try {
      const next = await api.put<DocumentDetail>(`/documents/${doc.id}/extraction`, {
        fields: changed,
        line_items: linesChanged ? lines.map((l) => ({
          description: l.description || null, qty: l.qty || null, unit_price: l.unit_price || null, subtotal: l.subtotal || null,
        })) : null,
      });
      onChange(next, next.issues.length
        ? { kind: "warn", text: "Tersimpan. Verifikasi ulang menemukan kendala; persetujuan ditahan sampai kendala selesai." }
        : { kind: "ok", text: "Tersimpan dan lolos verifikasi ulang. Perubahan tercatat di jejak audit." });
    } catch (e) {
      onNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    try {
      const next = await api.post<DocumentDetail>(`/documents/${doc.id}/approve`);
      onChange(next, { kind: "ok", text: `Disetujui. Voucher ${next.voucher?.voucher_no} sudah dibuat.` });
    } catch (e) {
      // Penolakan SoD: dokumen sudah dialihkan otomatis oleh sistem
      const err = e as ApiError;
      onNotice({ kind: err.status === 403 ? "warn" : "error", text: err.message });
      if (err.status === 403) onChange(await api.get<DocumentDetail>(`/documents/${doc.id}`), { kind: "warn", text: err.message });
    } finally {
      setBusy(false);
    }
  }

  const fieldInput = (k: Field) => (
    <div className="field" key={k}>
      <label htmlFor={`f-${k}`}>{FIELD_LABEL[k]} {k in doc.pic_overrides && <span className="chip gray">diisi PIC</span>}</label>
      <input id={`f-${k}`} className={`input ${flags.has(k) ? "flag" : ""} ${k === "account_no" ? "mono" : ""}`}
             type={inputType(k)} step={k === "total" ? "0.01" : undefined}
             value={fields[k]} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} />
    </div>
  );

  return (
    <section className="card panel">
      <div className="section-title">Informasi utama</div>
      <div className="grid-2">{HEADER_FIELDS.map(fieldInput)}</div>

      <div className="section-title">Rincian barang/jasa</div>
      <div style={{ overflowX: "auto" }}>
        <table className="table compact">
          <thead><tr><th>#</th><th>Uraian</th><th>Qty</th><th>Harga satuan</th><th>Subtotal</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td><input className="input" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} aria-label={`Uraian ${i + 1}`} /></td>
                <td style={{ width: 70 }}><input className="input num" type="number" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} aria-label={`Qty ${i + 1}`} /></td>
                <td style={{ width: 120 }}><input className="input num" type="number" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} aria-label={`Harga ${i + 1}`} /></td>
                <td style={{ width: 130 }}><input className={`input num ${flags.has("total") ? "flag" : ""}`} type="number" value={l.subtotal} onChange={(e) => setLine(i, "subtotal", e.target.value)} aria-label={`Subtotal ${i + 1}`} /></td>
                <td><button className="btn ghost sm" onClick={() => setLines(lines.filter((_, n) => n !== i))} aria-label={`Hapus baris ${i + 1}`}><Trash2 /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <button className="btn sm" onClick={() => setLines([...lines, { description: "", qty: "", unit_price: "", subtotal: "" }])}><Plus /> Tambah baris</button>
        <SumCheck lines={lines} total={fields.total} />
      </div>

      <div className="section-title">Data pembayaran</div>
      <div className="grid-2">{PAYMENT_FIELDS.map(fieldInput)}</div>
      <small className="muted">Cek nomor rekening digit per digit dengan PDF (SOP 7.4).</small>

      <div className="decision">
        {dirty && <button className="btn" disabled={busy} onClick={() => { setFields(initial.fields); setLines(initial.lines); }}><Undo2 /> Batalkan</button>}
        <button className="btn" disabled={busy || !dirty} onClick={save}><Save /> Simpan & verifikasi ulang</button>
        <button className="btn danger" disabled={busy} onClick={() => setReturning(true)}>Kembalikan ke PIC</button>
        <button className="btn success" disabled={busy || dirty || doc.issues.length > 0} onClick={approve}
                title={dirty ? "Simpan perubahan dulu" : doc.issues.length ? "Masih ada kendala" : undefined}>
          <CheckCircle2 /> Setujui
        </button>
      </div>

      {returning && (
        <ReasonModal title="Kembalikan ke PIC" label="Alasan (wajib, akan dibaca PIC)"
                     placeholder="mis. Lampirkan invoice revisi dengan total yang benar."
                     submitLabel="Kembalikan" onClose={() => setReturning(false)}
                     onSubmit={async (reason) => {
                       const next = await api.post<DocumentDetail>(`/documents/${doc.id}/return`, { reason });
                       setReturning(false);
                       onChange(next, { kind: "info", text: "Dokumen dikembalikan ke PIC (EXCEPTION · RETURNED_BY_REVIEWER)." });
                     }} />
      )}
    </section>
  );
}

function SumCheck({ lines, total }: { lines: Line[]; total: string }) {
  const sum = lines.reduce((s, l) => s + (Number(l.subtotal) || 0), 0);
  const match = total !== "" && Math.abs(sum - Number(total)) < 0.005;
  return (
    <span className="num">
      Jumlah rincian <b>{rupiah(sum)}</b> · total {rupiah(total || null)}{" "}
      <span className={`chip ${match ? "ok" : "warn"}`}>{match ? "cocok" : "tidak cocok"}</span>
    </span>
  );
}

/** Perbaikan oleh PIC Klien / Intake Support saat EXCEPTION (FR-3.4, SOP 7.3). */
function FixForm({ doc, onDone }: { doc: DocumentDetail; onDone: (d: DocumentDetail) => void }) {
  const flags = flagged(doc.issues);
  const current = toFields(doc.extraction);
  const [values, setValues] = useState<Partial<Fields>>({});
  const [showAll, setShowAll] = useState(flags.size === 0);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const shown = ALL_FIELDS.filter((k) => showAll || flags.has(k));

  async function submit() {
    const fields = Object.fromEntries(Object.entries(values).filter(([, v]) => v && v.trim()));
    setBusy(true);
    setError(null);
    try {
      onDone(await api.post<DocumentDetail>(`/documents/${doc.id}/fix`, { fields, note: note.trim() || null }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card panel" style={{ borderColor: "#f6d7b0" }}>
      <div className="panel-head">
        <div>
          <h2>Kirim perbaikan</h2>
          <p>Isi data yang kurang atau salah. Isian Anda tidak ditimpa saat AI membaca ulang invoice.</p>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="grid-2">
        {shown.map((k) => (
          <div className="field" key={k}>
            <label htmlFor={`fix-${k}`}>{FIELD_LABEL[k]}</label>
            <input id={`fix-${k}`} className={`input ${flags.has(k) ? "flag" : ""}`} type={inputType(k)}
                   placeholder={current[k] || "kosong"} value={values[k] ?? ""}
                   onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
            {k === "total" && <small>Angka tanpa titik ribuan, mis. 1250000</small>}
          </div>
        ))}
      </div>
      {!showAll && <button className="btn ghost sm" style={{ alignSelf: "flex-start" }} onClick={() => setShowAll(true)}>Perbaiki field lain</button>}
      <div className="field">
        <label htmlFor="fix-note">Catatan untuk reviewer</label>
        <textarea id="fix-note" className="input" value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="mis. Nomor rekening dikonfirmasi lewat email vendor tanggal 14/10." maxLength={1000} />
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn primary" disabled={busy} onClick={submit}>{busy ? "Mengirim…" : "Kirim perbaikan"}</button>
      </div>
    </section>
  );
}

function DismissDuplicate({ id, onDone }: { id: string; onDone: (d: DocumentDetail) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn" onClick={() => setOpen(true)}>Tandai bukan duplikat</button>
      {open && (
        <ReasonModal title="Tandai bukan duplikat" label="Alasan (wajib, tercatat di jejak audit)"
                     placeholder="mis. Tagihan bulan berbeda, sudah dikonfirmasi ke vendor." submitLabel="Tandai"
                     onClose={() => setOpen(false)}
                     onSubmit={async (reason) => {
                       const next = await api.post<DocumentDetail>(`/documents/${id}/dismiss-duplicate`, { reason });
                       setOpen(false);
                       onDone(next);
                     }} />
      )}
    </>
  );
}

function ReasonModal({ title, label, placeholder, submitLabel, onClose, onSubmit }: {
  title: string; label: string; placeholder: string; submitLabel: string;
  onClose: () => void; onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = reason.trim().length >= 5;
  return (
    <Modal title={title} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <div className="field">
        <label htmlFor="reason">{label}</label>
        <textarea id="reason" className="input" autoFocus value={reason} placeholder={placeholder} maxLength={1000}
                  onChange={(e) => setReason(e.target.value)} />
        <small>Minimal 5 karakter.</small>
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={!valid || busy} onClick={async () => {
          setBusy(true);
          try { await onSubmit(reason.trim()); } catch (e) { setError((e as Error).message); setBusy(false); }
        }}>{submitLabel}</button>
      </div>
    </Modal>
  );
}
