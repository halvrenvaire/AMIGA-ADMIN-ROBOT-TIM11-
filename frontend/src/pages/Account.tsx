import { useEffect, useState, type FormEvent } from "react";
import { Check, Eye, EyeOff, KeyRound, Monitor, Moon, Palette, PenLine, Send, Sun, UserRound, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { SignatureImage, SignatureModal } from "../components/Signature";
import { Alert, Loading, initials, useApi } from "../components/ui";
import { ROLE_LABEL } from "../format";
import { useTheme, type ThemeMode } from "../theme";
import type { Me, TelegramLinkCode, TelegramStatus } from "../types";

type Notice = { kind: "ok" | "error"; text: string } | null;

/** Pengaturan akun milik pengguna yang sedang login: profil, password, tampilan. */
export function Account() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <>
      <div className="page-head">
        <div><h1>Pengaturan akun</h1><p>Kelola profil, keamanan, dan tampilan akun Anda.</p></div>
      </div>
      <div className="account-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          <ProfileCard user={user} />
          <PasswordCard user={user} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
          <AccountInfo user={user} />
          <TelegramCard />
          {user.roles.includes("PIC_KLIEN") && <SignatureCard user={user} />}
          <ThemeCard />
        </div>
      </div>
    </>
  );
}

function CardHead({ icon: Icon, title, note }: { icon: typeof UserRound; title: string; note: string }) {
  return (
    <div className="panel-head">
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <span className="stat-ic navy"><Icon /></span>
        <div><h2>{title}</h2><p>{note}</p></div>
      </div>
    </div>
  );
}

function ProfileCard({ user }: { user: Me }) {
  const { updateSession } = useAuth();
  const [name, setName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email);
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const emailChanged = email.trim().toLowerCase() !== user.email;
  const dirty = name.trim() !== user.full_name || emailChanged;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const me = await api.patch<Me>("/auth/me", {
        full_name: name.trim(), ...(emailChanged ? { email: email.trim(), current_password: password } : {}),
      });
      updateSession(me);
      setEmail(me.email);
      setPassword("");
      setNotice({ kind: "ok", text: emailChanged ? "Profil disimpan. Gunakan email baru saat login berikutnya." : "Profil disimpan." });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card panel" onSubmit={submit}>
      <CardHead icon={UserRound} title="Profil" note="Nama tampilan dan email untuk login." />
      <div className="profile-row">
        <div className="avatar lg" aria-hidden="true">{initials(name || user.full_name)}</div>
        <div className="muted" style={{ fontSize: 12.5 }}>Nama tampil di top bar, riwayat audit, dan voucher yang Anda setujui.</div>
      </div>
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      <div className="grid-2">
        <div className="field">
          <label htmlFor="p-name">Nama tampilan</label>
          <input id="p-name" className="input" required minLength={2} maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="p-email">Email (untuk login)</label>
          <input id="p-email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
      </div>
      {emailChanged && (
        <div className="field">
          <label htmlFor="p-current">Password saat ini</label>
          <input id="p-current" className="input" type="password" required autoComplete="current-password"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
          <small>Diperlukan untuk mengganti email.</small>
        </div>
      )}
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        {dirty && <button type="button" className="btn" onClick={() => { setName(user.full_name); setEmail(user.email); setPassword(""); }}>Batal</button>}
        <button className="btn primary" disabled={busy || !dirty}>Simpan profil</button>
      </div>
    </form>
  );
}

function PasswordInput({ id, label, value, onChange, autoComplete }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-with-btn">
        <input id={id} className="input" type={show ? "text" : "password"} value={value} autoComplete={autoComplete}
               onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="btn ghost sm" onClick={() => setShow(!show)} aria-label={show ? "Sembunyikan" : "Tampilkan"}>
          {show ? <EyeOff /> : <Eye />}
        </button>
      </div>
    </div>
  );
}

