import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Eraser, ImageUp, PenLine } from "lucide-react";
import { api } from "../api";
import { Alert, Modal } from "./ui";

const MAX_UPLOAD_MB = 2;

/** Gambar spesimen tanda tangan dari endpoint yang butuh token. `version` memaksa muat ulang setelah diganti. */
export function SignatureImage({ path, version, alt }: { path: string; version: string | null; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!version) { setUrl(null); return; }
    let objectUrl: string | null = null;
    api.blob(path).then((b) => { objectUrl = URL.createObjectURL(b); setUrl(objectUrl); }).catch(() => setUrl(null));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path, version]);
  if (!version) return <span className="sig-empty">Belum ada</span>;
  return url ? <img className="sig-img" src={url} alt={alt} /> : <span className="sig-empty">Memuat…</span>;
}

/** Goreskan tanda tangan di layar atau unggah gambar (PNG/JPG). Server merapikan dan menyimpannya sebagai PNG. */
export function SignatureModal({ title, signer, onSave, onClose }: {
  title: string; signer: string; onSave: (image: string) => Promise<void>; onClose: () => void;
}) {
  const [mode, setMode] = useState<"draw" | "upload">("draw");
  const [drawn, setDrawn] = useState(false);
  const [upload, setUpload] = useState<string | null>(null);
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const last = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || mode !== "draw") return;
    // Resolusi mengikuti layar supaya goresan tajam
    const ratio = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * ratio;
    canvas.height = canvas.clientHeight * ratio;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.6;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#13233f";
    setDrawn(false);
  }, [mode]);

  const point = (e: PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    last.current = point(e);
    const ctx = e.currentTarget.getContext("2d")!;
    ctx.beginPath();
    ctx.arc(last.current.x, last.current.y, 1.2, 0, Math.PI * 2);
    ctx.fillStyle = "#13233f";
    ctx.fill();
    setDrawn(true);
  };
  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!last.current) return;
    const p = point(e);
    const ctx = e.currentTarget.getContext("2d")!;
    ctx.beginPath();
    ctx.moveTo(last.current.x, last.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last.current = p;
  };
  const up = () => { last.current = null; };
  const clear = () => {
    const canvas = canvasRef.current!;
    canvas.getContext("2d")!.clearRect(0, 0, canvas.width, canvas.height);
    setDrawn(false);
  };

  function pick(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (!/^image\/(png|jpeg)$/.test(file.type)) { setError("Gunakan gambar PNG atau JPG."); return; }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) { setError(`Ukuran gambar maksimal ${MAX_UPLOAD_MB} MB.`); return; }
    const reader = new FileReader();
    reader.onload = () => setUpload(String(reader.result));
    reader.readAsDataURL(file);
  }

  const image = mode === "draw" ? (drawn ? "canvas" : null) : upload;
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave(mode === "draw" ? canvasRef.current!.toDataURL("image/png") : upload!);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <div className="seg" role="group" aria-label="Cara mengisi tanda tangan" style={{ alignSelf: "flex-start" }}>
        <button type="button" aria-pressed={mode === "draw"} onClick={() => setMode("draw")}><PenLine /> Goreskan</button>
        <button type="button" aria-pressed={mode === "upload"} onClick={() => setMode("upload")}><ImageUp /> Unggah gambar</button>
      </div>
      {mode === "draw" ? (
        <div className="sig-pad">
          <canvas ref={canvasRef} aria-label="Area tanda tangan" onPointerDown={down} onPointerMove={move}
                  onPointerUp={up} onPointerLeave={up} onPointerCancel={up} />
          {!drawn && <span className="sig-hint">Goreskan tanda tangan di sini dengan mouse, touchpad, atau jari</span>}
          <button type="button" className="btn ghost sm" onClick={clear} disabled={!drawn}><Eraser /> Ulangi</button>
        </div>
      ) : (
        <label className="sig-pad upload">
          {upload ? <img src={upload} alt="Pratinjau tanda tangan" /> : (
            <span className="sig-hint">Pilih foto atau scan tanda tangan di kertas putih (PNG/JPG, maks. {MAX_UPLOAD_MB} MB)</span>
          )}
          <input type="file" accept="image/png,image/jpeg" hidden onChange={(e) => pick(e.target.files?.[0])} />
        </label>
      )}
      <small className="muted">Latar putih otomatis dibuang dan gambar dipotong ke goresan sebelum disimpan.</small>
      <label className="toggle" style={{ alignItems: "flex-start" }}>
        <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 3 }} />
        <span>Ini tanda tangan <b>{signer}</b>, dan yang bersangkutan setuju tanda tangan ini dibubuhkan otomatis pada
          voucher yang mencantumkan namanya.</span>
      </label>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || !image || !agree} onClick={save}>{busy ? "Menyimpan…" : "Simpan tanda tangan"}</button>
      </div>
    </Modal>
  );
}
