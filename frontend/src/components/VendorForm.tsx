import { useEffect, useState, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../api";
import type { Vendor } from "../types";
import { Alert, Modal } from "./ui";

export const VENDOR_FIELDS: { key: keyof Vendor; label: string; hint?: string; wide?: boolean }[] = [
  { key: "name", label: "Nama perusahaan vendor", wide: true },
  { key: "npwp", label: "NPWP", hint: "mis. 01.234.567.8-901.000. Kosongkan bila vendor tidak punya NPWP (tarif PPh lebih tinggi)." },
  { key: "contact_name", label: "Nama kontak" },
  { key: "phone", label: "Telepon" },
  { key: "email", label: "Email" },
  { key: "address", label: "Alamat", wide: true },
  { key: "bank_name", label: "Nama bank" },
  { key: "account_no", label: "Nomor rekening" },
  { key: "account_name", label: "Nama penerima" },
  { key: "notes", label: "Catatan", wide: true },
];

/** Tambah atau ubah vendor di Data Referensi. `prefill` mengisi kolom awal (mis. dari data invoice); `intro`
 *  tampil di atas formulir. Dipakai di halaman Data Referensi dan dari layar dokumen. */
export function VendorModal({ vendor, clientId, prefill, intro, onClose, onDone }: {
  vendor: Vendor | null; clientId: string; prefill?: Partial<Record<keyof Vendor, string | null>>; intro?: ReactNode;
  onClose: () => void; onDone: (saved: Vendor) => void;
}) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(VENDOR_FIELDS.map((f) => [f.key, (prefill?.[f.key] ?? (vendor?.[f.key] as string | null)) ?? ""])));
  const [existing, setExisting] = useState<Vendor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Cek nama langsung saat diketik: bila sudah ada, pengguna tidak perlu menambahkan
  useEffect(() => {
    const name = form.name.trim();
    if (name.length < 2) { setExisting(null); return; }
    const timer = setTimeout(() => {
      api.get<{ exists: boolean; vendor: Vendor | null }>("/vendors/check", { client_id: vendor?.client.id ?? clientId, name })
        .then((r) => setExisting(r.vendor && r.vendor.id !== vendor?.id ? r.vendor : null))
        .catch(() => setExisting(null));
    }, 300);
    return () => clearTimeout(timer);
  }, [form.name, clientId, vendor]);

  async function submit() {
    setBusy(true);
    setError(null);
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]));
    try {
      onDone(vendor ? await api.put<Vendor>(`/vendors/${vendor.id}`, body)
                    : await api.post<Vendor>("/vendors", { ...body, client_id: clientId }));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={vendor ? `Ubah ${vendor.name}` : "Tambah vendor"} onClose={onClose}>
      {intro}
      {error && <Alert>{error}</Alert>}
      {existing && (
        <Alert kind="info">
          <span><b>{existing.name}</b> sudah terdaftar{existing.is_active ? "" : " (nonaktif)"}. Tidak perlu ditambahkan lagi;
            gunakan data yang ada atau ubah datanya dari tabel.</span>
        </Alert>
      )}
      <div className="grid-2">
        {VENDOR_FIELDS.map((f) => (
          <div key={f.key} className="field" style={f.wide ? { gridColumn: "1 / -1" } : undefined}>
            <label htmlFor={`v-${f.key}`}>{f.label}{f.key === "name" && " *"}</label>
            {f.key === "address" || f.key === "notes" ? (
              <textarea id={`v-${f.key}`} className="input" style={{ minHeight: 56 }} value={form[f.key]}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            ) : (
              <input id={`v-${f.key}`} className={`input ${f.key === "account_no" || f.key === "npwp" ? "mono" : ""}`} value={form[f.key]}
                     placeholder={f.hint} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
            )}
          </div>
        ))}
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || form.name.trim().length < 2 || Boolean(existing)} onClick={submit}>Simpan</button>
      </div>
    </Modal>
  );
}

/** Finance Reviewer memverifikasi rekening vendor setelah mengeceknya ke sumber tepercaya. */
export function VerifyVendorModal({ vendor, onClose, onDone }: {
  vendor: Pick<Vendor, "id" | "name" | "bank_name" | "account_no" | "account_name">; onClose: () => void; onDone: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`Verifikasi rekening ${vendor.name}`} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <dl className="meta">
        <dt>Bank</dt><dd>{vendor.bank_name ?? "-"}</dd>
        <dt>No. rekening</dt><dd className="mono">{vendor.account_no ?? "-"}</dd>
        <dt>Atas nama</dt><dd>{vendor.account_name ?? "-"}</dd>
      </dl>
      <Alert kind="warn">
        Verifikasi hanya setelah rekening dicek ke sumber tepercaya, mis. konfirmasi langsung ke vendor lewat kontak resmi,
        bukan dari invoice atau isian PIC. Tindakan ini tercatat di jejak audit atas nama Anda.
      </Alert>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy} onClick={async () => {
          setError(null);
          setBusy(true);
          try { await api.post(`/vendors/${vendor.id}/verify`); onDone(); }
          catch (e) { setError((e as Error).message); setBusy(false); }
        }}><ShieldCheck /> Rekening sudah saya cek</button>
      </div>
    </Modal>
  );
}
