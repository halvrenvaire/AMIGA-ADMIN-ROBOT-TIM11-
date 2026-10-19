import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Circle, Eye, FileText, Send, UploadCloud, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignerPicker } from "../components/SignerPicker";
import { Alert } from "../components/ui";
import { tanggal, todayIso, REQUEST_CATEGORIES } from "../format";
import type { DocumentSummary, Signatory } from "../types";

const MAX_MB = 10;
// Batas bukti per voucher: Reimburse (bon tol, parkir) bisa sampai 20, kategori lain 10
const maxFilesFor = (category: string) => (category === "Voucher Pengeluaran Reimburse" ? 20 : 10);

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const ACCEPT = "application/pdf,.pdf,image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp";
const isImage = (f: File) => IMAGE_TYPES.includes(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name);
/** PDF atau foto invoice; foto diubah menjadi PDF oleh server (isi file diperiksa lagi di server). */
const isAccepted = (f: File) => f.type === "application/pdf" || /\.pdf$/i.test(f.name) || isImage(f);

/** Layar 02 — Pembuatan Voucher (PIC Klien, Intake Support). FR-1.1–1.5.
 *  1–10 invoice PDF digabung dalam satu voucher; PIC meninjau dulu di halaman Preview sebelum mengirim. */
export function Upload() {
  const { user, has } = useAuth();
  // Hanya perusahaan yang ditugaskan System Admin untuk diajukan (bukan semua yang bisa dilihat reviewer)
  const clients = user?.upload_clients ?? [];
  // Intake Support mengajukan atas nama PIC yang mendelegasikan; nama PIC dicetak oleh sistem
  const defaultSubmitter = has("PIC_KLIEN") ? user?.full_name ?? "" : "";
  // Nama di kotak "Diajukan oleh" boleh diganti karyawan lain (feedback owner)
  const [submitterName, setSubmitterName] = useState(defaultSubmitter);
  const submitter = submitterName.trim() || (has("PIC_KLIEN") ? user?.full_name ?? "-" : "PIC Klien yang mendelegasikan");
  // Satu perusahaan per pengajuan; bila PIC memegang beberapa perusahaan, harus dipilih dulu
  const [clientId, setClientId] = useState(clients.length === 1 ? clients[0].id : "");
  const [requestType, setRequestType] = useState<string>(REQUEST_CATEGORIES[0]);
  const MAX_FILES = maxFilesFor(requestType);
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
      if (!isAccepted(f)) {
        setError(`${f.name}: file harus berformat PDF atau foto (JPG, PNG, WEBP). Simpan atau ekspor invoice ke salah satu format itu, lalu pilih ulang.`);
        continue;
      }
      if (f.size > MAX_MB * 1024 * 1024) { setError(`${f.name}: ukuran file melebihi ${MAX_MB} MB.`); continue; }
      if (next.some((x) => x.name === f.name && x.size === f.size)) continue;
      if (next.length >= MAX_FILES) { setError(`Maksimal ${MAX_FILES} file bukti per voucher untuk kategori ini.`); break; }
      next.push(f);
    }
    setFiles(next);
    if (inputRef.current) inputRef.current.value = "";
  }

  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); };

  function preview(e: FormEvent) {
    e.preventDefault();
    if (!clientId) { setError("Pilih perusahaan yang mengajukan."); return; }
    if (!files.length) { setError("Pilih minimal 1 file invoice (PDF atau foto)."); return; }
    if (files.length > MAX_FILES) { setError(`Kategori ini maksimal ${MAX_FILES} file bukti. Hapus sebagian file atau pilih kategori lain.`); return; }
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
    if (submitterName.trim() && submitterName.trim() !== defaultSubmitter) form.set("submitter_name", submitterName.trim());
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
      <Preview companyName={company?.name ?? "-"} submitter={submitter} requestType={requestType} channel={channel} submittedDate={submittedDate}
               dueDate={dueDate} approvers={approvers} files={files} error={error} busy={busy}
               onBack={() => { setError(null); setStep("form"); }} onSend={send} />
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pembuatan voucher</h1>
          <p>1–{MAX_FILES} file bukti (invoice, bon) berupa PDF atau foto JPG, PNG, WEBP untuk satu voucher, tiap file maksimal 5 halaman. Semua bukti ikut dilampirkan di voucher. Tinjau dulu di Preview sebelum dikirim.</p>
        </div>
      </div>

      {result && (
        <Alert kind="ok">
          <span>
            Draf dibuat dengan Request ID <b className="mono">{result.request_id}</b>. Setelah AI selesai membaca, periksa datanya,
            lihat simulasi voucher, lalu kirim ke Finance Reviewer. <Link to={`/dokumen/${result.id}`}>Buka draf →</Link>
          </span>
        </Alert>
      )}

      <div className="with-aside">
      <form className="card panel" onSubmit={preview}>
        {error && <Alert>{error}</Alert>}
        {!clients.length && <Alert kind="warn">Akun Anda belum ditugaskan ke perusahaan mana pun. Hubungi System Admin.</Alert>}
        <div className="grid-2">
          <div className="field">
            <label htmlFor="client">Perusahaan</label>
            <select id="client" className="input" required value={clientId} onChange={(e) => setClientId(e.target.value)}>
              {clients.length !== 1 && <option value="" disabled>Pilih perusahaan…</option>}
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <small>Hanya perusahaan yang ditugaskan System Admin kepada Anda.</small>
          </div>
          <div className="field">
            <label htmlFor="type">Kategori</label>
            <select id="type" className="input" required value={requestType} onChange={(e) => setRequestType(e.target.value)}>
              {REQUEST_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <small>Untuk filter di dashboard; tidak dicetak di voucher.</small>
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
            <div className="field" style={{ maxWidth: 420 }}>
              <label htmlFor="submitter-name">Nama &quot;Diajukan oleh&quot;</label>
              <input id="submitter-name" className="input" maxLength={200} value={submitterName}
                     placeholder={has("PIC_KLIEN") ? user?.full_name : "Kosongkan = PIC yang mendelegasikan"}
                     onChange={(e) => setSubmitterName(e.target.value)} />
              <small>Boleh diganti dengan nama karyawan lain yang mengajukan.</small>
            </div>
            <SignerPicker key={clientId} clientId={clientId} clientName={company.name} submitter={submitter}
                          onChange={(ids, chosen) => { setSigners(ids); setApprovers(chosen); }} />
          </>
        )}

        <div className="section-title">File bukti <span className="muted">({files.length}/{MAX_FILES})</span></div>
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
              Seret file PDF atau foto invoice ke sini atau <b>klik untuk memilih</b>{files.length > 0 && " (tambah invoice lain)"}
            </div>
            <small className="muted">Bisa beberapa file sekaligus. PDF (maks. 5 halaman) atau foto JPG/PNG/WEBP, maks. {MAX_MB} MB per file</small>
          </div>
        )}
        <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => add(e.target.files)} />

        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary" disabled={!clients.length || !files.length || !clientId}><Eye /> Preview</button>
        </div>
      </form>
      <UploadAside company={company?.name} requestType={requestType} dueDate={dueDate} files={files} approvers={approvers} />
      </div>
    </>
  );
}

