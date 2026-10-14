'use client';

import React from 'react';
import { AuditLogItem } from '../../lib/types';
import { formatAuditTimestamp } from '../../lib/utils';
import { StatusBadge } from '../common/status-badge';
import { AuditDiffViewer } from './audit-diff-viewer';
import {
  UploadCloud,
  Cpu,
  ShieldCheck,
  Edit3,
  ListOrdered,
  CheckCircle2,
  Award,
  AlertOctagon,
  UserCheck,
  Users,
  FileCheck2,
  Download,
  ArrowRight,
  Bot,
  User,
  Activity,
} from 'lucide-react';

interface AuditTimelineItemProps {
  item: AuditLogItem;
  isFirst?: boolean;
  isLast?: boolean;
}

/**
 * Konfigurasi visual untuk setiap jenis aksi di jejak audit.
 */
function getActionMeta(actionType: string) {
  switch (actionType) {
    case 'INVOICE_UPLOADED':
    case 'INTAKE_DOCUMENT_UPLOADED':
      return {
        label: 'Dokumen Invoice Diunggah',
        icon: UploadCloud,
        color: 'text-blue-600',
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        dotBorder: 'border-blue-500',
      };
    case 'AI_EXTRACTION_COMPLETED':
      return {
        label: 'Ekstraksi AI Bedrock Selesai',
        icon: Cpu,
        color: 'text-indigo-600',
        bg: 'bg-indigo-50',
        border: 'border-indigo-200',
        dotBorder: 'border-indigo-500',
      };
    case 'SYSTEM_VERIFICATION_PASSED':
      return {
        label: 'Verifikasi Sistem Lolos',
        icon: ShieldCheck,
        color: 'text-emerald-600',
        bg: 'bg-emerald-50',
        border: 'border-emerald-200',
        dotBorder: 'border-emerald-500',
      };
    case 'FIELD_VALUE_MODIFIED':
      return {
        label: 'Modifikasi Nilai Bidang',
        icon: Edit3,
        color: 'text-amber-600',
        bg: 'bg-amber-50',
        border: 'border-amber-200',
        dotBorder: 'border-amber-500',
      };
    case 'LINE_ITEMS_UPDATED':
      return {
        label: 'Pembaruan Rincian Item (Line Items)',
        icon: ListOrdered,
        color: 'text-amber-700',
        bg: 'bg-amber-50',
        border: 'border-amber-300',
        dotBorder: 'border-amber-500',
      };
    case 'INVOICE_CORRECTED':
      return {
        label: 'Perbaikan Dokumen oleh PIC Klien',
        icon: CheckCircle2,
        color: 'text-teal-600',
        bg: 'bg-teal-50',
        border: 'border-teal-200',
        dotBorder: 'border-teal-500',
      };
    case 'REVIEW_APPROVED':
      return {
        label: 'Persetujuan Dokumen oleh Reviewer',
        icon: Award,
        color: 'text-indigo-700',
        bg: 'bg-indigo-50',
        border: 'border-indigo-300',
        dotBorder: 'border-indigo-600',
      };
    case 'SOD_VIOLATION_BLOCKED':
      return {
        label: 'Pelanggaran SoD Diblokir Sistem',
        icon: AlertOctagon,
        color: 'text-rose-700',
        bg: 'bg-rose-50',
        border: 'border-rose-300',
        dotBorder: 'border-rose-600',
      };
    case 'SOD_AUTO_REASSIGN':
    case 'WORKLOAD_REASSIGNED':
      return {
        label: 'Pengalihan Otomatis Penugasan Reviewer',
        icon: UserCheck,
        color: 'text-purple-600',
        bg: 'bg-purple-50',
        border: 'border-purple-200',
        dotBorder: 'border-purple-500',
      };
    case 'WORKLOAD_REBALANCE_LEAD':
      return {
        label: 'Penyeimbangan Beban Kerja (Service Lead)',
        icon: Users,
        color: 'text-sky-600',
        bg: 'bg-sky-50',
        border: 'border-sky-200',
        dotBorder: 'border-sky-500',
      };
    case 'VOUCHER_GENERATED':
      return {
        label: 'Voucher Pembayaran Resmi Terbit',
        icon: FileCheck2,
        color: 'text-emerald-700',
        bg: 'bg-emerald-50',
        border: 'border-emerald-300',
        dotBorder: 'border-emerald-600',
      };
    case 'VOUCHER_DOWNLOADED':
      return {
        label: 'Voucher Resmi Diunduh',
        icon: Download,
        color: 'text-teal-700',
        bg: 'bg-teal-50',
        border: 'border-teal-200',
        dotBorder: 'border-teal-500',
      };
    default:
      return {
        label: actionType.replace(/_/g, ' '),
        icon: Activity,
        color: 'text-slate-700',
        bg: 'bg-slate-50',
        border: 'border-slate-200',
        dotBorder: 'border-slate-400',
      };
  }
}

