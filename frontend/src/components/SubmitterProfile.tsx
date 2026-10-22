import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ImageUp, Lock, X } from "lucide-react";

export const SIGNATURE_MAX_MB = 2;
const SIGNATURE_ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";

export type SubmitterSource = "PIC" | "MANUAL";

export type SubmitterProfile = {
  /** PIC = profil akun PIC Klien (dikunci, termasuk tanda tangan); MANUAL = diisi di sini, tidak diingat. */
  source: SubmitterSource;
  name: string; position: string; company: string;
  /** Mode manual: gambar tanda tangan; null = tanpa tanda tangan (diisi basah). */
  signature: File | null;
};

export const EMPTY_PROFILE: SubmitterProfile = { source: "PIC", name: "", position: "", company: "", signature: null };

/** Profil PIC Klien yang dikunci. `null` = diisi server dari PIC yang mendelegasikan (Intake Support). */
export type LockedProfile = { name: string; position: string; company: string; signature: ReactNode } | null;

/** Pilihan "Diisi PIC Klien" / "Diisi manual" (dipakai juga di halaman detail). */
export function SourceToggle({ value, onChange }: { value: SubmitterSource; onChange: (s: SubmitterSource) => void }) {
  return (
    <div className="source-toggle" role="radiogroup" aria-label="Sumber data Diajukan oleh">
      {(["PIC", "MANUAL"] as const).map((s) => (
        <button key={s} type="button" role="radio" aria-checked={value === s} className={value === s ? "on" : ""}
                onClick={() => onChange(s)}>{s === "PIC" ? "Diisi PIC Klien" : "Diisi manual"}</button>
      ))}
    </div>
  );
}

/** Profil PIC Klien yang dikunci: nama, jabatan, perusahaan/unit, dan tanda tangan dari halaman Akun. */
export function LockedProfileView({ pic, accountLink }: { pic: LockedProfile; accountLink: boolean }) {
  if (!pic) {
    return <p className="muted" style={{ margin: 0, fontSize: 13 }}>
      Diisi otomatis dari profil PIC Klien yang mendelegasikan (nama, jabatan, perusahaan, dan tanda tangannya).
    </p>;
  }
  return (
    <>
      <dl className="pic-profile">
        <div><dt>Nama</dt><dd>{pic.name || "-"}</dd></div>
        <div><dt>Jabatan</dt><dd>{pic.position || "-"}</dd></div>
        <div><dt>Perusahaan / unit</dt><dd>{pic.company || "-"}</dd></div>
      </dl>
      <div className="sig-row">
        <div className="sig-box">{pic.signature}</div>
        <small className="muted"><Lock size={12} /> Terkunci ke profil akun.{" "}
          {accountLink ? <>Ubah di <Link to="/akun">halaman Akun</Link>.</> : "Pilih \"Diisi manual\" untuk mengganti."}</small>
      </div>
    </>
  );
}

/** Unggah gambar tanda tangan (PNG/JPG/WEBP) untuk mode manual. */
export function SignatureUpload({ file, onChange }: { file: File | null; onChange: (f: File | null) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function pick(picked: File | undefined) {
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
    if (!picked) return;
    if (!/\.(png|jpe?g|webp)$/i.test(picked.name) && !["image/png", "image/jpeg", "image/webp"].includes(picked.type)) {
      setError("Tanda tangan harus berupa gambar PNG, JPG, atau WEBP."); return;
    }
    if (picked.size > SIGNATURE_MAX_MB * 1024 * 1024) { setError(`Ukuran gambar maksimal ${SIGNATURE_MAX_MB} MB.`); return; }
    onChange(picked);
  }

  return (
    <div className="field">
      <label>Tanda tangan <span className="muted">(opsional)</span></label>
      <div className="sig-row">
        <div className="sig-box">
          {preview ? <img className="sig-img" src={preview} alt="Tanda tangan" />
            : <span className="sig-empty">Tanpa tanda tangan (diisi basah)</span>}
        </div>
        <div className="sig-actions">
          <button type="button" className="btn sm" onClick={() => inputRef.current?.click()}>
            <ImageUp /> {file ? "Ganti gambar" : "Unggah gambar"}
          </button>
          {file && <button type="button" className="btn ghost sm" onClick={() => onChange(null)}><X /> Hapus</button>}
        </div>
      </div>
      <small>PNG, JPG, atau WEBP, maks. {SIGNATURE_MAX_MB} MB. Hanya untuk pengajuan ini.</small>
      {error && <small className="error-text">{error}</small>}
      <input ref={inputRef} type="file" accept={SIGNATURE_ACCEPT} hidden onChange={(e) => pick(e.target.files?.[0])} />
    </div>
  );
}

/** Isian "Diajukan oleh" di layar Pembuatan Voucher: profil PIC Klien (dikunci) atau diisi manual. */
export function SubmitterProfileFields({ value, onChange, pic, accountLink }: {
  value: SubmitterProfile; onChange: (next: SubmitterProfile) => void; pic: LockedProfile; accountLink: boolean;
}) {
  const set = (patch: Partial<SubmitterProfile>) => onChange({ ...value, ...patch });
  return (
    <div className="submitter-profile">
      <SourceToggle value={value.source} onChange={(source) => set({ source })} />
      {value.source === "PIC" ? <LockedProfileView pic={pic} accountLink={accountLink} /> : (
        <>
          <div className="grid-3">
            <div className="field">
              <label htmlFor="sub-name">Nama</label>
              <input id="sub-name" className="input" required maxLength={200} value={value.name}
                     onChange={(e) => set({ name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sub-position">Jabatan</label>
              <input id="sub-position" className="input" maxLength={120} value={value.position}
                     onChange={(e) => set({ position: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sub-company">Perusahaan / unit</label>
              <input id="sub-company" className="input" maxLength={200} value={value.company}
                     placeholder="Kosongkan = nama perusahaan" onChange={(e) => set({ company: e.target.value })} />
            </div>
          </div>
          <SignatureUpload file={value.signature} onChange={(signature) => set({ signature })} />
          <small className="muted">Isian manual tidak disimpan untuk pengajuan berikutnya.</small>
        </>
      )}
    </div>
  );
}
