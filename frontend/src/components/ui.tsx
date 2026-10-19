import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertCircle, Check, CheckCircle2, ChevronDown, Info, Loader2, Search, X } from "lucide-react";
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

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
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

export interface SelectOption { value: string; label: string; disabled?: string | null }

/** Pilihan ganda dalam satu kontrol: chip untuk yang terpilih, daftar dengan pencarian untuk memilih.
 *  `disabled` pada opsi berisi alasan opsi tidak bisa dipilih (ditampilkan di daftar). */
export function MultiSelect({ id, options, value, onChange, placeholder = "Pilih…", bulk = false }: {
  id?: string; options: SelectOption[]; value: string[]; onChange: (v: string[]) => void;
  placeholder?: string; bulk?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchable = options.length > 6;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!rootRef.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const label = (v: string) => options.find((o) => o.value === v)?.label ?? v;
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  const shown = options.filter((o) => o.label.toLowerCase().includes(q.trim().toLowerCase()));
  const selectable = shown.filter((o) => !o.disabled).map((o) => o.value);

  return (
    <div className="ms" ref={rootRef}
         onKeyDown={(e) => { if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); } }}>
      <div className={`ms-control${open ? " open" : ""}`} onClick={() => setOpen((o) => !o)}>
        <div className="ms-values">
          {value.length === 0 && <span className="ms-placeholder">{placeholder}</span>}
          {value.map((v) => (
            <span key={v} className="ms-chip">
              {label(v)}
              <button type="button" aria-label={`Hapus ${label(v)}`}
                      onClick={(e) => { e.stopPropagation(); toggle(v); }}><X size={12} /></button>
            </span>
          ))}
        </div>
        <button type="button" id={id} className="ms-caret" aria-haspopup="listbox" aria-expanded={open}
                aria-label={open ? "Tutup pilihan" : "Buka pilihan"}><ChevronDown size={16} /></button>
      </div>
      {open && (
        <div className="ms-menu">
          {searchable && (
            <div className="ms-search">
              <Search size={14} />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari…" aria-label="Cari pilihan" />
            </div>
          )}
          {bulk && (
            <div className="ms-bulk">
              <span>{value.length} dipilih</span>
              <button type="button" onClick={() => onChange([...new Set([...value, ...selectable])])}>Pilih semua</button>
              <button type="button" disabled={!value.length} onClick={() => onChange([])}>Kosongkan</button>
            </div>
          )}
          <ul role="listbox" aria-multiselectable="true">
            {shown.map((o) => {
              const on = value.includes(o.value);
              return (
                <li key={o.value} role="option" aria-selected={on} aria-disabled={!!o.disabled && !on}
                    className={o.disabled && !on ? "off" : undefined}
                    tabIndex={0} onClick={() => (!o.disabled || on) && toggle(o.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (!o.disabled || on) toggle(o.value); }
                    }}>
                  <span className={`ms-box${on ? " on" : ""}`}>{on && <Check size={12} />}</span>
                  <span className="ms-label">{o.label}{o.disabled && !on && <small>{o.disabled}</small>}</span>
                </li>
              );
            })}
            {shown.length === 0 && <li className="off">Tidak ada yang cocok</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
