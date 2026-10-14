'use client';

import React from 'react';
import { InvoiceStatus } from '../../lib/types';
import { cn } from '../../lib/utils';
import { Clock, Cpu, CheckCircle2, AlertTriangle, FileCheck, Send, Layers } from 'lucide-react';

interface MetricCardsBarProps {
  statusCounts: {
    QUEUED: number;
    PROCESSING: number;
    READY_FOR_REVIEW: number;
    EXCEPTION: number;
    AMIGA_REVIEWED: number;
    SENT_TO_CLIENT: number;
    ALL: number;
  };
  activeFilter: InvoiceStatus | 'ALL';
  onSelectFilter: (filter: InvoiceStatus | 'ALL') => void;
}

export function MetricCardsBar({
  statusCounts,
  activeFilter,
  onSelectFilter,
}: MetricCardsBarProps) {
  const cards: Array<{
    key: InvoiceStatus | 'ALL';
    label: string;
    count: number;
    icon: React.ComponentType<{ className?: string }>;
    accentColor: string;
    badgeBg: string;
    badgeText: string;
  }> = [
    {
      key: 'ALL',
      label: 'Semua Dokumen',
      count: statusCounts.ALL,
      icon: Layers,
      accentColor: 'border-slate-300',
      badgeBg: 'bg-slate-100',
      badgeText: 'text-slate-700',
    },
    {
      key: 'QUEUED',
      label: 'Dalam Antrean',
      count: statusCounts.QUEUED,
      icon: Clock,
      accentColor: 'border-slate-300',
      badgeBg: 'bg-slate-100',
      badgeText: 'text-slate-700',
    },
    {
      key: 'PROCESSING',
      label: 'Ekstraksi AI',
      count: statusCounts.PROCESSING,
      icon: Cpu,
      accentColor: 'border-blue-300',
      badgeBg: 'bg-blue-50',
      badgeText: 'text-blue-700',
    },
    {
      key: 'READY_FOR_REVIEW',
      label: 'Siap Ditinjau',
      count: statusCounts.READY_FOR_REVIEW,
      icon: CheckCircle2,
      accentColor: 'border-emerald-300',
      badgeBg: 'bg-emerald-50',
      badgeText: 'text-emerald-700',
    },
    {
      key: 'EXCEPTION',
      label: 'Kendala Sistem',
      count: statusCounts.EXCEPTION,
      icon: AlertTriangle,
      accentColor: 'border-amber-400',
      badgeBg: 'bg-amber-50',
      badgeText: 'text-amber-800',
    },
    {
      key: 'AMIGA_REVIEWED',
      label: 'Voucher Terbit',
      count: statusCounts.AMIGA_REVIEWED,
      icon: FileCheck,
      accentColor: 'border-indigo-300',
      badgeBg: 'bg-indigo-50',
      badgeText: 'text-indigo-700',
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
      {cards.map((card) => {
        const Icon = card.icon;
        const isSelected = activeFilter === card.key;
        return (
          <button
            key={card.key}
            type="button"
            onClick={() => onSelectFilter(card.key)}
            className={cn(
              'flex flex-col text-left p-3.5 rounded-xl border bg-white transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]',
              isSelected
                ? 'border-[#006BFF] ring-2 ring-blue-100 bg-blue-50/20 shadow-md'
                : 'border-slate-200 hover:border-slate-300 hover:shadow'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-500 truncate">
                {card.label}
              </span>
              <div className={cn('p-1 rounded-md', card.badgeBg)}>
                <Icon className={cn('w-3.5 h-3.5', card.badgeText)} />
              </div>
            </div>
            <div className="text-2xl font-bold font-mono tabular-nums text-[#0B3558]">
              {card.count}
            </div>
          </button>
        );
      })}
    </div>
  );
}
