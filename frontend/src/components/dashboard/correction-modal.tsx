'use client';

import React, { useState } from 'react';
import { api } from '../../lib/api';
import { InvoiceSummaryItem } from '../../lib/types';
import { X, CheckCircle, AlertTriangle, Building, CreditCard, User, MessageSquare } from 'lucide-react';

interface CorrectionModalProps {
  invoice: InvoiceSummaryItem;
  onClose: () => void;
  onSuccess: () => void;
}

export function CorrectionModal({ invoice, onClose, onSuccess }: CorrectionModalProps) {
  const [bankName, setBankName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [accountHolderName, setAccountHolderName] = useState(invoice.vendorName || '');
  const [comments, setComments] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await api.correctInvoice(invoice.requestId, {
        paymentDetails: {
          bankName: bankName.trim() || undefined,
          accountNumber: accountNumber.trim() || undefined,
          accountHolderName: accountHolderName.trim() || undefined,
        },
        comments: comments.trim() || 'Koreksi data rekening oleh PIC Klien via Dashboard',
      });
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Gagal mengirim koreksi dokumen.';
      setErrorMsg(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div
        className="bg-white rounded-2xl max-w-lg w-full shadow-2xl border border-slate-200 overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="correction-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-slate-50 border-b border-slate-200">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-amber-100 text-amber-800">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <h2 id="correction-modal-title" className="text-sm font-bold text-[#0B3558]">
                Koreksi Dokumen EXCEPTION
              </h2>
              <p className="text-[11px] text-slate-500 font-mono">
                Request ID: {invoice.requestId}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 transition-colors focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
            aria-label="Tutup modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="p-3 rounded-lg bg-amber-50/70 border border-amber-200 text-xs text-amber-900 leading-relaxed">
            Dokumen ini membutuhkan kelengkapan data rekening atau klarifikasi nilai. Request ID akan dipertahankan identik dan dokumen akan otomatis diverifikasi ulang oleh sistem.
          </div>

          {errorMsg && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800">
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#0B3558] mb-1">
              Nama Bank Tujuan Transfer
            </label>
            <div className="relative">
              <Building className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
              <input
                type="text"
                required
                placeholder="Contoh: Bank Central Asia (BCA) / Mandiri"
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0B3558] mb-1">
              Nomor Rekening Bank
            </label>
            <div className="relative">
              <CreditCard className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
              <input
                type="text"
                required
                placeholder="Contoh: 8820192831"
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 font-mono focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0B3558] mb-1">
              Nama Pemilik Rekening
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
              <input
                type="text"
                placeholder="Nama pemilik rekening bank tujuan"
                value={accountHolderName}
                onChange={(e) => setAccountHolderName(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0B3558] mb-1">
              Catatan Koreksi (Opsional)
            </label>
            <div className="relative">
              <MessageSquare className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
              <textarea
                rows={2}
                placeholder="Catatan pendukung untuk Finance Reviewer"
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
              />
            </div>
          </div>

          {/* Footer Buttons */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-slate-300"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] disabled:opacity-50 rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
            >
              <CheckCircle className="w-4 h-4" />
              <span>{isSubmitting ? 'Mengirim...' : 'Kirim Koreksi Dokumen'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
