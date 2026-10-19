import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Building2, CheckCircle2, Plus, UserPlus, UserX, Users } from "lucide-react";
import { ClientLogo } from "../components/ClientLogo";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, Modal, MultiSelect, useApi } from "../components/ui";
import { ROLE_LABEL, tanggal } from "../format";
import type { AdminUser, ClientOverview, ClientRef, Role } from "../types";

const ROLES = Object.keys(ROLE_LABEL) as Role[];
// Peran yang dibatasi per perusahaan. Finance Reviewer (kasus dibagi sistem) dan Service Lead (mengawasi
// semua invoice) menangani semua perusahaan.
const CLIENT_SCOPED: Role[] = ["PIC_KLIEN", "INTAKE_SUPPORT"];
const needsClients = (roles: Role[]) => roles.some((r) => CLIENT_SCOPED.includes(r));

/** Alasan peran tidak bisa ditambahkan ke pilihan saat ini (aturan kombinasi peran di backend). */
function roleConflict(role: Role, selected: Role[]): string | null {
  if (selected.includes(role)) return null;
  if (role === "PIC_KLIEN" && selected.length) return "Tidak bisa digabung dengan peran internal";
  if (role !== "PIC_KLIEN" && selected.includes("PIC_KLIEN")) return "Tidak bisa digabung dengan PIC Klien";
  if (role === "FINANCE_REVIEWER" && selected.includes("SYSTEM_ADMIN")) return "Tidak bisa digabung dengan System Admin";
  if (role === "SYSTEM_ADMIN" && selected.includes("FINANCE_REVIEWER")) return "Tidak bisa digabung dengan Finance Reviewer";
  return null;
}

