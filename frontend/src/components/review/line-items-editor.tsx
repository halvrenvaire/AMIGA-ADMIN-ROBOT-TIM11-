'use client';

import React, { useState, useEffect } from 'react';
import { LineItemDetail } from '../../lib/types';
import { formatCurrency } from '../../lib/utils';
import { Plus, Trash2, Save, Check, AlertCircle } from 'lucide-react';

interface LineItemsEditorProps {
  initialItems: LineItemDetail[];
  taxAmount: number;
  onSaveItems: (
    items: Array<{
      id?: string;
      description: string;
      quantity: number;
      unitPrice: number;
      subtotal: number;
    }>
  ) => Promise<void>;
  isSaving: boolean;
}

export function LineItemsEditor({
  initialItems,
  taxAmount,
  onSaveItems,
  isSaving,
}: LineItemsEditorProps) {
  const [items, setItems] = useState<LineItemDetail[]>(initialItems);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  const handleFieldChange = (
    index: number,
    field: 'description' | 'quantity' | 'unitPrice',
    value: string | number
  ) => {
    const updated = [...items];
    const item = { ...updated[index] };

    if (field === 'description') {
      item.description = String(value);
    } else if (field === 'quantity') {
      const q = Math.max(0, Number(value) || 0);
      item.quantity = q;
      item.subtotal = item.quantity * item.unitPrice; // LIVE SUBTOTAL MATH [T-015]
    } else if (field === 'unitPrice') {
      const price = Math.max(0, Number(value) || 0);
      item.unitPrice = price;
      item.subtotal = item.quantity * item.unitPrice; // LIVE SUBTOTAL MATH [T-015]
    }

    item.isManuallyEdited = true;
    updated[index] = item;
    setItems(updated);
    setHasUnsavedChanges(true);
    setSaveSuccessMsg(null);
  };

  const handleAddItem = () => {
    const newItem: LineItemDetail = {
      id: `new-${Date.now()}`,
      itemIndex: items.length + 1,
      description: 'Item Baru',
      quantity: 1,
      unitPrice: 0,
      subtotal: 0,
      isManuallyEdited: true,
    };
    setItems([...items, newItem]);
    setHasUnsavedChanges(true);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length <= 1) return;
    const updated = items.filter((_, i) => i !== index);
    setItems(updated);
    setHasUnsavedChanges(true);
  };

  const calculatedSubtotal = items.reduce((acc, curr) => acc + curr.subtotal, 0);
  const calculatedGrandTotal = calculatedSubtotal + taxAmount;

  const handleSave = async () => {
    try {
      await onSaveItems(
        items.map((i) => ({
          id: i.id.startsWith('new-') ? undefined : i.id,
          description: i.description,
          quantity: i.quantity,
          unitPrice: i.unitPrice,
          subtotal: i.subtotal,
        }))
      );
      setHasUnsavedChanges(false);
      setSaveSuccessMsg('Perubahan rincian item berhasil disimpan ke database.');
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
        <div>
          <h3 className="text-xs font-bold text-[#0B3558] uppercase tracking-wider">
            Rincian Barang & Jasa (Line Items)
          </h3>
          <p className="text-[11px] text-slate-500">
            Koreksi deskripsi, kuantitas, atau harga satuan. Kalkulasi subtotal berjalan otomatis.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {saveSuccessMsg && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">
              <Check className="w-3.5 h-3.5 text-emerald-600" />
              <span>Tersimpan</span>
            </span>
          )}

          <button
            type="button"
            onClick={handleAddItem}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Tambah Baris</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={!hasUnsavedChanges || isSaving}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold text-white bg-[#006BFF] hover:bg-[#0055CC] disabled:opacity-40 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-[#006BFF]"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isSaving ? 'Menyimpan...' : 'Simpan Rincian'}</span>
          </button>
        </div>
      </div>

      {/* Line Items Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/50 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th className="py-2.5 px-3 w-10 text-center">No</th>
              <th className="py-2.5 px-3">Deskripsi Barang / Jasa</th>
              <th className="py-2.5 px-3 w-24 text-right">Kuantitas</th>
              <th className="py-2.5 px-3 w-36 text-right">Harga Satuan (IDR)</th>
              <th className="py-2.5 px-3 w-36 text-right">Subtotal (IDR)</th>
              <th className="py-2.5 px-3 w-10 text-center"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((item, idx) => {
              return (
                <tr key={item.id} className="hover:bg-slate-50/50">
                  <td className="py-2 px-3 text-center font-mono text-slate-400">
                    {idx + 1}
                  </td>

                  {/* Deskripsi */}
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={item.description}
                      onChange={(e) => handleFieldChange(idx, 'description', e.target.value)}
                      className="w-full px-2 py-1 text-xs rounded border border-transparent hover:border-slate-300 focus:border-[#006BFF] focus:bg-white focus:outline-none"
                    />
                    {item.isManuallyEdited && (
                      <span className="inline-block text-[9px] font-semibold text-blue-700 bg-blue-50 px-1 rounded ml-1">
                        Diedit
                      </span>
                    )}
                  </td>

                  {/* Kuantitas */}
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={item.quantity}
                      onChange={(e) => handleFieldChange(idx, 'quantity', e.target.value)}
                      className="w-20 px-2 py-1 text-xs text-right font-mono font-medium rounded border border-transparent hover:border-slate-300 focus:border-[#006BFF] focus:bg-white focus:outline-none tabular-nums"
                    />
                  </td>

                  {/* Harga Satuan */}
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      min="0"
                      step="500"
                      value={item.unitPrice}
                      onChange={(e) => handleFieldChange(idx, 'unitPrice', e.target.value)}
                      className="w-32 px-2 py-1 text-xs text-right font-mono font-medium rounded border border-transparent hover:border-slate-300 focus:border-[#006BFF] focus:bg-white focus:outline-none tabular-nums"
                    />
                  </td>

                  {/* Subtotal (Live Calculated) */}
                  <td className="py-2 px-3 text-right font-mono font-bold text-[#0B3558] tabular-nums">
                    {formatCurrency(item.subtotal)}
                  </td>

                  {/* Hapus Baris */}
                  <td className="py-2 px-3 text-center">
                    <button
                      type="button"
                      onClick={() => handleRemoveItem(idx)}
                      disabled={items.length <= 1}
                      className="text-slate-400 hover:text-rose-600 disabled:opacity-20 transition-colors p-1"
                      title="Hapus baris"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Kalkulasi Total Summary Footer */}
      <div className="bg-slate-50/70 p-4 border-t border-slate-200 flex flex-col items-end space-y-1.5">
        <div className="flex items-center gap-6 text-xs text-slate-600">
          <span>Subtotal Rincian Item:</span>
          <span className="font-mono font-bold text-slate-800 tabular-nums">
            {formatCurrency(calculatedSubtotal)}
          </span>
        </div>
        <div className="flex items-center gap-6 text-xs text-slate-600">
          <span>Pajak (PPN):</span>
          <span className="font-mono font-medium text-slate-800 tabular-nums">
            {formatCurrency(taxAmount)}
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm font-bold text-[#0B3558] pt-1.5 border-t border-slate-200">
          <span>Grand Total Tagihan:</span>
          <span className="font-mono text-base text-[#006BFF] tabular-nums">
            {formatCurrency(calculatedGrandTotal)}
          </span>
        </div>
      </div>
    </div>
  );
}
