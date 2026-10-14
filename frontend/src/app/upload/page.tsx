'use client';

import React, { useState, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Navbar } from '../../components/layout/navbar';
import { api } from '../../lib/api';
import {
  UploadCloud,
  FileCheck2,
  AlertCircle,
  Building,
  Calendar,
  Layers,
  Radio,
  CheckCircle2,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';

const SUBMISSION_CHANNELS = ['Portal', 'Email', 'WhatsApp', 'Shared Drive'];
const REQUEST_TYPES = [
  'Standard Vendor Invoice',
  'Urgent Operational Invoice',
  'Recurring Monthly Vendor',
  'Contractor Fee Invoice',
];

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form states
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [clientId, setClientId] = useState<string>('');
  const [requestType, setRequestType] = useState<string>('Standard Vendor Invoice');
  const [submissionChannel, setSubmissionChannel] = useState<string>('Portal');
  const [submissionDate, setSubmissionDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );

  // UI status
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [successResult, setSuccessResult] = useState<{
    requestId: string;
    originalFileName: string;
    filePageCount: number;
  } | null>(null);

  // Fetch clients
  const { data: clients = [], isLoading: isLoadingClients } = useQuery({
    queryKey: ['clients-list'],
    queryFn: () => api.getClients(),
  });

  // Client-side file validation [PR-002, PR-003, PF-012]
  const validateAndSetFile = (file: File) => {
    setValidationError(null);

    // 1. Validasi ekstensi & mime type
    if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
      setValidationError('Berkas wajib berformat PDF digital (.pdf).');
      setSelectedFile(null);
      return;
    }

    // 2. Validasi ukuran (maks. 10MB)
    const MAX_SIZE_BYTES = 10 * 1024 * 1024;
    if (file.size > MAX_SIZE_BYTES) {
      setValidationError(
        `Ukuran berkas (${(file.size / (1024 * 1024)).toFixed(1)} MB) melebihi batas maksimal 10 MB.`
      );
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setValidationError('Silakan pilih berkas invoice PDF terlebih dahulu.');
      return;
    }
    if (!clientId) {
      setValidationError('Silakan pilih organisasi klien target.');
      return;
    }

    setIsUploading(true);
    setUploadProgress(20);
    setValidationError(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('clientId', clientId);
      formData.append('requestType', requestType);
      formData.append('submissionChannel', submissionChannel);
      formData.append('submissionDate', submissionDate);

      setUploadProgress(60);

      const result = await api.uploadInvoice(formData);

      setUploadProgress(100);
      setSuccessResult({
        requestId: result.requestId,
        originalFileName: result.originalFileName,
        filePageCount: result.filePageCount,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Gagal mengunggah berkas invoice.';
      setValidationError(msg);
      setUploadProgress(0);
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setSuccessResult(null);
    setUploadProgress(0);
    setValidationError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F8F9FB]">
      <Navbar />

      <main className="flex-1 max-w-3xl w-full mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <h1 className="text-xl font-bold text-[#0B3558] tracking-tight">
            Formulir Intake & Pengunggahan Invoice
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Unggah invoice vendor digital (maks. 5 halaman, 10MB) untuk ekstraksi asinkron dan verifikasi otomatis.
          </p>
        </div>

        {/* Modal Sukses Penerbitan Request ID */}
        {successResult && (
          <div className="bg-white border border-emerald-200 rounded-2xl p-6 shadow-md mb-6 animate-in fade-in-50 zoom-in-95">
            <div className="flex items-start gap-4">
              <div className="p-2 rounded-xl bg-emerald-100 text-emerald-700 flex-shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <span className="inline-block text-[11px] font-semibold text-emerald-700 uppercase tracking-wider mb-1">
                  Unggahan Berhasil Diterima
                </span>
                <h2 className="text-lg font-bold text-[#0B3558] mb-1">
                  Request ID: <span className="font-mono text-[#006BFF]">{successResult.requestId}</span>
                </h2>
                <p className="text-xs text-slate-600 mb-4 leading-relaxed">
                  Dokumen <strong>{successResult.originalFileName}</strong> ({successResult.filePageCount} halaman) telah masuk ke antrean pemrosesan dengan status <strong>QUEUED</strong>. Ekstraksi AI Bedrock Titan Express sedang berjalan di latar belakang (SLA 15 detik).
                </p>

                <div className="flex flex-wrap items-center gap-3">
                  <Link
                    href="/queue"
                    className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
                  >
                    <span>Buka Antrean & Pantau Dokumen</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>

                  <button
                    type="button"
                    onClick={handleReset}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
                  >
                    <span>Unggah Dokumen Lain</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Form Intake */}
        <form
          onSubmit={handleSubmit}
          className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6"
        >
          {/* Error Banner */}
          {validationError && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <span>{validationError}</span>
            </div>
          )}

          {/* 1. Drag & Drop Zone */}
          <div>
            <label className="block text-xs font-semibold text-[#0B3558] mb-1.5">
              Berkas Invoice Vendor (PDF Digital) <span className="text-rose-500">*</span>
            </label>

            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                isDragging
                  ? 'border-[#006BFF] bg-blue-50/50 scale-[0.99]'
                  : selectedFile
                  ? 'border-emerald-300 bg-emerald-50/20'
                  : 'border-slate-300 hover:border-slate-400 bg-slate-50/50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                className="hidden"
                id="invoice-file-upload"
              />

              {selectedFile ? (
                <div className="flex flex-col items-center justify-center">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mb-2">
                    <FileCheck2 className="w-6 h-6" />
                  </div>
                  <span className="text-xs font-bold text-slate-800 truncate max-w-sm">
                    {selectedFile.name}
                  </span>
                  <span className="text-[11px] text-slate-500 font-mono mt-0.5">
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Klik untuk mengganti
                  </span>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center">
                  <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mb-2">
                    <UploadCloud className="w-6 h-6 text-[#006BFF]" />
                  </div>
                  <span className="text-xs font-semibold text-slate-700">
                    Tarik dan lepas berkas PDF di sini, atau <span className="text-[#006BFF] underline">pilih dari komputer</span>
                  </span>
                  <span className="text-[11px] text-slate-400 mt-1">
                    Maksimal 5 halaman digital · Ukuran maksimum 10 MB
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* 2. Metadata: Klien & Tanggal */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="client-select" className="block text-xs font-semibold text-[#0B3558] mb-1.5">
                Organisasi Klien <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Building className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <select
                  id="client-select"
                  required
                  value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
                >
                  <option value="">Pilih Organisasi Klien</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.clientCode} · {c.clientName}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="submission-date" className="block text-xs font-semibold text-[#0B3558] mb-1.5">
                Tanggal Pengajuan <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <Calendar className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <input
                  id="submission-date"
                  type="date"
                  required
                  value={submissionDate}
                  onChange={(e) => setSubmissionDate(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
                />
              </div>
            </div>
          </div>

          {/* 3. Metadata: Tipe Pengajuan & Saluran Masuk */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="request-type" className="block text-xs font-semibold text-[#0B3558] mb-1.5">
                Tipe Permintaan
              </label>
              <div className="relative">
                <Layers className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <select
                  id="request-type"
                  value={requestType}
                  onChange={(e) => setRequestType(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
                >
                  {REQUEST_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="submission-channel" className="block text-xs font-semibold text-[#0B3558] mb-1.5">
                Saluran Penerimaan
              </label>
              <div className="relative">
                <Radio className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <select
                  id="submission-channel"
                  value={submissionChannel}
                  onChange={(e) => setSubmissionChannel(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-[#006BFF] focus:border-[#006BFF]"
                >
                  {SUBMISSION_CHANNELS.map((ch) => (
                    <option key={ch} value={ch}>
                      {ch}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Progress Bar saat Mengunggah */}
          {isUploading && (
            <div className="space-y-1.5 pt-2">
              <div className="flex justify-between text-[11px] text-slate-600 font-medium">
                <span>Mengunggah dan menerbitkan antrean...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full bg-[#006BFF] transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* Action Button */}
          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
            <button
              type="submit"
              disabled={isUploading || !selectedFile || !clientId}
              className="flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
            >
              {isUploading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Sedang Mengunggah...</span>
                </>
              ) : (
                <>
                  <UploadCloud className="w-4 h-4" />
                  <span>Unggah Invoice & Mulai Ekstraksi</span>
                </>
              )}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
