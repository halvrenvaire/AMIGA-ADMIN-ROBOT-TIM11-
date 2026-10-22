import { useEffect, useRef, useState } from "react";
import { ImageUp, X } from "lucide-react";
import { SignatureImage } from "./Signature";

export const SIGNATURE_MAX_MB = 2;
const SIGNATURE_ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";

export type SubmitterProfile = {
  name: string; position: string; company: string;
  /** Gambar tanda tangan baru; null = pakai yang tersimpan (bila `useSaved`) atau tanpa tanda tangan */
  signature: File | null; useSaved: boolean;
};

/** Isian profil "Diajukan oleh": nama, jabatan, perusahaan/unit, dan tanda tangan (PNG/JPG/WEBP).
 *  Profil terakhir PIC diisikan otomatis; tanda tangan tersimpan hanya dipakai untuk nama pemiliknya. */
export function SubmitterProfileFields({ value, onChange, placeholderName, savedName, savedSignature }: {
  value: SubmitterProfile; onChange: (next: SubmitterProfile) => void;
  placeholderName?: string; savedName?: string; savedSignature?: string | null;
}) {
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const set = (patch: Partial<SubmitterProfile>) => onChange({ ...value, ...patch });

  useEffect(() => {
    if (!value.signature) { setPreview(null); return; }
    const url = URL.createObjectURL(value.signature);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [value.signature]);

  function pick(file: File | undefined) {
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    if (!/\.(png|jpe?g|webp)$/i.test(file.name) && !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setError("Tanda tangan harus berupa gambar PNG, JPG, atau WEBP."); return;
    }
    if (file.size > SIGNATURE_MAX_MB * 1024 * 1024) { setError(`Ukuran gambar maksimal ${SIGNATURE_MAX_MB} MB.`); return; }
    set({ signature: file });
  }

  // Tanda tangan tersimpan berlaku bila nama sama dengan profil tersimpan (atau dikosongkan = nama tersimpan)
  const ownsSaved = Boolean(savedSignature) && (!value.name.trim() || value.name.trim() === (savedName ?? "").trim());
  const showSaved = !value.signature && value.useSaved && ownsSaved;

  return (
    <div className="submitter-profile">
      <div className="grid-3">
        <div className="field">
          <label htmlFor="sub-name">Nama</label>
          <input id="sub-name" className="input" maxLength={200} value={value.name} placeholder={placeholderName}
                 onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="sub-position">Jabatan</label>
          <input id="sub-position" className="input" maxLength={120} value={value.position} placeholder="PIC Klien"
                 onChange={(e) => set({ position: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="sub-company">Perusahaan / unit</label>
          <input id="sub-company" className="input" maxLength={200} value={value.company}
                 placeholder="Kosongkan = nama perusahaan" onChange={(e) => set({ company: e.target.value })} />
        </div>
      </div>
      <div className="field">
        <label>Tanda tangan <span className="muted">(opsional)</span></label>
        <div className="sig-row">
          <div className="sig-box">
            {preview ? <img className="sig-img" src={preview} alt="Tanda tangan baru" />
              : showSaved ? <SignatureImage path="/auth/me/signature" version={savedSignature ?? null} alt="Tanda tangan tersimpan" />
              : <span className="sig-empty">Tanpa tanda tangan (diisi basah)</span>}
          </div>
          <div className="sig-actions">
            <button type="button" className="btn sm" onClick={() => inputRef.current?.click()}>
              <ImageUp /> {value.signature || showSaved ? "Ganti gambar" : "Unggah gambar"}
            </button>
            {(value.signature || showSaved) && (
              <button type="button" className="btn ghost sm"
                      onClick={() => set(value.signature ? { signature: null } : { useSaved: false })}><X /> Hapus</button>
            )}
            {!value.signature && !value.useSaved && ownsSaved && (
              <button type="button" className="btn ghost sm" onClick={() => set({ useSaved: true })}>Pakai yang tersimpan</button>
            )}
          </div>
        </div>
        <small>PNG, JPG, atau WEBP, maks. {SIGNATURE_MAX_MB} MB. Profil dan tanda tangan diingat untuk pengajuan berikutnya.</small>
        {error && <small className="error-text">{error}</small>}
      </div>
      <input ref={inputRef} type="file" accept={SIGNATURE_ACCEPT} hidden onChange={(e) => pick(e.target.files?.[0])} />
    </div>
  );
}
