import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, PenLine, Pencil, Plus, ShieldCheck, Star } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignatureImage, SignatureModal } from "../components/Signature";
import { Alert, Loading, Modal, useApi } from "../components/ui";
import type { ClientRef, Me, Signatory, Vendor } from "../types";

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
  const canVerify = has("FINANCE_REVIEWER");
  const [verifying, setVerifying] = useState<Vendor | null>(null);
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
      <Alert kind="info">
        Rekening vendor menjadi acuan tepercaya setelah <b>diverifikasi Finance Reviewer</b> (bukan pendaftarnya). Invoice
        dengan rekening berbeda dari data terverifikasi otomatis ditahan; mengubah data bank membatalkan verifikasi.
      </Alert>
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
              <thead><tr><th>Vendor</th><th>NPWP</th><th>Kontak</th><th>Rekening</th><th className="right">Dokumen</th><th>Status</th>{(canEdit || canVerify) && <th className="right">Aksi</th>}</tr></thead>
              <tbody>
                {vendors.data.map((v) => (
                  <tr key={v.id} style={v.is_active ? undefined : { opacity: 0.55 }}>
                    <td className="vendor"><b>{v.name}</b>{v.address && <div className="muted" style={{ fontSize: 12 }}>{v.address}</div>}</td>
                    <td className="mono">{v.npwp ?? "-"}</td>
                    <td className="wrap">{v.contact_name ?? "-"}{v.phone && <div className="muted" style={{ fontSize: 12 }}>{v.phone}</div>}</td>
                    <td className="wrap">{v.bank_name ?? "-"}{v.account_no && <div className="mono">{v.account_no}</div>}
                      {v.account_no && (v.verified_at
                        ? <span className="chip ok" title={`Diverifikasi ${v.verified_by ?? ""}`}><ShieldCheck size={11} /> Terverifikasi</span>
                        : <span className="chip warn">Belum diverifikasi</span>)}</td>
                    <td className="right num">{v.documents}</td>
                    <td>{v.is_active ? <span className="chip ok">Aktif</span> : <span className="chip gray">Nonaktif</span>}</td>
                    {(canEdit || canVerify) && (
                      <td className="right">
                        <span className="actions" style={{ justifyContent: "flex-end" }}>
                          {canVerify && !v.verified_at && v.is_active && v.account_no && (
                            <button className="btn sm" onClick={() => setVerifying(v)}><ShieldCheck /> Verifikasi rekening</button>
                          )}
                          {canEdit && <button className="btn sm" onClick={() => setEditing(v)}><Pencil /> Ubah</button>}
                          {canEdit && <button className="btn sm" onClick={() => toggle(v)}>{v.is_active ? "Nonaktifkan" : "Aktifkan"}</button>}
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
      {verifying && (
        <Modal title={`Verifikasi rekening ${verifying.name}`} onClose={() => setVerifying(null)}>
          {error && <Alert>{error}</Alert>}
          <dl className="meta">
            <dt>Bank</dt><dd>{verifying.bank_name ?? "-"}</dd>
            <dt>No. rekening</dt><dd className="mono">{verifying.account_no ?? "-"}</dd>
            <dt>Atas nama</dt><dd>{verifying.account_name ?? "-"}</dd>
          </dl>
          <Alert kind="warn">
            Verifikasi hanya setelah rekening dicek ke sumber tepercaya, mis. konfirmasi langsung ke vendor lewat kontak resmi,
            bukan dari invoice atau isian PIC. Tindakan ini tercatat di jejak audit atas nama Anda.
          </Alert>
          <div className="actions" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={() => setVerifying(null)}>Batal</button>
            <button className="btn primary" onClick={async () => {
              setError(null);
              try { await api.post(`/vendors/${verifying.id}/verify`); setVerifying(null); vendors.reload(); }
              catch (e) { setError((e as Error).message); }
            }}><ShieldCheck /> Rekening sudah saya cek</button>
          </div>
        </Modal>
      )}
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

export function Signatories() {
  const { user, has } = useAuth();
  const clients = user?.clients ?? [];
  const [clientId, setClientId] = useState(clients[0]?.id ?? "");
  const [editing, setEditing] = useState<Signatory | "new" | null>(null);
  const [signing, setSigning] = useState<Signatory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canEdit = has("PIC_KLIEN");
  const list = useApi(() => api.get<Signatory[]>("/signatories", { client_id: clientId, include_inactive: true }), [clientId]);
  const items = list.data ?? [];
  const clientName = clients.find((c) => c.id === clientId)?.name ?? "-";

  async function removeSignature(s: Signatory) {
    setError(null);
    try {
      await api.del(`/signatories/${s.id}/signature`);
      list.reload();
    } catch (e) { setError((e as Error).message); }
  }

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
          <p>Pemberi persetujuan yang bisa dipilih di kotak "Disetujui oleh". Yang default otomatis mengisi kotak pertama saat unggah.</p>
        </div>
        <ClientPicker clients={clients} value={clientId} onChange={setClientId} />
      </div>
      {(error || list.error) && <Alert>{error ?? list.error}</Alert>}
      {list.loading && !list.data ? <Loading /> : (
      <div className="with-aside">
        <section className="card panel">
          <div className="panel-head">
            <div><h2>Disetujui oleh</h2><p>Direktur, bendahara, atau pejabat lain yang menyetujui. Maks. 5 kotak per voucher.</p></div>
            {canEdit && <button className="btn sm" onClick={() => setEditing("new")}><Plus /> Tambah</button>}
          </div>
          {!items.length ? <p className="muted" style={{ margin: 0 }}>Belum ada. Kotak "Disetujui oleh" dicetak kosong di voucher.</p> : (
            <table className="table compact">
              <thead><tr><th>Nama</th><th>Status</th><th>Tanda tangan elektronik</th>{canEdit && <th className="right">Aksi</th>}</tr></thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} style={s.is_active ? undefined : { opacity: 0.55 }}>
                    <td><b>{s.full_name}</b><div className="muted" style={{ fontSize: 12 }}>{s.position}</div></td>
                    <td>{s.is_default && s.is_active && <span className="chip ok"><Star size={11} /> Default</span>}
                      {!s.is_active && <span className="chip gray">Nonaktif</span>}</td>
                    <td><SignatureImage path={`/signatories/${s.id}/signature`} version={s.signature_updated_at}
                                        alt={`Tanda tangan ${s.full_name}`} /></td>
                    {canEdit && (
                      <td className="right">
                        <span className="actions" style={{ justifyContent: "flex-end" }}>
                          <button className="btn sm" onClick={() => setSigning(s)}><PenLine />{s.signature_updated_at ? "Ganti TTD" : "Tanda tangan"}</button>
                          {s.signature_updated_at && <button className="btn sm" onClick={() => removeSignature(s)}>Hapus TTD</button>}
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
        <SignatureAside clientName={clientName} items={items} me={user} isPic={canEdit} />
      </div>
      )}
      {signing && (
        <SignatureModal title={`Tanda tangan ${signing.full_name}`} signer={`${signing.full_name} (${signing.position})`}
                        onClose={() => setSigning(null)}
                        onSave={async (image) => { await api.put(`/signatories/${signing.id}/signature`, { image }); setSigning(null); list.reload(); }} />
      )}
      {editing && (
        <SignatoryModal value={editing === "new" ? null : editing} clientId={clientId} onClose={() => setEditing(null)}
                        onDone={() => { setEditing(null); list.reload(); }} />
      )}
    </>
  );
}

/** Pratinjau baris tanda tangan di voucher, supaya PIC tahu hasil daftar ini di dokumen akhir. */
function SignatureAside({ clientName, items, me, isPic }: {
  clientName: string; items: Signatory[]; me: Me | null; isPic: boolean;
}) {
  const active = items.filter((s) => s.is_active);
  const first = active.find((s) => s.is_default) ?? active[0];
  const signed = active.filter((s) => s.signature_updated_at).length;
  return (
    <aside className="aside">
      <section className="card panel">
        <div className="panel-head"><div><h2>Pratinjau di voucher</h2><p>Baris tanda tangan saat unggah dengan pilihan default</p></div></div>
        <div className="sign-preview">
          <div>
            <span>Diajukan oleh</span>
            <i>{isPic && me && <SignatureImage path="/auth/me/signature" version={me.signature_updated_at ?? null} alt="Tanda tangan Anda" />}</i>
            <b>{isPic && me ? me.full_name : "Nama PIC pengaju"}</b><small>PIC Klien, {clientName}</small>
          </div>
          <div>
            <span>Disetujui oleh</span>
            <i>{first && <SignatureImage path={`/signatories/${first.id}/signature`} version={first.signature_updated_at} alt={`Tanda tangan ${first.full_name}`} />}</i>
            <b>{first?.full_name ?? "(kosong)"}</b><small>{first?.position ?? "diisi manual"}</small>
          </div>
        </div>
        <small className="muted">
          Kotak <b>Diajukan oleh</b> otomatis berisi PIC Klien yang mengajukan, jadi tidak perlu didaftarkan. Saat unggah,
          "Disetujui oleh" bisa ditambah sampai 5 kotak.
        </small>
      </section>
      <section className="card panel">
        <div className="panel-head"><div><h2>Ringkasan</h2></div></div>
        <dl className="meta compact">
          <dt>Aktif</dt><dd>{active.length} orang</dd>
          <dt>Nonaktif</dt><dd>{items.length - active.length} orang</dd>
          <dt>Default</dt><dd>{active.find((s) => s.is_default)?.full_name ?? <span className="muted">Belum ada</span>}</dd>
          <dt>TTD elektronik</dt><dd>{signed} dari {active.length} penyetuju</dd>
        </dl>
        {isPic && !me?.signature_updated_at && (
          <small className="muted">Tanda tangan Anda untuk kotak "Diajukan oleh" belum ada. Daftarkan di{" "}
            <Link to="/akun">Pengaturan akun</Link>.</small>
        )}
      </section>
    </aside>
  );
}

function SignatoryModal({ value: existing, clientId, onClose, onDone }: {
  value: Signatory | null; clientId: string; onClose: () => void; onDone: () => void;
}) {
  const [name, setName] = useState(existing?.full_name ?? "");
  const [position, setPosition] = useState(existing?.position ?? "");
  const [isDefault, setIsDefault] = useState(existing?.is_default ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    const body = { kind: "PENYETUJU", full_name: name.trim(), position: position.trim(), is_default: isDefault };
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
    <Modal title={existing ? `Ubah ${existing.full_name}` : `Tambah pemberi persetujuan`} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <div className="field">
        <label htmlFor="s-name">Nama lengkap</label>
        <input id="s-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="s-pos">Jabatan</label>
        <input id="s-pos" className="input" value={position} placeholder="mis. Direktur, Bendahara"
               onChange={(e) => setPosition(e.target.value)} />
      </div>
      <label className="toggle"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
        Jadikan default (mengisi kotak pertama saat unggah invoice; hanya satu per perusahaan)</label>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || name.trim().length < 2 || position.trim().length < 2} onClick={submit}>Simpan</button>
      </div>
    </Modal>
  );
}
