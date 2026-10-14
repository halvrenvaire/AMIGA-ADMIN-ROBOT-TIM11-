'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ReviewDataResponse } from '../../lib/types';
import { LineItemsEditor } from './line-items-editor';
import { StatusBadge } from '../common/status-badge';
import { formatCurrency, formatDate } from '../../lib/utils';
import {
  Building2,
  Calendar,
  CreditCard,
  AlertTriangle,
  ShieldAlert,
  CheckCircle,
  RotateCcw,
  FileCheck,
  Building,
  User,
  ExternalLink,
} from 'lucide-react';

interface FinancialEditorPaneProps {
  data: ReviewDataResponse;
  onSaveLineItems: (
    items: Array<{
      id?: string;
      description: string;
      quantity: number;
      unitPrice: number;
      subtotal: number;
    }>
  ) => Promise<void>;
  onApprove: () => Promise<void>;
  onReturn: (reason: string) => Promise<void>;
  isProcessingAction: boolean;
}

export function FinancialEditorPane({
  data,
  onSaveLineItems,
  onApprove,
  onReturn,
  isProcessingAction,
}: FinancialEditorPaneProps) {
  const router = useRouter();
  const { invoice, lineItems, paymentDetails, issues, isUploader, canApprove } = data;

  const [returnModalOpen, setReturnModalOpen] = useState<boolean>(false);
  const [returnReason, setReturnReason] = useState<string>('');
  const [actionError, setActionError] = useState<string | null>(null);

  const handleReturnSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      await onReturn(returnReason);
      setReturnModalOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Gagal mengembalikan dokumen.';
      setActionError(msg);
    }
  };

  const handleApproveClick = async () => {
    setActionError(null);
    try {
      await onApprove();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Gagal menyetujui dokumen.';
      setActionError(msg);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 bg-[#F8F9FB]">
      {/* 1. Header Card */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-[#0B3558] bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
              {invoice.requestId}
            </span>
            <StatusBadge status={invoice.status} />
          </div>

          <div className="text-right">
            <span className="text-[11px] text-slate-400 block">Klien:</span>
            <span className="text-xs font-bold text-slate-800">
              {invoice.clientName} ({invoice.clientCode})
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 border-t border-slate-100 text-xs">
          <div>
            <span className="text-slate-400 block text-[11px]">Nama Vendor:</span>
            <span className="font-semibold text-[#0B3558]">
              {invoice.vendorName || 'Belum terdeteksi'}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block text-[11px]">Nomor Invoice:</span>
            <span className="font-mono font-medium text-slate-800">
              {invoice.invoiceNumber || '-'}
            </span>
          </div>
          <div>
            <span className="text-slate-400 block text-[11px]">Tanggal Invoice:</span>
            <span className="font-mono text-slate-800">
              {formatDate(invoice.invoiceDate)}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Segregation of Duties (SoD) Warning Banner */}
      {isUploader && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 shadow-sm flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 text-amber-700 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-amber-900 leading-relaxed">
            <strong className="block text-amber-950 font-bold mb-0.5">
              Pemberitahuan Segregation of Duties (SoD)
            </strong>
            Anda terdaftar sebagai <strong>pengunggah dokumen ini</strong>. Berdasarkan aturan bisnis <strong>BR-002</strong> dan integritas audit, pengunggah dilarang menyetujui dokumennya sendiri. Tombol persetujuan dinonaktifkan dan verifikasi akhir wajib dilakukan oleh Finance Reviewer lain.
          </div>
        </div>
      )}

      {/* 3. Action Error Banner */}
      {actionError && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
          <span>{actionError}</span>
        </div>
      )}

      {/* 4. Active Issues Alert Banner */}
      {issues && issues.length > 0 && (
        <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 shadow-sm space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>Kendala Terdeteksi oleh Mesin Verifikasi ({issues.length})</span>
          </div>
          <ul className="space-y-1.5 pl-6 list-disc text-xs text-amber-800">
            {issues.map((issue) => (
              <li key={issue.id}>
                <strong className="font-mono">{issue.issueCode}</strong> ({issue.issueCategory}):{' '}
                {issue.messageId}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 5. Payment Details Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
        <h3 className="text-xs font-bold text-[#0B3558] uppercase tracking-wider mb-3 flex items-center gap-1.5">
          <CreditCard className="w-4 h-4 text-[#006BFF]" />
          <span>Informasi Rekening Bank Tujuan Transfer</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] text-slate-500 block">Bank Tujuan:</span>
            <span className="font-semibold text-slate-900">
              {paymentDetails?.bankName || (
                <span className="text-amber-700 italic">Belum terdeteksi</span>
              )}
            </span>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] text-slate-500 block">Nomor Rekening:</span>
            <span className="font-mono font-bold text-[#0B3558]">
              {paymentDetails?.accountNumber || (
                <span className="text-amber-700 italic font-sans">Belum terdeteksi</span>
              )}
            </span>
          </div>

          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] text-slate-500 block">Nama Pemilik Rekening:</span>
            <span className="font-medium text-slate-900 truncate block">
              {paymentDetails?.accountHolderName || '-'}
            </span>
          </div>
        </div>
      </div>

      {/* 6. Line Items Editor with Live Math */}
      <LineItemsEditor
        initialItems={lineItems}
        taxAmount={invoice.taxAmount}
        onSaveItems={onSaveLineItems}
        isSaving={isProcessingAction}
      />

      {/* 7. Action Buttons Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="text-xs text-slate-500 block">
            Pengunggah: <strong>{invoice.uploader.fullName}</strong>
          </span>
          <span className="text-[11px] text-slate-400">
            Diajukan pada {formatDate(invoice.submissionDate)}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {invoice.status === 'READY_FOR_REVIEW' && (
            <>
              <button
                type="button"
                onClick={() => setReturnModalOpen(true)}
                disabled={isProcessingAction}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-300 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Kembalikan ke PIC</span>
              </button>

              <button
                type="button"
                onClick={handleApproveClick}
                disabled={!canApprove || isProcessingAction}
                title={
                  isUploader
                    ? 'Pelanggaran SoD: Pengunggah dilarang menyetujui dokumen sendiri'
                    : !canApprove
                    ? 'Selesaikan seluruh kendala sebelum menyetujui dokumen'
                    : 'Setujui dokumen dan terbitkan voucher resmi'
                }
                className="flex items-center gap-2 px-5 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
              >
                <CheckCircle className="w-4 h-4" />
                <span>{isProcessingAction ? 'Memproses...' : 'Setujui Voucher'}</span>
              </button>
            </>
          )}

          {(invoice.status === 'AMIGA_REVIEWED' || invoice.status === 'SENT_TO_CLIENT') && (
            <div className="flex items-center gap-2 text-xs text-emerald-800 font-semibold bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200">
              <FileCheck className="w-4 h-4 text-emerald-600" />
              <span>Dokumen Telah Disetujui (Voucher Resmi Terbit)</span>
            </div>
          )}
        </div>
      </div>

      {/* Return Modal */}
      {returnModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <h3 className="text-sm font-bold text-[#0B3558] mb-1">
              Kembalikan Dokumen ke PIC Klien
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              Status dokumen akan berubah menjadi <strong>EXCEPTION</strong> dengan kode kendala REVIEWER_RETURNED.
            </p>

            <form onSubmit={handleReturnSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Alasan Pengembalian (Min. 10 karakter)
                </label>
                <textarea
                  rows={3}
                  required
                  placeholder="Jelaskan bagian invoice yang perlu direvisi atau dilengkapi oleh PIC Klien..."
                  value={returnReason}
                  onChange={(e) => setReturnReason(e.target.value)}
                  className="w-full p-2.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setReturnModalOpen(false)}
                  className="px-3.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={returnReason.trim().length < 10 || isProcessingAction}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40 rounded-lg"
                >
                  Kirim Pengembalian
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
