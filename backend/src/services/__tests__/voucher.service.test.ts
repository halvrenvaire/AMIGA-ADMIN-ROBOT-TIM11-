import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import dotenv from 'dotenv';

dotenv.config();
if (process.env.DATABASE_URL?.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, 'postgresql://');
}

import { PrismaClient, InvoiceStatus, UserRole, IssueCode, IssueCategory } from '@prisma/client';
import { VoucherService, VoucherError, terbilang } from '../voucher.service.js';
import { StorageService } from '../storage.service.js';
import { JwtPayload } from '../../types/auth.types.js';

describe('T-018: VoucherService & PDF Generation Engine', () => {
  let prisma: PrismaClient;
  let storage: StorageService;
  let voucherService: VoucherService;

  let clientMainId: string;
  let clientCode: string;
  let reviewerUser: JwtPayload;
  let picUser: JwtPayload;
  let unauthorizedUser: JwtPayload;
  const testInvoiceIds: string[] = [];

  beforeAll(async () => {
    prisma = new PrismaClient();
    await prisma.$connect();
    storage = new StorageService();
    voucherService = new VoucherService(prisma, storage);

    // Ambil client CLI-MAIN
    const client = await prisma.client.findUniqueOrThrow({
      where: { clientCode: 'CLI-MAIN' },
    });
    clientMainId = client.id;
    clientCode = client.clientCode;

    // Ambil user reviewer1
    const reviewer = await prisma.user.findUniqueOrThrow({
      where: { email: 'reviewer1@amiga.co.id' },
    });
    reviewerUser = {
      id: reviewer.id,
      email: reviewer.email,
      fullName: reviewer.fullName,
      role: reviewer.role,
      assignedClientIds: [clientMainId],
    };

    // Ambil user pic_client
    const pic = await prisma.user.findUniqueOrThrow({
      where: { email: 'pic_client@amiga.co.id' },
    });
    picUser = {
      id: pic.id,
      email: pic.email,
      fullName: pic.fullName,
      role: pic.role,
      assignedClientIds: [clientMainId],
    };

    // Buat user unauthorised (tidak punya akses clientMainId)
    unauthorizedUser = {
      id: '00000000-0000-0000-0000-000000000099',
      email: 'outsider@other.co.id',
      fullName: 'Outsider User',
      role: UserRole.PIC_KLIEN,
      assignedClientIds: ['00000000-0000-0000-0000-000000000001'],
    };
  });

  afterAll(async () => {
    for (const id of testInvoiceIds) {
      await prisma.auditLog.deleteMany({ where: { requestId: id } }).catch(() => {});
      await prisma.paymentVoucher.deleteMany({ where: { requestId: id } }).catch(() => {});
      await prisma.verificationIssue.deleteMany({ where: { requestId: id } }).catch(() => {});
      await prisma.invoiceLineItem.deleteMany({ where: { requestId: id } }).catch(() => {});
      await prisma.invoicePaymentDetail.deleteMany({ where: { requestId: id } }).catch(() => {});
      await prisma.invoiceRequest.delete({ where: { id } }).catch(() => {});
    }
    await prisma.$disconnect();
  });

  describe('Fungsi Helper: terbilang (Konversi Rupiah)', () => {
    it('harus mengonversi angka nominal ke kalimat terbilang bahasa Indonesia yang benar', () => {
      expect(terbilang(0)).toBe('Nol Rupiah');
      expect(terbilang(1000)).toBe('Seribu Rupiah');
      expect(terbilang(50000)).toBe('Lima Puluh Ribu Rupiah');
      expect(terbilang(1110000)).toBe('Satu Juta Seratus Sepuluh Ribu Rupiah');
      expect(terbilang(16650000)).toBe('Enam Belas Juta Enam Ratus Lima Puluh Ribu Rupiah');
    });
  });

  describe('Kompilasi Voucher PDF & Transaksi Atomik', () => {
    it('harus berhasil mengompilasi voucher PDF resmi dengan SLA <= 3000ms dan nomor berformat VCH/YYYYMM/CLI/XXXXX', async () => {
      const reqId = `REQ-VCH-${Date.now()}`;
      const invoice = await prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUser.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'voucher_test.pdf',
          storageFilePath: 'invoices/voucher_test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Sumber Berkah Sejahtera',
          invoiceNumber: 'INV/2026/VCH-01',
          invoiceDate: new Date('2026-10-10'),
          subtotalAmount: 15000000,
          taxAmount: 1650000,
          totalAmount: 16650000,
        },
      });
      testInvoiceIds.push(invoice.id);

      // Line items
      await prisma.invoiceLineItem.createMany({
        data: [
          {
            requestId: invoice.id,
            itemIndex: 1,
            description: 'Pengadaan Perangkat Server Rack 2U',
            quantity: 1,
            unitPrice: 10000000,
            subtotal: 10000000,
          },
          {
            requestId: invoice.id,
            itemIndex: 2,
            description: 'Instalasi & Konfigurasi Jaringan',
            quantity: 1,
            unitPrice: 5000000,
            subtotal: 5000000,
          },
        ],
      });

      // Payment details
      await prisma.invoicePaymentDetail.create({
        data: {
          requestId: invoice.id,
          bankName: 'Bank Central Asia (BCA)',
          accountNumber: '8800112233',
          accountHolderName: 'PT Sumber Berkah Sejahtera',
        },
      });

      // Eksekusi kompilasi voucher dan ukur durasi (SLA <= 3000ms)
      const startTime = Date.now();
      const result = await voucherService.generateVoucher(reviewerUser, reqId);
      const durationMs = Date.now() - startTime;

      // 1. Verifikasi SLA kompilasi
      expect(durationMs).toBeLessThanOrEqual(3000);

      // 2. Verifikasi format nomor voucher: VCH/YYYYMM/CLI/XXXXX
      const yearMonth = new Date().toISOString().slice(0, 7).replace('-', '');
      const expectedPrefix = `VCH/${yearMonth}/${clientCode}/`;
      expect(result.voucher.voucherNumber.startsWith(expectedPrefix)).toBe(true);
      expect(result.voucher.voucherNumber).toMatch(/^VCH\/\d{6}\/[A-Z0-9-]+\/\d{5}$/);

      // 3. Verifikasi teks batas otorisasi legal verbatim
      const expectedLegalText =
        'Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin atas dasar verifikasi independen tim Keuangan AMIGA. Otorisasi pembayaran akhir dan eksekusi transfer dana merupakan kewenangan mutlak Client Approver di luar sistem AMIGA.';
      expect(result.voucher.authorizationBoundaryText).toBe(expectedLegalText);

      // 4. Verifikasi buffer berkas PDF
      expect(result.pdfBuffer).toBeDefined();
      expect(result.pdfBuffer.length).toBeGreaterThan(1000);
      expect(result.pdfBuffer.slice(0, 5).toString('ascii')).toBe('%PDF-');

      // 5. Verifikasi mutasi status invoice menjadi AMIGA_REVIEWED
      const updatedInvoice = await prisma.invoiceRequest.findUnique({
        where: { id: invoice.id },
      });
      expect(updatedInvoice?.status).toBe(InvoiceStatus.AMIGA_REVIEWED);

      // 6. Verifikasi audit log tercatat
      const auditLog = await prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'VOUCHER_GENERATED' },
      });
      expect(auditLog).toBeDefined();
      expect(auditLog?.actorRole).toBe(UserRole.FINANCE_REVIEWER);
      expect(auditLog?.newStatus).toBe(InvoiceStatus.AMIGA_REVIEWED);
    });

    it('harus menolak pembuatan voucher jika masih ada kendala verifikasi yang belum tuntas', async () => {
      const reqId = `REQ-ISSUE-${Date.now()}`;
      const invoice = await prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUser.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'issue_test.pdf',
          storageFilePath: 'invoices/issue_test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Masih Bermasalah',
          subtotalAmount: 100000,
          totalAmount: 100000,
        },
      });
      testInvoiceIds.push(invoice.id);

      // Buat issue belum terselesaikan
      await prisma.verificationIssue.create({
        data: {
          requestId: invoice.id,
          issueCode: IssueCode.MISSING_EVIDENCE,
          issueCategory: IssueCategory.COMPLETENESS,
          messageId: 'Nomor rekening bank tidak terdeteksi.',
          isResolved: false,
        },
      });

      await expect(
        voucherService.generateVoucher(reviewerUser, reqId)
      ).rejects.toThrow(VoucherError);
    });

    it('harus menolak akses jika pengguna tidak memiliki izin atas tenant klien', async () => {
      const reqId = `REQ-TENANT-${Date.now()}`;
      const invoice = await prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUser.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'tenant_test.pdf',
          storageFilePath: 'invoices/tenant_test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Tenant Isolasi',
        },
      });
      testInvoiceIds.push(invoice.id);

      await expect(
        voucherService.generateVoucher(unauthorizedUser, reqId)
      ).rejects.toThrow(VoucherError);
    });
  });
});
