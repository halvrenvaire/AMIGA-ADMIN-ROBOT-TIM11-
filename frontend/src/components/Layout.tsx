import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  ClipboardCheck, FileClock, FileText, LayoutDashboard, LogOut, Receipt, Search, Upload, Users, Building2,
} from "lucide-react";
import { useAuth } from "../auth";
import { ROLE_LABEL } from "../format";
import type { Role } from "../types";
import { Assistant } from "./Assistant";
import { initials } from "./ui";

interface NavItem { to: string; label: string; icon: typeof FileText; roles: Role[] }

// Menu sesuai 5 layar PRD bagian 5, ditambah layar System Admin
const NAV: NavItem[] = [
  { to: "/antrean", label: "Dashboard Antrean", icon: LayoutDashboard, roles: ["SERVICE_LEAD", "FINANCE_REVIEWER"] },
  { to: "/peninjauan", label: "Peninjauan Saya", icon: ClipboardCheck, roles: ["FINANCE_REVIEWER"] },
  { to: "/unggah", label: "Unggah Dokumen", icon: Upload, roles: ["PIC_KLIEN", "INTAKE_SUPPORT"] },
  { to: "/pengajuan", label: "Pengajuan Saya", icon: FileText, roles: ["PIC_KLIEN", "INTAKE_SUPPORT"] },
  { to: "/voucher", label: "Voucher", icon: Receipt, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER"] },
  { to: "/riwayat", label: "Riwayat & Audit", icon: FileClock, roles: ["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER", "SERVICE_LEAD"] },
];
const ADMIN_NAV: NavItem[] = [
  { to: "/admin/pengguna", label: "Pengguna & Peran", icon: Users, roles: ["SYSTEM_ADMIN"] },
  { to: "/admin/klien", label: "Klien", icon: Building2, roles: ["SYSTEM_ADMIN"] },
];

// Dicocokkan berurutan; pola yang lebih spesifik di atas
const TITLES: [RegExp, string][] = [
  [/^\/dokumen\/[^/]+\/voucher$/, "Pratinjau Voucher"], [/^\/dokumen\/[^/]+\/riwayat$/, "Riwayat Dokumen"],
  [/^\/dokumen/, "Detail Dokumen"], [/^\/antrean/, "Dashboard Antrean"], [/^\/peninjauan/, "Peninjauan Saya"],
  [/^\/unggah/, "Unggah Dokumen"], [/^\/pengajuan/, "Pengajuan Saya"], [/^\/voucher/, "Voucher"],
  [/^\/riwayat/, "Riwayat & Audit"], [/^\/cari/, "Hasil Pencarian"],
  [/^\/admin\/pengguna/, "Pengguna & Peran"], [/^\/admin\/klien/, "Klien"],
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
          <div className="logo">A</div>
          <div><b>AMIGA</b><span>Robot Admin</span></div>
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
          <b>Kami Tangani Back Office Anda</b>
          <span>Seperti bagian dari tim. Panduan lengkap ada di SOP-AMIGA-FIN-001.</span>
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
          <div className="user" style={canSearch ? undefined : { marginLeft: "auto" }}>
            <div className="avatar" aria-hidden="true">{initials(user.full_name)}</div>
            <div>
              <b>{user.full_name}</b>
              <span>{user.roles.map((r) => ROLE_LABEL[r]).join(" + ")}</span>
            </div>
            <button className="btn ghost sm" onClick={logout} title="Keluar" aria-label="Keluar"><LogOut /></button>
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
      <Assistant />
    </div>
  );
}
