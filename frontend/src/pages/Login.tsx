import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { homePath, useAuth } from "../auth";
import { Alert } from "../components/ui";

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
        <div className="brand" style={{ padding: 0 }}>
          <div className="logo" style={{ background: "#fff", color: "var(--navy)" }}>A</div>
          <div><b>AMIGA</b><span style={{ color: "#c7d5f6" }}>Robot Admin</span></div>
        </div>
        <div>
          <h1>Kami Tangani Back Office Anda Seperti Bagian dari Tim.</h1>
          <p>Invoice vendor menjadi voucher pembayaran resmi dalam hitungan detik. AI membaca invoice, sistem memverifikasi,
            Finance Reviewer menyetujui.</p>
        </div>
        <small style={{ color: "#c7d5f6" }}>PoC MAIN Hackathon 2026 · Kelompok 11</small>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <div>
            <h2 style={{ fontSize: 22 }}>Masuk</h2>
            <p className="muted" style={{ margin: "4px 0 0" }}>Gunakan akun AMIGA Robot Admin Anda.</p>
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
          <button className="btn primary" disabled={busy}><LogIn /> {busy ? "Memeriksa…" : "Masuk"}</button>
          <div className="demo-accounts">
            Akun demo (data dummy):
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", marginTop: 4 }}>
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