function PasswordCard({ user }: { user: Me }) {
  const { updateSession } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const rules = [
    { ok: next.length >= 8, text: "Minimal 8 karakter" },
    { ok: /[a-zA-Z]/.test(next) && /\d/.test(next), text: "Berisi huruf dan angka" },
    { ok: next !== "" && next.toLowerCase() !== user.email && next.toLowerCase() !== user.email.split("@")[0], text: "Tidak sama dengan email" },
    { ok: next !== "" && next === confirm, text: "Konfirmasi cocok" },
  ];
  const valid = current !== "" && rules.every((r) => r.ok);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const res = await api.post<{ access_token: string }>("/auth/me/password", { current_password: current, new_password: next });
      updateSession(user, res.access_token);
      setCurrent(""); setNext(""); setConfirm("");
      setNotice({ kind: "ok", text: "Password diganti. Sesi di perangkat atau tab lain sudah dikeluarkan." });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card panel" onSubmit={submit}>
      <CardHead icon={KeyRound} title="Keamanan" note="Ganti password. Semua sesi lain akan otomatis keluar." />
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      <PasswordInput id="pw-current" label="Password saat ini" value={current} onChange={setCurrent} autoComplete="current-password" />
      <div className="grid-2">
        <PasswordInput id="pw-new" label="Password baru" value={next} onChange={setNext} autoComplete="new-password" />
        <PasswordInput id="pw-confirm" label="Ulangi password baru" value={confirm} onChange={setConfirm} autoComplete="new-password" />
      </div>
      <ul className="pw-rules">
        {rules.map((r) => (
          <li key={r.text} className={r.ok ? "ok" : ""}>{r.ok ? <Check /> : <X />}{r.text}</li>
        ))}
      </ul>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn primary" disabled={busy || !valid}>Ganti password</button>
      </div>
    </form>
  );
}

function AccountInfo({ user }: { user: Me }) {
  return (
    <section className="card panel">
      <CardHead icon={UserRound} title="Akses akun" note="Diatur oleh System Admin." />
      <dl className="meta">
        <dt>Peran</dt>
        <dd><span className="actions">{user.roles.map((r) => <span key={r} className="chip">{ROLE_LABEL[r]}</span>)}</span></dd>
        <dt>Klien</dt>
        <dd>{user.clients.map((c) => c.name).join(", ") || <span className="muted">-</span>}</dd>
      </dl>
      <small className="muted">Butuh peran atau akses klien lain? Hubungi System Admin.</small>
    </section>
  );
}

/** Profil "Diajukan oleh" mode PIC: nama akun, jabatan, perusahaan/unit, dan tanda tangan elektronik. Dipakai
 *  otomatis di voucher bila pengajuan memilih "Diisi PIC Klien". */
