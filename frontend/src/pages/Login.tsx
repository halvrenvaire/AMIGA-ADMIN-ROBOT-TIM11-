import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { BadgeCheck, LogIn, ScanText, ShieldCheck } from "lucide-react";
import { homePath, useAuth } from "../auth";
import { Alert } from "../components/ui";
import { Clover, Logo } from "../components/Logo";
import { ThemeToggle } from "../theme";

// Akun hasil seed.py (data dummy PoC); password dari SEED_DEFAULT_PASSWORD di backend/.env
const DEMO = [
  ["pic.alpha@amiga.test", "PIC Klien Alpha"], ["intake@amiga.test", "Intake Support"],
  ["reviewer1@amiga.test", "Finance Reviewer"], ["multi@amiga.test", "Intake + Reviewer (UAT 5)"],
  ["lead@amiga.test", "Service Lead"], ["admin@amiga.test", "System Admin"], ["pic.beta@amiga.test", "PIC Klien Beta"],
];

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homePath(user.roles)} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await login(email.trim(), password);
      navigate(homePath(me.roles), { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <section className="login-art">
        <Logo height={64} />
        <div className="login-copy">
          <span className="eyebrow">Robot Admin · Back Office as A Service</span>
          <h1>Read. Verify. Approve.</h1>
          <p>Dari invoice vendor ke voucher pembayaran resmi, cepat, akurat, dan bisa diaudit.</p>
          <ul className="login-points">
            <li><span><ScanText /></span>AI membaca invoice PDF dalam hitungan detik</li>
            <li><span><ShieldCheck /></span>Sistem memverifikasi angka, kelengkapan, dan duplikasi</li>
            <li><span><BadgeCheck /></span>Finance Reviewer menyetujui, setiap aksi tercatat</li>
          </ul>
        </div>
        <small className="muted">PoC MAIN Hackathon 2026 · Kelompok 11</small>
        <Clover className="clover-bg" size={340} />
        <Clover className="clover-bg small" size={120} />
      </section>
      <section className="login-form">
        <ThemeToggle className="btn ghost sm icon-btn theme-corner" />
        <form onSubmit={submit} className="login-card">
          <div>
            <h2>Selamat datang kembali</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>Masuk dengan akun amiga Robot Admin Anda.</p>
          </div>
          {error && <Alert>{error}</Alert>}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" className="input" type="email" autoComplete="username" required value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="nama@amiga.test" />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" className="input" type="password" autoComplete="current-password" required
                   value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="btn primary lg" disabled={busy}><LogIn /> {busy ? "Memeriksa…" : "Masuk"}</button>
          <div className="demo-accounts">
            <span>Akun demo (data dummy)</span>
            <div className="demo-grid">
              {DEMO.map(([e, label]) => (
                <button type="button" key={e} onClick={() => setEmail(e)} title={e}>{label}</button>
              ))}
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}