/** Panel samping Unggah: ringkasan pengajuan yang sedang diisi, dan hal yang sering membuat invoice tertahan. */
function UploadAside({ company, requestType, dueDate, files, approvers }: {
  company?: string; requestType: string; dueDate: string; files: File[]; approvers: Signatory[];
}) {
  const sizeKb = files.reduce((n, f) => n + f.size, 0) / 1024;
  const checks: [boolean, string][] = [
    [Boolean(company), company ? `Perusahaan: ${company}` : "Pilih perusahaan"],
    [requestType.trim().length > 0, `Kategori: ${requestType}`],
    [files.length > 0, files.length ? `${files.length} file invoice (${sizeKb < 1024 ? `${sizeKb.toFixed(0)} KB` : `${(sizeKb / 1024).toFixed(1)} MB`})` : "Tambahkan minimal 1 file invoice"],
  ];
  const ready = checks.every(([ok]) => ok);
  return (
    <aside className="aside sticky">
      <section className="card panel">
        <div className="panel-head">
          <div><h2>Ringkasan pengajuan</h2><p>{ready ? "Siap dipreview" : "Lengkapi dulu sebelum preview"}</p></div>
          <span className={`chip ${ready ? "ok" : "gray"}`}>{checks.filter(([ok]) => ok).length}/{checks.length}</span>
        </div>
        <ul className="checklist">
          {checks.map(([ok, text]) => (
            <li key={text} className={ok ? "ok" : undefined}>{ok ? <CheckCircle2 /> : <Circle />}<span>{text}</span></li>
          ))}
        </ul>
        <dl className="meta compact">
          <dt>Tenggat</dt><dd>{dueDate ? tanggal(dueDate) : <span className="muted">Tidak diisi</span>}</dd>
          <dt>Disetujui oleh</dt>
          <dd>{approvers.length ? approvers.map((a) => a.full_name).join(", ") : <span className="muted">Kotak kosong</span>}</dd>
          <dt>TTD elektronik</dt>
          <dd>{approvers.filter((a) => a.signature_updated_at).length} dari {approvers.length} penyetuju
            {approvers.some((a) => !a.signature_updated_at) && <span className="muted"> · sisanya tanda tangan basah</span>}</dd>
        </dl>
      </section>
      <section className="card panel">
        <div className="panel-head"><div><h2>Agar tidak tertahan</h2><p>Penyebab kendala yang paling sering</p></div></div>
        <ul className="tips">
          <li><b>Satu voucher, satu vendor.</b> Semua invoice harus untuk vendor dan rekening tujuan yang sama.</li>
          <li><b>Invoice, bukan struk.</b> Struk/nota disusun AI sebagai draft dan ditahan sampai ada invoice resmi atau
            keputusan Finance Reviewer. Dokumen yang tidak relevan langsung ditolak.</li>
          <li><b>Rekening dicek ke data vendor.</b> Rekening yang berbeda dari data vendor terverifikasi akan ditahan.</li>
          <li><b>Rekening terbaca.</b> Pastikan nama bank dan nomor rekening vendor tertulis jelas.</li>
          <li><b>Jangan unggah ulang.</b> Invoice yang pernah diajukan ditandai sebagai kemungkinan duplikat.</li>
        </ul>
      </section>
    </aside>
  );
}

function Preview({ companyName, submitter, requestType, channel, submittedDate, dueDate, approvers, files, error, busy, onBack, onSend }: {
  companyName: string; submitter: string; requestType: string; channel: string; submittedDate: string; dueDate: string;
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
            <dt>Perusahaan</dt><dd><b>{companyName}</b></dd>
            <dt>Diajukan oleh</dt><dd>{submitter}</dd>
            <dt>Disetujui oleh</dt>
            <dd>{approvers.length ? (
              <ol className="plain-list">{approvers.map((a) => <li key={a.id}>{a.full_name} <span className="muted">· {a.position}</span></li>)}</ol>
            ) : <span className="muted">1 kotak kosong (diisi manual)</span>}</dd>
            <dt>Kategori</dt><dd>{requestType}</dd>
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
          {urls[active] && (isImage(files[active])
            ? <img key={urls[active]} className="photo-preview" alt={`Preview ${files[active].name}`} src={urls[active]} />
            : <iframe key={urls[active]} title={`Preview ${files[active].name}`} src={urls[active]} />)}
        </section>
      </div>
    </>
  );
}
