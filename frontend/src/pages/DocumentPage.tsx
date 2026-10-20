import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Ban, CheckCircle2, CloudOff, Download, Equal, ExternalLink, Eye, FileClock, Maximize2, Minimize2, PenLine, Plus, Receipt, RotateCcw,
  Save, Send, ShieldCheck, Trash2, Undo2, UserPlus,
} from "lucide-react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { AiProcessingCard, AiResultCard, AiScanOverlay } from "../components/AiProcessing";
import { AccountCheckBox, ClassificationPanel } from "../components/DocumentPreview";
import { ReassignModal } from "../components/ReassignModal";
import { SignerPicker } from "../components/SignerPicker";
import { Anchor, SectionNav, jumpTo, type NavSection } from "../components/SectionNav";
import { TaxPanel, TaxSummaryBox } from "../components/TaxPanel";
import { VendorModal, VerifyVendorModal } from "../components/VendorForm";
import { Alert, Loading, Modal, PdfFrame, StatusBadge, useApi } from "../components/ui";
import { FIELD_LABEL, ISSUE_LABEL, lineSubtotal, plainNumber, rupiah, tanggal, waktu } from "../format";
import type { DocumentDetail, Extraction, FileData, Issue, Payee, Signatory, Vendor } from "../types";

type DocumentFile = DocumentDetail["files"][number];

const HEADER_FIELDS = ["vendor_name", "invoice_no", "invoice_date", "total"] as const;
const PAYMENT_FIELDS = ["bank_name", "account_no", "account_name"] as const;
const ALL_FIELDS = [...HEADER_FIELDS, ...PAYMENT_FIELDS];
type Field = (typeof ALL_FIELDS)[number];
type Fields = Record<Field, string>;
interface Line {
  description: string; qty: string; unit_price: string; subtotal: string;
  // Pengaturan pajak baris dari panel pajak; ikut dikirim ulang saat data disimpan
  pph?: string | null; vat?: boolean | null; kind?: "item" | "vat" | null;
}

const toLines = (ex: Extraction | null): Line[] =>
  (ex?.line_items ?? []).map((l) => ({
    description: l.description ?? "", qty: plainNumber(l.qty), unit_price: plainNumber(l.unit_price), subtotal: plainNumber(l.subtotal),
  }));

/** Kendala yang harus dibereskan PIC sebelum draf boleh dikirim (sama dengan BLOCKING di backend). */
const BLOCKING = new Set(["MISSING_EVIDENCE", "CALCULATION_DISCREPANCY", "NOT_AN_INVOICE", "EXTRACTION_FAILED", "ACCOUNT_MISMATCH"]);
/** Peringatan yang cukup dikonfirmasi PIC beserta alasannya (ACKNOWLEDGEABLE di backend). */
const NEEDS_ACK = "VENDOR_MISMATCH";

