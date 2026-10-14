import { useEffect, useState } from "react";
import { Building2, Pencil, Plus, Star } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, Modal, useApi } from "../components/ui";
import type { ClientRef, Signatory, SignatoryKind, Vendor } from "../types";

const VENDOR_FIELDS: { key: keyof Vendor; label: string; hint?: string; wide?: boolean }[] = [
  { key: "name", label: "Nama perusahaan vendor", wide: true },
  { key: "npwp", label: "NPWP", hint: "mis. 01.234.567.8-901.000" },
  { key: "contact_name", label: "Nama kontak" },
  { key: "phone", label: "Telepon" },
  { key: "email", label: "Email" },
  { key: "address", label: "Alamat", wide: true },
  { key: "bank_name", label: "Nama bank" },
  { key: "account_no", label: "Nomor rekening" },
  { key: "account_name", label: "Nama penerima" },
  { key: "notes", label: "Catatan", wide: true },
];

/** Pilihan klien untuk pengguna yang ditugaskan ke lebih dari satu klien. */
function ClientPicker({ clients, value, onChange }: { clients: ClientRef[]; value: string; onChange: (v: string) => void }) {
  if (clients.length <= 1) return null;
  return (
    <select className="input" style={{ width: "auto" }} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Klien">
      {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  );
}

// --- Vendor ---

export function Vendors() {
  const { user, has } = useAuth();
  const clients = user?.clients ?? [];
  const [clientId, setClientId] = useState(clients[0]?.id ?? "");
  const [q, setQ] = useState("");
  const [inactive, setInactive] = useState(false);
  const [editing, setEditing] = useState<Vendor | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canEdit = has("PIC_KLIEN", "INTAKE_SUPPORT");
  const vendors = useApi(() => api.get<Vendor[]>("/vendors", { client_id: clientId, q, include_inactive: inactive }),
    [clientId, q, inactive]);

  async function toggle(v: Vendor) {
    setError(null);
    try {
      await api.patch(`/vendors/${v.id}/active`, { is_active: !v.is_active });
      vendors.reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data vendor</h1>
          <p>Data referensi perusahaan vendor. Nama yang sudah terdaftar tidak perlu ditambahkan lagi.</p>
        </div>
        <div className="actions">
          <ClientPicker clients={clients} value={clientId} onChange={setClientId} />
          {canEdit && <button className="btn primary" onClick={() => setEditing("new")}><Plus /> Tambah vendor</button>}
        </div>
      </div>
      {(error || vendors.error) && <Alert>{error ?? vendors.error}</Alert>}
      <section className="card panel">
        <div className="filters">
          <input className="input" placeholder="Cari nama atau NPWP" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 260 }} />
          <label className="toggle"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> Tampilkan nonaktif</label>
        </div>
        {vendors.loading && !vendors.data ? <Loading /> : !vendors.data?.length ? (
          <div className="empty"><Building2 size={22} /><br />Belum ada vendor{q ? " yang cocok" : ""}.
            {canEdit && !q && <> Tambahkan vendor yang sering menagih klien ini.</>}</div>
        ) : (
          <div className="table-wrap">
            <table className="table docs">
              <thead><tr><th>Vendor</th><th>NPWP</th><th>Kontak</th><th>Rekening</th><th className="right">Dokumen</th><th>Status</th>{canEdit && <th className="right">Aksi</th>}</tr></thead>
              <tbody>
                {vendors.data.map((v) => (
                  <tr key={v.id} style={v.is_active ? undefined : { opacity: 0.55 }}>
                    <td className="vendor"><b>{v.name}</b>{v.address && <div className="muted" style={{ fontSize: 12 }}>{v.address}</div>}</td>
                    <td className="mono">{v.npwp ?? "-"}</td>
                    <td className="wrap">{v.contact_name ?? "-"}{v.phone && <div className="muted" style={{ fontSize: 12 }}>{v.phone}</div>}</td>
                    <td className="wrap">{v.bank_name ?? "-"}{v.account_no && <div className="mono">{v.account_no}</div>}</td>
                    <td className="right num">{v.documents}</td>
                    <td>{v.is_active ? <span className="chip ok">Aktif</span> : <span className="chip gray">Nonaktif</span>}</td>
                    {canEdit && (
                      <td className="right">
                        <span className="actions" style={{ justifyContent: "flex-end" }}>
                          <button className="btn sm" onClick={() => setEditing(v)}><Pencil /> Ubah</button>
                          <button className="btn sm" onClick={() => toggle(v)}>{v.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
                        </span>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {editing && (
        <VendorModal vendor={editing === "new" ? null : editing} clientId={clientId}
                     onClose={() => setEditing(null)} onDone={() => { setEditing(null); vendors.reload(); }} />
      )}
    </>
  );
}

function VendorModal({ vendor, clientId, onClose, onDone }: {
  vendor: Vendor | null; clientId: string; onClose: () => void; onDone: () => void;
}) {
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(VENDOR_FIELDS.map((f) => [f.key, (vendor?.[f.key] as string | null) ?? ""])));
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
      if (vendor) await api.put(`/vendors/${vendor.id}`, body);
      else await api.post("/vendors", { ...body, client_id: clientId });
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={vendor ? `Ubah ${vendor.name}` : "Tambah vendor"} onClose={onClose}>
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

// --- Penanda tangan ---

const KIND_LABEL: Record<SignatoryKind, string> = { PENGAJU: "Diajukan oleh", PENYETUJU: "Disetujui oleh" };
const KIND_NOTE: Record<SignatoryKind, string> = {
  PENGAJU: "Pihak PIC Klien yang mengajukan pembayaran. Satu default.",
  PENYETUJU: "Direktur, bendahara, atau pejabat lain yang menyetujui. Boleh beberapa default (maks. 3 di voucher).",
};

export function Signatories() {
  const { user, has } = useAuth();
  const clients = user?.clients ?? [];
  const [clientId, setClientId] = useState(clients[0]?.id ?? "");
  const [editing, setEditing] = useState<Signatory | { kind: SignatoryKind } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canEdit = has("PIC_KLIEN");
  const list = useApi(() => api.get<Signatory[]>("/signatories", { client_id: clientId, include_inactive: true }), [clientId]);

  async function toggle(s: Signatory) {
    setError(null);
    try {
      await api.patch(`/signatories/${s.id}/active`, { is_active: !s.is_active });
      list.reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Penanda tangan voucher</h1>
          <p>Nama yang dicetak di kotak tanda tangan voucher. Penanda tangan default terpilih otomatis saat unggah invoice.</p>
        </div>
        <ClientPicker clients={clients} value={clientId} onChange={setClientId} />
      </div>
      {(error || list.error) && <Alert>{error ?? list.error}</Alert>}
      {list.loading && !list.data ? <Loading /> : (
        <div className="grid-2">
          {(["PENGAJU", "PENYETUJU"] as SignatoryKind[]).map((kind) => {
            const items = (list.data ?? []).filter((s) => s.kind === kind);
            return (
              <section key={kind} className="card panel">
                <div className="panel-head">
                  <div><h2>{KIND_LABEL[kind]}</h2><p>{KIND_NOTE[kind]}</p></div>
                  {canEdit && <button className="btn sm" onClick={() => setEditing({ kind })}><Plus /> Tambah</button>}
                </div>
                {!items.length ? <p className="muted" style={{ margin: 0 }}>Belum ada. Kotak akan dicetak kosong di voucher.</p> : (
                  <table className="table compact">
                    <tbody>
                      {items.map((s) => (
                        <tr key={s.id} style={s.is_active ? undefined : { opacity: 0.55 }}>
                          <td><b>{s.full_name}</b><div className="muted" style={{ fontSize: 12 }}>{s.position}</div></td>
                          <td>{s.is_default && s.is_active && <span className="chip ok"><Star size={11} /> Default</span>}
                            {!s.is_active && <span className="chip gray">Nonaktif</span>}</td>
                          {canEdit && (
                            <td className="right">
                              <span className="actions" style={{ justifyContent: "flex-end" }}>
                                <button className="btn sm" onClick={() => setEditing(s)}>Ubah</button>
                                <button className="btn sm" onClick={() => toggle(s)}>{s.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
                              </span>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
            );
          })}
        </div>
      )}
      {editing && (
        <SignatoryModal value={editing} clientId={clientId} onClose={() => setEditing(null)}
                        onDone={() => { setEditing(null); list.reload(); }} />
      )}
    </>
  );
}

function SignatoryModal({ value, clientId, onClose, onDone }: {
  value: Signatory | { kind: SignatoryKind }; clientId: string; onClose: () => void; onDone: () => void;
}) {
  const existing = "id" in value ? value : null;
  const [kind, setKind] = useState<SignatoryKind>(value.kind);
  const [name, setName] = useState(existing?.full_name ?? "");
  const [position, setPosition] = useState(existing?.position ?? "");
  const [isDefault, setIsDefault] = useState(existing?.is_default ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    const body = { kind, full_name: name.trim(), position: position.trim(), is_default: isDefault };
    try {
      if (existing) await api.put(`/signatories/${existing.id}`, body);
      else await api.post("/signatories", { ...body, client_id: clientId });
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Modal title={existing ? `Ubah ${existing.full_name}` : `Tambah penanda tangan`} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <div className="field">
        <label htmlFor="s-kind">Kotak tanda tangan</label>
        <select id="s-kind" className="input" value={kind} onChange={(e) => setKind(e.target.value as SignatoryKind)}>
          <option value="PENGAJU">Diajukan oleh</option>
          <option value="PENYETUJU">Disetujui oleh</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="s-name">Nama lengkap</label>
        <input id="s-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="s-pos">Jabatan</label>
        <input id="s-pos" className="input" value={position} placeholder={kind === "PENGAJU" ? "mis. Staf Keuangan" : "mis. Direktur, Bendahara"}
               onChange={(e) => setPosition(e.target.value)} />
      </div>
      <label className="toggle"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
        Jadikan default (otomatis terpilih saat unggah invoice)</label>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || name.trim().length < 2 || position.trim().length < 2} onClick={submit}>Simpan</button>
      </div>
    </Modal>
  );
}
