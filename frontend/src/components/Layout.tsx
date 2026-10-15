import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, Bot, Building2, ClipboardCheck, FileBarChart, FileClock, FileText, LayoutDashboard, LogOut, PenLine, Receipt, Search, Store,
  Upload, Users,
} from "lucide-react";
import { useAuth } from "../auth";
import { ROLE_LABEL } from "../format";
import type { Role } from "../types";
import { Assistant } from "./Assistant";
import { Clover, Logo } from "./Logo";
import { ThemeToggle } from "../theme";
import { initials } from "./ui";

interface NavItem { to: string; label: string; icon: typeof FileText; roles: Role[] }

// Menu sesuai 5 layar PRD bagian 5, ditambah layar System Admin
const NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: BarChart3, roles: ["SERVICE_LEAD", "FINANCE_REVIEWER", "PIC_KLIEN", "INTAKE_SUPPORT"] },
  { to: "/antrean", label: "Dashboard Antrean", icon: LayoutDashboard, roles: ["SERVICE_LEAD", "FINANCE_REVIEWER"] },
  { to: "/peninjauan", label: "Peninjauan Saya", icon: ClipboardCheck, roles: ["FINANCE_REVIEWER"] },
  { to: "/unggah", label: "Unggah Dokumen", icon: Upload, roles: ["PIC_KLIEN", "INTAKE_SUPPORT"] },
  { to: "/pengajuan", label: "Pengajuan Saya", icon: FileText, roles: ["PIC_KLIEN", "INTAKE_SUPPORT"] },
  { to: "/voucher", label: "Voucher", icon: Receipt, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER", "SERVICE_LEAD"] },
  { to: "/rekap-voucher", label: "Rekap Voucher", icon: FileBarChart, roles: ["SERVICE_LEAD"] },
  { to: "/riwayat", label: "Riwayat & Audit", icon: FileClock, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER", "SERVICE_LEAD"] },
  { to: "/asisten", label: "Asisten AI", icon: Bot, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER", "SERVICE_LEAD", "SYSTEM_ADMIN"] },
];
const REFERENCE_NAV: NavItem[] = [
  { to: "/referensi/vendor", label: "Vendor", icon: Store, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER", "SERVICE_LEAD"] },
  { to: "/referensi/penanda-tangan", label: "Penanda tangan", icon: PenLine, roles: ["PIC_KLIEN", "INTAKE_SUPPORT"] },
];
const ADMIN_NAV: NavItem[] = [
  { to: "/admin/pengguna", label: "Pengguna & Peran", icon: Users, roles: ["SYSTEM_ADMIN"] },
  { to: "/admin/klien", label: "Klien", icon: Building2, roles: ["SYSTEM_ADMIN"] },
];

// Dicocokkan berurutan; pola yang lebih spesifik di atas
const TITLES: [RegExp, string][] = [
  [/^\/dokumen\/[^/]+\/voucher$/, "Pratinjau Voucher"], [/^\/dokumen\/[^/]+\/riwayat$/, "Riwayat Dokumen"],
  [/^\/dokumen/, "Detail Dokumen"], [/^\/dashboard/, "Dashboard"], [/^\/antrean/, "Dashboard Antrean"],
  [/^\/referensi\/vendor/, "Data Referensi / Vendor"], [/^\/referensi\/penanda-tangan/, "Data Referensi / Penanda tangan"], [/^\/peninjauan/, "Peninjauan Saya"],
  [/^\/unggah/, "Unggah Dokumen"], [/^\/pengajuan/, "Pengajuan Saya"], [/^\/voucher/, "Voucher"],
  [/^\/riwayat/, "Riwayat & Audit"], [/^\/cari/, "Hasil Pencarian"],
  [/^\/akun/, "Pengaturan Akun"], [/^\/asisten/, "Asisten AI"], [/^\/rekap-voucher/, "Rekap Voucher"], [/^\/admin\/pengguna/, "Pengguna & Peran"], [/^\/admin\/klien/, "Klien"],
];

export function Layout() {
  const { user, logout, has } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [q, setQ] = useState("");
  if (!user) return null;

  const visible = (items: NavItem[]) => items.filter((i) => has(...i.roles));
  const title = TITLES.find(([re]) => re.test(pathname))?.[1] ?? "AMIGA";
  const canSearch = !(user.roles.length === 1 && user.roles[0] === "SYSTEM_ADMIN");
  const search = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) navigate(`/cari?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="shell">
      <aside className="side" aria-label="Navigasi utama">
        <div className="brand">
          <Logo height={36} />
          <span className="brand-sub">Robot Admin</span>
        </div>
        {visible(NAV).length > 0 && (
          <nav>
            <div className="nav-label">Menu</div>
            <ul className="nav">
              {visible(NAV).map(({ to, label, icon: Icon }) => (
                <li key={to}><NavLink to={to}><Icon /><span>{label}</span></NavLink></li>
              ))}
            </ul>
          </nav>
        )}
        {visible(REFERENCE_NAV).length > 0 && (
          <nav>
            <div className="nav-label">Data Referensi</div>
            <ul className="nav">
              {visible(REFERENCE_NAV).map(({ to, label, icon: Icon }) => (
                <li key={to}><NavLink to={to}><Icon /><span>{label}</span></NavLink></li>
              ))}
            </ul>
          </nav>
        )}
        {visible(ADMIN_NAV).length > 0 && (
          <nav>
            <div className="nav-label">Administrasi</div>
            <ul className="nav">
              {visible(ADMIN_NAV).map(({ to, label, icon: Icon }) => (
                <li key={to}><NavLink to={to}><Icon /><span>{label}</span></NavLink></li>
              ))}
            </ul>
          </nav>
        )}
        <div className="side-foot">
          <Clover size={64} style={{ position: "absolute", right: -14, bottom: -14, opacity: 0.35 }} />
          <b>We Run Your Ops, So You Can Run the Business</b>
          <span>Back Office as A Service. Panduan kerja: SOP-AMIGA-FIN-001.</span>
        </div>
      </aside>

      <div className="main">
        <header className="top">
          <div className="crumb">Beranda / <b>{title}</b></div>
          {canSearch && (
            <form className="search" onSubmit={search} role="search">
              <Search size={16} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari Request ID atau vendor…" aria-label="Cari dokumen" />
            </form>
          )}
          <div style={canSearch ? undefined : { marginLeft: "auto" }}><ThemeToggle className="btn ghost sm icon-btn" /></div>
          <div className="user">
            <NavLink to="/akun" className="user-link" title="Pengaturan akun">
              <div className="avatar" aria-hidden="true">{initials(user.full_name)}</div>
              <div>
                <b>{user.full_name}</b>
                <span>{user.roles.map((r) => ROLE_LABEL[r]).join(" + ")}</span>
              </div>
            </NavLink>
            <button className="btn ghost sm" onClick={logout} title="Keluar" aria-label="Keluar"><LogOut /></button>
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
      <Assistant />
    </div>
  );
}
