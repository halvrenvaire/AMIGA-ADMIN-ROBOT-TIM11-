import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Circle, Eye, FileText, ListOrdered, Receipt, Save, UploadCloud, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignerPicker } from "../components/SignerPicker";
import { EMPTY_PROFILE, SubmitterProfileFields, type LockedProfile, type SubmitterProfile } from "../components/SubmitterProfile";
import { SignatureImage } from "../components/Signature";
import { Alert, Modal } from "../components/ui";
import { tanggal, todayIso, REQUEST_CATEGORIES } from "../format";
import type { DocumentSummary, ExtractionMode, Signatory } from "../types";

const MAX_MB = 10;
// Batas bukti per voucher: Reimburse (bon tol, parkir) bisa sampai 20, kategori lain 10
const maxFilesFor = (category: string) => (category === "Voucher Pengeluaran Reimburse" ? 20 : 10);

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const ACCEPT = "application/pdf,.pdf,image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp";
const isImage = (f: File) => IMAGE_TYPES.includes(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name);
/** PDF atau foto invoice; foto diubah menjadi PDF oleh server (isi file diperiksa lagi di server). */
const isAccepted = (f: File) => f.type === "application/pdf" || /\.pdf$/i.test(f.name) || isImage(f);

/** Dua mode baca AI (Tahap 14). "Total saja" lebih cepat dan hemat; "Rincian" membaca setiap barang/jasa. */
export const MODE_INFO: Record<ExtractionMode, { title: string; desc: string }> = {
  TOTAL_ONLY: { title: "Total saja", desc: "AI membaca total, jenis dokumen, vendor, nomor, dan tanggal. Voucher berisi 1 baris per invoice. Lebih cepat dan hemat." },
  ITEMIZED: { title: "Rincian barang/jasa", desc: "AI membaca setiap baris barang/jasa. Voucher berisi 1 baris per item, pajak bisa diatur per baris." },
};

/** Layar 02 — Pembuatan Voucher (PIC Klien, Intake Support). FR-1.1–1.5.
 *  Data pengajuan, profil pengaju, penyetuju, mode AI, lalu file bukti. Setelah disimpan sebagai draf,
 *  pengguna langsung dibawa ke halaman detail untuk memeriksa hasil AI dan mengajukannya. */
