import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import { api } from "../api";
import { STATUS_LABEL } from "../format";
import type { DocStatus } from "../types";

export function StatusBadge({ status }: { status: DocStatus }) {
  return <span className={`badge ${status}`} title={status}>{STATUS_LABEL[status]}</span>;
}

export function Alert({ kind = "error", children }: { kind?: "error" | "info" | "ok" | "warn"; children: ReactNode }) {
  const Icon = kind === "ok" ? CheckCircle2 : kind === "info" ? Info : AlertCircle;
  return <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}><Icon /><div>{children}</div></div>;
}

export function Loading({ label = "Memuat…" }: { label?: string }) {
  return <div className="empty"><Loader2 className="spin" size={18} style={{ verticalAlign: "-4px" }} /> {label}</div>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="panel-head">
          <h2>{title}</h2>
          <button className="btn ghost sm" onClick={onClose} aria-label="Tutup"><X /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Memuat data dari API; `reload` untuk memuat ulang, `setData` untuk memperbarui setelah aksi. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, setData, error, loading, reload };
}

/** PDF dari endpoint yang butuh token: diunduh sebagai blob lalu ditampilkan di iframe. */
export function PdfFrame({ path, title }: { path: string; title: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let objectUrl: string | null = null;
    setUrl(null);
    setError(null);
    api.blob(path)
      .then((blob) => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); })
      .catch((e: Error) => setError(e.message));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path]);
  if (error) return <div style={{ padding: 16 }}><Alert>{error}</Alert></div>;
  if (!url) return <Loading label="Memuat PDF…" />;
  return <iframe src={url} title={title} />;
}

export function initials(name: string) {
  return name.replace(/\(.*?\)/g, "").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");
}
