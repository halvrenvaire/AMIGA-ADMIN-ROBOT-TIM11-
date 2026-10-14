import { useState } from "react";
import { Plus, UserPlus } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, Modal, useApi } from "../components/ui";
import { ROLE_LABEL } from "../format";
import type { AdminUser, ClientRef, Role } from "../types";

const ROLES = Object.keys(ROLE_LABEL) as Role[];

/** System Admin: kelola akun, peran, dan penugasan klien (FR-7.1). */
export function AdminUsers() {
  const { user: me } = useAuth();
  const users = useApi(() => api.get<AdminUser[]>("/admin/users"), []);
  const clients = useApi(() => api.get<ClientRef[]>("/admin/clients"), []);
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);
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
      <section className="card panel">
        {users.loading && !users.data ? <Loading /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Nama</th><th>Email</th><th>Peran</th><th>Klien</th><th>Status</th><th className="right">Aksi</th></tr></thead>
              <tbody>
                {(users.data ?? []).map((u) => {
                  const self = u.id === me?.id;
                  return (
                    <tr key={u.id} style={u.is_active ? undefined : { opacity: 0.55 }}>
                      <td><b>{u.full_name}</b>{self && <> <span className="chip gray">Anda</span></>}</td>
                      <td className="mono">{u.email}</td>
                      <td><span className="actions">{u.roles.map((r) => <span key={r} className="chip">{ROLE_LABEL[r]}</span>)}</span></td>
                      <td>{u.clients.map((c) => c.name).join(", ") || <span className="muted">-</span>}</td>
                      <td>{u.is_active ? <span className="chip ok">Aktif</span> : <span className="chip gray">Nonaktif</span>}</td>
                      <td className="right">
                        <span className="actions" style={{ justifyContent: "flex-end" }}>
                          <button className="btn sm" disabled={self} onClick={() => setEditing(u)}>Ubah</button>
                          <button className="btn sm" disabled={self} onClick={() => toggleActive(u)}>{u.is_active ? "Nonaktifkan" : "Aktifkan"}</button>
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
          mengubah akun Anda sendiri.
        </small>
      </section>
      {editing && clients.data && (
        <UserModal user={editing === "new" ? null : editing} clients={clients.data}
                   onClose={() => setEditing(null)} onDone={() => { setEditing(null); users.reload(); }} />
      )}
    </>
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
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (user) {
        await api.put(`/admin/users/${user.id}/roles`, { roles });
        await api.put(`/admin/users/${user.id}/clients`, { client_ids: clientIds });
      } else {
        await api.post("/admin/users", { email, full_name: name, password, roles, client_ids: clientIds });
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
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
        <label>Peran</label>
        {ROLES.map((r) => (
          <label key={r} className="toggle"><input type="checkbox" checked={roles.includes(r)} onChange={() => setRoles(toggle(roles, r))} /> {ROLE_LABEL[r]}</label>
        ))}
      </fieldset>
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
        <label>Klien yang ditugaskan</label>
        {clients.map((c) => (
          <label key={c.id} className="toggle"><input type="checkbox" checked={clientIds.includes(c.id)} onChange={() => setClientIds(toggle(clientIds, c.id))} /> {c.name}</label>
        ))}
      </fieldset>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={busy || !roles.length} onClick={submit}>Simpan</button>
      </div>
    </Modal>
  );
}

export function AdminClients() {
  const clients = useApi(() => api.get<ClientRef[]>("/admin/clients"), []);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setError(null);
    try {
      await api.post("/admin/clients", { name });
      setName("");
      clients.reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <div className="page-head"><div><h1>Klien</h1><p>Klien yang dilayani AMIGA. Tugaskan pengguna ke klien di menu Pengguna & Peran.</p></div></div>
      <section className="card panel" style={{ maxWidth: 640 }}>
        {error && <Alert>{error}</Alert>}
        <div className="actions">
          <input className="input" style={{ flex: 1 }} placeholder="Nama klien, mis. PT Klien Gamma" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn primary" disabled={!name.trim()} onClick={add}><Plus /> Tambah</button>
        </div>
        {clients.loading && !clients.data ? <Loading /> : (
          <table className="table compact"><tbody>
            {(clients.data ?? []).map((c) => <tr key={c.id}><td>{c.name}</td><td className="mono muted right">{c.id.slice(0, 8)}</td></tr>)}
          </tbody></table>
        )}
      </section>
    </>
  );
}
