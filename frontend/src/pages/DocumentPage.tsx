import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Ban, CheckCircle2, Download, ExternalLink, Eye, FileClock, Maximize2, Minimize2, Plus, Receipt, RotateCcw, Save, Send, Trash2, Undo2 } from "lucide-react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { AiProcessingCard, AiResultCard, AiScanOverlay } from "../components/AiProcessing";
import { AccountCheckBox, ClassificationPanel } from "../components/DocumentPreview";
import { ReassignModal } from "../components/ReassignModal";
import { SignerPicker } from "../components/SignerPicker";
import { Alert, Loading, Modal, PdfFrame, StatusBadge, useApi } from "../components/ui";
import { FIELD_LABEL, ISSUE_LABEL, plainNumber, rupiah, tanggal, waktu } from "../format";
import type { DocumentDetail, Extraction, FileData, Issue, Signatory, TaxRate, TaxSummary, Vendor } from "../types";

const HEADER_FIELDS = ["vendor_name", "invoice_no", "invoice_date", "total"] as const;
const PAYMENT_FIELDS = ["bank_name", "account_no", "account_name"] as const;
const ALL_FIELDS = [...HEADER_FIELDS, ...PAYMENT_FIELDS];
type Field = (typeof ALL_FIELDS)[number];
type Fields = Record<Field, string>;
interface Line { description: string; qty: string; unit_price: string; subtotal: string }

const toLines = (ex: Extraction | null): Line[] =>
  (ex?.line_items ?? []).map((l) => ({
    description: l.description ?? "", qty: plainNumber(l.qty), unit_price: plainNumber(l.unit_price), subtotal: plainNumber(l.subtotal),
  }));

/** Kendala yang harus dibereskan PIC sebelum draf boleh dikirim (sama dengan BLOCKING di backend). */
const BLOCKING = new Set(["MISSING_EVIDENCE", "CALCULATION_DISCREPANCY", "VENDOR_MISMATCH", "NOT_AN_INVOICE",
                          "EXTRACTION_FAILED", "ACCOUNT_MISMATCH"]);

const flagged = (issues: Issue[]) => new Set(issues.map((i) => i.field).filter(Boolean) as string[]);
const inputType = (k: Field) => (k === "invoice_date" ? "date" : k === "total" ? "number" : "text");

