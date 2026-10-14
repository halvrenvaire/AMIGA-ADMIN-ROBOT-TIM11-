import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import dotenv from 'dotenv';

dotenv.config();
if (process.env.DATABASE_URL?.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, 'postgresql://');
}

import { PrismaClient, InvoiceStatus } from '@prisma/client';
import fs from 'fs';
import path from 'path';
import {
  AIExtractionWorker,
  normalizeText,
  extractTextFromPdfBuffer,
  withTimeout,
} from '../ai-extraction.worker.js';
import { StorageService, LocalStorageProvider } from '../../services/storage.service.js';
import { BedrockService } from '../../services/bedrock.service.js';

// Minimal valid PDF with text content stream
const samplePdfWithInvoiceText = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 350 >>
stream
BT
/F1 12 Tf
72 712 Td
(Vendor: PT Solusi Digital Nusantara) Tj
0 -20 Td
(Invoice No: INV/2026/04/9912) Tj
0 -20 Td
(Tanggal: 2026-04-15) Tj
0 -20 Td
(Item 1: Pengembangan Fitur AI Worker 1 x Rp 20.000.000 = Rp 20.000.000) Tj
0 -20 Td
(Nama Bank: Bank Central Asia BCA) Tj
0 -20 Td
(No. Rekening: 8820192831) Tj
0 -20 Td
(Atas Nama: PT Solusi Digital Nusantara) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000202 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
600
%%EOF`
);

describe('T-008: AI Extraction BullMQ Worker & PDF Parsing Tests', () => {
  const prisma = new PrismaClient();
  const testStorageDir = path.resolve(process.cwd(), './test-worker-storage');
  const storage = new StorageService(new LocalStorageProvider(testStorageDir));
  const bedrock = new BedrockService();
  const worker = new AIExtractionWorker(prisma, storage, bedrock, { timeoutMs: 15000 });

  let clientId: string;
  let uploaderId: string;
  const createdInvoiceIds: string[] = [];

  beforeAll(async () => {
    // Ambil client CLI-MAIN dan user pic_client yang sudah di-seed
    const client = await prisma.client.findUnique({ where: { clientCode: 'CLI-MAIN' } });
    if (!client) throw new Error('Client CLI-MAIN tidak ditemukan dalam database seed');
    clientId = client.id;

    const uploader = await prisma.user.findUnique({ where: { email: 'pic_client@amiga.co.id' } });
    if (!uploader) throw new Error('User pic_client@amiga.co.id tidak ditemukan dalam seed');
    uploaderId = uploader.id;
  });

  afterAll(async () => {
    // Bersihkan invoice yang dibuat selama pengujian
    for (const invId of createdInvoiceIds) {
      await prisma.auditLog.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoicePaymentDetail.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoiceLineItem.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoiceRequest.delete({ where: { id: invId } }).catch(() => {});
    }

    if (fs.existsSync(testStorageDir)) {
      fs.rmSync(testStorageDir, { recursive: true, force: true });
    }

    await worker.close();
    await prisma.$disconnect();
  });

  describe('Utility: normalizeText', () => {
    it('harus menormalkan string menjadi huruf kecil alfanumerik tanpa spasi & simbol [SRD]', () => {
      expect(normalizeText('PT Solusi Digital Nusantara')).toBe('ptsolusidigitalnusantara');
      expect(normalizeText('INV/2026/04/9912 #A')).toBe('inv2026049912a');
      expect(normalizeText('PT. Maju Bersama, TBK!')).toBe('ptmajubersamatbk');
      expect(normalizeText(null)).toBeNull();
      expect(normalizeText('')).toBeNull();
      expect(normalizeText('   ')).toBeNull();
    });
  });

  describe('Utility: extractTextFromPdfBuffer', () => {
    it('harus mengekstrak teks dari PDF buffer yang valid', async () => {
      const extracted = await extractTextFromPdfBuffer(samplePdfWithInvoiceText);
      expect(extracted).toContain('PT Solusi Digital');
      expect(extracted).toContain('INV/2026/04/9912');
    });
  });

  describe('Utility: withTimeout SLA Guard', () => {
    it('harus mengembalikan nilai jika operasi selesai sebelum batas timeout', async () => {
      const fastOp = new Promise<string>((resolve) => setTimeout(() => resolve('OK'), 20));
      const res = await withTimeout(fastOp, 500, 'Test Fast');
      expect(res).toBe('OK');
    });

    it('harus melempar error timeout jika operasi melebihi SLA batas waktu [PF-007]', async () => {
      const slowOp = new Promise<string>((resolve) => setTimeout(() => resolve('SLOW'), 200));
      await expect(withTimeout(slowOp, 50, 'Test Slow')).rejects.toThrow(
        /melebihi batas waktu SLA/
      );
    });
  });

  describe('Worker Process: processExtractionJob', () => {
    it('harus memproses invoice QUEUED, mengekstrak data via Bedrock fallback, dan menyimpannya ke database', async () => {
      // 1. Simpan berkas PDF ke storage
      const saveResult = await storage.saveFile(
        samplePdfWithInvoiceText,
        'invoice-worker-test.pdf',
        'worker-test'
      );

      // 2. Buat record InvoiceRequest berstatus QUEUED
      const testReqId = `REQ-TEST-WORKER-${Date.now()}`;
      const createdInvoice = await prisma.invoiceRequest.create({
        data: {
          requestId: testReqId,
          clientId,
          uploaderId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'invoice-worker-test.pdf',
          storageFilePath: saveResult.storageFilePath,
          filePageCount: 1,
          status: InvoiceStatus.QUEUED,
        },
      });
      createdInvoiceIds.push(createdInvoice.id);

      // 3. Jalankan pemrosesan worker
      const jobResult = await worker.processExtractionJob({
        invoiceId: createdInvoice.id,
        requestId: testReqId,
        clientId,
        storageFilePath: saveResult.storageFilePath,
      });

      // 4. Verifikasi hasil pengembalian pemrosesan (Lolos verifikasi -> READY_FOR_REVIEW) [T-010]
      expect(jobResult.invoiceId).toBe(createdInvoice.id);
      expect(jobResult.status).toBe(InvoiceStatus.READY_FOR_REVIEW);
      expect(jobResult.vendorName).toContain('PT Solusi Digital');
      expect(jobResult.invoiceNumber).toBe('INV/2026/04/9912');
      expect(jobResult.lineItemsCount).toBeGreaterThan(0);
      expect(jobResult.durationMs).toBeGreaterThan(0);
      expect(jobResult.slaExceeded).toBe(false);

      // 5. Verifikasi pembaruan pada tabel invoice_requests
      const updatedInvoice = await prisma.invoiceRequest.findUnique({
        where: { id: createdInvoice.id },
      });
      expect(updatedInvoice?.status).toBe(InvoiceStatus.READY_FOR_REVIEW);
      expect(updatedInvoice?.vendorName).toContain('PT Solusi Digital');
      expect(updatedInvoice?.vendorNameNormalized).toBe('ptsolusidigitalnusantara');
      expect(updatedInvoice?.invoiceNumber).toBe('INV/2026/04/9912');
      expect(updatedInvoice?.invoiceNumberNormalized).toBe('inv2026049912');
      expect(Number(updatedInvoice?.totalAmount)).toBeGreaterThan(0);

      // 6. Verifikasi persistensi invoice_line_items
      const lineItems = await prisma.invoiceLineItem.findMany({
        where: { requestId: createdInvoice.id },
        orderBy: { itemIndex: 'asc' },
      });
      expect(lineItems.length).toBeGreaterThan(0);
      expect(lineItems[0].itemIndex).toBe(1);
      expect(Number(lineItems[0].quantity)).toBe(1);
      expect(Number(lineItems[0].unitPrice)).toBe(20000000);
      expect(Number(lineItems[0].subtotal)).toBe(20000000);

      // 7. Verifikasi persistensi invoice_payment_details
      const paymentDetails = await prisma.invoicePaymentDetail.findUnique({
        where: { requestId: createdInvoice.id },
      });
      expect(paymentDetails).not.toBeNull();
      expect(paymentDetails?.accountNumber).toBe('8820192831');
      expect(paymentDetails?.bankName).toMatch(/BCA|Bank Central Asia/);

      // 8. Verifikasi Immutable Audit Log tercatat [SR-016, BR-015]
      const auditLogs = await prisma.auditLog.findMany({
        where: { requestId: createdInvoice.id },
        orderBy: { createdAt: 'asc' },
      });
      expect(auditLogs.length).toBeGreaterThanOrEqual(2);

      const statusChangeLog = auditLogs.find((l) => l.actionType === 'STATUS_CHANGED');
      expect(statusChangeLog).toBeDefined();

      const extractionLog = auditLogs.find((l) => l.actionType === 'AI_EXTRACTION_COMPLETED');
      expect(extractionLog).toBeDefined();
      expect(extractionLog?.actorName).toContain('AI Engine');
      expect((extractionLog?.changeDiff as any).invoiceNumber).toBe('INV/2026/04/9912');
    });

    it('harus mentransisi status ke EXCEPTION jika ditemukan kendala pada ekstraksi PDF (misal tanpa bank) [T-010]', async () => {
      // PDF tanpa rekening bank
      const pdfWithoutBank = Buffer.from(
        `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 200 >>
