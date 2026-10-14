import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { FileUp, UploadCloud } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignerPicker } from "../components/SignerPicker";
import { Alert } from "../components/ui";
import { todayIso } from "../format";
import type { DocumentSummary } from "../types";

const MAX_MB = 10;

/** Layar 02 — Unggah Dokumen (PIC Klien, Intake Support). FR-1.1–1.5. */
export function Upload() {
  const { user } = useAuth();
  const clients = user?.clients ?? [];
  const [clientId, setClientId] = useState(clients[0]?.id ?? "");
  const [requestType, setRequestType] = useState("Pembayaran vendor");
  const [channel, setChannel] = useState("Email");
  const [submittedDate, setSubmittedDate] = useState(todayIso());
  const [dueDate, setDueDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocumentSummary | null>(null);
  const [signers, setSigners] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(f: File | undefined) {
    setError(null);
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("File harus berformat PDF. Simpan atau ekspor invoice sebagai PDF, lalu pilih ulang.");
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`Ukuran file melebihi ${MAX_MB} MB.`);
      return;
    }
    setFile(f);
  }

  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) { setError("Pilih file invoice PDF terlebih dahulu."); return; }
    const form = new FormData();
    form.set("client_id", clientId);
    form.set("request_type", requestType);
    form.set("channel", channel);
    form.set("submitted_date", submittedDate);
    if (dueDate) form.set("due_date", dueDate);
    form.set("signatory_ids", signers.join(","));
    form.set("file", file);
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<DocumentSummary>("/documents", form));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      // FR-1.5: file ditolak → tetap di formulir dengan pesan yang jelas
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Unggah invoice</h1>
          <p>Satu file PDF, maksimal 5 halaman. Setelah dikirim, AI membaca invoice dan sistem memverifikasinya.</p>
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

      <form className="card panel" onSubmit={submit} style={{ maxWidth: 760 }}>
        {error && <Alert>{error}</Alert>}
        {!clients.length && <Alert kind="warn">Akun Anda belum ditugaskan ke klien mana pun. Hubungi System Admin.</Alert>}
        <div className="grid-2">
          <div className="field">
            <label htmlFor="client">Nama klien</label>
            <select id="client" className="input" required value={clientId} onChange={(e) => setClientId(e.target.value)}>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
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

        <div className="section-title">Penanda tangan voucher</div>
        {clientId && <SignerPicker key={clientId} clientId={clientId} onChange={setSigners} />}

        <div className={`drop ${over ? "over" : ""}`} onClick={() => inputRef.current?.click()}
             onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
             role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}>
          {file ? <FileUp /> : <UploadCloud />}
          <div style={{ marginTop: 6 }}>
            {file ? <><b>{file.name}</b> · {(file.size / 1024).toFixed(0)} KB</> : <>Seret file PDF ke sini atau <b>klik untuk memilih</b></>}
          </div>
          <small className="muted">PDF, maksimal 5 halaman dan {MAX_MB} MB</small>
          <input ref={inputRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => pick(e.target.files?.[0])} />
        </div>

        <div className="actions" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary" disabled={busy || !clients.length}>{busy ? "Mengirim…" : "Kirim ke antrean"}</button>
        </div>
      </form>
    </>
  );
}
