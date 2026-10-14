'use client';

import React from 'react';
import Link from 'next/link';
import { StatusBadge } from '../common/status-badge';
import { formatDate } from '../../lib/utils';
import { InvoiceStatus, AuditLogItem } from '../../lib/types';
import {
  ArrowLeft,
  ShieldCheck,
  Building2,
  Calendar,
  FileText,
  ExternalLink,
  Download,
  Clock,
  GitCommit,
  CheckCircle2,
} from 'lucide-react';

interface AuditHeaderProps {
  invoice: {
    id: string;
    requestId: string;
    clientId: string;
    clientName: string;
    clientCode: string;
    vendorName: string | null;
    invoiceNumber: string | null;
    status: InvoiceStatus;
    submissionDate: string;
  };
  auditLogs: AuditLogItem[];
  onExportCsv: () => void;
  onExportJson: () => void;
}

export function AuditHeader({
  invoice,
  auditLogs,
  onExportCsv,
  onExportJson,
}: AuditHeaderProps) {
  // Hitung metrik ringkasan audit
  const totalEvents = auditLogs.length;
  const statusTransitionsCount = auditLogs.filter((l) => l.previousStatus && l.newStatus).length;
  const diffCount = auditLogs.filter((l) => l.changeDiff && Object.keys(l.changeDiff).length > 0).length;

  const isVoucherReady =
    invoice.status === 'AMIGA_REVIEWED' || invoice.status === 'SENT_TO_CLIENT';

  return (
    <div className="space-y-4 mb-6">
      {/* Top Navigation & Action Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            href="/queue"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors shadow-2xs"
          >
            <ArrowLeft className="w-3.5 h-3.5 text-slate-500" />
            <span>Kembali ke Antrean</span>
          </Link>
          <div className="h-4 w-px bg-slate-200" />
          <h1 className="text-xs font-bold text-[#0B3558] tracking-wider uppercase">
            Jejak Audit & Riwayat Dokumen
          </h1>
        </div>

        {/* Action Buttons: Tinjau/Voucher & Ekspor */}
        <div className="flex items-center gap-2 flex-wrap">
          {isVoucherReady ? (
            <Link
              href={`/voucher/${invoice.requestId}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-[#006BFF] hover:bg-blue-700 rounded-lg transition-colors shadow-xs"
            >
              <span>Lihat Voucher Resmi</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          ) : (
            <Link
              href={`/review/${invoice.requestId}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-[#006BFF] hover:bg-blue-700 rounded-lg transition-colors shadow-xs"
            >
              <span>Layar Peninjauan Reviewer</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          )}

          {/* Export Dropdown / Buttons */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={onExportCsv}
              title="Ekspor Jejak Audit ke berkas CSV"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors shadow-2xs"
            >
              <Download className="w-3.5 h-3.5 text-slate-500" />
              <span>Ekspor CSV</span>
            </button>
            <button
              type="button"
              onClick={onExportJson}
              title="Ekspor Jejak Audit ke berkas JSON"
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors shadow-2xs font-mono"
            >
              <span>JSON</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Document Details Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
        {/* Row 1: Title, Request ID, Tenant Isolation Badge */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Dokumen Request ID:
              </span>
              <h2 className="text-base sm:text-lg font-bold text-[#0B3558] font-mono tracking-tight">
                {invoice.requestId}
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Jejak riwayat operasional berstatus permanen (append-only) dan terlindungi aturan Segregation of Duties.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Multi-Tenant Security Badge [DR-005, SR-003] */}
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>Hak Akses: Terisolasi</span>
            </div>

            {/* Status Terkini Badge */}
            <StatusBadge status={invoice.status} size="md" />
          </div>
        </div>

        {/* Row 2: Metadata Badges Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 pt-4 text-xs">
          {/* Organisasi Klien */}
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
              <Building2 className="w-4 h-4" />
            </div>
            <div>
              <span className="text-slate-400 text-[11px] block">Organisasi Klien:</span>
              <span className="font-semibold text-slate-800">{invoice.clientName}</span>
              <span className="text-slate-500 font-mono text-[11px] block">({invoice.clientCode})</span>
            </div>
          </div>

          {/* Vendor Tagihan */}
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-100">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <span className="text-slate-400 text-[11px] block">Vendor Rekanan:</span>
              <span className="font-semibold text-slate-800">
                {invoice.vendorName || 'Belum Terdeteksi'}
              </span>
              {invoice.invoiceNumber && (
                <span className="text-slate-500 font-mono text-[11px] block">
                  No: {invoice.invoiceNumber}
                </span>
              )}
            </div>
          </div>

          {/* Tanggal Pengajuan */}
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-lg bg-purple-50 text-purple-600 border border-purple-100">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <span className="text-slate-400 text-[11px] block">Tanggal Pengajuan:</span>
              <span className="font-semibold text-slate-800">
                {formatDate(invoice.submissionDate)}
              </span>
              <span className="text-slate-400 text-[11px] block">Melalui Digital PDF</span>
            </div>
          </div>

          {/* Statistik Jejak Audit */}
          <div className="flex items-start gap-2.5">
            <div className="p-2 rounded-lg bg-teal-50 text-teal-600 border border-teal-100">
              <Clock className="w-4 h-4" />
            </div>
            <div>
              <span className="text-slate-400 text-[11px] block">Aktivitas Jejak:</span>
              <span className="font-semibold text-slate-800">{totalEvents} Entri Tercatat</span>
              <span className="text-slate-500 text-[11px] block">
                {statusTransitionsCount} Mutasi &bull; {diffCount} Diff
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
