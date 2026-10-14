'use client';

import React from 'react';
import { ReviewerWorkload } from '../../lib/types';
import { cn } from '../../lib/utils';
import { Users, AlertCircle, CheckCircle } from 'lucide-react';

interface ReviewerWorkloadBarProps {
  workloads: ReviewerWorkload[];
}

export function ReviewerWorkloadBar({ workloads }: ReviewerWorkloadBarProps) {
  if (!workloads || workloads.length === 0) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 mb-6 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-[#006BFF]" />
          <h2 className="text-sm font-semibold text-[#0B3558]">
            Monitoring Beban Antrean Reviewer
          </h2>
        </div>
        <span className="text-[11px] text-slate-500 font-medium">
          Ambang Batas Maksimal: 10 Dokumen Aktif
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {workloads.map((r) => {
          return (
            <div
              key={r.id}
              className={cn(
                'flex items-center justify-between p-3 rounded-lg border transition-all',
                r.isOverloaded
                  ? 'bg-rose-50 border-rose-300 text-rose-900 ring-1 ring-rose-200'
                  : 'bg-slate-50/70 border-slate-200 text-slate-800'
              )}
            >
              <div className="flex flex-col truncate pr-2">
                <span className="text-xs font-semibold truncate text-[#0B3558]">
                  {r.fullName}
                </span>
                <span className="text-[11px] text-slate-500 truncate">
                  {r.email}
                </span>
              </div>

              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span
                  className={cn(
                    'font-mono text-sm font-bold px-2 py-0.5 rounded-md tabular-nums',
                    r.isOverloaded
                      ? 'bg-rose-200/80 text-rose-900'
                      : 'bg-white border border-slate-200 text-[#0B3558]'
                  )}
                >
                  {r.activeCount} dok
                </span>
                {r.isOverloaded ? (
                  <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                ) : (
                  <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