/**
 * Konfigurasi badge peran aktor.
 */
function getRoleBadge(role: string) {
  switch (role) {
    case 'FINANCE_REVIEWER':
      return { label: 'Finance Reviewer', bg: 'bg-indigo-100 text-indigo-800 border-indigo-200' };
    case 'PIC_KLIEN':
      return { label: 'PIC Klien', bg: 'bg-blue-100 text-blue-800 border-blue-200' };
    case 'SERVICE_LEAD':
      return { label: 'Service Lead', bg: 'bg-purple-100 text-purple-800 border-purple-200' };
    case 'SYSTEM_ADMIN':
      return { label: 'System Admin', bg: 'bg-slate-200 text-slate-800 border-slate-300' };
    case 'INTAKE_SUPPORT':
      return { label: 'Intake Support', bg: 'bg-teal-100 text-teal-800 border-teal-200' };
    case 'SYSTEM':
    default:
      return { label: 'Sistem AMIGA', bg: 'bg-emerald-100 text-emerald-800 border-emerald-200' };
  }
}

export function AuditTimelineItem({ item, isFirst, isLast }: AuditTimelineItemProps) {
  const meta = getActionMeta(item.actionType);
  const ActionIcon = meta.icon;
  const roleBadge = getRoleBadge(item.actorRole);
  const isSystemActor = item.actorRole === 'SYSTEM' || !item.actorId;

  return (
    <div className="relative pl-8 sm:pl-10 pb-8 group last:pb-2">
      {/* Garis vertikal kronologis penghubung */}
      {!isLast && (
        <span
          className="absolute left-[15px] sm:left-[19px] top-7 -bottom-2 w-0.5 bg-slate-200 group-hover:bg-slate-300 transition-colors"
          aria-hidden="true"
        />
      )}

      {/* Node / Titik Indikator Garis Waktu */}
      <div
        className={`absolute left-0 sm:left-1 top-1 w-8 h-8 rounded-full ${meta.bg} border-2 ${meta.dotBorder} flex items-center justify-center shadow-xs transition-transform group-hover:scale-105`}
      >
        <ActionIcon className={`w-4 h-4 ${meta.color}`} />
      </div>

      {/* Konten Kartu Acara Audit */}
      <div className="bg-white border border-slate-200/90 rounded-xl p-4 sm:p-5 shadow-xs transition-shadow hover:shadow-sm">
        {/* Baris Header Kartu: Aksi & Waktu Presisi */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-sm text-[#0B3558] tracking-tight">
              {meta.label}
            </span>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
              {item.actionType}
            </span>
          </div>

          <time className="text-xs font-mono font-medium text-slate-500 whitespace-nowrap">
            {formatAuditTimestamp(item.createdAt)}
          </time>
        </div>

        {/* Informasi Aktor & IP Address */}
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600">
              {isSystemActor ? (
                <Bot className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <User className="w-3.5 h-3.5 text-slate-600" />
              )}
            </div>
            <span className="font-semibold text-slate-800">
              {item.actorName || (isSystemActor ? 'AMIGA Robot Engine' : 'Pengguna')}
            </span>
          </div>

          <span
            className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${roleBadge.bg}`}
          >
            {roleBadge.label}
          </span>

          {item.ipAddress && (
            <span className="text-[11px] font-mono text-slate-400">
              IP: {item.ipAddress}
            </span>
          )}
        </div>

        {/* Mutasi Status (Jika Ada Transisi Status Sebelumnya -> Baru) */}
        {(item.previousStatus || item.newStatus) && (
          <div className="mt-3.5 pt-3 border-t border-slate-100 flex items-center gap-2 flex-wrap text-xs">
            <span className="text-slate-500 font-medium">Mutasi Status:</span>
            {item.previousStatus ? (
              <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                {item.previousStatus}
              </span>
            ) : (
              <span className="text-slate-400 italic text-[11px]">(Awal)</span>
            )}
            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
            {item.newStatus && (
              <StatusBadge status={item.newStatus as any} size="sm" />
            )}
          </div>
        )}

        {/* Panel Diff Viewer Delta Nilai Lama vs Baru */}
        {item.changeDiff && (
          <AuditDiffViewer changeDiff={item.changeDiff} actionType={item.actionType} />
        )}
      </div>
    </div>
  );
}
