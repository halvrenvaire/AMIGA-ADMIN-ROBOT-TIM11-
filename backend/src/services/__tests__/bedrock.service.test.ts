import { describe, it, expect } from 'vitest';
import { BedrockService } from '../bedrock.service.js';

const sampleInvoiceText = `
FAKTUR TAGIHAN / INVOICE
Vendor: PT Prima Digital Nusantara
Invoice No: INV/2026/04/9912
Tanggal: 2026-04-15

Item 1: Pengembangan Modul Keuangan Backend 1 x Rp 25.000.000 = Rp 25.000.000
Item 2: Konfigurasi Cloud AWS Bedrock 1 x Rp 5.000.000 = Rp 5.000.000

Informasi Pembayaran / Transfer:
Nama Bank: Bank Central Asia (BCA)
No. Rekening: 8820192831
Atas Nama: PT Prima Digital Nusantara
`;

const sampleInvoiceTextWithoutBank = `
TAGIHAN PEMBAYARAN
PT Sukses Bersama
Nomor Invoice: INV-2026-888
Tanggal: 2026-05-10

Layanan 1: Jasa Desain UI UX Web App 2 x Rp 4.000.000 = Rp 8.000.000
(Silakan hubungi finance untuk nomor rekening transfer)
`;

describe('T-007: BedrockService AI Extraction & Fallback Tests', () => {
  const service = new BedrockService();

  describe('Deterministic Heuristic Extractor', () => {
    it('harus mengekstrak vendor, nomor invoice, tanggal, rekening, dan line items secara akurat', () => {
      const result = service.deterministicHeuristicExtraction(sampleInvoiceText);

      expect(result.vendorName).toContain('PT Prima Digital Nusantara');
      expect(result.invoiceNumber).toBe('INV/2026/04/9912');
      expect(result.invoiceDate).toBe('2026-04-15');
      expect(result.paymentDetails.bankName).toMatch(/Bank Central Asia|BCA/);
      expect(result.paymentDetails.accountNumber).toBe('8820192831');
      expect(result.paymentDetails.accountHolderName).toContain('PT Prima Digital Nusantara');

      expect(result.lineItems.length).toBe(2);
      expect(result.lineItems[0].description).toContain('Pengembangan Modul Keuangan');
      expect(result.lineItems[0].subtotal).toBe(25000000);
      expect(result.lineItems[1].subtotal).toBe(5000000);
      expect(result.subtotalAmount).toBe(30000000);
      expect(result.taxAmount).toBe(3300000); // PPN 11%
      expect(result.totalAmount).toBe(33300000);
    });

    it('harus mengembalikan accountNumber null jika informasi rekening tidak ditemukan pada invoice', () => {
      const result = service.deterministicHeuristicExtraction(sampleInvoiceTextWithoutBank);

      expect(result.vendorName).toContain('PT Sukses Bersama');
      expect(result.invoiceNumber).toBe('INV-2026-888');
      expect(result.paymentDetails.accountNumber).toBeNull();
    });
  });

  describe('extractInvoiceData Method', () => {
    it('harus mengembalikan InvoiceExtractionResult lengkap dengan durasi pengukuran', async () => {
      const result = await service.extractInvoiceData(sampleInvoiceText);

      expect(result).toBeDefined();
      expect(result.vendorName).toBeDefined();
      expect(result.invoiceNumber).toBeDefined();
      expect(result.lineItems.length).toBeGreaterThan(0);
      expect(result.extractionDurationMs).toBeGreaterThanOrEqual(0);
      expect(result.isMockFallback).toBe(true); // Karena AWS_ACCESS_KEY='xxx' di test env
    });
  });
});
