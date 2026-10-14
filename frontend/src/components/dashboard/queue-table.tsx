'use client';

import React from 'react';
import Link from 'next/link';
import { InvoiceSummaryItem } from '../../lib/types';
import { StatusBadge } from '../common/status-badge';
import { formatCurrency, formatDateTime } from '../../lib/utils';
import { ExternalLink, Edit3, AlertCircle, FileText, CheckCircle2, History } from 'lucide-react';

interface QueueTableProps {
  items: InvoiceSummaryItem[];
  isLoading: boolean;
  onOpenCorrection: (item: InvoiceSummaryItem) => void;
}

export function QueueTable({ items, isLoading, onOpenCorrection }: QueueTableProps) {
  if (isLoading && items.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
        <div className="inline-block w-8 h-8 border-3 border-blue-200 border-t-[#006BFF] rounded-full animate-spin mb-3" />
        <p className="text-sm font-medium text-slate-600">Memuat antrean invoice...</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-12 text-center shadow-sm">
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
          <FileText className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-bold text-[#0B3558] mb-1">
          Tidak Ada Dokumen
        </h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mb-4">
          Tidak ada dokumen invoice yang sesuai dengan kriteria filter saat ini.
        </p>
        <Link
          href="/upload"
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] rounded-lg transition-colors shadow-sm"
        >
          Unggah Dokumen Baru
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/70 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th className="py-3 px-4">Request ID</th>
              <th className="py-3 px-4">Klien & Tanggal</th>
              <th className="py-3 px-4">Vendor & No. Invoice</th>
              <th className="py-3 px-4 text-right">Total Finansial</th>
              <th className="py-3 px-4 text-center">Status Dokumen</th>
              <th className="py-3 px-4">Reviewer / Isu</th>
              <th className="py-3 px-4 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
            {items.map((item) => {
              return (
                <tr
                  key={item.id}
                  className="hover:bg-slate-50/60 transition-colors"
                >
                  {/* Request ID */}
                  <td className="py-3.5 px-4 font-mono font-bold text-[#0B3558]">
                    {item.requestId}
                    <div className="text-[10px] text-slate-400 font-normal">
                      {item.filePageCount} Halaman ({item.originalFileName})
                    </div>
                  </td>

                  {/* Klien & Tanggal */}
                  <td className="py-3.5 px-4">
                    <span className="font-semibold text-slate-900 block">
                      {item.clientName}
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      {item.clientCode} · {formatDateTime(item.submissionDate)}
                    </span>
                  </td>

                  {/* Vendor & No. Invoice */}
                  <td className="py-3.5 px-4">
                    <span className="font-medium text-slate-900 block truncate max-w-[200px]">
                      {item.vendorName || 'Dalam Proses Ekstraksi...'}
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      {item.invoiceNumber || '-'}
                    </span>
                  </td>

                  {/* Total Finansial */}
                  <td className="py-3.5 px-4 text-right font-mono tabular-nums font-semibold text-[#0B3558]">
                    {formatCurrency(item.totalAmount)}
                  </td>

                  {/* Status Dokumen */}
                  <td className="py-3.5 px-4 text-center">
                    <StatusBadge status={item.status} size="sm" />
                  </td>

                  {/* Reviewer / Isu */}
                  <td className="py-3.5 px-4">
                    {item.activeIssuesCount > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        <AlertCircle className="w-3 h-3 text-amber-600" />
                        {item.activeIssuesCount} Kendala
                      </span>
                    ) : item.currentReviewerName ? (
                      <span className="text-[11px] text-slate-600 truncate block max-w-[140px]">
                        {item.currentReviewerName}
                      </span>
                    ) : (
                      <span className="text-[11px] text-slate-400">-</span>
                    )}
                  </td>

                  {/* Aksi */}
                  <td className="py-3.5 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <Link
                        href={`/audit/${item.requestId}`}
                        title="Lihat Jejak Audit Dokumen"
                        className="p-1.5 text-slate-400 hover:text-[#0B3558] hover:bg-slate-100 rounded-lg transition-colors border border-transparent hover:border-slate-200"
                      >
                        <History className="w-3.5 h-3.5" />
                      </Link>

                      {item.status === 'READY_FOR_REVIEW' && (
                        <Link
                          href={`/review/${item.requestId}`}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
                        >
                          <span>Tinjau</span>
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      )}

                      {item.status === 'EXCEPTION' && (
                        <button
                          type="button"
                          onClick={() => onOpenCorrection(item)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-amber-900 bg-amber-100 hover:bg-amber-200 rounded-lg transition-colors border border-amber-300 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
                        >
                          <Edit3 className="w-3 h-3" />
                          <span>Koreksi</span>
                        </button>
                      )}

                      {(item.status === 'AMIGA_REVIEWED' || item.status === 'SENT_TO_CLIENT') && (
                        <Link
                          href={`/voucher/${item.requestId}`}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors border border-blue-200"
                        >
                          <span>Lihat Voucher</span>
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      )}

                      {(item.status === 'QUEUED' || item.status === 'PROCESSING') && (
                        <span className="text-[11px] text-slate-400 font-medium italic">
                          Memproses...
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
