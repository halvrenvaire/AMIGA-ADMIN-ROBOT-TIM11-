import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import dotenv from 'dotenv';

dotenv.config();
if (process.env.DATABASE_URL?.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, 'postgresql://');
}

import { PrismaClient, InvoiceStatus, IssueCode, IssueCategory, Prisma } from '@prisma/client';
import { VerificationService } from '../verification.service.js';

describe('T-009 & T-010: Verification Engine & Lifecycle State Machine Tests', () => {
  const prisma = new PrismaClient();
  const service = new VerificationService(prisma);

  let clientId: string;
  let otherClientId: string;
  let uploaderId: string;
  const createdInvoiceIds: string[] = [];

  beforeAll(async () => {
    const client = await prisma.client.findUnique({ where: { clientCode: 'CLI-MAIN' } });
    if (!client) throw new Error('Client CLI-MAIN tidak ditemukan');
    clientId = client.id;

    const otherClient = await prisma.client.findUnique({ where: { clientCode: 'CLI-001' } });
    if (!otherClient) throw new Error('Client CLI-001 tidak ditemukan');
    otherClientId = otherClient.id;

    const uploader = await prisma.user.findUnique({ where: { email: 'pic_client@amiga.co.id' } });
    if (!uploader) throw new Error('User pic_client@amiga.co.id tidak ditemukan');
    uploaderId = uploader.id;
  });

  afterAll(async () => {
    for (const invId of createdInvoiceIds) {
      await prisma.auditLog.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.verificationIssue.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoicePaymentDetail.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoiceLineItem.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await prisma.invoiceRequest.delete({ where: { id: invId } }).catch(() => {});
    }

    await prisma.$disconnect();
  });

  // Helper membuat invoice pengujian di database
  async function createTestInvoice(options: {
    targetClientId?: string;
    vendorName?: string;
    invoiceNumber?: string;
    subtotalAmount?: number;
    taxAmount?: number;
    totalAmount?: number;
    bankName?: string | null;
    accountNumber?: string | null;
    lineItems?: Array<{ description: string; quantity: number; unitPrice: number; subtotal: number }>;
  }) {
    const {
      targetClientId = clientId,
      vendorName = 'PT Mega Perkasa Abadi',
      invoiceNumber = `INV-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      subtotalAmount = 10000000,
      taxAmount = 1100000,
      totalAmount = 11100000,
      bankName = 'Bank Central Asia (BCA)',
      accountNumber = '1234567890',
    } = options;

    const lineItems = options.lineItems || [
      {
        description: 'Layanan Pengadaan Server Cloud',
        quantity: 1,
        unitPrice: subtotalAmount,
        subtotal: subtotalAmount,
      },
    ];

    const reqId = `REQ-VERIF-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
    const vendorNorm = service.normalizeText(vendorName);
    const invNumNorm = service.normalizeText(invoiceNumber);

    const invoice = await prisma.invoiceRequest.create({
      data: {
        requestId: reqId,
        clientId: targetClientId,
        uploaderId,
        requestType: 'Standard Vendor Invoice',
        submissionChannel: 'Portal',
        submissionDate: new Date(),
        originalFileName: 'test-invoice.pdf',
        storageFilePath: 'invoices/test.pdf',
        filePageCount: 1,
        status: InvoiceStatus.PROCESSING,
        vendorName,
        vendorNameNormalized: vendorNorm,
        invoiceNumber,
        invoiceNumberNormalized: invNumNorm,
        subtotalAmount: new Prisma.Decimal(subtotalAmount),
        taxAmount: new Prisma.Decimal(taxAmount),
        totalAmount: new Prisma.Decimal(totalAmount),
        lineItems: {
          create: lineItems.map((item, idx) => ({
            itemIndex: idx + 1,
            description: item.description,
            quantity: new Prisma.Decimal(item.quantity),
            unitPrice: new Prisma.Decimal(item.unitPrice),
            subtotal: new Prisma.Decimal(item.subtotal),
          })),
        },
        paymentDetails: {
          create: {
            bankName,
            accountNumber,
            accountHolderName: vendorName,
          },
        },
      },
    });

    createdInvoiceIds.push(invoice.id);
    return invoice;
  }

  describe('T-009: 3 Aturan Verifikasi Sistem Otomatis', () => {
    it('Skenario Bersih: Dokumen valid tanpa kejanggalan lolos seluruh aturan', async () => {
      const invoice = await createTestInvoice({
        subtotalAmount: 10000000,
        taxAmount: 1100000,
        totalAmount: 11100000,
        bankName: 'BCA',
        accountNumber: '992817261',
        lineItems: [
          { description: 'Item 1', quantity: 2, unitPrice: 5000000, subtotal: 10000000 },
        ],
      });

      const issues = await service.evaluateRules(invoice.id);
      expect(issues.length).toBe(0);
    });

    it('Aturan 1 (MISSING_EVIDENCE): Menghasilkan issue jika nomor rekening atau nama bank kosong [BR-008, PR-011]', async () => {
      const invoice = await createTestInvoice({
        bankName: null,
        accountNumber: null,
      });

      const issues = await service.evaluateRules(invoice.id);
      expect(issues.length).toBe(1);
      expect(issues[0].issueCode).toBe(IssueCode.MISSING_EVIDENCE);
      expect(issues[0].issueCategory).toBe(IssueCategory.COMPLETENESS);
      expect(issues[0].messageId).toContain('nomor rekening atau nama bank');
    });

    it('Aturan 2 (POSSIBLE_DUPLICATE): Menghasilkan issue jika vendor dan nomor invoice identik pada klien yang sama [BR-008, PR-011, SR-013]', async () => {
      const sharedVendor = 'PT Cahaya Abadi Teknologi';
      const sharedInvoiceNo = 'INV/2026/DUPLIKAT/001';

      // Invoice pertama
      await createTestInvoice({
        targetClientId: clientId,
        vendorName: sharedVendor,
        invoiceNumber: sharedInvoiceNo,
      });

      // Invoice kedua dengan variasi huruf besar-kecil & tanda baca (normalisasi sama)
      const duplicateInvoice = await createTestInvoice({
        targetClientId: clientId,
        vendorName: 'pt. cahaya abadi teknologi',
        invoiceNumber: 'inv-2026-duplikat-001',
      });

      const issues = await service.evaluateRules(duplicateInvoice.id);
      expect(issues.length).toBe(1);
      expect(issues[0].issueCode).toBe(IssueCode.POSSIBLE_DUPLICATE);
      expect(issues[0].issueCategory).toBe(IssueCategory.INTEGRITY);
      expect(issues[0].messageId).toContain('sudah pernah diunggah sebelumnya');
    });

    it('Aturan 2 Isolasi Multi-Tenant: Dokumen dengan nomor & vendor sama pada KLIEN BERBEDA bukan duplikat [SR-003, BR-014]', async () => {
      const vendor = 'PT Mitra Lintas Klien';
      const invNo = 'INV/CROSS-CLIENT/999';

      // Invoice di Klien A
      await createTestInvoice({
        targetClientId: clientId,
        vendorName: vendor,
        invoiceNumber: invNo,
      });

      // Invoice di Klien B
      const clientBInvoice = await createTestInvoice({
        targetClientId: otherClientId,
        vendorName: vendor,
        invoiceNumber: invNo,
      });

      const issues = await service.evaluateRules(clientBInvoice.id);
      const duplicateIssue = issues.find((i) => i.issueCode === IssueCode.POSSIBLE_DUPLICATE);
      expect(duplicateIssue).toBeUndefined();
    });

    it('Aturan 3 (CALCULATION_DISCREPANCY): Menghasilkan issue jika total != sum(subtotal line items) + tax [BR-008, PR-011]', async () => {
      // Acceptance Criteria: total Rp 1.500.000 namun line items Rp 1.400.000 (tax 0)
      const invoice = await createTestInvoice({
        subtotalAmount: 1400000,
        taxAmount: 0,
        totalAmount: 1500000, // Discrepancy! Selisih 100.000
        lineItems: [
          { description: 'Konsultasi Modul', quantity: 1, unitPrice: 1400000, subtotal: 1400000 },
        ],
      });

      const issues = await service.evaluateRules(invoice.id);
      expect(issues.length).toBe(1);
      expect(issues[0].issueCode).toBe(IssueCode.CALCULATION_DISCREPANCY);
      expect(issues[0].issueCategory).toBe(IssueCategory.ARITHMETIC);
      expect(issues[0].messageId).toContain('tidak sama dengan penjumlahan subtotal');
    });
  });

  describe('T-010: Transisi State Siklus Hidup Dokumen (6 Status Pasti)', () => {
    it('Lolos Verifikasi: Transisi status PROCESSING -> READY_FOR_REVIEW dan catat audit log [PR-012, PF-009]', async () => {
      const invoice = await createTestInvoice({
        subtotalAmount: 5000000,
        taxAmount: 550000,
        totalAmount: 5550000,
        bankName: 'Bank Mandiri',
        accountNumber: '140001928312',
      });

      const result = await service.verifyAndTransition(invoice.id);

      expect(result.hasIssues).toBe(false);
      expect(result.newStatus).toBe(InvoiceStatus.READY_FOR_REVIEW);

      // Cek record database
      const updated = await prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
      expect(updated?.status).toBe(InvoiceStatus.READY_FOR_REVIEW);

      // Cek tabel verification_issues kosong
      const savedIssues = await prisma.verificationIssue.findMany({ where: { requestId: invoice.id } });
      expect(savedIssues.length).toBe(0);

      // Cek audit logs immutable tercatat
      const auditLog = await prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'STATUS_CHANGED' },
        orderBy: { createdAt: 'desc' },
      });
      expect(auditLog?.newStatus).toBe(InvoiceStatus.READY_FOR_REVIEW);
      expect((auditLog?.changeDiff as any).hasIssues).toBe(false);
    });

    it('Gagal Verifikasi: Transisi status PROCESSING -> EXCEPTION, simpan issue ke database, dan catat audit log [PR-012, PF-009]', async () => {
      const invoice = await createTestInvoice({
        bankName: null,
        accountNumber: null, // Memicu MISSING_EVIDENCE
        subtotalAmount: 2000000,
        taxAmount: 0,
        totalAmount: 2500000, // Memicu CALCULATION_DISCREPANCY
      });

      const result = await service.verifyAndTransition(invoice.id);

      expect(result.hasIssues).toBe(true);
      expect(result.newStatus).toBe(InvoiceStatus.EXCEPTION);
      expect(result.issues.length).toBe(2);

      // Cek record database status EXCEPTION
      const updated = await prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
      expect(updated?.status).toBe(InvoiceStatus.EXCEPTION);

      // Cek tabel verification_issues tersimpan 2 baris
      const savedIssues = await prisma.verificationIssue.findMany({ where: { requestId: invoice.id } });
      expect(savedIssues.length).toBe(2);
      const codes = savedIssues.map((i) => i.issueCode);
      expect(codes).toContain(IssueCode.MISSING_EVIDENCE);
      expect(codes).toContain(IssueCode.CALCULATION_DISCREPANCY);

      // Cek audit log immutable
      const auditLog = await prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'STATUS_CHANGED' },
        orderBy: { createdAt: 'desc' },
      });
      expect(auditLog?.newStatus).toBe(InvoiceStatus.EXCEPTION);
      expect((auditLog?.changeDiff as any).hasIssues).toBe(true);
      expect((auditLog?.changeDiff as any).issuesCount).toBe(2);
    });
  });
});
