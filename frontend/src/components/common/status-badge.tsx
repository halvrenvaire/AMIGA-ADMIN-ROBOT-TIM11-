import React from 'react';
import { InvoiceStatus } from '../../lib/types';
import { cn } from '../../lib/utils';

interface StatusBadgeProps {
  status: InvoiceStatus;
  className?: string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<
  InvoiceStatus,
  { label: string; bg: string; text: string; border: string; pulse?: boolean }
> = {
  QUEUED: {
    label: 'QUEUED',
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    border: 'border-slate-200',
  },
  PROCESSING: {
    label: 'PROCESSING',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    pulse: true,
  },
  READY_FOR_REVIEW: {
    label: 'READY FOR REVIEW',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
  },
  EXCEPTION: {
    label: 'EXCEPTION',
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-300',
  },
  AMIGA_REVIEWED: {
    label: 'AMIGA REVIEWED',
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
  },
  SENT_TO_CLIENT: {
    label: 'SENT TO CLIENT',
    bg: 'bg-teal-50',
    text: 'text-teal-700',
    border: 'border-teal-200',
  },
};

export function StatusBadge({ status, className, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    border: 'border-slate-200',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold rounded-md border tracking-wide whitespace-nowrap',
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
        config.bg,
        config.text,
        config.border,
        config.pulse && 'animate-pulse',
        className
      )}
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full mr-1.5',
          status === 'READY_FOR_REVIEW' && 'bg-emerald-500',
          status === 'EXCEPTION' && 'bg-amber-500',
          status === 'PROCESSING' && 'bg-blue-500',
          status === 'QUEUED' && 'bg-slate-400',
          status === 'AMIGA_REVIEWED' && 'bg-indigo-500',
          status === 'SENT_TO_CLIENT' && 'bg-teal-500'
        )}
      />
      {config.label}
    </span>
  );
}
