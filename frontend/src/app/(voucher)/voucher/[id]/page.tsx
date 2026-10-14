'use client';

import React, { use, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navbar } from '../../../../components/layout/navbar';
import { StatusBadge } from '../../../../components/common/status-badge';
import { api } from '../../../../lib/api';
import { formatCurrency, formatDate, formatDateTime, terbilang } from '../../../../lib/utils';
import {
  ArrowLeft,
  Download,
  FileCheck2,
  AlertCircle,
  Building2,
  Calendar,
  CreditCard,
  UserCheck,
  ShieldCheck,
  Loader2,
  ExternalLink,
  History,
} from 'lucide-react';

interface VoucherPageProps {
  params: Promise<{ id: string }>;
}

/**
 * Layar 04: Pratinjau & Alur Unduh Berkas Voucher Resmi [T-019].
 * Memenuhi kebutuhan PR-022, PR-023, DR-004, PF-018.
 */
export default function VoucherPreviewPage({ params }: VoucherPageProps) {
  const router = useRouter();
  const resolvedParams = use(params);
  const lookupId = resolvedParams.id;
  const queryClient = useQueryClient();

  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadSuccessMessage, setDownloadSuccessMessage] = useState<string | null>(null);
  const [downloadErrorMessage, setDownloadErrorMessage] = useState<string | null>(null);

  // 1. Fetch Voucher Detail [PR-022, DR-004]
  const {
    data: voucher,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['voucher-detail', lookupId],
    queryFn: () => api.getVoucher(lookupId),
    staleTime: 5000,
  });

  const invoice = voucher?.invoiceRequest;
  const paymentDetails = invoice?.paymentDetails;
  const lineItems = invoice?.lineItems || [];

  // Hitung kalimat terbilang
  const terbilangText = invoice?.totalAmount
    ? terbilang(invoice.totalAmount)
    : 'Nol Rupiah';

  // 2. Handler Download Voucher Resmi
  const handleDownload = async () => {
    if (!voucher || isDownloading) return;
    setIsDownloading(true);
    setDownloadSuccessMessage(null);
    setDownloadErrorMessage(null);

    try {
      const fileName = `${voucher.voucherNumber.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
      await api.downloadVoucherPdf(voucher.invoiceRequest.requestId, fileName);

      // Invalidate query agar status termutasi (AMIGA_REVIEWED -> SENT_TO_CLIENT) jika diunduh oleh PIC Klien
      await queryClient.invalidateQueries({ queryKey: ['voucher-detail', lookupId] });
      await queryClient.invalidateQueries({ queryKey: ['invoice-queue'] });

      setDownloadSuccessMessage('Berkas voucher resmi berhasil diunduh ke perangkat Anda.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Terjadi kendala saat mengunduh berkas voucher.';
      setDownloadErrorMessage(msg);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8F9FB] text-[#0B3558] flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
        {/* Navigation Breadcrumb & Actions Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <Link
              href="/queue"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors shadow-xs"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Kembali ke Antrean
            </Link>
            <div className="h-4 w-px bg-slate-300" />
            <h1 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
              Pratinjau Voucher Pembayaran Resmi
            </h1>
          </div>

          {voucher && (
            <div className="flex items-center gap-3">
              <Link
                href={`/audit/${voucher.invoiceRequest.requestId}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-md hover:bg-slate-50 transition-colors shadow-2xs"
              >
                <History className="w-3.5 h-3.5 text-slate-500" />
                <span>Jejak Audit</span>
              </Link>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 font-medium">Status:</span>
                <StatusBadge status={invoice?.status || 'AMIGA_REVIEWED'} size="md" />
              </div>
            </div>
          )}
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="bg-white border border-slate-200 rounded-lg p-16 flex flex-col items-center justify-center text-center shadow-xs">
            <Loader2 className="w-8 h-8 text-[#006BFF] animate-spin mb-3" />
            <p className="text-sm font-semibold text-[#0B3558]">Memuat berkas voucher resmi...</p>
            <p className="text-xs text-slate-500 mt-1">Mengambil data verifikasi finansial dan nomor voucher.</p>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="bg-white border border-amber-200 rounded-lg p-10 flex flex-col items-center justify-center text-center shadow-xs">
            <div className="w-12 h-12 rounded-full bg-amber-50 flex items-center justify-center text-amber-600 mb-3">
              <AlertCircle className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-[#0B3558]">Voucher Pembayaran Belum Tersedia</h3>
            <p className="text-xs text-slate-600 max-w-md mt-1 mb-6">
              Dokumen ini belum berstatus disetujui (AMIGA_REVIEWED) atau nomor identifikasi voucher tidak ditemukan pada sistem.
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => refetch()}
                className="px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-blue-700 rounded-md transition-colors"
              >
                Coba Muat Ulang
              </button>
              <Link
                href="/queue"
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors"
              >
                Kembali ke Antrean
              </Link>
            </div>
          </div>
        )}

        {/* Voucher Preview Card (A4 Document Canvas) [DR-004] */}
        {voucher && invoice && (
          <div className="space-y-6">
            {/* Feedback Notifications */}
            {downloadSuccessMessage && (
              <div className="p-3.5 bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-md flex items-center gap-2">
                <FileCheck2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{downloadSuccessMessage}</span>
              </div>
            )}
            {downloadErrorMessage && (
              <div className="p-3.5 bg-red-50 border border-red-200 text-red-800 text-xs rounded-md flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{downloadErrorMessage}</span>
              </div>
            )}

            {/* Document Canvas Container */}
            <div className="bg-white border border-slate-200 shadow-md rounded-lg overflow-hidden">
              {/* Official Header */}
              <div className="p-6 sm:p-8 border-b-2 border-[#0B3558] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50/50">
                <div>
                  <div className="flex items-center gap-2 text-[#0B3558]">
                    <Building2 className="w-5 h-5 text-[#006BFF]" />
                    <span className="text-base font-extrabold tracking-wider">AMIGA OPERATING PARTNER</span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Intelligent Invoice-to-Voucher Automated Processing
                  </p>
                </div>
                <div className="text-left sm:text-right">
                  <span className="text-xl sm:text-2xl font-black text-[#006BFF] tracking-wide block">
                    PAYMENT VOUCHER
                  </span>
                  <span className="text-xs text-slate-500 font-medium">
                    Dokumen Resmi Verifikasi Keuangan
                  </span>
                </div>
              </div>

              {/* Identification Bar */}
              <div className="px-6 sm:px-8 py-3.5 bg-[#F8F9FB] border-b border-slate-200 flex flex-wrap items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-slate-500 font-medium">Nomor Voucher:</span>
                  <span className="font-mono font-bold text-slate-900 bg-white px-2 py-0.5 border border-slate-200 rounded">
                    {voucher.voucherNumber}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-500 font-medium">Tanggal Terbit:</span>
                  <span className="font-semibold text-slate-800">
                    {formatDate(voucher.generatedAt)}
                  </span>
                </div>
              </div>

              {/* Metadata 2-Column Grid */}
              <div className="p-6 sm:p-8 grid grid-cols-1 md:grid-cols-2 gap-6 border-b border-slate-200 text-xs">
                {/* Kolom Kiri: Penerima Pembayaran & Rekening */}
                <div className="space-y-3.5">
                  <h4 className="text-xs font-bold text-[#0B3558] tracking-wider uppercase flex items-center gap-1.5 pb-1 border-b border-slate-100">
                    <CreditCard className="w-3.5 h-3.5 text-[#006BFF]" />
                    Informasi Pembayaran & Rekening
                  </h4>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Dibayarkan Kepada</span>
                    <span className="col-span-2 font-bold text-slate-900">
                      {invoice.vendorName || '-'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Bank Tujuan</span>
                    <span className="col-span-2 font-semibold text-slate-800">
                      {paymentDetails?.bankName || '-'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Nomor Rekening</span>
                    <span className="col-span-2 font-mono font-bold text-slate-900 tracking-wider">
                      {paymentDetails?.accountNumber || '-'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Nama Pemilik Rekening</span>
                    <span className="col-span-2 font-semibold text-slate-800">
                      {paymentDetails?.accountHolderName || invoice.vendorName || '-'}
                    </span>
                  </div>
                </div>

                {/* Kolom Kanan: Referensi Dokumen & Tagihan */}
                <div className="space-y-3.5">
                  <h4 className="text-xs font-bold text-[#0B3558] tracking-wider uppercase flex items-center gap-1.5 pb-1 border-b border-slate-100">
                    <Calendar className="w-3.5 h-3.5 text-[#006BFF]" />
                    Referensi Invoice & Organisasi Klien
                  </h4>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Organisasi Klien</span>
                    <span className="col-span-2 font-semibold text-slate-800">
                      {invoice.client.clientName} ({invoice.client.clientCode})
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Referensi Request ID</span>
                    <span className="col-span-2 font-mono font-medium text-slate-700">
                      {invoice.requestId}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Nomor Invoice Vendor</span>
                    <span className="col-span-2 font-mono font-semibold text-slate-800">
                      {invoice.invoiceNumber || '-'}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="text-slate-500">Tanggal Invoice</span>
                    <span className="col-span-2 font-semibold text-slate-800">
                      {formatDate(invoice.invoiceDate)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Terbilang Banner */}
              <div className="px-6 sm:px-8 py-3.5 bg-slate-50 border-b border-slate-200 text-xs">
                <span className="text-slate-500 font-medium mr-2">Jumlah Transfer Terbilang:</span>
                <span className="font-semibold text-slate-900 italic">
                  {terbilangText}
                </span>
              </div>

              {/* Rincian Line Items Table */}
              <div className="p-6 sm:p-8 border-b border-slate-200">
                <h4 className="text-xs font-bold text-[#0B3558] tracking-wider uppercase mb-3">
                  Rincian Barang dan Jasa Terverifikasi
                </h4>
                <div className="border border-slate-200 rounded-md overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-[#0B3558] text-white">
                      <tr>
                        <th className="py-2.5 px-3 text-center w-12 font-semibold">No</th>
                        <th className="py-2.5 px-3 text-left font-semibold">Deskripsi</th>
                        <th className="py-2.5 px-3 text-center w-20 font-semibold">Kuantitas</th>
                        <th className="py-2.5 px-3 text-right w-36 font-semibold">Harga Satuan</th>
                        <th className="py-2.5 px-3 text-right w-40 font-semibold">Subtotal</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 bg-white">
                      {lineItems.map((item, idx) => (
                        <tr key={item.id || idx} className="hover:bg-slate-50/70 transition-colors">
                          <td className="py-2.5 px-3 text-center text-slate-500 font-mono">
                            {item.itemIndex || idx + 1}
                          </td>
                          <td className="py-2.5 px-3 text-slate-800 font-medium">
                            {item.description}
                          </td>
                          <td className="py-2.5 px-3 text-center text-slate-700 font-mono">
                            {item.quantity}
                          </td>
                          <td className="py-2.5 px-3 text-right text-slate-700 font-mono tabular-nums">
                            {formatCurrency(item.unitPrice)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-slate-900 font-mono font-semibold tabular-nums">
                            {formatCurrency(item.subtotal)}
                          </td>
                        </tr>
                      ))}
                      {lineItems.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-4 text-center text-slate-400 italic">
                            Tidak ada rincian baris transaksi.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Subtotal, Pajak, Grand Total */}
                <div className="mt-4 flex justify-end">
                  <div className="w-full sm:w-80 space-y-2 text-xs">
                    <div className="flex justify-between text-slate-600">
                      <span>Subtotal:</span>
                      <span className="font-mono tabular-nums font-semibold text-slate-800">
                        {formatCurrency(invoice.subtotalAmount)}
                      </span>
                    </div>
                    <div className="flex justify-between text-slate-600">
                      <span>Pajak (PPN):</span>
                      <span className="font-mono tabular-nums font-semibold text-slate-800">
                        {formatCurrency(invoice.taxAmount)}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm font-bold text-[#0B3558] pt-2 border-t border-slate-300">
                      <span>TOTAL TRANSFER:</span>
                      <span className="font-mono tabular-nums text-[#006BFF] text-base">
                        {formatCurrency(invoice.totalAmount)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Sign-off & Audit Verification */}
              <div className="px-6 sm:px-8 py-5 border-b border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 text-xs">
                <div className="flex items-center gap-2.5 text-slate-700">
                  <UserCheck className="w-4 h-4 text-[#006BFF]" />
                  <div>
                    <span className="text-slate-500">Diverifikasi & Disetujui Oleh: </span>
                    <span className="font-bold text-slate-900">{voucher.generator.fullName}</span>
                    <span className="text-slate-500"> ({voucher.generator.role})</span>
                  </div>
                </div>
                <div className="text-slate-500 font-mono text-[11px]">
                  Waktu Verifikasi: {formatDateTime(voucher.generatedAt)} WIB
                </div>
              </div>

              {/* Legal Authorization Boundary Banner (Verbatim DRD & SRD) [DR-004] */}
              <div className="p-6 sm:p-8 bg-[#EFF6FF] border-t-2 border-blue-200">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="w-5 h-5 text-[#006BFF] shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h5 className="text-xs font-bold text-[#0B3558] tracking-wider uppercase">
                      BATAS OTORISASI PEMBAYARAN LEGAL
                    </h5>
                    <p className="text-xs leading-relaxed text-slate-700">
                      {voucher.authorizationBoundaryText ||
                        'Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin atas dasar verifikasi independen tim Keuangan AMIGA. Otorisasi pembayaran akhir dan eksekusi transfer dana merupakan kewenangan mutlak Client Approver di luar sistem AMIGA.'}
                    </p>
                    <p className="text-[11px] text-slate-500 pt-1 italic">
                      Dokumen ini sah secara digital dan diterbitkan tanpa tanda tangan basah.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Buttons Toolbar [DR-004, PR-023] */}
            <div className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-xs">
              <Link
                href="/queue"
                className="w-full sm:w-auto px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors text-center"
              >
                Kembali ke Antrean
              </Link>

              <div className="flex items-center gap-3 w-full sm:w-auto">
                <button
                  onClick={handleDownload}
                  disabled={isDownloading}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 text-xs font-bold text-white bg-[#006BFF] hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed rounded-md shadow-xs transition-colors"
                >
                  {isDownloading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Sedang Mengunduh...
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4" />
                      Unduh Voucher PDF Resmi
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