/** Layar 03 — Peninjauan & Verifikasi, sekaligus status dan perbaikan untuk PIC (Layar 02). */
export function DocumentPage() {
  const { id = "" } = useParams();
  const { has } = useAuth();
  const doc = useApi(() => api.get<DocumentDetail>(`/documents/${id}`), [id]);
  const [notice, setNotice] = useState<{ kind: "ok" | "info" | "error" | "warn"; text: string } | null>(null);
  const [reassign, setReassign] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  // Invoice yang sedang diedit PIC (posisi file, mulai 1)
  const [pos, setPos] = useState(1);
  const d = doc.data;
  // Ringkasan hasil AI dianimasikan bila prosesnya selesai saat halaman ini terbuka
  const sawProcessing = useRef(false);
  const [fresh, setFresh] = useState(false);
  const [resultClosed, setResultClosed] = useState(false);
  useEffect(() => {
    if (!d) return;
    const busy = d.status === "QUEUED" || d.status === "PROCESSING";
    if (busy) { sawProcessing.current = true; setResultClosed(false); }
    else if (sawProcessing.current) { sawProcessing.current = false; setFresh(true); }
  }, [d?.status]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const isPic = has("PIC_KLIEN", "INTAKE_SUPPORT");
  const canReview = isReviewer && d.status === "READY_FOR_REVIEW" && Boolean(d.extraction);
  // Draf dan dokumen berkendala diedit PIC per invoice; Finance Reviewer tidak mengedit (feedback owner)
  const canEdit = isPic && (d.status === "DRAFT" || d.status === "EXCEPTION") && d.files.length > 0;
  const canReprocess = (isReviewer || isPic) && d.status === "EXCEPTION" && codes.has("EXTRACTION_FAILED");
  const canDismissDup = isReviewer && d.status === "READY_FOR_REVIEW" && codes.has("POSSIBLE_DUPLICATE");
  const filePos = Math.min(pos, Math.max(d.files.length, 1));
  const hasVoucher = d.status === "AMIGA_REVIEWED" || d.status === "SENT_TO_CLIENT";
  // Pengaju boleh membatalkan selama voucher belum terbit (setelah AI selesai membaca)
  const canCancel = isPic && (d.status === "DRAFT" || d.status === "EXCEPTION" || d.status === "READY_FOR_REVIEW");

  const update = (next: DocumentDetail, message?: typeof notice) => {
    doc.setData(next);
    setNotice(message ?? null);
  };

  async function reprocess() {
    try {
      update(await api.post<DocumentDetail>(`/documents/${id}/reprocess`), { kind: "info", text: "Dokumen diproses ulang oleh AI." });
    } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
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
          {has("SERVICE_LEAD") && d.status === "READY_FOR_REVIEW" && <button className="btn" onClick={() => setReassign(true)}>Alihkan reviewer</button>}
          {canCancel && <button className="btn danger" onClick={() => setCancelling(true)}><Ban /> Batalkan pengajuan</button>}
          <Link className="btn" to={`/dokumen/${id}/riwayat`}><FileClock /> Riwayat</Link>
          {hasVoucher && !has("SERVICE_LEAD") && <Link className="btn primary" to={`/dokumen/${id}/voucher`}><Receipt /> Voucher</Link>}
        </div>
      </div>

      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {d.cancellation && (
        <Alert kind="warn">
          Pengajuan ini <b>dibatalkan</b> oleh {d.cancellation.by} pada {waktu(d.cancellation.at)}. Alasan: {d.cancellation.reason}
        </Alert>
      )}
      {cancelling && (
        <ReasonModal title="Batalkan pengajuan" label="Alasan pembatalan (wajib, tercatat di jejak audit)"
                     placeholder="mis. Salah unggah: file ini struk belanja, bukan invoice vendor." submitLabel="Batalkan pengajuan"
                     onClose={() => setCancelling(false)}
                     onSubmit={async (reason) => {
                       const next = await api.post<DocumentDetail>(`/documents/${id}/cancel`, { reason });
                       setCancelling(false);
                       update(next, { kind: "ok", text: "Pengajuan dibatalkan. Data dan riwayatnya tetap tersimpan; invoice yang benar bisa diajukan ulang." });
                     }} />
      )}

      <div className="split">
        <section className="card pdf-pane" aria-label="PDF asli">
          <div className="pdf-head">
            <b>{canEdit && d.files.length > 1 ? `Bukti ${filePos} dari ${d.files.length}` : "PDF asli"}</b>
            <span className="muted">{d.files.length > 1 ? `${d.files.length} invoice` : d.original_filename} · {d.page_count} hal.
              {d.files.length === 1 && d.files[0].source_format && <> · dari foto <OriginalLink docId={d.id} position={1} /></>}</span>
          </div>
          <div className="pdf-body">
            <PdfFrame path={canEdit && d.files.length > 1 ? `/documents/${id}/files/${filePos}` : `/documents/${id}/file`}
                      title={`Invoice ${d.request_id}`} />
            {processing && <AiScanOverlay label={d.status === "QUEUED" ? "Menunggu giliran AI" : "AI membaca invoice"} />}
          </div>
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          <section className="card panel">
            <dl className="meta">
              <dt>Pengunggah</dt><dd>{d.uploaded_by}{d.on_behalf_of && <> · atas nama {d.on_behalf_of}</>}</dd>
              {d.files.length > 1 && (
                <><dt>File invoice</dt>
                  <dd><ol className="plain-list">{d.files.map((f) => (
                    <li key={f.position}>{f.original_filename} <span className="muted">· {f.page_count} hal.</span>
                      {f.source_format && <> <span className="muted">· dari foto</span> <OriginalLink docId={d.id} position={f.position} /></>}</li>
                  ))}</ol></dd></>
              )}
              <dt>Tanggal pengajuan</dt><dd>{tanggal(d.submitted_date)}</dd>
              <dt>Tenggat</dt><dd>{tanggal(d.due_date)}</dd>
              <dt>Finance Reviewer</dt><dd>{d.assigned_reviewer ?? "-"}</dd>
              <dt>Vendor</dt>
              <dd>{d.vendor_name ?? "-"} {d.vendor
                ? <span className="chip ok">terdaftar di data referensi</span>
                : d.vendor_name && <span className="chip gray">belum terdaftar</span>}</dd>
              {d.extraction?.duration_ms != null && <><dt>Dibaca AI</dt><dd>{(d.extraction.duration_ms / 1000).toFixed(1)} detik · {waktu(d.extraction.extracted_at)}</dd></>}
              {d.voucher && <><dt>Voucher</dt><dd className="mono">{d.voucher.voucher_no}</dd></>}
            </dl>
          </section>

          {processing && <AiProcessingCard doc={d} />}
          {!processing && !resultClosed && d.extraction && (fresh || d.status === "DRAFT" || d.status === "READY_FOR_REVIEW" || d.status === "EXCEPTION") && (
            <AiResultCard doc={d} onClose={() => setResultClosed(true)} />
          )}
          <ClassificationPanel doc={d} canDecide={isReviewer && d.status === "READY_FOR_REVIEW"}
                               onDecided={(n, text) => update(n, { kind: "ok", text })} />

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
                  {canDismissDup && <DismissDuplicate id={id} onDone={(n) => update(n, { kind: "ok", text: "Ditandai bukan duplikat." })} />}
                </div>
              )}
            </section>
          )}

          <SignersPanel doc={d} onChange={(n) => update(n, { kind: "ok", text: "Penanda tangan voucher diperbarui." })} />

          {canEdit
            ? <DraftEditor doc={d} pos={filePos} onPos={setPos} onChange={update} onNotice={setNotice} />
            : d.extraction && <ReadOnlyData doc={d} />}
          {!canEdit && d.extraction && d.status !== "CANCELLED" && !hasVoucher && <SimulationButton docId={d.id} />}
          {canReview && <ReviewDecision doc={d} onChange={update} onNotice={setNotice} />}
        </div>
      </div>

      <VendorOptions clientId={d.client.id} />

      {reassign && (
        <ReassignModal doc={d} onClose={() => setReassign(false)}
                       onDone={() => { setReassign(false); doc.reload(); setNotice({ kind: "ok", text: "Reviewer dialihkan." }); }} />
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
      {doc.tax_summary && <TaxSummaryBox summary={doc.tax_summary} multi={doc.files.length > 1} />}
      {doc.account_check && <AccountCheckBox check={doc.account_check} />}
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

type Notice = { kind: "ok" | "info" | "error" | "warn"; text: string } | null;

function dataFields(d: FileData | null | undefined): Fields {
  const f = {} as Fields;
  ALL_FIELDS.forEach((k) => { const v = d?.[k] ?? null; f[k] = k === "total" ? plainNumber(v) : v ?? ""; });
  return f;
}

const dataLines = (d: FileData | null | undefined): Line[] =>
  (d?.line_items ?? []).map((l) => ({
    description: l.description ?? "", qty: plainNumber(l.qty), unit_price: plainNumber(l.unit_price), subtotal: plainNumber(l.subtotal),
  }));

/** Draf oleh PIC Klien / Intake Support: edit per invoice, lihat simulasi voucher, kirim ke reviewer (feedback owner). */
function DraftEditor({ doc, pos, onPos, onChange, onNotice }: {
  doc: DocumentDetail; pos: number; onPos: (p: number) => void;
  onChange: (d: DocumentDetail, n?: Notice) => void; onNotice: (n: Notice) => void;
}) {
  const file = doc.files.find((f) => f.position === pos) ?? doc.files[0];
  const initial = useMemo(() => ({ fields: dataFields(file.data), lines: dataLines(file.data) }), [file]);
  const initialKey = JSON.stringify(initial);
  const [fields, setFields] = useState(initial.fields);
  const [lines, setLines] = useState(initial.lines);
  const [busy, setBusy] = useState(false);
  const [taxDirty, setTaxDirty] = useState(false);
  useEffect(() => { setFields(initial.fields); setLines(initial.lines); }, [initialKey, pos]); // eslint-disable-line react-hooks/exhaustive-deps

  const dataDirty = JSON.stringify({ fields, lines }) !== initialKey;
  const dirty = dataDirty || taxDirty;
  const reimburse = doc.request_type === "Voucher Pengeluaran Reimburse";
  const blocking = doc.issues.filter((i) => BLOCKING.has(i.code));
  const flags = flagged(blocking);
  const setLine = (i: number, k: keyof Line, v: string) => setLines((ls) => ls.map((l, n) => (n === i ? { ...l, [k]: v } : l)));

  async function save() {
    // Data lengkap satu invoice (backend mengganti data bukti ini dan mencatat field yang berubah)
    const data = {
      ...Object.fromEntries(ALL_FIELDS.map((k) => [k, fields[k].trim() || null])),
      line_items: lines.map((l) => ({
        description: l.description || null, qty: l.qty || null, unit_price: l.unit_price || null, subtotal: l.subtotal || null,
      })),
    };
    setBusy(true);
    try {
      const next = await api.put<DocumentDetail>(`/documents/${doc.id}/files/${file.position}/data`, data);
      const left = next.issues.filter((i) => BLOCKING.has(i.code)).length;
      onChange(next, left
        ? { kind: "warn", text: `Tersimpan. Masih ada ${left} kendala yang harus dibereskan sebelum dikirim ke reviewer.` }
        : { kind: "ok", text: "Tersimpan dan lolos verifikasi ulang. Cek simulasi voucher, lalu kirim ke reviewer." });
    } catch (e) {
      onNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true);
    try {
      const next = await api.post<DocumentDetail>(`/documents/${doc.id}/submit`);
      onChange(next, { kind: "ok", text: `Terkirim ke Finance Reviewer${next.assigned_reviewer ? ` (${next.assigned_reviewer})` : ""}.` });
    } catch (e) {
      onNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const fieldInput = (k: Field) => (
    <div className="field" key={k}>
      <label htmlFor={`f-${k}`}>{FIELD_LABEL[k]}</label>
      <input id={`f-${k}`} className={`input ${flags.has(k) ? "flag" : ""} ${k === "account_no" ? "mono" : ""}`}
             type={inputType(k)} step={k === "total" ? "0.01" : undefined} list={k === "vendor_name" ? "vendor-options" : undefined}
             value={fields[k]} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} />
    </div>
  );

  return (
    <section className="card panel" style={blocking.length ? { borderColor: "var(--amber-100)" } : undefined}>
      <div className="panel-head">
        <div>
          <h2>{doc.status === "DRAFT" ? "Draf voucher" : "Perbaiki data"}</h2>
          <p>Periksa data hasil bacaan AI untuk tiap bukti, lalu kirim ke Finance Reviewer. Reviewer hanya menyetujui atau mengembalikan.</p>
        </div>
      </div>

      {doc.files.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Bukti">
          {doc.files.map((f) => (
            <button key={f.position} role="tab" aria-selected={f.position === file.position} className={f.position === file.position ? "active" : ""}
                    disabled={busy} title={f.original_filename}
                    onClick={() => { if (!dirty || confirm("Perubahan pada bukti ini belum disimpan. Pindah bukti?")) onPos(f.position); }}>
              Bukti {f.position}
            </button>
          ))}
        </div>
      )}
      <small className="muted">{file.original_filename} · {file.page_count} hal.</small>

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
                <td style={{ width: 130 }}><input className="input num" type="number" value={l.subtotal} onChange={(e) => setLine(i, "subtotal", e.target.value)} aria-label={`Subtotal ${i + 1}`} /></td>
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

      {!reimburse && (
        <>
          <div className="section-title">Data pembayaran</div>
          <div className="grid-2">{PAYMENT_FIELDS.map(fieldInput)}</div>
          <small className="muted">Rekening tidak dicetak di voucher, tetapi tetap dicek sistem terhadap data referensi vendor.</small>
          {doc.account_check && <AccountCheckBox check={doc.account_check} />}
        </>
      )}

      <TaxPanel key={`${file.position}-${JSON.stringify(file.data?.tax ?? null)}`} doc={doc} file={file} lines={lines}
                total={fields.total} disabled={busy || dataDirty} onDirty={setTaxDirty} onChange={onChange} onNotice={onNotice} />
      {doc.tax_summary && <TaxSummaryBox summary={doc.tax_summary} multi={doc.files.length > 1} />}

      <div className="decision">
        {dataDirty && <button className="btn" disabled={busy} onClick={() => { setFields(initial.fields); setLines(initial.lines); }}><Undo2 /> Batalkan</button>}
        <button className="btn" disabled={busy || !dataDirty} onClick={save}><Save /> Simpan bukti {file.position}</button>
        <SimulationButton docId={doc.id} disabled={busy || dirty} />
        <button className="btn primary" onClick={submit} disabled={busy || dirty || blocking.length > 0}
                title={dirty ? "Simpan perubahan (data atau pajak) dulu" : blocking.length ? "Bereskan kendala dulu" : undefined}>
          <Send /> Kirim ke reviewer
        </button>
      </div>
    </section>
  );
}

const VAT_LINE = /\b(ppn|vat|pajak pertambahan|pb1|pajak restoran)\b/i;

/** DPP otomatis, sama dengan backend: jumlah rincian tanpa baris PPN; bila tidak ada rincian, total invoice. */
function autoBase(lines: Line[], total: string): number | null {
  const base = lines.filter((l) => l.subtotal !== "" && !VAT_LINE.test(l.description))
    .reduce((s, l) => s + Number(l.subtotal), 0);
  return base > 0 ? base : total !== "" ? Number(total) : null;
}

const pct = (v: string | number) => `${Number(v).toLocaleString("id-ID", { maximumFractionDigits: 3 })}%`;

/** Pajak per invoice (Tahap 4): PIC memilih jenis pajak; AI hanya menyarankan; tarif sesuai NPWP vendor. */
function TaxPanel({ doc, file, lines, total, disabled, onDirty, onChange, onNotice }: {
  doc: DocumentDetail; file: DocumentDetail["files"][number]; lines: Line[]; total: string; disabled: boolean;
  onDirty: (d: boolean) => void; onChange: (d: DocumentDetail, n?: Notice) => void; onNotice: (n: Notice) => void;
}) {
  const rates = useApi(() => api.get<TaxRate[]>("/tax-rates"), []);
  const current = file.data?.tax ?? null;
  const suggestion = file.data?.tax_suggestion ?? null;
  const known = file.data?.npwp_known;
  const [code, setCode] = useState(current?.code ?? "NONE");
  const [npwp, setNpwp] = useState(current?.npwp ?? known !== false);
  const [manual, setManual] = useState(current ? !current.base_auto : false);
  const [base, setBase] = useState(current && !current.base_auto ? plainNumber(current.base) : "");
  const [busy, setBusy] = useState(false);

  const dirty = code !== (current?.code ?? "NONE") || npwp !== (current?.npwp ?? known !== false)
    || manual !== (current ? !current.base_auto : false) || (manual && base !== plainNumber(current?.base ?? null));
  useEffect(() => { onDirty(dirty); }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onDirty(false), []); // eslint-disable-line react-hooks/exhaustive-deps

  const list = (rates.data ?? []).filter((r) => r.is_active || r.code === code);
  const rate = list.find((r) => r.code === code);
  const ratePct = rate ? Number(npwp ? rate.rate_npwp : rate.rate_no_npwp) : 0;
  const dpp = manual ? (base === "" ? null : Number(base)) : autoBase(lines, total);
  const cut = dpp && ratePct ? Math.round((dpp * ratePct) / 100) : 0;
  const gross = total === "" ? null : Number(total);

  async function apply() {
    setBusy(true);
    try {
      const next = await api.put<DocumentDetail>(`/documents/${doc.id}/files/${file.position}/tax`,
                                                 { code, npwp, base: manual && base !== "" ? base : null });
      onChange(next, { kind: "ok", text: `Pajak bukti ${file.position} diterapkan. Cek simulasi voucher sebelum dikirim.` });
    } catch (e) {
      onNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="tax-panel">
      <div className="section-title">Pajak (potongan PPh)</div>
      {suggestion && (
        <p className="tax-hint">
          <span className="chip gray">{suggestion.source === "ai" ? "Saran AI" : "Saran sistem"}</span>{" "}
          <b>{suggestion.name}</b> · {suggestion.reason}. Keputusan tetap di Anda.
        </p>
      )}
      <div className="grid-2">
        <div className="field">
          <label htmlFor="tax-code">Jenis pajak</label>
          <select id="tax-code" className="input" value={code} disabled={disabled || busy} onChange={(e) => setCode(e.target.value)}>
            {list.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
          </select>
          {rate?.description && <small>{rate.description}</small>}
        </div>
        <div className="field">
          <label htmlFor="tax-npwp">NPWP vendor</label>
          <select id="tax-npwp" className="input" value={npwp ? "1" : "0"} disabled={disabled || busy || code === "NONE"}
                  onChange={(e) => setNpwp(e.target.value === "1")}>
            <option value="1">Punya NPWP</option>
            <option value="0">Tidak punya NPWP</option>
          </select>
          <small>{known == null ? "Vendor belum terdaftar di data referensi; pastikan NPWP-nya."
            : known ? "Sesuai data referensi vendor (ada NPWP)." : "Data referensi vendor: tanpa NPWP."}</small>
        </div>
      </div>
      {code !== "NONE" && (
        <div className="grid-2">
          <div className="field">
            <label htmlFor="tax-base">Dasar pengenaan pajak (DPP)</label>
            <input id="tax-base" className="input num" type="number" disabled={disabled || busy || !manual}
                   value={manual ? base : dpp ?? ""} onChange={(e) => setBase(e.target.value)} />
            <label className="toggle" style={{ marginTop: 4 }}>
              <input type="checkbox" checked={!manual} disabled={disabled || busy}
                     onChange={(e) => { setManual(!e.target.checked); setBase(dpp != null ? String(dpp) : ""); }} />
              <span>Otomatis dari rincian (tanpa baris PPN)</span>
            </label>
          </div>
          <div className="field">
            <label>Potongan</label>
            <div className="tax-calc num">
              {pct(ratePct)} × {rupiah(dpp)} = <b>{rupiah(cut)}</b>
              {gross != null && <div className="muted">Dibayarkan untuk bukti ini: <b>{rupiah(gross - cut)}</b></div>}
            </div>
            {rate?.needs_confirmation && <small className="tax-warn">Tarif awal memakai aturan umum; perlu dikonfirmasi konsultan pajak.</small>}
          </div>
        </div>
      )}
      {dirty && (
        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn" disabled={busy} onClick={() => {
            setCode(current?.code ?? "NONE"); setNpwp(current?.npwp ?? known !== false);
            setManual(current ? !current.base_auto : false); setBase(current && !current.base_auto ? plainNumber(current.base) : "");
          }}><Undo2 /> Batalkan</button>
          <button className="btn primary" disabled={busy || disabled || (manual && base === "")} onClick={apply}>Terapkan pajak</button>
        </div>
      )}
    </div>
  );
}

/** Total tagihan, potongan pajak per invoice, dan nilai bersih yang dibayarkan voucher. */
function TaxSummaryBox({ summary, multi }: { summary: TaxSummary; multi: boolean }) {
  if (!summary.lines.length) {
    return <p className="muted" style={{ margin: 0 }}>Tanpa potongan pajak. Voucher membayar <b className="num">{rupiah(summary.net)}</b>.</p>;
  }
  return (
    <dl className="meta tax-summary">
      <dt>Jumlah tagihan</dt><dd className="num">{rupiah(summary.gross)}</dd>
      {summary.lines.map((t, i) => (
        <Fragment key={i}>
          <dt>Potongan {t.name} {pct(t.rate)}{t.npwp ? "" : " (tanpa NPWP)"}{multi && t.invoice_no ? ` · ${t.invoice_no}` : ""}</dt>
          <dd className="num">−{rupiah(t.amount)} <span className="muted">dari DPP {rupiah(t.base)}</span></dd>
        </Fragment>
      ))}
      <dt><b>Dibayarkan</b></dt><dd className="num"><b>{rupiah(summary.net)}</b></dd>
    </dl>
  );
}

/** Simulasi Voucher Pengeluaran (bertanda SIMULASI, lengkap dengan lampiran) sebelum disetujui.
 *  Bisa dibesarkan ke layar penuh, dibuka di tab baru, atau diunduh. */
function SimulationButton({ docId, disabled }: { docId: string; disabled?: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);
  const path = `/documents/${docId}/voucher-preview?t=${open}`;

  async function openInTab(download: boolean) {
    const win = download ? null : window.open("", "_blank");  // dibuka saat diklik supaya tidak diblokir browser
    setBusy(true);
    try {
      const url = URL.createObjectURL(await api.blob(path));
      if (download) {
        Object.assign(document.createElement("a"), { href: url, download: "simulasi-voucher.pdf" }).click();
      } else if (win) win.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      win?.close();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="btn" disabled={disabled} onClick={() => { setFull(false); setOpen(Date.now()); }}><Eye /> Lihat simulasi voucher</button>
      {open && (
        <Modal title="Simulasi voucher" onClose={() => setOpen(null)} wide full={full}>
          <div className="sim-toolbar">
            <span className="muted">Bertanda SIMULASI · nomor voucher dan tanda tangan elektronik muncul setelah disetujui</span>
            <div className="actions">
              <button className="btn sm" onClick={() => setFull(!full)}>
                {full ? <><Minimize2 /> Perkecil</> : <><Maximize2 /> Layar penuh</>}
              </button>
              <button className="btn sm" disabled={busy} onClick={() => openInTab(false)}><ExternalLink /> Buka di tab baru</button>
              <button className="btn sm" disabled={busy} onClick={() => openInTab(true)}><Download /> Unduh PDF</button>
            </div>
          </div>
          <div className="sim-body">
            <PdfFrame path={path} title="Simulasi voucher" />
          </div>
        </Modal>
      )}
    </>
  );
}

/** Keputusan Finance Reviewer: Setujui atau Kembalikan ke PIC; reviewer tidak mengedit data (feedback owner). */
function ReviewDecision({ doc, onChange, onNotice }: {
  doc: DocumentDetail; onChange: (d: DocumentDetail, n?: Notice) => void; onNotice: (n: Notice) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState(false);
  // Rekening yang belum terverifikasi wajib dicek manual dan dikonfirmasi sebelum menyetujui
  const [accountConfirmed, setAccountConfirmed] = useState(false);
  const [accountNote, setAccountNote] = useState("");
  const account = doc.account_check;
  const needsConfirm = account?.state === "UNVERIFIED";
  const accountKey = JSON.stringify(account ?? null);
  useEffect(() => { setAccountConfirmed(false); }, [accountKey]);

  async function approve() {
    setBusy(true);
    try {
      const next = await api.post<DocumentDetail>(`/documents/${doc.id}/approve`,
                                                  { account_confirmed: accountConfirmed, account_note: accountNote.trim() || null });
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

  return (
    <section className="card panel">
      <div className="panel-head">
        <div>
          <h2>Keputusan reviewer</h2>
          <p>Ada yang salah, termasuk salah ketik kecil? Kembalikan ke PIC dengan alasan yang jelas.</p>
        </div>
      </div>
      {needsConfirm && (
        <div className="account-confirm">
          <label className="toggle" style={{ alignItems: "flex-start" }}>
            <input type="checkbox" checked={accountConfirmed} onChange={(e) => setAccountConfirmed(e.target.checked)} style={{ marginTop: 3 }} />
            <span>Saya sudah mencocokkan rekening <b className="mono">{doc.extraction?.account_no || "-"}</b> dengan sumber tepercaya
              (mis. konfirmasi langsung ke vendor), bukan hanya dari dokumen atau isian PIC.</span>
          </label>
          <input className="input" placeholder="Cara pengecekan (opsional), mis. telepon bagian keuangan vendor" value={accountNote}
                 onChange={(e) => setAccountNote(e.target.value)} maxLength={500} aria-label="Catatan pengecekan rekening" />
        </div>
      )}
      <div className="decision">
        <button className="btn danger" disabled={busy} onClick={() => setReturning(true)}>Kembalikan ke PIC</button>
        <button className="btn success" onClick={approve}
                disabled={busy || doc.issues.length > 0 || account?.state === "MISMATCH" || (needsConfirm && !accountConfirmed)}
                title={doc.issues.length ? "Masih ada kendala" : needsConfirm && !accountConfirmed ? "Konfirmasi pengecekan rekening dulu" : undefined}>
          <CheckCircle2 /> Setujui
        </button>
      </div>

      {returning && (
        <ReasonModal title="Kembalikan ke PIC" label="Alasan (wajib, akan dibaca PIC)"
                     placeholder="mis. Total bukti 2 seharusnya 1.250.000, mohon diperbaiki."
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

/** Saran nama vendor dari data referensi klien untuk kolom nama vendor (datalist). */
function VendorOptions({ clientId }: { clientId: string }) {
  const vendors = useApi(() => api.get<Vendor[]>("/vendors", { client_id: clientId }), [clientId]);
  return <datalist id="vendor-options">{vendors.data?.map((v) => <option key={v.id} value={v.name} />)}</datalist>;
}

const KIND_TITLE = { PENGAJU: "Diajukan oleh", PENYETUJU: "Disetujui oleh" } as const;

/** Penanda tangan yang akan dicetak di voucher; PIC/Intake bisa mengubah sebelum voucher terbit. */
function SignersPanel({ doc, onChange }: { doc: DocumentDetail; onChange: (d: DocumentDetail) => void }) {
  const { has } = useAuth();
  const [editing, setEditing] = useState(false);
  const [ids, setIds] = useState<string[]>([]);
  const [initial, setInitial] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const currentSubmitter = doc.signers.find((s) => s.kind === "PENGAJU")?.name ?? doc.on_behalf_of ?? doc.uploaded_by;
  const [submitterName, setSubmitterName] = useState(currentSubmitter);
  const locked = doc.status === "AMIGA_REVIEWED" || doc.status === "SENT_TO_CLIENT" || doc.status === "CANCELLED";
  const canEdit = has("PIC_KLIEN", "INTAKE_SUPPORT") && !locked;

  async function open() {
    // Pilihan awal = penanda tangan dokumen saat ini (dicocokkan dari nama + jabatan)
    const list = await api.get<Signatory[]>("/signatories", { client_id: doc.client.id });
    // Urutan kotak "Disetujui oleh" saat ini, dicocokkan dari nama + jabatan
    setInitial(doc.signers.filter((x) => x.kind === "PENYETUJU")
      .map((x) => list.find((s) => s.full_name === x.name && s.position === x.position)?.id)
      .filter((id): id is string => Boolean(id)));
    setSubmitterName(currentSubmitter);
    setEditing(true);
  }

  async function save() {
    setError(null);
    try {
      onChange(await api.put<DocumentDetail>(`/documents/${doc.id}/signers`, {
        signatory_ids: ids,
        ...(submitterName.trim() !== currentSubmitter ? { submitter_name: submitterName.trim() } : {}),
      }));
      setEditing(false);
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <section className="card panel">
      <div className="panel-head">
        <div><h2>Penanda tangan voucher</h2><p>{doc.status === "CANCELLED" ? "Pengajuan dibatalkan." : locked ? "Sudah tercetak di voucher." : "Dicetak di kotak tanda tangan voucher."}</p></div>
        {canEdit && !editing && <button className="btn sm" onClick={open}>Ubah</button>}
      </div>
      {editing && initial ? (
        <>
          {error && <Alert>{error}</Alert>}
          <div className="field" style={{ maxWidth: 420 }}>
            <label htmlFor="edit-submitter">Nama &quot;Diajukan oleh&quot;</label>
            <input id="edit-submitter" className="input" maxLength={200} value={submitterName}
                   onChange={(e) => setSubmitterName(e.target.value)} />
            <small>Boleh nama karyawan lain. Kosongkan untuk kembali ke PIC pengaju.</small>
          </div>
          <SignerPicker clientId={doc.client.id} clientName={doc.client.name} initial={initial} onChange={setIds}
                        submitter={submitterName.trim() || currentSubmitter} />
          <div className="actions" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={() => setEditing(false)}>Batal</button>
            <button className="btn primary" onClick={save}>Simpan</button>
          </div>
        </>
      ) : !doc.signers.length ? (
        <p className="muted" style={{ margin: 0 }}>Belum dipilih. Kotak tanda tangan klien dicetak kosong untuk diisi manual.</p>
      ) : (
        <dl className="meta">
          {doc.signers.map((s, i) => (
            <Fragment key={i}><dt>{KIND_TITLE[s.kind]}</dt><dd><b>{s.name}</b> <span className="muted">· {s.position}</span></dd></Fragment>
          ))}
        </dl>
      )}
    </section>
  );
}

/** Buka foto asli (sebelum diubah ke PDF) di tab baru; file butuh token, jadi diunduh sebagai blob. */
function OriginalLink({ docId, position }: { docId: string; position: number }) {
  const [error, setError] = useState(false);
  async function open() {
    const win = window.open("", "_blank");  // dibuka langsung saat diklik supaya tidak diblokir browser
    try {
      const blob = await api.blob(`/documents/${docId}/files/${position}/original`);
      const url = URL.createObjectURL(blob);
      if (win) win.location.href = url; else window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      win?.close();
      setError(true);
    }
  }
  return (
    <button type="button" className="btn ghost sm" onClick={open} title="Foto yang diunggah, sebelum diubah menjadi PDF">
      {error ? "Foto asli tidak tersedia" : "Lihat foto asli"}
    </button>
  );
}