/** Subtotal yang berlaku: qty × harga bila keduanya terisi (dihitung sistem), selain itu isian manual. */
const effectiveSubtotal = (l: Line) => lineSubtotal(l.qty, l.unit_price) ?? l.subtotal;

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
  // AI tidak membaca sebagian/semua bukti (dimatikan atau bermasalah): PIC mengisi manual, atau mencoba AI lagi
  const manual = d.ai_manual ?? null;
  const allManual = Boolean(manual) && manual!.files.length >= Math.max(d.files.length, 1);
  const canRetryAi = isPic && Boolean(manual) && d.ai_enabled !== false && (d.status === "DRAFT" || d.status === "EXCEPTION");
  const canDismissDup = isReviewer && d.status === "READY_FOR_REVIEW" && codes.has("POSSIBLE_DUPLICATE");
  const filePos = Math.min(pos, Math.max(d.files.length, 1));
  const hasVoucher = d.status === "AMIGA_REVIEWED" || d.status === "SENT_TO_CLIENT";
  // Pengaju boleh membatalkan selama voucher belum terbit (setelah AI selesai membaca)
  const canCancel = isPic && (d.status === "DRAFT" || d.status === "EXCEPTION" || d.status === "READY_FOR_REVIEW");

  const shownIssues = displayIssues(d);
  const showAiResult = !processing && !resultClosed && Boolean(d.extraction) && !allManual
    && (fresh || d.status === "DRAFT" || d.status === "READY_FOR_REVIEW" || d.status === "EXCEPTION");
  const showClassification = Boolean(d.classification) && !(d.classification!.doc_class === "INVOICE" && !d.classification!.decision);
  const sections = navSections(d, { filePos, canEdit, canReview, showAiResult, showClassification, manual: Boolean(manual) && !processing });
  // Kendala di kartu hasil AI bisa diklik: langsung ke bagian yang perlu diperbaiki
  const jumpToIssue = (code: string) => {
    const target = issueSection(d, code, canEdit);
    if (sections.some((x) => x.id === target)) jumpTo(target);
  };

  const update = (next: DocumentDetail, message?: typeof notice) => {
    doc.setData(next);
    setNotice(message ?? null);
  };

  async function reprocess() {
    if (manual && !confirm(`AI akan membaca ulang ${manual.files.length > 1 ? `${manual.files.length} bukti` : "bukti"} yang belum terbaca. `
      + "Isian manual Anda pada bukti itu akan diganti hasil baca AI. Lanjutkan?")) return;
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

        <div className="review-col">
          <SectionNav sections={sections} />
          <div className="review-body">
          <Anchor id="info">
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
              {allManual
                ? <><dt>Data invoice</dt><dd>Diisi manual oleh PIC <span className="chip warn">AI tidak membaca</span></dd></>
                : d.extraction?.duration_ms != null && <><dt>Dibaca AI</dt><dd>{(d.extraction.duration_ms / 1000).toFixed(1)} detik · {waktu(d.extraction.extracted_at)}</dd></>}
              {d.voucher && <><dt>Voucher</dt><dd className="mono">{d.voucher.voucher_no}</dd></>}
            </dl>
          </section>
          </Anchor>

          {manual && !processing && (
            <Anchor id="manual">
              <ManualEntryCard doc={d} canEdit={canEdit} canRetry={canRetryAi} onRetry={reprocess} />
            </Anchor>
          )}
          {processing && <AiProcessingCard doc={d} />}
          {showAiResult && (
            <Anchor id="ai"><AiResultCard doc={d} onClose={() => setResultClosed(true)} onJump={jumpToIssue} /></Anchor>
          )}
          {showClassification && (
            <Anchor id="klasifikasi">
              <ClassificationPanel doc={d} canDecide={isReviewer && d.status === "READY_FOR_REVIEW"}
                                   onDecided={(n, text) => update(n, { kind: "ok", text })} />
            </Anchor>
          )}

          {d.issues.length > 0 && (
            <Anchor id="kendala">
            <section className="card panel">
              <div className="section-title">Kendala ({shownIssues.length})</div>
              <div className="issues">
                {shownIssues.map((i, n) => (
                  <div className="issue" key={n}>
                    <b>{ISSUE_LABEL[i.code]} {i.field && <>· {FIELD_LABEL[i.field] ?? i.field}</>}</b>
                    <span>{i.message}</span>
                    <code>{i.code}</code>
                  </div>
                ))}
              </div>
              {(canReprocess || canDismissDup || (canEdit && codes.has(NEEDS_ACK))) && (
                <div className="actions">
                  {canReprocess && <button className="btn primary" onClick={reprocess}><RotateCcw /> Proses ulang</button>}
                  {canDismissDup && <DismissDuplicate id={id} onDone={(n) => update(n, { kind: "ok", text: "Ditandai bukan duplikat." })} />}
                  {canEdit && codes.has(NEEDS_ACK) && (
                    <AcknowledgePayees doc={d} onDone={(n) => update(n, { kind: "ok", text: "Perbedaan vendor/rekening dikonfirmasi. Alasan Anda tampil untuk Finance Reviewer." })} />
                  )}
                </div>
              )}
            </section>
            </Anchor>
          )}

          <Anchor id="penanda">
            <SignersPanel doc={d} onChange={(n) => update(n, { kind: "ok", text: "Penanda tangan voucher diperbarui." })} />
          </Anchor>

          {canEdit
            ? <DraftEditor doc={d} pos={filePos} onPos={setPos} onChange={update} onNotice={setNotice} />
            : d.extraction && <Anchor id="data"><ReadOnlyData doc={d} onChange={update} /></Anchor>}
          {!canEdit && d.extraction && d.status !== "CANCELLED" && !hasVoucher && <SimulationButton docId={d.id} />}
          {canReview && <Anchor id="keputusan"><ReviewDecision doc={d} onChange={update} onNotice={setNotice} /></Anchor>}
          </div>
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

/** Kendala untuk ditampilkan. Saat isi manual, data kosong diringkas jadi satu baris: semuanya memang belum diisi,
 *  bukan "tidak ditemukan di invoice". */
function displayIssues(d: DocumentDetail): Issue[] {
  const missing = d.issues.filter((i) => i.code === "MISSING_EVIDENCE");
  if (!d.ai_manual || missing.length < 2) return d.issues;
  const names = missing.map((i) => (i.field ? FIELD_LABEL[i.field] ?? i.field : "-").toLowerCase());
  return [{ ...missing[0], field: null, message: `${missing.length} data belum diisi: ${names.join(", ")}. Isi dari file bukti, lalu simpan.` },
          ...d.issues.filter((i) => i.code !== "MISSING_EVIDENCE")];
}

const isEmpty = (v: string | null | undefined) => v == null || String(v).trim() === "";

/** Daftar bagian panel kanan untuk navigasi cepat, beserta statusnya. Dihitung dari data yang sudah disimpan
 *  dan kendala hasil verifikasi sistem, jadi selalu sejalan dengan pemeriksaan di backend. */
function navSections(d: DocumentDetail, o: { filePos: number; canEdit: boolean; canReview: boolean;
  showAiResult: boolean; showClassification: boolean; manual: boolean }): NavSection[] {
  const blocking = d.issues.filter((i) => BLOCKING.has(i.code));
  const pendingAck = d.issues.some((i) => i.code === NEEDS_ACK);
  const has = (code: string) => d.issues.some((i) => i.code === code);
  const flaggedIn = (fields: readonly string[]) => blocking.some((i) => i.field && fields.includes(i.field));
  const list: NavSection[] = [{ id: "info", label: "Info dokumen", state: "info" }];
  if (o.manual) {
    const missing = d.issues.some((i) => i.code === "MISSING_EVIDENCE");
    list.push({ id: "manual", label: "Isi manual (AI tidak membaca)", state: o.canEdit && missing ? "fix" : "info",
                note: o.canEdit && missing ? "lengkapi data dari file bukti" : undefined });
  }
  if (o.showAiResult) list.push({ id: "ai", label: "Hasil AI", state: d.issues.length ? "fix" : "ok" });
  if (o.showClassification) {
    list.push({ id: "klasifikasi", label: "Klasifikasi dokumen",
                state: has("NOT_AN_INVOICE") ? "block" : has("RECEIPT_NOT_INVOICE") || has("NEEDS_MANUAL_REVIEW") ? "fix" : "ok" });
  }
  if (d.issues.length) {
    list.push({ id: "kendala", label: `Kendala (${displayIssues(d).length})`, state: blocking.length ? "block" : "fix",
                note: blocking.length ? `${blocking.length} wajib dibereskan` : pendingAck && o.canEdit ? "perlu konfirmasi PIC" : "diputuskan reviewer" });
  }
  list.push({ id: "penanda", label: "Penanda tangan", state: "info", note: d.signers.length ? undefined : "belum dipilih" });
  if (o.canEdit) {
    const file = d.files.find((f) => f.position === o.filePos) ?? d.files[0];
    const data = file?.data;
    const tag = d.files.length > 1 ? ` (bukti ${file.position})` : "";
    const fieldState = (fields: readonly Field[], label: string, id: string) => {
      const empty = fields.filter((k) => isEmpty(data?.[k] ?? null)).length;
      list.push({ id, label: label + tag, state: flaggedIn(fields) ? "block" : empty ? "fix" : "ok",
                  note: empty ? `${empty} kolom kosong` : flaggedIn(fields) ? "perlu diperbaiki" : undefined });
    };
    fieldState(HEADER_FIELDS, "Informasi utama", "data");
    const lines = data?.line_items ?? [];
    list.push({ id: "rincian", label: "Rincian barang/jasa" + tag,
                state: has("CALCULATION_DISCREPANCY") ? "block" : !lines.length ? "fix" : "ok",
                note: has("CALCULATION_DISCREPANCY") ? "total tidak cocok" : !lines.length ? "belum ada baris" : `${lines.length} baris` });
    if (d.request_type !== "Voucher Pengeluaran Reimburse") {
      const empty = PAYMENT_FIELDS.filter((k) => isEmpty(data?.[k] ?? null)).length;
      const mismatch = d.issues.some((i) => i.code === "ACCOUNT_MISMATCH");
      list.push({ id: "pembayaran", label: "Data pembayaran" + tag, state: mismatch ? "block" : empty ? "fix" : "ok",
                  note: mismatch ? "rekening tidak cocok" : empty ? `${empty} kolom kosong`
                    : d.account_check?.state === "UNVERIFIED" ? "rekening belum terverifikasi" : undefined });
    }
    const noTax = d.files.filter((f) => !f.data?.tax).map((f) => f.position);
    const vatWarn = (d.tax_summary?.vat ?? []).some((v) => v.warning);
    list.push({ id: "pajak", label: "Pajak", state: noTax.length ? "fix" : vatWarn ? "fix" : "ok",
                note: noTax.length ? `belum dipilih: bukti ${noTax.join(", ")}` : vatWarn ? "cek PPN" : undefined });
    const waiting = blocking.length || noTax.length || pendingAck;
    list.push({ id: "kirim", label: "Kirim ke reviewer", state: waiting ? "info" : "ok",
                note: waiting ? "setelah semua lengkap" : "siap dikirim" });
  } else if (d.extraction) {
    list.push({ id: "data", label: "Data invoice & pajak", state: "info" });
    if (o.canReview) {
      list.push({ id: "keputusan", label: "Keputusan reviewer", state: d.account_check?.state === "UNVERIFIED" ? "fix" : "info",
                  note: d.account_check?.state === "UNVERIFIED" ? "cek rekening dulu" : undefined });
    }
  }
  return list;
}

/** Bagian tujuan untuk satu pemeriksaan di kartu hasil AI. */
function issueSection(d: DocumentDetail, code: string, canEdit: boolean): string {
  if (!canEdit) return code === "ACCOUNT" ? "keputusan" : d.issues.length ? "kendala" : "data";
  const missing = d.issues.find((i) => i.code === "MISSING_EVIDENCE" && i.field && (PAYMENT_FIELDS as readonly string[]).includes(i.field));
  return {
    MISSING_EVIDENCE: missing && !d.issues.some((i) => i.code === "MISSING_EVIDENCE" && i.field && (HEADER_FIELDS as readonly string[]).includes(i.field))
      ? "pembayaran" : "data",
    CALCULATION_DISCREPANCY: "rincian",
    VENDOR_MISMATCH: "kendala",
    ACCOUNT: "pembayaran",
    NOT_AN_INVOICE: "klasifikasi",
  }[code] ?? "kendala";
}

function ReadOnlyData({ doc, onChange }: { doc: DocumentDetail; onChange: (d: DocumentDetail, n?: Notice) => void }) {
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
      <LinesTable lines={doc.files.length === 1 && doc.files[0].data ? dataLines(doc.files[0].data) : toLines(ex)} total={ex.total}
                  pphNames={pphNames(doc)} />
      {doc.tax_summary && <TaxSummaryBox summary={doc.tax_summary} multi={doc.files.length > 1} />}
      <PaymentChecks doc={doc} onChange={onChange} />
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

/** Nama jenis PPh yang dipakai per baris (dari salinan tarif saat diterapkan). */
const pphNames = (doc: DocumentDetail): Record<string, string> =>
  Object.fromEntries(doc.files.flatMap((f) => (f.data?.tax?.groups ?? []).map((g) => [g.code, g.name])));

function LinesTable({ lines, total, pphNames = {} }: { lines: Line[]; total: string | null; pphNames?: Record<string, string> }) {
  const sum = lines.reduce((s, l) => s + (Number(l.subtotal) || 0), 0);
  const match = total !== null && Math.abs(sum - Number(total)) < 0.005;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table compact">
        <thead><tr><th>#</th><th>Uraian</th><th className="right">Qty</th><th className="right">Harga</th><th className="right">Subtotal</th></tr></thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>{l.description || "-"}
                {l.kind === "vat" && <> <span className="chip gray">baris PPN</span></>}
                {l.vat === false && <> <span className="chip gray">tidak kena PPN</span></>}
                {l.pph && pphNames[l.pph] && <> <span className="chip">{pphNames[l.pph]}</span></>}</td>
              <td className="right num">{l.qty || "-"}</td>
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
    ...(l.pph != null && { pph: l.pph }), ...(l.vat != null && { vat: l.vat }), ...(l.kind != null && { kind: l.kind }),
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
  const pendingAck = doc.issues.some((i) => i.code === NEEDS_ACK);
  // PIC wajib memilih pajak sendiri untuk setiap bukti sebelum dikirim (AI hanya menyarankan)
  const noTax = doc.files.filter((f) => !f.data?.tax).map((f) => f.position);
  const flags = flagged(blocking);
  // Qty atau harga diubah: subtotal ikut dihitung ulang (qty × harga) bila keduanya terisi
  const setLine = (i: number, k: keyof Line, v: string) => setLines((ls) => ls.map((l, n) => {
    if (n !== i) return l;
    const next = { ...l, [k]: v };
    return k === "qty" || k === "unit_price" ? { ...next, subtotal: lineSubtotal(next.qty, next.unit_price) ?? next.subtotal } : next;
  }));
  const sum = lines.reduce((t, l) => t + (Number(effectiveSubtotal(l)) || 0), 0);

  async function save() {
    // Data lengkap satu invoice (backend mengganti data bukti ini dan mencatat field yang berubah)
    const data = {
      ...Object.fromEntries(ALL_FIELDS.map((k) => [k, fields[k].trim() || null])),
      line_items: lines.map((l) => ({
        description: l.description || null, qty: l.qty || null, unit_price: l.unit_price || null, subtotal: effectiveSubtotal(l) || null,
        pph: l.pph ?? null, vat: l.vat ?? null, kind: l.kind ?? null,
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
          <p>{doc.ai_manual ? "Isi atau periksa data tiap bukti sesuai file bukti" : "Periksa data hasil bacaan AI untuk tiap bukti"}, lalu kirim ke
            Finance Reviewer. Reviewer hanya menyetujui atau mengembalikan.</p>
        </div>
      </div>

      {doc.files.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Bukti">
          {doc.files.map((f) => (
            <button key={f.position} role="tab" aria-selected={f.position === file.position} className={f.position === file.position ? "active" : ""}
                    disabled={busy} title={f.original_filename}
                    onClick={() => { if (!dirty || confirm("Perubahan pada bukti ini belum disimpan. Pindah bukti?")) onPos(f.position); }}>
              Bukti {f.position}{f.data?.manual && <PenLine size={12} aria-label="diisi manual" />}
              {!f.data?.tax && <span className="tab-dot" title="Pajak belum dipilih" />}
            </button>
          ))}
        </div>
      )}
      <small className="muted">{file.original_filename} · {file.page_count} hal.
        {file.data?.manual && <> <span className="chip warn"><PenLine size={11} /> diisi manual: AI tidak membaca bukti ini</span></>}</small>

      <Anchor id="data">
        <div className="section-title">Informasi utama</div>
        <div className="grid-2">{HEADER_FIELDS.map(fieldInput)}</div>
      </Anchor>

      <Anchor id="rincian">
      <div className="section-title">Rincian barang/jasa</div>
      <div style={{ overflowX: "auto" }}>
        <table className="table compact">
          <thead><tr><th>#</th><th>Uraian</th><th>Qty</th><th>Harga satuan</th><th>Subtotal</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => {
              const auto = lineSubtotal(l.qty, l.unit_price);
              // Subtotal di invoice (hasil baca AI/isian lama) berbeda dengan qty × harga: tampilkan sebagai catatan
              const differs = auto !== null && l.subtotal !== "" && Math.abs(Number(l.subtotal) - Number(auto)) >= 0.005;
              return (
              <tr key={i}>
                <td>{i + 1}</td>
                <td><input className="input" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} aria-label={`Uraian ${i + 1}`} /></td>
                <td style={{ width: 70 }}><input className="input num" type="number" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} aria-label={`Qty ${i + 1}`} /></td>
                <td style={{ width: 120 }}><input className="input num" type="number" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} aria-label={`Harga ${i + 1}`} /></td>
                <td style={{ width: 140 }}>
                  {auto !== null ? (
                    <div className="auto-sub" title="Dihitung otomatis: qty × harga satuan. Kosongkan qty atau harga untuk mengisi subtotal manual.">
                      <input className="input num" readOnly tabIndex={-1} value={auto} aria-label={`Subtotal ${i + 1} (otomatis)`} />
                      <span className="chip gray">otomatis</span>
                      {differs && <small className="warn-text">di invoice {rupiah(l.subtotal)}</small>}
                    </div>
                  ) : (
                    <input className="input num" type="number" value={l.subtotal} onChange={(e) => setLine(i, "subtotal", e.target.value)} aria-label={`Subtotal ${i + 1}`} />
                  )}
                </td>
                <td><button className="btn ghost sm" onClick={() => setLines(lines.filter((_, n) => n !== i))} aria-label={`Hapus baris ${i + 1}`}><Trash2 /></button></td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="actions" style={{ justifyContent: "space-between" }}>
        <button className="btn sm" onClick={() => setLines([...lines, { description: "", qty: "", unit_price: "", subtotal: "" }])}><Plus /> Tambah baris</button>
        <SumCheck sum={sum} total={fields.total} onMatch={lines.length ? () => setFields({ ...fields, total: String(Math.round(sum * 100) / 100) }) : undefined} />
      </div>
      <small className="muted">Subtotal dihitung otomatis dari qty × harga satuan. Untuk harga borongan, kosongkan qty atau harga, lalu isi subtotalnya.</small>
      </Anchor>

      {!reimburse && (
        <Anchor id="pembayaran">
          <div className="section-title">Data pembayaran</div>
          <div className="grid-2">{PAYMENT_FIELDS.map(fieldInput)}</div>
          <small className="muted">Rekening tidak dicetak di voucher, tetapi tetap dicek sistem terhadap data referensi vendor.</small>
          <PaymentChecks doc={doc} file={file} editing onChange={onChange} disabled={busy || dataDirty} />
        </Anchor>
      )}

      <Anchor id="pajak">
      <TaxPanel key={`${file.position}-${JSON.stringify(file.data?.tax ?? null)}`} doc={doc} file={file} lines={lines}
                total={fields.total} disabled={busy || dataDirty} onDirty={setTaxDirty} onChange={onChange} onNotice={onNotice} />
      {noTax.length > 0
        ? <p className="muted" style={{ margin: 0 }}>Pajak belum dipilih untuk bukti {noTax.join(", ")}; total dibayarkan dihitung setelah dipilih.</p>
        : doc.tax_summary && <TaxSummaryBox summary={doc.tax_summary} multi={doc.files.length > 1} />}
      </Anchor>

      <div className="decision sec-anchor" id="sec-kirim">
        {dataDirty && <button className="btn" disabled={busy} onClick={() => { setFields(initial.fields); setLines(initial.lines); }}><Undo2 /> Batalkan</button>}
        <button className="btn" disabled={busy || !dataDirty} onClick={save}><Save /> Simpan bukti {file.position}</button>
        <SimulationButton docId={doc.id} disabled={busy || dirty} />
        <button className="btn primary" onClick={submit} disabled={busy || dirty || blocking.length > 0 || noTax.length > 0 || pendingAck}
                title={dirty ? "Simpan perubahan (data atau pajak) dulu" : blocking.length ? "Bereskan kendala dulu"
                  : noTax.length ? `Pilih pajak untuk bukti ${noTax.join(", ")}`
                  : pendingAck ? "Konfirmasi perbedaan vendor/rekening dulu (bagian Kendala)" : undefined}>
          <Send /> Kirim ke reviewer
        </button>
      </div>
    </section>
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
  // Konfirmasi mencakup semua rekening tujuan yang belum terverifikasi (voucher bisa berisi beberapa vendor)
  const unverified = (doc.payees ?? []).filter((p) => p.state === "UNVERIFIED").map((p) => p.account_no ?? "-");
  if (!unverified.length) unverified.push(doc.extraction?.account_no || "-");
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
            <span>Saya sudah mencocokkan rekening {unverified.length > 1 ? "berikut" : ""}{" "}
              {unverified.map((a, n) => <Fragment key={a}>{n > 0 && ", "}<b className="mono">{a}</b></Fragment>)} dengan sumber tepercaya
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

/** Jumlah rincian dibanding total invoice. `onMatch`: isi total dengan jumlah rincian (mis. invoice tanpa total
 *  tertulis atau data diisi manual); tetap harus disimpan PIC. */
function SumCheck({ sum, total, onMatch }: { sum: number; total: string; onMatch?: () => void }) {
  const match = total !== "" && Math.abs(sum - Number(total)) < 0.005;
  return (
    <span className="sum-check num">
      <span>Jumlah rincian <b>{rupiah(sum)}</b> · total {rupiah(total || null)}{" "}
        <span className={`chip ${match ? "ok" : "warn"}`}>{match ? "cocok" : "tidak cocok"}</span></span>
      {!match && onMatch && (
        <button type="button" className="btn sm" onClick={onMatch}
                title="Total invoice diisi sama dengan jumlah rincian. Pastikan sesuai dengan total di invoice, lalu simpan.">
          <Equal /> Samakan total dengan jumlah rincian
        </button>
      )}
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

/** Kartu mode isi manual: AI dimatikan atau bermasalah, jadi data invoice diisi PIC dari file bukti.
 *  Dokumen tetap draf yang bisa diproses seperti biasa, bukan dokumen rusak. */
function ManualEntryCard({ doc, canEdit, canRetry, onRetry }: {
  doc: DocumentDetail; canEdit: boolean; canRetry: boolean; onRetry: () => void;
}) {
  const m = doc.ai_manual!;
  const missing = doc.issues.some((i) => i.code === "MISSING_EVIDENCE");
  const off = m.status === "off";
  const Icon = off ? PenLine : CloudOff;
  if (!canEdit) {
    return (
      <Alert kind="info">
        Data {m.files.length > 1 || doc.files.length > 1 ? `bukti ${m.files.join(", ")}` : "invoice ini"} diisi manual oleh PIC
        karena AI {off ? "sedang dimatikan" : "tidak berhasil membacanya"}. Cocokkan datanya dengan file bukti di panel kiri.
      </Alert>
    );
  }
  return (
    <section className={`card manual-card ${missing ? "" : "done"}`} aria-live="polite">
      <div className="manual-head">
        <span className="manual-ic" aria-hidden="true"><Icon /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="ai-eyebrow">{off ? "Mode isi manual" : "AI sedang bermasalah"}</span>
          <h2>{missing ? "Isi data invoice secara manual" : "Data sudah diisi manual"}</h2>
        </div>
      </div>
      <p>{missing ? m.message : "Data bukti yang tidak terbaca AI sudah Anda lengkapi. Lanjutkan seperti biasa: pilih pajak, cek simulasi voucher, lalu kirim ke reviewer."}</p>
      {missing && (
        <ol className="manual-steps">
          <li>Buka file bukti di panel kiri{doc.files.length > 1 ? " (pilih tab bukti yang ditandai pensil)" : ""}.</li>
          <li>Isi informasi utama, rincian barang/jasa, dan data pembayaran, lalu simpan.</li>
          <li>Pilih pajak dan kirim ke reviewer seperti biasa.</li>
        </ol>
      )}
      {(missing || canRetry) && (
        <div className="actions">
          {missing && <button className="btn primary" onClick={() => jumpTo("data")}><PenLine /> Mulai isi data</button>}
          {canRetry && !off && <button className="btn" onClick={onRetry}><RotateCcw /> Coba baca ulang dengan AI</button>}
        </div>
      )}
    </section>
  );
}

/** PIC mengonfirmasi beberapa vendor/rekening dalam satu voucher beserta alasannya (peringatan, bukan kendala). */
function AcknowledgePayees({ doc, onDone }: { doc: DocumentDetail; onDone: (d: DocumentDetail) => void }) {
  const [open, setOpen] = useState(false);
  const payees = doc.payees ?? [];
  return (
    <>
      <button className="btn primary" onClick={() => setOpen(true)}><CheckCircle2 /> Konfirmasi perbedaan vendor/rekening</button>
      {open && (
        <ReasonModal title="Konfirmasi beberapa vendor/rekening" submitLabel="Konfirmasi"
                     label="Alasan (wajib; tercatat di riwayat dan tampil untuk Finance Reviewer, tidak dicetak di voucher)"
                     placeholder="mis. Dua vendor dalam satu proyek renovasi kantor; tagihan dibayar bersama."
                     intro={payees.length > 1 && (
                       <ul className="plain-list payee-mini">
                         {payees.map((p, n) => (
                           <li key={n}><b>{p.vendor_name ?? "Vendor tanpa nama"}</b> · <span className="mono">{p.bank_name ?? "-"} {p.account_no ?? "-"}</span>
                             <span className="muted"> · bukti {p.invoices.join(", ")} · {rupiah(p.net)}</span></li>
                         ))}
                       </ul>
                     )}
                     onClose={() => setOpen(false)}
                     onSubmit={async (reason) => {
                       const next = await api.post<DocumentDetail>(`/documents/${doc.id}/acknowledge`, { code: NEEDS_ACK, reason });
                       setOpen(false);
                       onDone(next);
                     }} />
      )}
    </>
  );
}

const PAYEE_STATE: Record<string, { label: string; tone: string }> = {
  VERIFIED: { label: "terverifikasi", tone: "ok" },
  MISMATCH: { label: "tidak cocok", tone: "bad" },
  UNVERIFIED: { label: "belum terverifikasi", tone: "warn" },
  MISSING: { label: "rekening kosong", tone: "gray" },
};

/** Pemeriksaan rekening tujuan: satu rekening = kotak status; beberapa rekening = tabel pembayaran per rekening.
 *  Pintasan: PIC mendaftarkan/memperbarui rekening vendor (hanya pencatatan, pengajuan tetap berjalan), Finance
 *  Reviewer memverifikasi rekening vendor (SoD tetap berlaku). */
function PaymentChecks({ doc, file, editing = false, disabled = false, onChange }: {
  doc: DocumentDetail; file?: DocumentFile; editing?: boolean; disabled?: boolean;
  onChange: (d: DocumentDetail, n?: Notice) => void;
}) {
  const { has } = useAuth();
  const [registering, setRegistering] = useState<{ payee: Payee; vendor: Vendor | null } | null>(null);
  const [verifying, setVerifying] = useState<Vendor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const payees = doc.payees ?? [];
  const ack = doc.acknowledgements?.[NEEDS_ACK];
  const canRegister = editing && has("PIC_KLIEN", "INTAKE_SUPPORT");
  const canVerify = !editing && has("FINANCE_REVIEWER") && doc.status === "READY_FOR_REVIEW";
  const refresh = async (text: string) => onChange(await api.get<DocumentDetail>(`/documents/${doc.id}`), { kind: "ok", text });
  const loadVendor = async (vendorId: string) => {
    setError(null);
    try { return await api.get<Vendor>(`/vendors/${vendorId}`); } catch (e) { setError((e as Error).message); return null; }
  };

  const actions = (p: Payee) => {
    if (canRegister && !p.vendor_id && p.vendor_name) {
      return <button className="btn sm" disabled={disabled} title={disabled ? "Simpan perubahan data dulu" : undefined}
                     onClick={() => setRegistering({ payee: p, vendor: null })}><UserPlus /> Daftarkan rekening vendor</button>;
    }
    if (canRegister && p.vendor_id && p.state === "UNVERIFIED" && p.reference_matches) {
      return <small className="muted">Rekening sudah tercatat di Data Referensi · menunggu verifikasi Finance Reviewer</small>;
    }
    if (canRegister && p.vendor_id && (p.state === "UNVERIFIED" || p.state === "MISMATCH")) {
      return <button className="btn sm" disabled={disabled} title={disabled ? "Simpan perubahan data dulu" : undefined}
                     onClick={async () => { const v = await loadVendor(p.vendor_id!); if (v) setRegistering({ payee: p, vendor: v }); }}>
        <PenLine /> Perbarui rekening vendor</button>;
    }
    if (canVerify && p.vendor_id && !p.vendor_verified) {
      return <button className="btn sm" onClick={async () => { const v = await loadVendor(p.vendor_id!); if (v) setVerifying(v); }}>
        <ShieldCheck /> Verifikasi rekening vendor ini</button>;
    }
    return null;
  };

  if (!doc.account_check || doc.account_check.state === "NOT_APPLICABLE") return null;
  const single = payees.length <= 1;
  const mine = file ? payees.find((p) => p.invoices.includes(file.position)) : undefined;
  return (
    <>
      {error && <Alert>{error}</Alert>}
      {single
        ? <AccountCheckBox check={doc.account_check} actions={payees[0] && actions(payees[0])} />
        : (
          <div className="payees">
            <div className="section-title" style={{ marginTop: 4 }}>Pembayaran per rekening ({payees.length})</div>
            <ul className="payee-list">
              {payees.map((p, n) => {
                const st = PAYEE_STATE[p.state] ?? { label: p.state, tone: "gray" };
                const act = actions(p);
                return (
                  <li key={n} className={mine === p ? "current" : undefined}>
                    <div className="payee-main">
                      <b>{p.vendor_name ?? "Vendor tanpa nama"}</b>
                      <span className="mono">{p.account_no ?? "-"}</span>
                      <small className="muted">{p.bank_name ?? "-"}{p.account_name && ` · a.n. ${p.account_name}`} · bukti {p.invoices.join(", ")}
                        {p.source === "PIC" && " · rekening diisi PIC"}</small>
                    </div>
                    <div className="payee-side">
                      <b className="num">{rupiah(p.net)}</b>
                      <span className={`chip ${st.tone}`} title={p.message}>{st.label}</span>
                    </div>
                    {act && <div className="payee-act">{act}</div>}
                  </li>
                );
              })}
            </ul>
            {doc.account_check.state === "MISMATCH" && <AccountCheckBox check={doc.account_check} />}
          </div>
        )}
      {ack && (
        <Alert kind="info">
          Beberapa vendor/rekening dalam satu voucher dikonfirmasi oleh <b>{ack.by}</b> ({waktu(ack.at)}): “{ack.reason}”
        </Alert>
      )}
      {registering && (
        <VendorModal vendor={registering.vendor} clientId={doc.client.id}
                     prefill={registering.vendor
                       ? { bank_name: registering.payee.bank_name, account_no: registering.payee.account_no, account_name: registering.payee.account_name }
                       : { name: registering.payee.vendor_name, bank_name: registering.payee.bank_name,
                           account_no: registering.payee.account_no, account_name: registering.payee.account_name }}
                     intro={<Alert kind="info">
                       Data diisi dari invoice. Ini hanya pencatatan ke Data Referensi untuk rekap: pengajuan voucher tetap berjalan seperti
                       biasa. Rekening baru dianggap terverifikasi setelah dicek Finance Reviewer.
                       {registering.vendor?.verified_at && " Mengubah data bank vendor yang sudah terverifikasi membuatnya perlu diverifikasi ulang."}
                     </Alert>}
                     onClose={() => setRegistering(null)}
                     onDone={async (v) => {
                       setRegistering(null);
                       await refresh(`Rekening ${v.name} tercatat di Data Referensi dan menunggu verifikasi Finance Reviewer.`);
                     }} />
      )}
      {verifying && (
        <VerifyVendorModal vendor={verifying} onClose={() => setVerifying(null)}
                           onDone={async () => { setVerifying(null); await refresh(`Rekening ${verifying.name} terverifikasi.`); }} />
      )}
    </>
  );
}

function ReasonModal({ title, label, placeholder, submitLabel, intro, onClose, onSubmit }: {
  title: string; label: string; placeholder: string; submitLabel: string; intro?: ReactNode;
  onClose: () => void; onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = reason.trim().length >= 5;
  return (
    <Modal title={title} onClose={onClose}>
      {intro}
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
