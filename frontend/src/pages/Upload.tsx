import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Eye, FileText, Send, UploadCloud, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignerPicker } from "../components/SignerPicker";
import { Alert } from "../components/ui";
import { tanggal, todayIso } from "../format";
import type { DocumentSummary, Signatory } from "../types";

const MAX_MB = 10;
const MAX_FILES = 10;

/** Layar 02 — Unggah Dokumen (PIC Klien, Intake Support). FR-1.1–1.5.
 *  1–10 invoice PDF digabung dalam satu voucher; PIC meninjau dulu di halaman Preview sebelum mengirim. */
export function Upload() {
  const { user } = useAuth();
  const clients = user?.clients ?? [];
  // Satu perusahaan per pengajuan; bila PIC memegang beberapa perusahaan, harus dipilih dulu
  const [clientId, setClientId] = useState(clients.length === 1 ? clients[0].id : "");
  const [requestType, setRequestType] = useState("Pembayaran vendor");
  const [channel, setChannel] = useState("Email");
  const [submittedDate, setSubmittedDate] = useState(todayIso());
  const [dueDate, setDueDate] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [signers, setSigners] = useState<string[]>([]);
  const [approvers, setApprovers] = useState<Signatory[]>([]);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"form" | "preview">("form");
  const [result, setResult] = useState<DocumentSummary | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const company = clients.find((c) => c.id === clientId);

  function add(list: FileList | null | undefined) {
    setError(null);
    if (!list?.length) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
        setError(`${f.name}: file harus berformat PDF. Simpan atau ekspor invoice sebagai PDF, lalu pilih ulang.`);
        continue;
      }
      if (f.size > MAX_MB * 1024 * 1024) { setError(`${f.name}: ukuran file melebihi ${MAX_MB} MB.`); continue; }
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (next.length >= MAX_FILES) { setError(`Maksimal ${MAX_FILES} file invoice per voucher.`); break; }
      next.push(f);
    }
    setFiles(next);
    if (inputRef.current) inputRef.current.value = "";
  }

  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); };

  function preview(e: FormEvent) {
    e.preventDefault();
    if (!clientId) { setError("Pilih perusahaan yang mengajukan."); return; }
    if (!files.length) { setError("Pilih minimal 1 file invoice PDF."); return; }
    setError(null);
    setResult(null);
    setStep("preview");
    window.scrollTo(0, 0);
  }

  async function send() {
    const form = new FormData();
    form.set("client_id", clientId);
    form.set("request_type", requestType);
    form.set("channel", channel);
    form.set("submitted_date", submittedDate);
    if (dueDate) form.set("due_date", dueDate);
    form.set("signatory_ids", signers.join(","));
    files.forEach((f) => form.append("files", f));
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<DocumentSummary>("/documents", form));
      setFiles([]);
      setStep("form");
    } catch (err) {
      // FR-1.5: file ditolak → pesan jelas, PIC bisa kembali mengubah
      setError((err as Error).message);
    } finally {
      setBusy(false);
      window.scrollTo(0, 0);
    }
  }

  if (step === "preview") {
    return (
      <Preview companyName={company?.name ?? "-"} requestType={requestType} channel={channel} submittedDate={submittedDate}
               dueDate={dueDate} approvers={approvers} files={files} error={error} busy={busy}
               onBack={() => { setError(null); setStep("form"); }} onSend={send} />
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Unggah invoice</h1>
          <p>1–{MAX_FILES} file PDF untuk satu voucher, tiap file maksimal 5 halaman. Tinjau dulu di Preview sebelum dikirim.</p>
        </div>
      </div>

      {result && (
        <Alert kind="ok">
          <span>
            Terkirim ke antrean dengan Request ID <b className="mono">{result.request_id}</b> (status QUEUED). Catat Request ID ini
            untuk pelacakan. <Link to={`/dokumen/${result.id}`}>Lihat status dokumen →</Link>
          </span>
        </Alert>
      )}

      <form className="card panel" onSubmit={preview} style={{ maxWidth: 820 }}>
        {error && <Alert>{error}</Alert>}
        {!clients.length && <Alert kind="warn">Akun Anda belum ditugaskan ke perusahaan mana pun. Hubungi System Admin.</Alert>}
        <div className="grid-2">
          <div className="field">
            <label htmlFor="client">Diajukan oleh (perusahaan)</label>
            <select id="client" className="input" required value={clientId} onChange={(e) => setClientId(e.target.value)}>
              {clients.length !== 1 && <option value="" disabled>Pilih perusahaan…</option>}
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <small>Hanya perusahaan yang ditugaskan System Admin kepada Anda.</small>
          </div>
          <div className="field">
            <label htmlFor="type">Jenis permintaan</label>
            <input id="type" className="input" required maxLength={100} value={requestType}
                   onChange={(e) => setRequestType(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="channel">Saluran</label>
            <select id="channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option>Email</option><option>WhatsApp</option><option>Lainnya</option>
            </select>
            <small>Asal invoice diterima. Invoice tetap diproses lewat unggahan ini.</small>
          </div>
          <div className="field">
            <label htmlFor="submitted">Tanggal pengajuan</label>
            <input id="submitted" className="input" type="date" required value={submittedDate}
                   onChange={(e) => setSubmittedDate(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="due">Tenggat (opsional)</label>
            <input id="due" className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
        </div>

        {company && (
          <>
            <div className="section-title">Kotak tanda tangan voucher</div>
            <SignerPicker key={clientId} clientId={clientId} clientName={company.name}
                          onChange={(ids, chosen) => { setSigners(ids); setApprovers(chosen); }} />
          </>
        )}

        <div className="section-title">File invoice <span className="muted">({files.length}/{MAX_FILES})</span></div>
        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`}>
                <FileText />
                <span className="name">{i + 1}. {f.name}</span>
                <span className="muted">{(f.size / 1024).toFixed(0)} KB</span>
                <button type="button" className="btn ghost sm" aria-label={`Hapus ${f.name}`}
                        onClick={() => setFiles(files.filter((_, j) => j !== i))}><X /></button>
              </li>
            ))}
          </ul>
        )}
        {files.length < MAX_FILES && (
          <div className={`drop ${over ? "over" : ""}`} onClick={() => inputRef.current?.click()}
               onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
               role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}>
            <UploadCloud />
            <div style={{ marginTop: 6 }}>
              Seret file PDF ke sini atau <b>klik untuk memilih</b>{files.length > 0 && " (tambah invoice lain)"}
            </div>
            <small className="muted">Bisa beberapa file sekaligus. PDF, maks. 5 halaman dan {MAX_MB} MB per file</small>
          </div>
        )}
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => add(e.target.files)} />

        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary" disabled={!clients.length || !files.length || !clientId}><Eye /> Preview</button>
        </div>
      </form>
    </>
  );
}

function Preview({ companyName, requestType, channel, submittedDate, dueDate, approvers, files, error, busy, onBack, onSend }: {
  companyName: string; requestType: string; channel: string; submittedDate: string; dueDate: string;
  approvers: Signatory[]; files: File[]; error: string | null; busy: boolean; onBack: () => void; onSend: () => void;
}) {
  const [active, setActive] = useState(0);
  // URL dibuat dan dicabut di efek yang sama: di StrictMode efek dijalankan dua kali, jadi URL
  // yang dibuat di luar efek (useMemo) sudah dicabut saat iframe memuatnya
  const [urls, setUrls] = useState<string[]>([]);
  useEffect(() => {
    const created = files.map((f) => URL.createObjectURL(f));
    setUrls(created);
    return () => created.forEach((u) => URL.revokeObjectURL(u));
  }, [files]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Preview pengajuan</h1>
          <p>Periksa setiap file invoice dan data pengajuan. Bila sudah benar, kirim ke antrean.</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={onBack} disabled={busy}><ArrowLeft /> Kembali ubah</button>
          <button className="btn primary" onClick={onSend} disabled={busy}><Send /> {busy ? "Mengirim…" : "Kirim ke antrean"}</button>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="preview-grid">
        <section className="card panel">
          <div className="section-title">Data pengajuan</div>
          <dl className="meta">
            <dt>Diajukan oleh</dt><dd><b>{companyName}</b></dd>
            <dt>Disetujui oleh</dt>
            <dd>{approvers.length ? (
              <ol className="plain-list">{approvers.map((a) => <li key={a.id}>{a.full_name} <span className="muted">· {a.position}</span></li>)}</ol>
            ) : <span className="muted">1 kotak kosong (diisi manual)</span>}</dd>
            <dt>Jenis permintaan</dt><dd>{requestType}</dd>
            <dt>Saluran</dt><dd>{channel}</dd>
            <dt>Tanggal pengajuan</dt><dd>{tanggal(submittedDate)}</dd>
            <dt>Tenggat</dt><dd>{dueDate ? tanggal(dueDate) : "-"}</dd>
            <dt>Jumlah invoice</dt><dd>{files.length} file</dd>
          </dl>
          <div className="section-title">File invoice</div>
          <ul className="file-list selectable">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`} className={i === active ? "on" : ""}>
                <button type="button" onClick={() => setActive(i)}>
                  <FileText /><span className="name">{i + 1}. {f.name}</span>
                  <span className="muted">{(f.size / 1024).toFixed(0)} KB</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="card panel pdf-preview">
          <div className="panel-head">
            <div><h2>{active + 1}. {files[active]?.name}</h2><p>Invoice {active + 1} dari {files.length}</p></div>
            {files.length > 1 && (
              <div className="actions">
                <button className="btn sm" disabled={active === 0} onClick={() => setActive(active - 1)}>Sebelumnya</button>
                <button className="btn sm" disabled={active === files.length - 1} onClick={() => setActive(active + 1)}>Berikutnya</button>
              </div>
            )}
          </div>
          {urls[active] && <iframe key={urls[active]} title={`Preview ${files[active].name}`} src={urls[active]} />}
        </section>
      </div>
    </>
  );
}
