import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { FastifyInstance } from 'fastify';
import { InvoiceStatus, UserRole } from '@prisma/client';
import { buildApp } from '../../app.js';

describe('T-012 & T-015: Fastify Review Routes & Financial Math Tests', () => {
  let app: FastifyInstance;
  let reviewer1Token: string;
  let reviewer2Token: string;
  let picToken: string;
  let reviewer1UserId: string;
  let reviewer2UserId: string;
  let picUserId: string;
  let clientMainId: string;
  const testInvoiceIds: string[] = [];

  beforeAll(async () => {
    app = buildApp();
    await app.ready();

    // 1. Login reviewer 1
    const resRev1 = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'reviewer1@amiga.co.id', password: 'password123!' },
    });
    const rev1Data = JSON.parse(resRev1.body).data;
    reviewer1Token = rev1Data.accessToken;
    reviewer1UserId = rev1Data.user.id;

    // 2. Login reviewer 2
    const resRev2 = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'reviewer2@amiga.co.id', password: 'password123!' },
    });
    const rev2Data = JSON.parse(resRev2.body).data;
    reviewer2Token = rev2Data.accessToken;
    reviewer2UserId = rev2Data.user.id;

    // 3. Login PIC Klien
    const resPic = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'pic_client@amiga.co.id', password: 'password123!' },
    });
    const picData = JSON.parse(resPic.body).data;
    picToken = picData.accessToken;
    picUserId = picData.user.id;

    // 4. Client
    const client = await app.prisma.client.findUnique({ where: { clientCode: 'CLI-MAIN' } });
    clientMainId = client!.id;
  });

  afterAll(async () => {
    for (const id of testInvoiceIds) {
      await app.prisma.paymentVoucher.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.auditLog.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.reviewerAssignment.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.verificationIssue.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoicePaymentDetail.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoiceLineItem.deleteMany({ where: { requestId: id } }).catch(() => {});
      await app.prisma.invoiceRequest.delete({ where: { id } }).catch(() => {});
    }
  });

  describe('T-012: GET /api/v1/invoices/queue', () => {
    it('harus berhasil memuat antrean, ringkasan metrics status, dan monitoring beban reviewer dalam SLA <= 2s', async () => {
      const startTime = Date.now();
      const res = await app.inject({
        method: 'GET',
        url: '/api/v1/invoices/queue?limit=10',
        headers: { authorization: `Bearer ${reviewer1Token}` },
      });
      const durationMs = Date.now() - startTime;

      expect(res.statusCode).toBe(200);
      expect(durationMs).toBeLessThanOrEqual(2000); // SLA <= 2 detik

      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(Array.isArray(body.data.items)).toBe(true);
      expect(body.data.statusCounts).toBeDefined();
      expect(body.data.statusCounts.ALL).toBeGreaterThanOrEqual(0);
      expect(body.data.statusCounts.QUEUED).toBeDefined();
      expect(body.data.statusCounts.PROCESSING).toBeDefined();
      expect(body.data.statusCounts.READY_FOR_REVIEW).toBeDefined();
      expect(body.data.statusCounts.EXCEPTION).toBeDefined();
      expect(body.data.statusCounts.AMIGA_REVIEWED).toBeDefined();
      expect(body.data.statusCounts.SENT_TO_CLIENT).toBeDefined();

      // Verifikasi daftar reviewer workloads
      expect(Array.isArray(body.data.reviewerWorkloads)).toBe(true);
      expect(body.data.reviewerWorkloads.length).toBeGreaterThanOrEqual(2);
      expect(body.data.reviewerWorkloads[0].activeCount).toBeDefined();
      expect(body.data.reviewerWorkloads[0].isOverloaded).toBe(false);
    });

    it('harus mengisolasi antrean dokumen berdasarkan akses tenant bagi PIC Klien', async () => {
      const res = await app.inject({
        method: 'GET',
        url: '/api/v1/invoices/queue',
        headers: { authorization: `Bearer ${picToken}` },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      for (const item of body.data.items) {
        expect(item.clientId).toBe(clientMainId);
      }
    });
  });

  describe('T-014: GET /api/v1/invoices/:requestId/review-data', () => {
    it('harus mengembalikan data split-screen lengkap dan penanda canApprove', async () => {
      const reqId = `REQ-REV-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUserId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'split_screen_test.pdf',
          storageFilePath: 'invoices/test.pdf',
          filePageCount: 2,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Layar Terpadu',
          invoiceNumber: 'INV-SPLIT-001',
          subtotalAmount: 1000000,
          taxAmount: 110000,
          totalAmount: 1110000,
        },
      });
      testInvoiceIds.push(invoice.id);

      await app.prisma.invoiceLineItem.create({
        data: {
          requestId: invoice.id,
          itemIndex: 1,
          description: 'Layanan Pengadaan Cloud Server',
          quantity: 1,
          unitPrice: 1000000,
          subtotal: 1000000,
        },
      });

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${reqId}/review-data`,
        headers: { authorization: `Bearer ${reviewer1Token}` },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(body.data.invoice.requestId).toBe(reqId);
      expect(body.data.lineItems.length).toBe(1);
      expect(body.data.isUploader).toBe(false);
      expect(body.data.canApprove).toBe(true);
      expect(body.data.pdfStreamUrl).toBe(`/api/v1/invoices/${reqId}/file`);
    });
  });

  describe('T-015: PUT /api/v1/invoices/:requestId/line-items & Financial Math', () => {
    it('harus mengkalkulasi ulang subtotal dan grand total saat item barang/jasa disunting', async () => {
      const reqId = `REQ-MATH-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUserId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'math_test.pdf',
          storageFilePath: 'invoices/test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Matematika Finansial',
          subtotalAmount: 50000,
          taxAmount: 5000,
          totalAmount: 55000,
        },
      });
      testInvoiceIds.push(invoice.id);

      // Reviewer mengubah harga satuan item dari Rp 10.000 menjadi Rp 12.000 dengan kuantitas 5 -> subtotal Rp 60.000
      const res = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/${reqId}/line-items`,
        headers: {
          authorization: `Bearer ${reviewer1Token}`,
          'content-type': 'application/json',
        },
        payload: {
          items: [
            {
              description: 'Item Konsumsi Rapat A',
              quantity: 5,
              unitPrice: 12000,
              subtotal: 60000,
            },
          ],
        },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(body.data.subtotalAmount).toBe(60000);
      expect(body.data.totalAmount).toBe(65000); // 60.000 + 5.000 tax

      // Verifikasi di DB
      const updated = await app.prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
      expect(updated?.subtotalAmount?.toNumber()).toBe(60000);
      expect(updated?.totalAmount?.toNumber()).toBe(65000);

      // Verifikasi audit log mencatat LINE_ITEMS_UPDATED
      const audit = await app.prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'LINE_ITEMS_UPDATED' },
      });
      expect(audit).toBeDefined();
      expect(audit?.actorName).toContain('Finance Reviewer');
    });
  });

  describe('T-016: Penegakan Segregation of Duties (SoD) di Server', () => {
    it('harus menolak persetujuan jika uploader == reviewer dan otomatis me-reassign dokumen (403 SOD_VIOLATION)', async () => {
      // Simulasikan uploader adalah reviewer 1
      const reqId = `REQ-SOD-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: reviewer1UserId, // Uploader adalah Reviewer 1!
          currentReviewerId: reviewer1UserId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'sod_violation.pdf',
          storageFilePath: 'invoices/test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Pelanggar SoD',
        },
      });
      testInvoiceIds.push(invoice.id);

      // Reviewer 1 mencoba menyetujui dokumen yang dia unggah sendiri
      const res = await app.inject({
        method: 'POST',
        url: `/api/v1/invoices/${reqId}/approve`,
        headers: { authorization: `Bearer ${reviewer1Token}` },
      });

      expect(res.statusCode).toBe(403);
      const body = JSON.parse(res.body);
      expect(body.error.code).toBe('SOD_VIOLATION');

      // Verifikasi audit log mencatat SOD_VIOLATION_BLOCKED
      const audit = await app.prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'SOD_VIOLATION_BLOCKED' },
      });
      expect(audit).toBeDefined();

      // Verifikasi penugasan otomatis beralih ke Reviewer 2
      const updatedInv = await app.prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
      expect(updatedInv?.currentReviewerId).toBe(reviewer2UserId);
    });

    it('harus berhasil menyetujui dokumen jika reviewer berbeda dari uploader (200 AMIGA_REVIEWED)', async () => {
      const reqId = `REQ-APPROVE-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUserId, // Uploader adalah PIC!
          currentReviewerId: reviewer1UserId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'approve_clean.pdf',
          storageFilePath: 'invoices/test.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Legal Bersih',
          subtotalAmount: 100000,
          totalAmount: 111000,
        },
      });
      testInvoiceIds.push(invoice.id);

      // Reviewer 1 menyetujui dokumen
      const res = await app.inject({
        method: 'POST',
        url: `/api/v1/invoices/${reqId}/approve`,
        headers: { authorization: `Bearer ${reviewer1Token}` },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(body.data.status).toBe('AMIGA_REVIEWED');

      // Verifikasi database status menjadi AMIGA_REVIEWED
      const updated = await app.prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
      expect(updated?.status).toBe(InvoiceStatus.AMIGA_REVIEWED);
    });
  });
});
