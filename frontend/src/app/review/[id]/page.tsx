'use client';

import React, { use } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Navbar } from '../../../components/layout/navbar';
import { PdfViewerPane } from '../../../components/pdf/pdf-viewer-pane';
import { FinancialEditorPane } from '../../../components/review/financial-editor-pane';
import { api } from '../../../lib/api';
import { ArrowLeft, RefreshCw, AlertCircle, History } from 'lucide-react';

interface ReviewPageProps {
  params: Promise<{ id: string }>;
}

export default function ReviewPage({ params }: ReviewPageProps) {
  const router = useRouter();
  const resolvedParams = use(params);
  const requestId = resolvedParams.id;
  const queryClient = useQueryClient();

  // 1. Fetch Review Data [PR-018, DR-003, PF-013]
  const {
    data: reviewData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['review-data', requestId],
    queryFn: () => api.getReviewData(requestId),
    staleTime: 5000,
  });

  // 2. Mutations
  const updateItemsMutation = useMutation({
    mutationFn: (
      items: Array<{
        id?: string;
        description: string;
        quantity: number;
        unitPrice: number;
        subtotal: number;
      }>
    ) => api.updateLineItems(requestId, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-data', requestId] });
      queryClient.invalidateQueries({ queryKey: ['invoice-queue'] });
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => api.approveInvoice(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-data', requestId] });
      queryClient.invalidateQueries({ queryKey: ['invoice-queue'] });
      router.push(`/voucher/${requestId}`);
    },
  });

  const returnMutation = useMutation({
    mutationFn: (reason: string) => api.returnInvoice(requestId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-data', requestId] });
      queryClient.invalidateQueries({ queryKey: ['invoice-queue'] });
      router.push('/queue');
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col bg-[#F8F9FB]">
        <Navbar />
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="w-10 h-10 border-3 border-blue-200 border-t-[#006BFF] rounded-full animate-spin mb-4" />
          <p className="text-sm font-semibold text-[#0B3558]">
            Memuat Layar Dual-Context Split-Screen...
          </p>
          <span className="text-xs text-slate-500 font-mono mt-1">
            Request ID: {requestId}
          </span>
        </div>
      </div>
    );
  }

  if (error || !reviewData) {
    return (
      <div className="min-h-screen flex flex-col bg-[#F8F9FB]">
        <Navbar />
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center max-w-md mx-auto">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center mb-3">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-[#0B3558] mb-1">
            Gagal Memuat Dokumen
          </h2>
          <p className="text-xs text-slate-600 mb-6 leading-relaxed">
            {error instanceof Error ? error.message : 'Dokumen tidak ditemukan atau akses ditolak.'}
          </p>
          <div className="flex items-center gap-3">
            <Link
              href="/queue"
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Kembali ke Antrean</span>
            </Link>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] rounded-lg transition-colors shadow-sm"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Coba Lagi</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#F8F9FB] h-screen overflow-hidden">
      <Navbar />

      {/* Subheader Toolbar */}
      <div className="bg-white border-b border-slate-200 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <Link
            href="/queue"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-[#0B3558] transition-colors p-1 rounded hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
          >
            <ArrowLeft className="w-4 h-4 text-slate-500" />
            <span>Kembali ke Antrean</span>
          </Link>
          <div className="h-4 w-px bg-slate-200" />
          <span className="text-xs font-bold text-[#0B3558]">
            Layar Peninjauan Invoice & Verifikasi Finansial
          </span>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href={`/audit/${reviewData.invoice.requestId}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors"
          >
            <History className="w-3.5 h-3.5 text-slate-500" />
            <span>Jejak Audit</span>
          </Link>
          <div className="text-xs text-slate-500 font-mono">
            Request ID: <strong className="text-[#006BFF]">{reviewData.invoice.requestId}</strong>
          </div>
        </div>
      </div>

      {/* Split-Screen 50:50 Grid Layout [PR-018, DR-003] */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 overflow-hidden">
        {/* Left Pane (50%): Original PDF Viewer */}
        <section className="h-full overflow-hidden" aria-label="Pratinjau PDF Asli">
          <PdfViewerPane
            pdfUrl={api.getPdfUrl(reviewData.invoice.requestId)}
            originalFileName={reviewData.invoice.originalFileName}
            filePageCount={reviewData.invoice.filePageCount}
          />
        </section>

        {/* Right Pane (50%): Financial Data & Line Items Editor */}
        <section className="h-full overflow-hidden" aria-label="Editor Data Finansial">
          <FinancialEditorPane
            data={reviewData}
            onSaveLineItems={async (items) => {
              await updateItemsMutation.mutateAsync(items);
            }}
            onApprove={async () => {
              await approveMutation.mutateAsync();
            }}
            onReturn={async (reason) => {
              await returnMutation.mutateAsync(reason);
            }}
            isProcessingAction={
              updateItemsMutation.isPending ||
              approveMutation.isPending ||
              returnMutation.isPending
            }
          />
        </section>
      </div>
    </div>
  );
}
