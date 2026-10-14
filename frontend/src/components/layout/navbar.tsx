'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api } from '../../lib/api';
import { UserProfile } from '../../lib/types';
import { cn } from '../../lib/utils';
import { FileText, Upload, UserCheck, Shield, ChevronDown, Check } from 'lucide-react';

const PRESET_USERS = [
  { label: 'Reviewer 1 (AMIGA)', email: 'reviewer1@amiga.co.id', role: 'FINANCE_REVIEWER' },
  { label: 'Reviewer 2 (AMIGA)', email: 'reviewer2@amiga.co.id', role: 'FINANCE_REVIEWER' },
  { label: 'PIC Klien (Client)', email: 'pic_client@amiga.co.id', role: 'PIC_KLIEN' },
  { label: 'Intake Support', email: 'intake_support@amiga.co.id', role: 'INTAKE_SUPPORT' },
  { label: 'Service Lead', email: 'service_lead@amiga.co.id', role: 'SERVICE_LEAD' },
  { label: 'System Admin', email: 'sysadmin@amiga.co.id', role: 'SYSTEM_ADMIN' },
];

export function Navbar() {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [isSwitching, setIsSwitching] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const fetchProfile = async () => {
    try {
      const res = await api.getMe();
      setCurrentUser(res.user);
    } catch {
      // Auto login as reviewer 1 default for demo if no session
      try {
        const loginRes = await api.login('reviewer1@amiga.co.id', 'password123!');
        setCurrentUser(loginRes.user);
      } catch {
        // offline or unseeded
      }
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  const handleSwitchUser = async (email: string) => {
    setIsSwitching(true);
    setDropdownOpen(false);
    try {
      const res = await api.login(email, 'password123!');
      setCurrentUser(res.user);
      window.location.reload();
    } catch (err) {
      console.error('Failed to switch user:', err);
    } finally {
      setIsSwitching(false);
    }
  };

  const navLinks = [
    { href: '/queue', label: 'Antrean Dokumen', icon: FileText },
    { href: '/upload', label: 'Unggah Invoice', icon: Upload },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white border-b border-slate-200 shadow-[0_2px_8px_rgba(11,53,88,0.04)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center gap-8">
            <Link href="/queue" className="flex items-center gap-3 group focus:outline-none focus:ring-2 focus:ring-[#006BFF] rounded-lg p-1">
              <div className="w-9 h-9 rounded-lg bg-[#0B3558] flex items-center justify-center text-white font-bold text-sm tracking-wider shadow-sm group-hover:bg-[#006BFF] transition-colors">
                AM
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-[#0B3558] text-base tracking-tight leading-none">
                  AMIGA Robot Admin
                </span>
                <span className="text-[11px] text-slate-500 font-medium tracking-wide">
                  Vendor Invoice to Voucher
                </span>
              </div>
            </Link>

            {/* Navigation tabs */}
            <nav className="hidden md:flex items-center gap-1">
              {navLinks.map((link) => {
                const Icon = link.icon;
                const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={cn(
                      'flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all focus:outline-none focus:ring-2 focus:ring-[#006BFF]',
                      isActive
                        ? 'bg-blue-50 text-[#006BFF] font-semibold'
                        : 'text-slate-600 hover:text-[#0B3558] hover:bg-slate-50'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{link.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Right side: Role Demo Switcher & Active User */}
          <div className="flex items-center gap-3">
            {/* Quick Demo Role Switcher */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                disabled={isSwitching}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-medium text-[#0B3558] shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
                aria-expanded={dropdownOpen}
                aria-haspopup="true"
              >
                <Shield className="w-3.5 h-3.5 text-[#006BFF]" />
                <span className="hidden sm:inline">Peran Demo:</span>
                <span className="font-semibold text-slate-900">
                  {currentUser?.role || 'Memuat...'}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {dropdownOpen && (
                <div className="absolute right-0 mt-1.5 w-64 bg-white rounded-xl shadow-lg border border-slate-200 py-1.5 z-50 animate-in fade-in-50 zoom-in-95">
                  <div className="px-3 py-1.5 border-b border-slate-100 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Ganti Peran Pengguna (SoD Demo)
                  </div>
                  {PRESET_USERS.map((u) => {
                    const isSelected = currentUser?.email === u.email;
                    return (
                      <button
                        key={u.email}
                        type="button"
                        onClick={() => handleSwitchUser(u.email)}
                        className={cn(
                          'w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-50 transition-colors',
                          isSelected && 'bg-blue-50/60 font-semibold text-[#006BFF]'
                        )}
                      >
                        <div className="flex flex-col">
                          <span className="text-[#0B3558] font-medium">{u.label}</span>
                          <span className="text-[10px] text-slate-500">{u.email}</span>
                        </div>
                        {isSelected && <Check className="w-3.5 h-3.5 text-[#006BFF]" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* User Profile Pill */}
            {currentUser && (
              <div className="flex items-center gap-2.5 pl-3 border-l border-slate-200">
                <div className="w-8 h-8 rounded-full bg-[#0B3558]/10 text-[#0B3558] flex items-center justify-center font-bold text-xs">
                  {currentUser.fullName
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .substring(0, 2)
                    .toUpperCase()}
                </div>
                <div className="hidden lg:flex flex-col text-left">
                  <span className="text-xs font-semibold text-[#0B3558] leading-tight">
                    {currentUser.fullName}
                  </span>
                  <span className="text-[10px] text-slate-500">
                    {currentUser.email}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