stream
BT
/F1 12 Tf
72 712 Td
(Vendor: PT Mitra Mandiri) Tj
0 -20 Td
(Invoice No: INV-NOBANK-001) Tj
0 -20 Td
(Item 1: Jasa Desain 1 x Rp 5.000.000 = Rp 5.000.000) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000202 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
450
%%EOF`
      );

      const saveResult = await storage.saveFile(
        pdfWithoutBank,
        'invoice-nobank.pdf',
        'worker-test'
      );

      const testReqId = `REQ-TEST-NOBANK-${Date.now()}`;
      const createdInvoice = await prisma.invoiceRequest.create({
        data: {
          requestId: testReqId,
          clientId,
          uploaderId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'invoice-nobank.pdf',
          storageFilePath: saveResult.storageFilePath,
          filePageCount: 1,
          status: InvoiceStatus.QUEUED,
        },
      });
      createdInvoiceIds.push(createdInvoice.id);

      const jobResult = await worker.processExtractionJob({
        invoiceId: createdInvoice.id,
        requestId: testReqId,
        clientId,
        storageFilePath: saveResult.storageFilePath,
      });

      expect(jobResult.status).toBe(InvoiceStatus.EXCEPTION);

      const updated = await prisma.invoiceRequest.findUnique({
        where: { id: createdInvoice.id },
      });
      expect(updated?.status).toBe(InvoiceStatus.EXCEPTION);

      const issues = await prisma.verificationIssue.findMany({
        where: { requestId: createdInvoice.id },
      });
      expect(issues.length).toBeGreaterThan(0);
    });

    it('harus melempar error jika invoice ID tidak ditemukan di database', async () => {
      const nonExistentId = '00000000-0000-0000-0000-000000000999';
      await expect(
        worker.processExtractionJob({
          invoiceId: nonExistentId,
          requestId: 'REQ-NONEXISTENT',
          clientId,
          storageFilePath: 'test.pdf',
        })
      ).rejects.toThrow(/tidak ditemukan/);
    });
  });
});
