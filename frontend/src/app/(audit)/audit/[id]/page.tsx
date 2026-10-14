'use client';

import React, { use, useState, useMemo } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '../../../../components/layout/navbar';
import { AuditHeader } from '../../../../components/audit/audit-header';
import {
  AuditFilterBar,
  AuditFilterCategory,
} from '../../../../components/audit/audit-filter-bar';
import { AuditTimelineItem } from '../../../../components/audit/audit-timeline-item';
import { api } from '../../../../lib/api';
import { formatAuditTimestamp } from '../../../../lib/utils';
import { AuditLogItem } from '../../../../lib/types';
import {
  Loader2,
  AlertCircle,
  FileSearch,
  ArrowLeft,
  RefreshCw,
  Clock,
  ShieldCheck,
} from 'lucide-react';

interface AuditTrailPageProps {
  params: Promise<{ id: string }>;
}

/**
 * Layar 05: Riwayat & Jejak Audit (Audit Trail Timeline & Diff Viewer) [T-021].
 * Memenuhi kebutuhan PR-025, DR-005, PF-020.
 */
export default function AuditTrailPage({ params }: AuditTrailPageProps) {
  const resolvedParams = use(params);
  const lookupId = resolvedParams.id;

  // Filter & Search Local States
  const [currentCategory, setCurrentCategory] = useState<AuditFilterCategory>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // Fetch Audit Trail Data [PR-025, DR-005]
  const {
    data: auditData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['audit-trail', lookupId],
    queryFn: () => api.getAuditTrail(lookupId),
    staleTime: 10000,
  });

  const invoice = auditData?.invoice;
  const rawLogs = auditData?.auditLogs || [];

  // Hitung jumlah kategori untuk filter bar
  const counts = useMemo(() => {
    let diffOnly = 0;
    let approvalSod = 0;

    for (const log of rawLogs) {
      if (log.changeDiff && Object.keys(log.changeDiff).length > 0) {
        diffOnly++;
      }
      if (
        log.actionType === 'REVIEW_APPROVED' ||
        log.actionType === 'SOD_VIOLATION_BLOCKED' ||
        log.actionType === 'SOD_AUTO_REASSIGN' ||
        log.actionType === 'WORKLOAD_REASSIGNED' ||
        log.actionType === 'WORKLOAD_REBALANCE_LEAD' ||
        (log.previousStatus && log.newStatus)
      ) {
        approvalSod++;
      }
    }

    return {
      all: rawLogs.length,
      diffOnly,
      approvalSod,
    };
  }, [rawLogs]);

  // Filter dan sorting logs berdasarkan input pengguna
  const filteredLogs = useMemo(() => {
    let result = [...rawLogs];

    // 1. Filter Kategori
    if (currentCategory === 'DIFF_ONLY') {
      result = result.filter(
        (log) => log.changeDiff && Object.keys(log.changeDiff).length > 0
      );
    } else if (currentCategory === 'APPROVAL_SOD') {
      result = result.filter(
        (log) =>
          log.actionType === 'REVIEW_APPROVED' ||
          log.actionType === 'SOD_VIOLATION_BLOCKED' ||
          log.actionType === 'SOD_AUTO_REASSIGN' ||
          log.actionType === 'WORKLOAD_REASSIGNED' ||
          log.actionType === 'WORKLOAD_REBALANCE_LEAD' ||
          (log.previousStatus && log.newStatus)
      );
    }

    // 2. Pencarian Teks Bebas
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((log) => {
        const matchAction = log.actionType.toLowerCase().includes(q);
        const matchActor = log.actorName.toLowerCase().includes(q);
        const matchRole = log.actorRole.toLowerCase().includes(q);
        const matchIp = log.ipAddress ? log.ipAddress.toLowerCase().includes(q) : false;
        const matchDiff = log.changeDiff
          ? JSON.stringify(log.changeDiff).toLowerCase().includes(q)
          : false;

        return matchAction || matchActor || matchRole || matchIp || matchDiff;
      });
    }

    // 3. Sorting (Default: ASC / Kronologis dari terawal)
    result.sort((a, b) => {
      const timeA = new Date(a.createdAt).getTime();
      const timeB = new Date(b.createdAt).getTime();
      return sortOrder === 'asc' ? timeA - timeB : timeB - timeA;
    });

    return result;
  }, [rawLogs, currentCategory, searchQuery, sortOrder]);

  // Handler Ekspor CSV [DR-005]
  const handleExportCsv = () => {
    if (!invoice || rawLogs.length === 0) return;

    const headers = [
      'ID Log',
      'Waktu Presisi (WIB)',
      'Aktor',
      'Peran Aktor',
      'Jenis Aktivitas',
      'Status Sebelumnya',
      'Status Baru',
      'Alamat IP',
      'Delta Perubahan (Diff JSON)',
    ];

    const escapeCsv = (str: string | null | undefined) => {
      if (!str) return '""';
      return `"${str.replace(/"/g, '""')}"`;
    };

    const rows = rawLogs.map((log) => [
      escapeCsv(log.id),
      escapeCsv(formatAuditTimestamp(log.createdAt)),
      escapeCsv(log.actorName),
      escapeCsv(log.actorRole),
      escapeCsv(log.actionType),
      escapeCsv(log.previousStatus || '-'),
      escapeCsv(log.newStatus || '-'),
      escapeCsv(log.ipAddress || '-'),
      escapeCsv(log.changeDiff ? JSON.stringify(log.changeDiff) : '-'),
    ]);

    const csvContent =
      'data:text/csv;charset=utf-8,\uFEFF' +
      [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute(
      'download',
      `audit-trail-${invoice.requestId.replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Handler Ekspor JSON [DR-005]
  const handleExportJson = () => {
    if (!invoice || rawLogs.length === 0) return;

    const exportPayload = {
      exportMetadata: {
        system: 'AMIGA Robot Admin (Intelligent Invoice Processing)',
        generatedAt: new Date().toISOString(),
        requestId: invoice.requestId,
        tenantClientCode: invoice.clientCode,
      },
      invoice,
      auditLogs: rawLogs,
    };

    const dataStr =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(JSON.stringify(exportPayload, null, 2));
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute(
      'download',
      `audit-trail-${invoice.requestId.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="min-h-screen bg-[#F8F9FB] text-[#0B3558] flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
        {/* Loading State */}
        {isLoading && (
          <div className="bg-white border border-slate-200 rounded-xl p-16 flex flex-col items-center justify-center text-center shadow-xs">
            <Loader2 className="w-8 h-8 text-[#006BFF] animate-spin mb-3" />
            <h3 className="text-sm font-bold text-[#0B3558]">
              Memuat Riwayat Jejak Audit...
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Mengambil buku besar permanen (immutable audit ledger) dokumen {lookupId}.
            </p>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="bg-white border border-amber-200 rounded-xl p-10 flex flex-col items-center justify-center text-center shadow-xs">
            <div className="w-12 h-12 rounded-full bg-amber-50 flex items-center justify-center text-amber-600 mb-3">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-[#0B3558]">
              Jejak Audit Tidak Dapat Diakses
            </h3>
            <p className="text-xs text-slate-600 max-w-md mt-1 mb-6">
              Dokumen tidak ditemukan atau akun Anda tidak memiliki hak akses multi-tenant ke dokumen organisasi klien ini.
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-blue-700 rounded-lg transition-colors shadow-xs"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Coba Muat Ulang</span>
              </button>
              <Link
                href="/queue"
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Kembali ke Antrean</span>
              </Link>
            </div>
          </div>
        )}

        {/* Main Content Area */}
        {invoice && !isLoading && (
          <>
            {/* Header Ringkasan Dokumen & Hak Akses Terisolasi */}
            <AuditHeader
              invoice={invoice}
              auditLogs={rawLogs}
              onExportCsv={handleExportCsv}
              onExportJson={handleExportJson}
            />

            {/* Bilah Filter Tabs, Search & Sort */}
            <AuditFilterBar
              currentCategory={currentCategory}
              onSelectCategory={setCurrentCategory}
              counts={counts}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              sortOrder={sortOrder}
              onToggleSortOrder={() =>
                setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))
              }
            />

            {/* Area Garis Waktu Kronologis Vertikal */}
            <section
              aria-label="Garis Waktu Kronologis Aktivitas Dokumen"
              className="mt-6"
            >
              {filteredLogs.length > 0 ? (
                <div className="relative">
                  {filteredLogs.map((log, index) => (
                    <AuditTimelineItem
                      key={log.id}
                      item={log}
                      isFirst={index === 0}
                      isLast={index === 0 ? false : index === filteredLogs.length - 1}
                    />
                  ))}
                </div>
              ) : (
                <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-xs">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mx-auto mb-3">
                    <FileSearch className="w-5 h-5" />
                  </div>
                  <h4 className="text-sm font-bold text-[#0B3558]">
                    Tidak Ada Aktivitas Sesuai Kriteria
                  </h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto mb-4">
                    Tidak ditemukan catatan audit yang cocok dengan kata kunci pencarian atau filter kategori yang dipilih.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setCurrentCategory('ALL');
                      setSearchQuery('');
                    }}
                    className="px-3.5 py-1.5 text-xs font-semibold text-[#006BFF] bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-colors"
                  >
                    Reset Filter
                  </button>
                </div>
              )}
            </section>

            {/* Footer Keterangan Keabsahan Buku Besar Audit */}
            <div className="mt-8 pt-6 border-t border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-400">
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Buku besar jejak audit bersifat append-only dan tidak dapat dimanipulasi.</span>
              </div>
              <div className="font-mono text-[11px]">
                Sistem Integritas AMIGA Robot Admin &bull; ISO/IEC 27001 Compliant
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