/** System Admin: kelola akun, peran, dan penugasan klien (FR-7.1). */
export function AdminUsers() {
  const { user: me } = useAuth();
  const users = useApi(() => api.get<AdminUser[]>("/admin/users"), []);
  const clients = useApi(() => api.get<ClientRef[]>("/admin/clients"), []);
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
  const [resetting, setResetting] = useState<AdminUser | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggleActive(u: AdminUser) {
    setError(null);
    try {
      await api.patch(`/admin/users/${u.id}/active`, { is_active: !u.is_active });
      users.reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Pengguna & peran</h1><p>Buat akun hanya berdasarkan permintaan tertulis dari atasan pengguna (SOP 7.7).</p></div>
        <button className="btn primary" onClick={() => setEditing("new")}><UserPlus /> Tambah pengguna</button>
      </div>
      {(error || users.error) && <Alert>{error ?? users.error}</Alert>}
      {notice && <Alert kind="ok">{notice}</Alert>}
      <section className="card panel">
        {users.loading && !users.data ? <Loading /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Nama</th><th>Email</th><th>Peran</th><th>Perusahaan</th><th>Status</th><th className="right">Aksi</th></tr></thead>
              <tbody>
                {(users.data ?? []).map((u) => {
                  const self = u.id === me?.id;
                  return (
                    <tr key={u.id} style={u.is_active ? undefined : { opacity: 0.55 }}>
                      <td><b>{u.full_name}</b>{self && <> <span className="chip gray">Anda</span></>}</td>
                      <td className="mono">{u.email}</td>
                      <td><span className="actions">{u.roles.map((r) => <span key={r} className="chip">{ROLE_LABEL[r]}</span>)}</span></td>
                      <td>
                        {needsClients(u.roles) ? (u.clients.map((c) => c.name).join(", ") || <span className="muted">-</span>) : null}
                        {u.roles.includes("FINANCE_REVIEWER") && (
                          <div className="muted" style={{ fontSize: 12 }}>Review: semua perusahaan</div>
                        )}
                        {u.roles.includes("SERVICE_LEAD") && (
                          <div className="muted" style={{ fontSize: 12 }}>Pengawasan: semua perusahaan</div>
                        )}
                      </td>
                      <td>{u.is_active ? <span className="chip ok">Aktif</span> : <span className="chip gray">Nonaktif</span>}</td>
                      <td className="right">
                        <span className="actions" style={{ justifyContent: "flex-end" }}>
                          <button className="btn sm" disabled={self} onClick={() => setEditing(u)}>Ubah</button>
                          <button className="btn sm" disabled={self} onClick={() => toggleActive(u)}>{u.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
                          <button className="btn sm" disabled={self} onClick={() => { setNotice(null); setResetting(u); }}>Reset password</button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <small className="muted">
          Kombinasi peran yang dilarang: PIC Klien dengan peran internal, dan System Admin dengan Finance Reviewer. Anda tidak bisa
          mengubah akun Anda sendiri; ganti data dan password Anda lewat Pengaturan akun.
        </small>
      </section>
      {editing && clients.data && (
        <UserModal user={editing === "new" ? null : editing} clients={clients.data}
                   onClose={() => setEditing(null)} onDone={() => { setEditing(null); users.reload(); }} />
      )}
      {resetting && (
        <ResetPasswordModal user={resetting} onClose={() => setResetting(null)}
                            onDone={() => { setNotice(`Password ${resetting.email} diatur ulang. Semua sesinya sudah dikeluarkan.`); setResetting(null); }} />
      )}
    </>
  );
}

function ResetPasswordModal({ user, onClose, onDone }: { user: AdminUser; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/admin/users/${user.id}/password`, { new_password: password });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Reset password ${user.full_name}`} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      <p className="muted" style={{ margin: 0 }}>
        Gunakan bila pengguna lupa password. Sampaikan password sementara lewat saluran resmi dan minta pengguna
        menggantinya di Pengaturan akun. Semua sesi {user.email} akan dikeluarkan.
      </p>
      <div className="field"><label htmlFor="r-pass">Password sementara</label>
        <input id="r-pass" className="input" type="text" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
        <small>Minimal 8 karakter, berisi huruf dan angka.</small></div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || password.length < 8} onClick={submit}>Reset password</button>
      </div>
    </Modal>
  );
}

function UserModal({ user, clients, onClose, onDone }: {
  user: AdminUser | null; clients: ClientRef[]; onClose: () => void; onDone: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState<Role[]>(user?.roles ?? []);
  const [clientIds, setClientIds] = useState<string[]>(user?.clients.map((c) => c.id) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const scoped = needsClients(roles);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (user) {
        await api.put(`/admin/users/${user.id}/roles`, { roles });
        await api.put(`/admin/users/${user.id}/clients`, { client_ids: scoped ? clientIds : [] });
      } else {
        await api.post("/admin/users", { email, full_name: name, password, roles, client_ids: scoped ? clientIds : [] });
      }
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={user ? `Ubah ${user.full_name}` : "Tambah pengguna"} onClose={onClose}>
      {error && <Alert>{error}</Alert>}
      {!user && (
        <>
          <div className="field"><label htmlFor="u-name">Nama lengkap</label>
            <input id="u-name" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="field"><label htmlFor="u-email">Email</label>
            <input id="u-email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className="field"><label htmlFor="u-pass">Password awal</label>
            <input id="u-pass" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <small>Minimal 8 karakter.</small></div>
        </>
      )}
      <div className="field">
        <label htmlFor="u-roles">Peran</label>
        <MultiSelect id="u-roles" placeholder="Pilih satu atau beberapa peran" value={roles}
                     onChange={(v) => setRoles(v as Role[])}
                     options={ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r], disabled: roleConflict(r, roles) }))} />
      </div>
      {scoped && (
        <div className="field">
          <label htmlFor="u-clients">Perusahaan yang ditugaskan{roles.some((r) => r === "FINANCE_REVIEWER" || r === "SERVICE_LEAD") && " (untuk PIC Klien / Intake Support)"}</label>
          <MultiSelect id="u-clients" bulk placeholder="Pilih perusahaan" value={clientIds} onChange={setClientIds}
                       options={clients.map((c) => ({ value: c.id, label: c.name }))} />
        </div>
      )}
      {roles.includes("SERVICE_LEAD") && (
        <Alert kind="info">Service Lead mengawasi semua invoice dari semua perusahaan, tanpa penugasan perusahaan.</Alert>
      )}
      {roles.includes("FINANCE_REVIEWER") && (
        <Alert kind="info">
          Finance Reviewer menangani pengajuan dari semua perusahaan. Sistem membagi kasus secara merata dan acak antar
          reviewer, dan tidak pernah memberikan dokumen kepada pihak pengajunya.
        </Alert>
      )}
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || !roles.length} onClick={submit}>Simpan</button>
      </div>
    </Modal>
  );
}

export function AdminClients() {
  const clients = useApi(() => api.get<ClientOverview[]>("/admin/clients/overview"), []);
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/admin/clients", { name });
      setName("");
      clients.reload();
    } catch (e) { setError((e as Error).message); }
  }

  const all = clients.data ?? [];
  const noPic = all.filter((c) => c.pics.length === 0);
  const submitters = new Set(all.flatMap((c) => [...c.pics, ...c.intakes])).size;
  const shown = all.filter((c) => c.name.toLowerCase().includes(query.trim().toLowerCase()));
  const people = (names: string[]) => (names.length
    ? <span className="actions" style={{ gap: 4 }}>{names.map((n) => <span key={n} className="chip">{n}</span>)}</span>
    : <span className="muted">-</span>);

  return (
    <>
      <div className="page-head"><div><h1>Klien</h1><p>Klien yang dilayani AMIGA. Tugaskan pengguna ke klien di menu Pengguna & Peran.</p></div></div>
      <section className="stats" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }} aria-label="Ringkasan klien">
        <div className="card stat">
          <div className="stat-top">Klien terdaftar<span className="stat-ic navy"><Building2 /></span></div>
          <div className="stat-val">{all.length}</div><div className="stat-foot">perusahaan yang dilayani</div>
        </div>
        <div className="card stat">
          <div className="stat-top">Pengaju ditugaskan<span className="stat-ic teal"><Users /></span></div>
          <div className="stat-val">{submitters}</div><div className="stat-foot">PIC Klien dan Intake Support aktif</div>
        </div>
        <div className="card stat">
          <div className="stat-top">Klien tanpa PIC<span className={`stat-ic ${noPic.length ? "amber" : "teal"}`}><UserX /></span></div>
          <div className="stat-val">{noPic.length}</div>
          <div className="stat-foot">{noPic.length ? "belum bisa mengajukan invoice" : "semua klien punya PIC"}</div>
        </div>
      </section>

      <div className="with-aside">
        <section className="card panel">
          <div className="panel-head">
            <div><h2>Daftar klien</h2><p>PIC Klien dan Intake Support yang ditugaskan ke setiap klien</p></div>
          </div>
          {(error || clients.error) && <Alert>{error ?? clients.error}</Alert>}
          <div className="filters">
            <form className="actions" style={{ flex: 1, minWidth: 280 }} onSubmit={add}>
              <input className="input" style={{ flex: 1 }} placeholder="Nama klien baru, mis. PT Klien Gamma" aria-label="Nama klien baru"
                     value={name} onChange={(e) => setName(e.target.value)} />
              <button className="btn primary" disabled={!name.trim()}><Plus /> Tambah</button>
            </form>
            <input className="input" style={{ width: 220 }} placeholder="Cari klien…" aria-label="Cari klien"
                   value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {clients.loading && !clients.data ? <Loading /> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Klien</th><th>Logo voucher</th><th>PIC Klien</th><th>Intake Support</th><th>Terdaftar</th><th className="right">ID</th></tr></thead>
                <tbody>
                  {shown.map((c) => (
                    <tr key={c.id}>
                      <td><b>{c.name}</b></td>
                      <td><ClientLogo clientId={c.id} clientName={c.name} version={c.logo_updated_at ?? null} canEdit compact
                                      onChange={clients.reload} /></td>
                      <td>{c.pics.length ? people(c.pics) : <span className="chip warn">Belum ada PIC</span>}</td>
                      <td>{people(c.intakes)}</td>
                      <td>{tanggal(c.created_at)}</td>
                      <td className="mono muted right">{c.id.slice(0, 8)}</td>
                    </tr>
                  ))}
                  {shown.length === 0 && <tr><td colSpan={6} className="empty">Tidak ada klien yang cocok.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <aside className="aside">
          <section className="card panel">
            <div className="panel-head"><div><h2>Perlu perhatian</h2><p>Klien yang belum punya PIC Klien</p></div></div>
            {noPic.length === 0 ? (
              <div className="muted" style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                <CheckCircle2 size={16} color="var(--teal)" /> Semua klien sudah punya PIC.
              </div>
            ) : (
              <ul className="plain-list">
                {noPic.map((c) => <li key={c.id}><span>{c.name}</span><span className="chip warn">Tanpa PIC</span></li>)}
              </ul>
            )}
            {noPic.length > 0 && <Link className="btn sm" to="/admin/pengguna">Tugaskan di Pengguna & Peran</Link>}
          </section>
          <section className="card panel">
            <div className="panel-head"><div><h2>Langkah menambah klien</h2></div></div>
            <ol className="steps">
              <li>Tambahkan nama klien di daftar ini.</li>
              <li>Buat atau ubah akun PIC Klien, lalu tugaskan ke klien tersebut.</li>
              <li>PIC Klien mendaftarkan vendor dan penanda tangan, lalu mulai mengunggah invoice.</li>
            </ol>
            <small className="muted">Finance Reviewer dan Service Lead otomatis menangani semua klien.</small>
          </section>
        </aside>
      </div>
    </>
  );
}
