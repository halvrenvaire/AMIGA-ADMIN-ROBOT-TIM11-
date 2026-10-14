'use client';

import React from 'react';
import { Search, ArrowUpDown, Filter } from 'lucide-react';

export type AuditFilterCategory = 'ALL' | 'DIFF_ONLY' | 'APPROVAL_SOD';

interface AuditFilterBarProps {
  currentCategory: AuditFilterCategory;
  onSelectCategory: (category: AuditFilterCategory) => void;
  counts: {
    all: number;
    diffOnly: number;
    approvalSod: number;
  };
  searchQuery: string;
  onSearchChange: (query: string) => void;
  sortOrder: 'asc' | 'desc';
  onToggleSortOrder: () => void;
}

export function AuditFilterBar({
  currentCategory,
  onSelectCategory,
  counts,
  searchQuery,
  onSearchChange,
  sortOrder,
  onToggleSortOrder,
}: AuditFilterBarProps) {
  const tabs: Array<{ id: AuditFilterCategory; label: string; count: number }> = [
    { id: 'ALL', label: 'Semua Aktivitas', count: counts.all },
    { id: 'DIFF_ONLY', label: 'Perubahan Data / Diff', count: counts.diffOnly },
    { id: 'APPROVAL_SOD', label: 'Persetujuan & SoD', count: counts.approvalSod },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3 sm:p-4 mb-6 shadow-xs space-y-3">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
          <div className="flex items-center text-xs font-semibold text-slate-500 mr-2 flex-shrink-0">
            <Filter className="w-3.5 h-3.5 mr-1" />
            <span>Kategori:</span>
          </div>

          {tabs.map((tab) => {
            const isActive = currentCategory === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onSelectCategory(tab.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-[#006BFF] text-white shadow-xs'
                    : 'text-slate-600 hover:text-[#0B3558] hover:bg-slate-100'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                    isActive ? 'bg-white/25 text-white' : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Search & Sort Controls */}
        <div className="flex items-center gap-2">
          {/* Pencarian Teks */}
          <div className="relative flex-1 sm:w-64">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Cari aktivitas, aktor, field..."
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-[#0B3558] placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:bg-white transition-all"
            />
          </div>

          {/* Toggle Urutan (ASC / DESC) */}
          <button
            type="button"
            onClick={onToggleSortOrder}
            title={
              sortOrder === 'asc'
                ? 'Urutan Kronologis (Paling Awal -> Terkini)'
                : 'Urutan Terbalik (Terkini -> Paling Awal)'
            }
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors flex-shrink-0"
          >
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-500" />
            <span className="hidden sm:inline">
              {sortOrder === 'asc' ? 'Kronologis (Awal)' : 'Terbaru Dulu'}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
