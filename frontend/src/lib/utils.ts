import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format angka nominal ke format Rupiah (IDR).
 */
export function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return 'Rp 0';
  }
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format tanggal ke format lokal Indonesia (contoh: 14 Okt 2026).
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return '-';
    return new Intl.DateTimeFormat('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(d);
  } catch {
    return dateString;
  }
}

/**
 * Format tanggal dan waktu (contoh: 14 Okt 2026, 10:30).
 */
export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return '-';
    return new Intl.DateTimeFormat('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d);
  } catch {
    return dateString;
  }
}

/**
 * Format tanggal dan waktu presisi jejak audit dengan detik (contoh: 14 Okt 2026, 14:35:12 WIB).
 */
export function formatAuditTimestamp(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) return '-';
    const formatted = new Intl.DateTimeFormat('id-ID', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(d);
    return `${formatted} WIB`;
  } catch {
    return dateString;
  }
}

/**
 * Konversi angka ke kalimat terbilang bahasa Indonesia [DR-004].
 */
export function terbilang(n: number): string {
  const bilangan = [
    '',
    'Satu',
    'Dua',
    'Tiga',
    'Empat',
    'Lima',
    'Enam',
    'Tujuh',
    'Delapan',
    'Sembilan',
    'Sepuluh',
    'Sebelas',
  ];
  const num = Math.floor(Math.abs(n));
  if (num === 0) return 'Nol Rupiah';

  function convert(x: number): string {
    if (x < 12) return bilangan[x];
    if (x < 20) return convert(x - 10) + ' Belas';
    if (x < 100) return convert(Math.floor(x / 10)) + ' Puluh ' + (x % 10 ? convert(x % 10) : '');
    if (x < 200) return 'Seratus ' + (x - 100 ? convert(x - 100) : '');
    if (x < 1000) return convert(Math.floor(x / 100)) + ' Ratus ' + (x % 100 ? convert(x % 100) : '');
    if (x < 2000) return 'Seribu ' + (x - 1000 ? convert(x - 1000) : '');
    if (x < 1000000) return convert(Math.floor(x / 1000)) + ' Ribu ' + (x % 1000 ? convert(x % 1000) : '');
    if (x < 1000000000) return convert(Math.floor(x / 1000000)) + ' Juta ' + (x % 1000000 ? convert(x % 1000000) : '');
    if (x < 1000000000000) return convert(Math.floor(x / 1000000000)) + ' Miliar ' + (x % 1000000000 ? convert(x % 1000000000) : '');
    return convert(Math.floor(x / 1000000000000)) + ' Triliun ' + (x % 1000000000000 ? convert(x % 1000000000000) : '');
  }

  const result = convert(num).replace(/\s+/g, ' ').trim();
  return `${result} Rupiah`;
}

