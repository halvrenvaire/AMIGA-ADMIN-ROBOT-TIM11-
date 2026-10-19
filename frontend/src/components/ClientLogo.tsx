import { useRef, useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";
import { api } from "../api";
import { SignatureImage } from "./Signature";
import { Alert } from "./ui";

const MAX_BYTES = 2 * 1024 * 1024;

/** Logo klien di kop Voucher Pengeluaran (feedback owner): pratinjau, unggah/ganti, hapus.
 *  `compact` untuk sel tabel (layar Klien System Admin). */
export function ClientLogo({ clientId, clientName, version, canEdit, compact = false, onChange }: {
  clientId: string; clientName: string; version: string | null; canEdit: boolean; compact?: boolean;
  onChange: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function pick(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { setError("Gunakan logo PNG, JPG, atau WEBP."); return; }
    if (file.size > MAX_BYTES) { setError("Logo maksimal 2 MB."); return; }
    const image = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    setBusy(true);
    try {
      await api.put(`/clients/${clientId}/logo`, { image });
      onChange();
    } catch (e) { setError((e as Error).message); } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    if (!confirm(`Hapus logo ${clientName}? Kop voucher kembali memakai nama perusahaan.`)) return;
    setBusy(true);
    try { await api.del(`/clients/${clientId}/logo`); onChange(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className={`client-logo${compact ? " compact" : ""}`}>
      <div className="client-logo-preview">
        {version ? <SignatureImage path={`/clients/${clientId}/logo`} version={version} alt={`Logo ${clientName}`} />
          : <span className="muted">{compact ? "Belum ada" : `Belum ada logo; kop voucher memakai nama "${clientName}".`}</span>}
      </div>
      {canEdit && (
        <div className="actions" style={{ gap: 6 }}>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden aria-label={`Logo ${clientName}`}
                 onChange={(e) => pick(e.target.files?.[0])} />
          <button className="btn sm" disabled={busy} onClick={() => input.current?.click()}>
            <ImagePlus /> {version ? "Ganti" : "Unggah"} logo
          </button>
          {version && <button className="btn ghost sm" disabled={busy} onClick={remove} aria-label="Hapus logo"><Trash2 /></button>}
        </div>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
