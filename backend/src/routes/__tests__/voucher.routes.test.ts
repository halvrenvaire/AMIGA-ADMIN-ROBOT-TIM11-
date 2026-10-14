import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import dotenv from 'dotenv';

dotenv.config();
if (process.env.DATABASE_URL?.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, 'postgresql://');
}

import { FastifyInstance } from 'fastify';
import { InvoiceStatus, UserRole } from '@prisma/client';
import bcrypt from 'bcryptjs';
import { buildApp } from '../../app.js';
import { VoucherService } from '../../services/voucher.service.js';

describe('T-019: Fastify Voucher Routes Tests (Preview & Download)', () => {
  let app: FastifyInstance;
  let reviewerToken: string;
  let picToken: string;
  let otherPicToken: string;
  let reviewerUserId: string;
  let picUserId: string;
  let clientMainId: string;
  let clientSecondId: string;
  const testInvoiceIds: string[] = [];

  beforeAll(async () => {
    app = buildApp();
    await app.ready();

    // 1. Login reviewer 1
    const resRev = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'reviewer1@amiga.co.id', password: 'password123!' },
    });
    const revData = JSON.parse(resRev.body).data;
    reviewerToken = revData.accessToken;
    reviewerUserId = revData.user.id;

    // 2. Login PIC Klien (akses ke CLI-MAIN)
    const resPic = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'pic_client@amiga.co.id', password: 'password123!' },
    });
    const picData = JSON.parse(resPic.body).data;
    picToken = picData.accessToken;
    picUserId = picData.user.id;

    // 3. Ambil data klien
    const clientMain = await app.prisma.client.findUniqueOrThrow({ where: { clientCode: 'CLI-MAIN' } });
    clientMainId = clientMain.id;

    // Ambil atau buat client kedua untuk uji multi-tenant isolation
    let clientSecond = await app.prisma.client.findFirst({
      where: { NOT: { id: clientMainId } },
    });
    if (!clientSecond) {
      clientSecond = await app.prisma.client.create({
        data: {
          clientCode: 'CLI-OTHER',
          clientName: 'PT Other Client',
        },
      });
    }
    clientSecondId = clientSecond.id;

    // Buat PIC Klien untuk clientSecond
    const otherPicEmail = `other_pic_${Date.now()}@other.co.id`;
    const passwordHash = await bcrypt.hash('password123!', 10);
    const otherPic = await app.prisma.user.create({
      data: {
        email: otherPicEmail,
        passwordHash,
        fullName: 'Other PIC',
        role: UserRole.PIC_KLIEN,
        defaultClient: { connect: { id: clientSecondId } },
      },
    });
    const otherPicUserId = otherPic.id;

    await app.prisma.userClientAssignment.create({
      data: {
        user: { connect: { id: otherPic.id } },
        client: { connect: { id: clientSecondId } },
        delegator: { connect: { id: reviewerUserId } },
      },
    });

    const resOtherPic = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: otherPicEmail, password: 'password123!' },
    });
    otherPicToken = JSON.parse(resOtherPic.body).data.accessToken;
  });

  afterAll(async () => {
    for (const id of testInvoiceIds) {
      await app.prisma.auditLog.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.paymentVoucher.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.verificationIssue.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoiceLineItem.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoicePaymentDetail.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoiceRequest.delete({ where: { id } }).catch(() => {});
    }
    await app.prisma.userClientAssignment.deleteMany({ where: { client: { clientCode: 'CLI-OTHER' } } }).catch(() => {});
    await app.prisma.user.deleteMany({ where: { email: { startsWith: 'other_pic_' } } }).catch(() => {});
    await app.prisma.client.deleteMany({ where: { clientCode: 'CLI-OTHER' } }).catch(() => {});
    await app.close();
  });

  /**
   * Helper untuk membuat invoice yang sudah memiliki payment voucher resmi
   */
  async function createApprovedInvoiceWithVoucher(): Promise<{
    invoiceId: string;
    requestId: string;
    voucherNumber: string;
  }> {
    const reqId = `REQ-TEST-VCH-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
    const invoice = await app.prisma.invoiceRequest.create({
      data: {
        requestId: reqId,
        clientId: clientMainId,
        uploaderId: picUserId,
        status: InvoiceStatus.READY_FOR_REVIEW,
        requestType: 'STANDARD_INVOICE',
        submissionChannel: 'PORTAL_UPLOAD',
        submissionDate: new Date('2026-10-10'),
        originalFileName: 'invoice_official.pdf',
        storageFilePath: 'invoices/sample.pdf',
        filePageCount: 1,
        vendorName: 'PT Mitra Sukses Mandiri',
        invoiceNumber: `INV-${Date.now()}`,
        invoiceDate: new Date('2026-10-10'),
        subtotalAmount: 15000000,
        taxAmount: 1650000,
        totalAmount: 16650000,
        paymentDetails: {
          create: {
            bankName: 'Bank Central Asia',
            accountNumber: '8800112233',
            accountHolderName: 'PT Mitra Sukses Mandiri',
          },
        },
        lineItems: {
          create: [
            {
              itemIndex: 1,
              description: 'Layanan Managed Cloud Server',
              quantity: 1,
              unitPrice: 15000000,
              subtotal: 15000000,
            },
          ],
        },
      },
    });
    testInvoiceIds.push(invoice.id);

    // Generate voucher menggunakan VoucherService
    const voucherService = new VoucherService(app.prisma, app.storage);
    const generated = await voucherService.generateVoucher(
      {
        id: reviewerUserId,
        email: 'reviewer1@amiga.co.id',
        fullName: 'Budi Santoso',
        role: UserRole.FINANCE_REVIEWER,
        assignedClientIds: [clientMainId],
      },
      invoice.id
    );

    return {
      invoiceId: invoice.id,
      requestId: invoice.requestId,
      voucherNumber: generated.voucher.voucherNumber,
    };
  }

  describe('1. GET /api/v1/invoices/:requestId/voucher (Pratinjau Voucher)', () => {
    it('harus berhasil mengembalikan detail voucher pembayaran resmi secara lengkap [PR-022, DR-004]', async () => {
      const { requestId, voucherNumber } = await createApprovedInvoiceWithVoucher();

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${requestId}/voucher`,
        headers: { authorization: `Bearer ${picToken}` },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(body.data).toBeDefined();
      expect(body.data.voucherNumber).toBe(voucherNumber);
      expect(body.data.authorizationBoundaryText).toContain('Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin');
      expect(body.data.invoiceRequest).toBeDefined();
      expect(body.data.invoiceRequest.vendorName).toBe('PT Mitra Sukses Mandiri');
      expect(body.data.invoiceRequest.paymentDetails.accountNumber).toBe('8800112233');
      expect(body.data.invoiceRequest.lineItems.length).toBe(1);
    });

    it('harus menolak akses jika pengguna dari tenant klien lain mencoba mengakses voucher (403 Forbidden) [SR-003]', async () => {
      const { requestId } = await createApprovedInvoiceWithVoucher();

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${requestId}/voucher`,
        headers: { authorization: `Bearer ${otherPicToken}` },
      });

      expect(res.statusCode).toBe(403);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('TENANT_FORBIDDEN');
    });

    it('harus mengembalikan 404 jika voucher belum diterbitkan untuk request ID terkait', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/REQ-NONEXISTENT-99999/voucher`,
        headers: { authorization: `Bearer ${reviewerToken}` },
      });

      expect(res.statusCode).toBe(404);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('VOUCHER_NOT_FOUND');
    });
  });

  describe('2. GET /api/v1/invoices/:requestId/voucher/download (Stream Unduh & Mutasi SENT_TO_CLIENT)', () => {
    it('harus mengalirkan stream berkas PDF dengan header Content-Disposition attachment yang tepat [PR-023, PF-018]', async () => {
      const { requestId, voucherNumber } = await createApprovedInvoiceWithVoucher();

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${requestId}/voucher/download`,
        headers: { authorization: `Bearer ${reviewerToken}` },
      });

      expect(res.statusCode).toBe(200);
      expect(res.headers['content-type']).toBe('application/pdf');
      const expectedFileName = `${voucherNumber.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
      expect(res.headers['content-disposition']).toBe(`attachment; filename="${expectedFileName}"`);
      expect(res.rawPayload.length).toBeGreaterThan(100);

      // Pastikan status invoice TIDAK berubah ke SENT_TO_CLIENT jika reviewer yang mengunduh
      const invoiceAfter = await app.prisma.invoiceRequest.findUniqueOrThrow({
        where: { requestId },
      });
      expect(invoiceAfter.status).toBe(InvoiceStatus.AMIGA_REVIEWED);
    });

    it('harus mengubah status invoice menjadi SENT_TO_CLIENT dan mencatat audit log saat diunduh oleh PIC Klien [BR-011, PR-022, UAT-08]', async () => {
      const { requestId, voucherNumber, invoiceId } = await createApprovedInvoiceWithVoucher();

      // Verifikasi status awal sebelum diunduh PIC
      const invoiceBefore = await app.prisma.invoiceRequest.findUniqueOrThrow({
        where: { requestId },
      });
      expect(invoiceBefore.status).toBe(InvoiceStatus.AMIGA_REVIEWED);

      // PIC Klien mengunduh voucher PDF
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${requestId}/voucher/download`,
        headers: { authorization: `Bearer ${picToken}` },
      });

      expect(res.statusCode).toBe(200);
      expect(res.headers['content-type']).toBe('application/pdf');
      expect(res.rawPayload.length).toBeGreaterThan(100);

      // Verifikasi mutasi status invoice di database menjadi SENT_TO_CLIENT
      const invoiceAfter = await app.prisma.invoiceRequest.findUniqueOrThrow({
        where: { requestId },
      });
      expect(invoiceAfter.status).toBe(InvoiceStatus.SENT_TO_CLIENT);

      // Verifikasi pencatatan audit log VOUCHER_DOWNLOADED
      const auditEntry = await app.prisma.auditLog.findFirst({
        where: {
          requestId: invoiceId,
          actionType: 'VOUCHER_DOWNLOADED',
        },
      });

      expect(auditEntry).toBeDefined();
      expect(auditEntry!.previousStatus).toBe(InvoiceStatus.AMIGA_REVIEWED);
      expect(auditEntry!.newStatus).toBe(InvoiceStatus.SENT_TO_CLIENT);
      expect(auditEntry!.actorRole).toBe(UserRole.PIC_KLIEN);
      expect((auditEntry!.changeDiff as { voucherNumber?: string })?.voucherNumber).toBe(voucherNumber);
    });

    it('harus menolak pengunduhan jika pengguna tidak memiliki izin tenant (403 Forbidden)', async () => {
      const { requestId } = await createApprovedInvoiceWithVoucher();

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${requestId}/voucher/download`,
        headers: { authorization: `Bearer ${otherPicToken}` },
      });

      expect(res.statusCode).toBe(403);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('TENANT_FORBIDDEN');
    });
  });
});