function SignatureCard({ user }: { user: Me }) {
  const { updateSession } = useAuth();
  const saved = user.submitter_profile ?? {};
  const [position, setPosition] = useState(saved.position ?? "");
  const [company, setCompany] = useState(saved.company ?? "");
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const dirty = position.trim() !== (saved.position ?? "") || company.trim() !== (saved.company ?? "");

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      updateSession(await api.patch<Me>("/auth/me", { submitter_position: position.trim(), submitter_company: company.trim() }));
      setNotice({ kind: "ok", text: "Profil pengaju disimpan. Berlaku untuk pengajuan berikutnya." });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setNotice(null);
    try { updateSession(await api.del<Me>("/auth/me/signature")); } catch (e) { setNotice({ kind: "error", text: (e as Error).message }); }
  }

  return (
    <form className="card panel" onSubmit={save}>
      <CardHead icon={PenLine} title={'Profil "Diajukan oleh"'}
                note={'Dipakai otomatis di voucher bila pengajuan memilih "Diisi PIC Klien".'} />
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      <div className="field">
        <label>Nama</label>
        <div className="readonly-value">{user.full_name}</div>
        <small>Sama dengan nama tampilan di kartu Profil.</small>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="sp-position">Jabatan</label>
          <input id="sp-position" className="input" maxLength={120} value={position} placeholder="PIC Klien"
                 onChange={(e) => setPosition(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="sp-company">Perusahaan / unit</label>
          <input id="sp-company" className="input" maxLength={200} value={company} placeholder="Kosongkan = nama perusahaan"
                 onChange={(e) => setCompany(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>Tanda tangan elektronik</label>
        <div className="sig-frame">
          <SignatureImage path="/auth/me/signature" version={user.signature_updated_at ?? null} alt="Tanda tangan Anda" />
        </div>
        <div className="actions">
          <button type="button" className="btn sm" onClick={() => setOpen(true)}>
            <PenLine /> {user.signature_updated_at ? "Ganti" : "Buat tanda tangan"}
          </button>
          {user.signature_updated_at && <button type="button" className="btn sm" onClick={remove}>Hapus</button>}
        </div>
        <small>Tanpa tanda tangan elektronik, kotak di voucher tetap kosong untuk tanda tangan basah.</small>
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        {dirty && <button type="button" className="btn" onClick={() => { setPosition(saved.position ?? ""); setCompany(saved.company ?? ""); }}>Batal</button>}
        <button className="btn primary" disabled={busy || !dirty}>Simpan profil pengaju</button>
      </div>
      {open && (
        <SignatureModal title="Tanda tangan Anda" signer={user.full_name} onClose={() => setOpen(false)}
                        onSave={async (image) => { updateSession(await api.put<Me>("/auth/me/signature", { image })); setOpen(false); }} />
      )}
    </form>
  );
}

/** Menghubungkan akun dengan bot Telegram lewat kode sekali pakai (password tidak diketik di chat). */
function TelegramCard() {
  const { data: status, error, loading, reload } = useApi(() => api.get<TelegramStatus>("/auth/me/telegram"), []);
  const [code, setCode] = useState<TelegramLinkCode | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const secondsLeft = code ? Math.max(0, Math.round((new Date(code.expires_at).getTime() - now) / 1000)) : 0;

  // Selama kode tampil: hitung mundur, dan cek tiap 3 detik apakah bot sudah menerima kodenya
  useEffect(() => {
    if (!code) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const poll = setInterval(async () => {
      const s = await api.get<TelegramStatus>("/auth/me/telegram").catch(() => null);
      if (s?.linked) {
        setCode(null);
        setNotice({ kind: "ok", text: `Telegram terhubung${s.telegram_username ? ` (@${s.telegram_username})` : ""}.` });
        reload();
      }
    }, 3000);
    return () => { clearInterval(tick); clearInterval(poll); };
  }, [code, reload]);

  async function createCode() {
    setBusy(true);
    setNotice(null);
    try {
      setCode(await api.post<TelegramLinkCode>("/auth/me/telegram/link-code"));
      setNow(Date.now());
    } catch (e) {
      setNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function unlink() {
    setBusy(true);
    setNotice(null);
    try {
      await api.del("/auth/me/telegram");
      setNotice({ kind: "ok", text: "Telegram diputus dari akun ini." });
      reload();
    } catch (e) {
      setNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card panel">
      <CardHead icon={Send} title="Telegram" note="Cek progres invoice dan tanya Asisten AI lewat bot Telegram." />
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
      {error && <Alert>{error}</Alert>}
      {loading && !status ? <Loading /> : status && (
        !status.configured ? (
          <Alert kind="info">Bot Telegram belum diaktifkan di server. Hubungi tim teknis.</Alert>
        ) : status.linked ? (
          <>
            <dl className="meta">
              <dt>Status</dt><dd><span className="chip">Terhubung</span></dd>
              <dt>Akun Telegram</dt><dd>{status.telegram_username ? `@${status.telegram_username}` : <span className="muted">tanpa username</span>}</dd>
              <dt>Bot</dt><dd><a href={status.bot_url} target="_blank" rel="noreferrer">@{status.bot_username}</a></dd>
            </dl>
            <div className="actions">
              <button className="btn sm" onClick={unlink} disabled={busy}>Putuskan Telegram</button>
            </div>
          </>
        ) : code && secondsLeft > 0 ? (
          <>
            <div style={{ textAlign: "center", padding: "8px 0" }}>
              <div className="muted" style={{ fontSize: 12.5 }}>Kode sekali pakai</div>
              <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: 6, fontVariantNumeric: "tabular-nums" }}>{code.code}</div>
              <div className="muted" style={{ fontSize: 12.5 }}>
                Berlaku {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")} lagi
              </div>
            </div>
            <div className="actions" style={{ justifyContent: "center" }}>
              <a className="btn primary sm" href={code.deep_link} target="_blank" rel="noreferrer"><Send /> Buka @{code.bot_username}</a>
              <button className="btn sm" onClick={() => setCode(null)}>Batal</button>
            </div>
            <small className="muted">
              Klik tombol di atas lalu tekan <b>Start</b>, atau kirim <code>/login {code.code}</code> ke @{code.bot_username}.
              Halaman ini otomatis berubah setelah terhubung.
            </small>
          </>
        ) : (
          <>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Belum terhubung. Buat kode, lalu kirim ke bot. Jangan pernah mengirim password Anda di chat.
            </p>
            <div className="actions">
              <button className="btn primary sm" onClick={createCode} disabled={busy}><Send /> {code ? "Kode kedaluwarsa, buat lagi" : "Hubungkan Telegram"}</button>
            </div>
          </>
        )
      )}
    </section>
  );
}

const THEMES: { mode: ThemeMode; label: string; icon: typeof Sun }[] = [
  { mode: "light", label: "Terang", icon: Sun },
  { mode: "dark", label: "Gelap", icon: Moon },
  { mode: "system", label: "Ikut sistem", icon: Monitor },
];

function ThemeCard() {
  const { mode, setMode } = useTheme();
  return (
    <section className="card panel">
      <CardHead icon={Palette} title="Tampilan" note="Tersimpan di browser ini." />
      <div className="theme-options" role="radiogroup" aria-label="Tema">
        {THEMES.map(({ mode: m, label, icon: Icon }) => (
          <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
            <Icon /> {label}
          </button>
        ))}
      </div>
    </section>
  );
}