export function Upload() {
  const { user, has } = useAuth();
  const navigate = useNavigate();
  const isPic = has("PIC_KLIEN");
  // Hanya perusahaan yang ditugaskan System Admin untuk diajukan (bukan semua yang bisa dilihat reviewer)
  const clients = user?.upload_clients ?? [];
  // Satu perusahaan per pengajuan; bila PIC memegang beberapa perusahaan, harus dipilih dulu
  const [clientId, setClientId] = useState(clients.length === 1 ? clients[0].id : "");
  const company = clients.find((c) => c.id === clientId);
  const [requestType, setRequestType] = useState<string>(REQUEST_CATEGORIES[0]);
  const MAX_FILES = maxFilesFor(requestType);
  const [submittedDate, setSubmittedDate] = useState(todayIso());
  const [profile, setProfile] = useState<SubmitterProfile>(EMPTY_PROFILE);
  const [signers, setSigners] = useState<string[]>([]);
  const [approvers, setApprovers] = useState<Signatory[]>([]);
  const [mode, setMode] = useState<ExtractionMode>("TOTAL_ONLY");
  // Fitur tambahan (bawaan mati): saluran & tenggat, serta rekening tujuan di voucher
  const [extras, setExtras] = useState(false);
  const [channel, setChannel] = useState("Email");
  const [dueDate, setDueDate] = useState("");
  const [includeAccount, setIncludeAccount] = useState(false);
  const [autoTax, setAutoTax] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  // File yang sedang dilihat di pratinjau (hanya di browser, belum dikirim ke server)
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  // "Diajukan oleh" mode PIC: profil akun PIC Klien (Intake Support: PIC yang mendelegasikan, diisi server)
  const saved = user?.submitter_profile ?? {};
  const pic: LockedProfile = isPic && user ? {
    name: user.full_name, position: saved.position || "PIC Klien",
    company: saved.company || (clientId && saved.companies?.[clientId]) || company?.name || "Nama perusahaan klien",
    signature: user.signature_updated_at
      ? <SignatureImage path="/auth/me/signature" version={user.signature_updated_at} alt="Tanda tangan Anda" />
      : <span className="sig-empty">Tanpa tanda tangan (diisi basah)</span>,
  } : null;
  const submitterLabel = profile.source === "MANUAL" ? profile.name.trim() || "-"
    : pic?.name ?? "PIC Klien yang mendelegasikan";

  function chooseClient(id: string) {
    setClientId(id);
  }

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

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!clientId) { setError("Pilih perusahaan yang mengajukan."); return; }
    if (!files.length) { setError("Pilih minimal 1 file invoice (PDF atau foto)."); return; }
    if (files.length > MAX_FILES) { setError(`Kategori ini maksimal ${MAX_FILES} file bukti. Hapus sebagian file atau pilih kategori lain.`); return; }
    const form = new FormData();
    form.set("client_id", clientId);
    form.set("request_type", requestType);
    form.set("submitted_date", submittedDate);
    form.set("signatory_ids", signers.join(","));
    form.set("extraction_mode", mode);
    form.set("include_account", String(includeAccount));
    form.set("auto_tax", String(autoTax));
    form.set("submitter_source", profile.source);
    if (profile.source === "MANUAL") {
      form.set("submitter_name", profile.name.trim());
      form.set("submitter_position", profile.position.trim());
      if (profile.company.trim()) form.set("submitter_company", profile.company.trim());
      if (profile.signature) form.set("submitter_signature", profile.signature);
    }
    if (extras) {
      form.set("channel", channel);
      if (dueDate) form.set("due_date", dueDate);
    }
    files.forEach((f) => form.append("files", f));
    setBusy(true);
    setError(null);
    try {
      const doc = await api.post<DocumentSummary>("/documents", form);
      navigate(`/dokumen/${doc.id}`);
    } catch (err) {
      // FR-1.5: file ditolak → pesan jelas, PIC bisa mengubah lalu menyimpan lagi
      setError((err as Error).message);
      window.scrollTo(0, 0);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Pembuatan voucher</h1>
          <p>Isi data pengajuan, pilih mode baca AI, lalu unggah 1–{MAX_FILES} file bukti (PDF atau foto JPG, PNG, WEBP).
            Setelah disimpan sebagai draf, Anda langsung memeriksa hasil AI dan pratinjau voucher sebelum mengajukannya.</p>
        </div>
      </div>

      <div className="with-aside">
      <form className="card panel upload-form" onSubmit={save}>
        {error && <Alert>{error}</Alert>}
        {!clients.length && <Alert kind="warn">Akun Anda belum ditugaskan ke perusahaan mana pun. Hubungi System Admin.</Alert>}

        <div className="section-title">1. Data pengajuan</div>
        <div className="grid-3">
          <div className="field">
            <label htmlFor="client">Klien</label>
            <select id="client" className="input" required value={clientId} onChange={(e) => chooseClient(e.target.value)}>
              {clients.length !== 1 && <option value="" disabled>Pilih perusahaan…</option>}
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <small>Hanya perusahaan yang ditugaskan kepada Anda.</small>
          </div>
          <div className="field">
            <label htmlFor="type">Kategori</label>
            <select id="type" className="input" required value={requestType} onChange={(e) => setRequestType(e.target.value)}>
              {REQUEST_CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
            <small>Untuk filter di dashboard; tidak dicetak di voucher.</small>
          </div>
          <div className="field">
            <label htmlFor="submitted">Tanggal pengajuan</label>
            <input id="submitted" className="input" type="date" required value={submittedDate}
                   onChange={(e) => setSubmittedDate(e.target.value)} />
          </div>
        </div>

        <div data-tour="submitter">
          <div className="section-title">2. Diajukan oleh</div>
          <SubmitterProfileFields value={profile} onChange={setProfile} pic={pic} accountLink={isPic} />
        </div>

        <div data-tour="approver">
          <div className="section-title">3. Disetujui oleh</div>
          {company
            ? <SignerPicker key={clientId} clientId={clientId} clientName={company.name} submitter={submitterLabel} showSubmitter={false}
                            onChange={(ids, chosen) => { setSigners(ids); setApprovers(chosen); }} />
            : <p className="muted" style={{ margin: 0 }}>Pilih klien dulu untuk memilih pemberi persetujuan.</p>}
        </div>

        <div className="section-title">4. Mode baca AI</div>
        <div className="mode-cards" role="radiogroup" aria-label="Mode baca AI">
          {(Object.keys(MODE_INFO) as ExtractionMode[]).map((m) => (
            <label key={m} className={`mode-card${mode === m ? " on" : ""}`}>
              <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
              <span className="mode-ic">{m === "TOTAL_ONLY" ? <Receipt /> : <ListOrdered />}</span>
              <span><b>{MODE_INFO[m].title}{m === "TOTAL_ONLY" && <small className="chip ok">Bawaan</small>}</b>
                <small>{MODE_INFO[m].desc}</small></span>
            </label>
          ))}
        </div>
        <small className="muted">Mode masih bisa diganti di halaman berikutnya.</small>

        <details className="extras">
          <summary>Fitur tambahan <span className="muted">(opsional)</span></summary>
          <div className="extras-body">
          <label className="toggle">
            <input type="checkbox" checked={extras} onChange={(e) => setExtras(e.target.checked)} />
            Catat saluran asal dan tenggat
          </label>
          {extras && (
            <div className="grid-2">
              <div className="field">
                <label htmlFor="channel">Saluran</label>
                <select id="channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
                  <option>Email</option><option>WhatsApp</option><option>Lainnya</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="due">Tenggat</label>
                <input id="due" className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
              </div>
            </div>
          )}
          <label className="toggle">
            <input type="checkbox" checked={includeAccount} onChange={(e) => setIncludeAccount(e.target.checked)} />
            Perlu input rekening tujuan ke voucher
          </label>
          {includeAccount && <small className="muted">AI ikut membaca bank dan nomor rekening, lalu dicek ke data vendor dan dicetak di voucher.</small>}
          <label className="toggle">
            <input type="checkbox" checked={autoTax} onChange={(e) => setAutoTax(e.target.checked)} />
            Atur pajak secara otomatis <span className="muted">· sistem langsung menerapkan rekomendasi PPh &amp; PPN ke setiap invoice (bisa diubah di draf)</span>
          </label>
          </div>
        </details>

        <div className="section-title">5. File bukti <span className="muted">({files.length}/{MAX_FILES})</span></div>
        {files.length > 0 && (
          <ul className="file-list">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`}>
                <FileText />
                <span className="name">{i + 1}. {f.name}</span>
                <span className="muted">{(f.size / 1024).toFixed(0)} KB</span>
                <button type="button" className="btn ghost sm" aria-label={`Lihat ${f.name}`} title="Lihat file"
                        onClick={() => setPreviewFile(f)}><Eye /></button>
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
              Seret file PDF atau foto invoice ke sini atau <b>ketuk untuk memilih</b>{files.length > 0 && " (tambah invoice lain)"}
            </div>
            <small className="muted">Bisa beberapa file sekaligus. Maks. {MAX_MB} MB per file. Satu file boleh berisi invoice beserta Faktur Pajak dan timesheet, atau beberapa invoice sekaligus: AI memisahkannya per invoice.</small>
          </div>
        )}
        <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => add(e.target.files)} />

        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary" disabled={busy || !clients.length || !files.length || !clientId}>
            <Save /> {busy ? "Menyimpan…" : "Simpan draf & lanjutkan"}
          </button>
        </div>
      </form>
      {previewFile && <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />}
      <UploadAside company={company?.name} requestType={requestType} dueDate={extras ? dueDate : ""} files={files}
                   approvers={approvers} mode={mode} submitter={submitterLabel} includeAccount={includeAccount} />
      </div>
    </>
  );
}

/** Pratinjau file yang baru dipilih, langsung dari memori browser. Tidak ada yang dikirim atau disimpan ke server;
 *  tujuannya hanya memastikan PIC tidak salah memilih file. */
function FilePreviewModal({ file, onClose }: { file: File; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return (
    <Modal title={file.name} onClose={onClose} wide>
      <div className="pdf-preview" style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {url && (isImage(file)
          ? <img className="photo-preview" src={url} alt={`Pratinjau ${file.name}`} />
          : <iframe src={url} title={`Pratinjau ${file.name}`} style={{ height: "100%", minHeight: "60vh" }} />)}
      </div>
    </Modal>
  );
}

/** Panel samping Unggah: ringkasan pengajuan yang sedang diisi, dan hal yang sering membuat invoice tertahan. */
function UploadAside({ company, requestType, dueDate, files, approvers, mode, submitter, includeAccount }: {
  company?: string; requestType: string; dueDate: string; files: File[]; approvers: Signatory[];
  mode: ExtractionMode; submitter: string; includeAccount: boolean;
}) {
  const sizeKb = files.reduce((n, f) => n + f.size, 0) / 1024;
  const checks: [boolean, string][] = [
    [Boolean(company), company ? `Klien: ${company}` : "Pilih klien"],
    [requestType.trim().length > 0, `Kategori: ${requestType}`],
    [files.length > 0, files.length ? `${files.length} file bukti (${sizeKb < 1024 ? `${sizeKb.toFixed(0)} KB` : `${(sizeKb / 1024).toFixed(1)} MB`})` : "Tambahkan minimal 1 file bukti"],
  ];
  const ready = checks.every(([ok]) => ok);
  return (
    <aside className="aside sticky">
      <section className="card panel">
        <div className="panel-head">
          <div><h2>Ringkasan pengajuan</h2><p>{ready ? "Siap disimpan sebagai draf" : "Lengkapi dulu sebelum disimpan"}</p></div>
          <span className={`chip ${ready ? "ok" : "gray"}`}>{checks.filter(([ok]) => ok).length}/{checks.length}</span>
        </div>
        <ul className="checklist">
          {checks.map(([ok, text]) => (
            <li key={text} className={ok ? "ok" : undefined}>{ok ? <CheckCircle2 /> : <Circle />}<span>{text}</span></li>
          ))}
        </ul>
        <dl className="meta compact">
          <dt>Mode AI</dt><dd>{MODE_INFO[mode].title}</dd>
          <dt>Diajukan oleh</dt><dd>{submitter}</dd>
          <dt>Disetujui oleh</dt>
          <dd>{approvers.length ? approvers.map((a) => a.full_name).join(", ") : <span className="muted">Kotak kosong</span>}</dd>
          <dt>Rekening</dt><dd>{includeAccount ? "Dicantumkan di voucher" : <span className="muted">Tidak dicantumkan</span>}</dd>
          {dueDate && <><dt>Tenggat</dt><dd>{tanggal(dueDate)}</dd></>}
        </dl>
      </section>
      <section className="card panel">
        <div className="panel-head"><div><h2>Agar tidak tertahan</h2><p>Penyebab kendala yang paling sering</p></div></div>
        <ul className="tips">
          <li><b>Invoice, bukan struk.</b> Struk/nota disusun AI sebagai draft dan ditahan sampai ada invoice resmi atau
            keputusan Finance Reviewer. Dokumen yang tidak relevan langsung ditolak.</li>
          <li><b>Total terbaca jelas.</b> Pastikan angka total, nomor, dan tanggal invoice tidak terpotong atau buram.</li>
          <li><b>Satu voucher, satu vendor.</b> Bila vendor berbeda, sistem hanya memberi pengingat untuk dicek.</li>
          <li><b>Jangan unggah ulang.</b> Invoice yang pernah diajukan ditandai sebagai kemungkinan duplikat.</li>
        </ul>
      </section>
    </aside>
  );
}
