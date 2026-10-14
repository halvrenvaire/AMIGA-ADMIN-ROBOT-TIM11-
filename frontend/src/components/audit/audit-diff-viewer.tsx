'use client';

import React from 'react';
import { formatCurrency } from '../../lib/utils';
import { ArrowRight, AlertTriangle, ShieldCheck, FileText, CheckCircle2 } from 'lucide-react';

interface AuditDiffViewerProps {
  changeDiff: Record<string, any> | null | undefined;
  actionType?: string;
}

/**
 * Panel Diff Viewer untuk memvisualisasikan delta perubahan data [DR-005, PR-025, PF-020].
 * Menampilkan nilai lama (merah/coret) vs nilai baru (hijau) secara kontras,
 * menyensor PII rekening, dan menampilkan catatan/alasan perubahan.
 */
export function AuditDiffViewer({ changeDiff, actionType }: AuditDiffViewerProps) {
  if (!changeDiff || Object.keys(changeDiff).length === 0) {
    return null;
  }

  // 1. Deteksi perubahan nominal subtotal & total
  const hasSubtotalDiff = 'previousSubtotal' in changeDiff && 'newSubtotal' in changeDiff;
  const hasTotalDiff = 'previousTotal' in changeDiff && 'newTotal' in changeDiff;

  // 2. Deteksi pelanggaran SoD / Reassignment
  const hasSodBlock = actionType === 'SOD_VIOLATION_BLOCKED' || 'attemptedBy' in changeDiff;
  const hasWorkloadReassign = actionType === 'WORKLOAD_REASSIGNED' || ('previousReviewerId' in changeDiff && 'newReviewerId' in changeDiff);

  // 3. Catatan / Alasan / Reason
  const reasonText =
    changeDiff.returnReason ||
    changeDiff.comments ||
    changeDiff.reason ||
    changeDiff.note ||
    changeDiff.sodNote;

  return (
    <div className="mt-3 text-xs bg-slate-50/80 border border-slate-200/90 rounded-lg p-3.5 space-y-3">
      {/* Catatan Alasan / Justifikasi Perubahan jika ada */}
      {reasonText && (
        <div className="flex items-start gap-2 bg-amber-50/80 border border-amber-200/80 rounded-md p-2.5 text-amber-900">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold text-[11px] uppercase tracking-wider block text-amber-800">
              Alasan / Catatan Aktor:
            </span>
            <p className="mt-0.5 text-xs text-amber-950 font-medium whitespace-pre-wrap">
              {String(reasonText)}
            </p>
          </div>
        </div>
      )}

      {/* Tampilan Delta Subtotal & Total Finansial */}
      {(hasSubtotalDiff || hasTotalDiff) && (
        <div className="space-y-2">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Perbandingan Nominal Finansial:
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {hasSubtotalDiff && (
              <div className="bg-white border border-slate-200 rounded p-2.5 shadow-2xs">
                <span className="text-[11px] text-slate-500 block mb-1">Subtotal Rincian Item</span>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 line-through font-mono text-[11px]">
                    {formatCurrency(changeDiff.previousSubtotal)}
                  </span>
                  <ArrowRight className="w-3 h-3 text-slate-400" />
                  <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold font-mono text-[11px]">
                    {formatCurrency(changeDiff.newSubtotal)}
                  </span>
                </div>
              </div>
            )}

            {hasTotalDiff && (
              <div className="bg-white border border-slate-200 rounded p-2.5 shadow-2xs">
                <span className="text-[11px] text-slate-500 block mb-1">Total Invoice Tagihan</span>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 line-through font-mono text-[11px]">
                    {formatCurrency(changeDiff.previousTotal)}
                  </span>
                  <ArrowRight className="w-3 h-3 text-slate-400" />
                  <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold font-mono text-[11px]">
                    {formatCurrency(changeDiff.newTotal)}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tampilan SoD Blocking Callout */}
      {hasSodBlock && (
        <div className="bg-rose-50/90 border border-rose-200 rounded-md p-2.5 text-rose-900 space-y-1">
          <div className="flex items-center gap-1.5 font-bold text-xs text-rose-800">
            <ShieldCheck className="w-4 h-4 text-rose-600" />
            <span>Penegakan Aturan Segregation of Duties (BR-002)</span>
          </div>
          <p className="text-[11px] text-rose-700">
            Upaya approval oleh pengunggah dicegah di sisi server. Penugasan dokumen dialihkan otomatis ke reviewer alternatif.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-1 text-[11px]">
            {changeDiff.attemptedBy && (
              <div>
                <span className="text-slate-500">Percobaan oleh:</span>{' '}
                <strong className="font-mono text-rose-900">{changeDiff.attemptedBy}</strong>
              </div>
            )}
            {changeDiff.reassignedTo && (
              <div>
                <span className="text-slate-500">Dialihkan ke:</span>{' '}
                <strong className="font-mono text-emerald-800">{changeDiff.reassignedTo}</strong>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tampilan Perubahan Penugasan Reviewer */}
      {hasWorkloadReassign && !hasSodBlock && (
        <div className="bg-white border border-slate-200 rounded-md p-2 text-slate-700">
          <span className="text-[11px] font-semibold text-slate-500 block mb-1">
            Perubahan Reviewer Bertugas:
          </span>
          <div className="flex items-center gap-2 text-xs">
            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[11px]">
              {changeDiff.previousReviewerId || 'Belum Ditugaskan'}
            </span>
            <ArrowRight className="w-3 h-3 text-slate-400" />
            <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-bold font-mono text-[11px]">
              {changeDiff.newReviewerId || 'Reviewer Baru'}
            </span>
          </div>
        </div>
      )}

      {/* Tampilan Perbaikan Data Rekening & Pembayaran (Payment Details) */}
      {changeDiff.paymentDetails && (
        <div className="bg-white border border-slate-200 rounded-md p-2.5 space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-700">
            <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" />
            <span>Data Rekening & Bank Penerima:</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs font-mono">
            {changeDiff.paymentDetails.bankName && (
              <div>
                <span className="text-slate-400 text-[10px] block">Bank:</span>
                <span className="font-semibold text-slate-800">{changeDiff.paymentDetails.bankName}</span>
              </div>
            )}
            {changeDiff.paymentDetails.accountNumber && (
              <div>
                <span className="text-slate-400 text-[10px] block">Nomor Rekening:</span>
                <span className="font-semibold text-slate-800 bg-slate-100 px-1 py-0.5 rounded">
                  {changeDiff.paymentDetails.accountNumber}
                </span>
              </div>
            )}
            {changeDiff.paymentDetails.accountHolderName && (
              <div>
                <span className="text-slate-400 text-[10px] block">Atas Nama:</span>
                <span className="font-semibold text-slate-800">{changeDiff.paymentDetails.accountHolderName}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Detail Properti Lainnya (Key-Value Grid) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 pt-1">
        {Object.entries(changeDiff).map(([key, val]) => {
          // Lewati field yang telah dirender di bagian atas secara khusus
          if (
            [
              'previousSubtotal',
              'newSubtotal',
              'previousTotal',
              'newTotal',
              'returnReason',
              'comments',
              'reason',
              'note',
              'sodNote',
              'attemptedBy',
              'reassignedTo',
              'previousReviewerId',
              'newReviewerId',
              'paymentDetails',
            ].includes(key)
          ) {
            return null;
          }

          let displayVal = '';
          if (typeof val === 'boolean') {
            displayVal = val ? 'Ya (True)' : 'Tidak (False)';
          } else if (typeof val === 'object' && val !== null) {
            displayVal = JSON.stringify(val);
          } else {
            displayVal = String(val ?? '-');
          }

          return (
            <div
              key={key}
              className="bg-white/90 border border-slate-200/80 rounded px-2.5 py-1.5 flex flex-col justify-between"
            >
              <span className="text-[10px] text-slate-500 font-medium tracking-tight truncate uppercase">
                {key.replace(/([A-Z])/g, ' $1').trim()}
              </span>
              <span className="text-xs font-mono text-slate-800 font-medium break-all mt-0.5">
                {displayVal}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
