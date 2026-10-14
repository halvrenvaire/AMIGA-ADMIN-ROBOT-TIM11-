'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '../../components/layout/navbar';
import { MetricCardsBar } from '../../components/dashboard/metric-cards-bar';
import { ReviewerWorkloadBar } from '../../components/dashboard/reviewer-workload-bar';
import { QueueTable } from '../../components/dashboard/queue-table';
import { CorrectionModal } from '../../components/dashboard/correction-modal';
import { api } from '../../lib/api';
import { InvoiceStatus, InvoiceSummaryItem } from '../../lib/types';
import { Search, RefreshCw, Filter, ChevronLeft, ChevronRight } from 'lucide-react';

export default function QueuePage() {
  const [activeStatus, setActiveStatus] = useState<InvoiceStatus | 'ALL'>('ALL');
  const [selectedClientId, setSelectedClientId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [correctionTarget, setCorrectionTarget] = useState<InvoiceSummaryItem | null>(null);

  // 1. Fetch Client List for Filter
  const { data: clients = [] } = useQuery({
    queryKey: ['clients-list'],
    queryFn: () => api.getClients(),
    staleTime: 60000,
  });

  // 2. Fetch Queue with 5-second polling interval [PR-016, DR-001]
  const {
    data: queueData,
    isLoading,
    isRefetching,
    refetch,
  } = useQuery({
    queryKey: ['invoice-queue', activeStatus, selectedClientId, searchQuery, page],
    queryFn: () =>
      api.getQueue({
        status: activeStatus === 'ALL' ? undefined : activeStatus,
        clientId: selectedClientId || undefined,
        search: searchQuery || undefined,
        page,
        limit: 15,
      }),
    refetchInterval: 5000, // SLA Auto-refetch setiap 5 detik
  });

  const statusCounts = queueData?.statusCounts || {
    QUEUED: 0,
    PROCESSING: 0,
    READY_FOR_REVIEW: 0,
    EXCEPTION: 0,
    AMIGA_REVIEWED: 0,
    SENT_TO_CLIENT: 0,
    ALL: 0,
  };

  const handleSelectFilter = (filter: InvoiceStatus | 'ALL') => {
    setActiveStatus(filter);
    setPage(1);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F8F9FB]">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Page Title & Refresh */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-xl font-bold text-[#0B3558] tracking-tight">
              Dashboard Antrean & Monitoring Beban
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Pemrosesan otomatis invoice vendor multi-klien menuju voucher pembayaran resmi terverifikasi.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isRefetching}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 text-slate-500 ${
                  isRefetching ? 'animate-spin text-[#006BFF]' : ''
                }`}
              />
              <span>{isRefetching ? 'Memperbarui...' : 'Segarkan Antrean'}</span>
            </button>
          </div>
        </div>

        {/* 1. Metric Cards Bar */}
        <MetricCardsBar
          statusCounts={statusCounts}
          activeFilter={activeStatus}
          onSelectFilter={handleSelectFilter}
        />

        {/* 2. Reviewer Workload Bar */}
        {queueData?.reviewerWorkloads && (
          <ReviewerWorkloadBar workloads={queueData.reviewerWorkloads} />
        )}

        {/* 3. Filters & Search Bar */}
        <div className="bg-white border border-slate-200 rounded-xl p-3.5 mb-4 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
              <input
                type="text"
                placeholder="Cari nomor invoice, vendor, atau Request ID..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs font-medium text-slate-600">Klien:</span>
            </div>
            <select
              value={selectedClientId}
              onChange={(e) => {
                setSelectedClientId(e.target.value);
                setPage(1);
              }}
              className="text-xs py-2 px-2.5 rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
            >
              <option value="">Semua Klien Terotorisasi</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.clientCode} · {c.clientName}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 4. Queue Table */}
        <QueueTable
          items={queueData?.items || []}
          isLoading={isLoading}
          onOpenCorrection={(item) => setCorrectionTarget(item)}
        />

        {/* 5. Pagination */}
        {queueData && queueData.totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 px-2 text-xs text-slate-500">
            <span>
              Menampilkan {(queueData.page - 1) * queueData.limit + 1} sampai{' '}
              {Math.min(queueData.page * queueData.limit, queueData.totalCount)} dari{' '}
              <strong className="text-slate-800">{queueData.totalCount}</strong> dokumen
            </span>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={queueData.page <= 1}
                className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors"
                aria-label="Halaman sebelumnya"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 font-mono font-medium text-slate-700">
                {queueData.page} / {queueData.totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(queueData.totalPages, p + 1))}
                disabled={queueData.page >= queueData.totalPages}
                className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors"
                aria-label="Halaman selanjutnya"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Correction Modal for EXCEPTION */}
        {correctionTarget && (
          <CorrectionModal
            invoice={correctionTarget}
            onClose={() => setCorrectionTarget(null)}
            onSuccess={() => {
              setCorrectionTarget(null);
              refetch();
            }}
          />
        )}
      </main>
    </div>
  );
}
