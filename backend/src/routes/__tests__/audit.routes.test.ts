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
import { AuditService, maskSensitiveAccountNumber, sanitizeChangeDiff } from '../../services/audit.service.js';

describe('T-020: Fastify Audit Routes & Immutable Audit Logger Tests', () => {
  let app: FastifyInstance;
  let reviewerToken: string;
  let picToken: string;
  let otherPicToken: string;
  let reviewerUserId: string;
  let picUserId: string;
  let clientMainId: string;
  let clientSecondId: string;
  let otherPicUserId: string;
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

    // 2. Login PIC Klien
    const resPic = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'pic_client@amiga.co.id', password: 'password123!' },
    });
    const picData = JSON.parse(resPic.body).data;
    picToken = picData.accessToken;
    picUserId = picData.user.id;

    // 3. Ambil data klien CLI-MAIN
    const clientMain = await app.prisma.client.findUniqueOrThrow({ where: { clientCode: 'CLI-MAIN' } });
    clientMainId = clientMain.id;

    // Ambil atau buat client kedua untuk isolasi tenant
    let clientSecond = await app.prisma.client.findFirst({
      where: { NOT: { id: clientMainId } },
    });
    if (!clientSecond) {
      clientSecond = await app.prisma.client.create({
        data: {
          clientCode: 'CLI-AUDIT-OTHER',
          clientName: 'PT Audit Other Client',
        },
      });
    }
    clientSecondId = clientSecond.id;

    // Buat PIC Klien untuk clientSecond
    const otherPicEmail = `audit_other_pic_${Date.now()}@other.co.id`;
    const passwordHash = await bcrypt.hash('password123!', 10);
    const otherPic = await app.prisma.user.create({
      data: {
        email: otherPicEmail,
        passwordHash,
        fullName: 'Audit Other PIC',
        role: UserRole.PIC_KLIEN,
        defaultClient: { connect: { id: clientSecondId } },
      },
    });
    otherPicUserId = otherPic.id;

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

    if (otherPicUserId) {
      await app.prisma.userClientAssignment.deleteMany({ where: { userId: otherPicUserId } }).catch(() => {});
      await app.prisma.user.delete({ where: { id: otherPicUserId } }).catch(() => {});
    }
    await app.prisma.client.deleteMany({ where: { clientCode: 'CLI-AUDIT-OTHER' } }).catch(() => {});
    await app.close();
  });

  describe('Unit Helper: PII Masking & Sanitasi', () => {
    it('harus memvalidasi fungsi maskSensitiveAccountNumber secara presisi [SR-016]', () => {
      expect(maskSensitiveAccountNumber('8800112233')).toBe('8800****33');
      expect(maskSensitiveAccountNumber('12345')).toBe('12****5');
      expect(maskSensitiveAccountNumber('1234')).toBe('****');
      expect(maskSensitiveAccountNumber(null)).toBeNull();
      expect(maskSensitiveAccountNumber(undefined)).toBeNull();
    });

    it('harus menyamarkan nomor rekening di dalam JSON diff secara rekursif [SR-016]', () => {
      const inputDiff = {
        vendorName: 'PT Sumber Berkah',
        bankDetails: {
          bankName: 'BCA',
          accountNumber: '8800112233',
        },
        items: [{ desc: 'Server', total: 10000 }],
      };

      const sanitized = sanitizeChangeDiff(inputDiff) as {
        vendorName: string;
        bankDetails: { bankName: string; accountNumber: string };
      };

      expect(sanitized.vendorName).toBe('PT Sumber Berkah');
      expect(sanitized.bankDetails.bankName).toBe('BCA');
      expect(sanitized.bankDetails.accountNumber).toBe('8800****33');
    });
  });

  describe('GET /api/v1/invoices/:requestId/audit-trail', () => {
    it('harus berhasil memuat kronologi jejak audit terurut ASC dengan serialisasi ID aman [BR-015, PR-025]', async () => {
      const reqId = `REQ-AUDIT-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUserId,
          status: InvoiceStatus.QUEUED,
          requestType: 'STANDARD_INVOICE',
          submissionChannel: 'PORTAL_UPLOAD',
          submissionDate: new Date('2026-10-10'),
          originalFileName: 'audit_test.pdf',
          storageFilePath: 'invoices/audit_test.pdf',
          filePageCount: 1,
          vendorName: 'PT Audit Solusi Mandiri',
          totalAmount: 10000000,
        },
      });
      testInvoiceIds.push(invoice.id);

      // Simpan 3 entri audit secara berurutan
      const auditService = new AuditService(app.prisma);

      await auditService.log({
        requestId: invoice.id,
        actorId: picUserId,
        actorName: 'PIC User',
        actorRole: UserRole.PIC_KLIEN,
        actionType: 'INVOICE_UPLOADED',
        previousStatus: null,
        newStatus: InvoiceStatus.QUEUED,
        changeDiff: { originalFileName: 'audit_test.pdf' },
        ipAddress: '127.0.0.1',
      });

      await auditService.log({
        requestId: invoice.id,
        actorId: null,
        actorName: 'AMIGA System Verification',
        actorRole: 'SYSTEM',
        actionType: 'SYSTEM_VERIFICATION_PASSED',
        previousStatus: InvoiceStatus.PROCESSING,
        newStatus: InvoiceStatus.READY_FOR_REVIEW,
        changeDiff: { checkAccount: true, duplicatePassed: true },
        ipAddress: '127.0.0.1',
      });

      await auditService.log({
        requestId: invoice.id,
        actorId: reviewerUserId,
        actorName: 'Reviewer Budi',
        actorRole: UserRole.FINANCE_REVIEWER,
        actionType: 'FIELD_VALUE_MODIFIED',
        previousStatus: InvoiceStatus.READY_FOR_REVIEW,
        newStatus: InvoiceStatus.READY_FOR_REVIEW,
        changeDiff: {
          field: 'accountNumber',
          accountNumber: '8800112233',
        },
        ipAddress: '127.0.0.1',
      });

      // Panggil endpoint audit trail
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${reqId}/audit-trail`,
        headers: { authorization: `Bearer ${reviewerToken}` },
      });

      expect(res.statusCode).toBe(200);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(true);
      expect(body.data.invoice).toBeDefined();
      expect(body.data.invoice.requestId).toBe(reqId);
      expect(Array.isArray(body.data.auditLogs)).toBe(true);
      expect(body.data.auditLogs.length).toBe(3);

      // Verifikasi urutan kronologis ASC
      const logs = body.data.auditLogs;
      expect(logs[0].actionType).toBe('INVOICE_UPLOADED');
      expect(logs[1].actionType).toBe('SYSTEM_VERIFICATION_PASSED');
      expect(logs[2].actionType).toBe('FIELD_VALUE_MODIFIED');

      // Verifikasi ID BigInt terserialisasi sebagai string
      expect(typeof logs[0].id).toBe('string');

      // Verifikasi masking PII rekening di changeDiff
      expect(logs[2].changeDiff.accountNumber).toBe('8800****33');
    });

    it('harus menolak akses jika pengguna tenant lain mencoba melihat jejak audit (403 TENANT_FORBIDDEN) [SR-003]', async () => {
      const reqId = `REQ-AUDIT-TENANT-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: reqId,
          clientId: clientMainId,
          uploaderId: picUserId,
          status: InvoiceStatus.QUEUED,
          requestType: 'STANDARD_INVOICE',
          submissionChannel: 'PORTAL_UPLOAD',
          submissionDate: new Date('2026-10-10'),
          originalFileName: 'audit_tenant.pdf',
          storageFilePath: 'invoices/audit_tenant.pdf',
          filePageCount: 1,
        },
      });
      testInvoiceIds.push(invoice.id);

      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/${reqId}/audit-trail`,
        headers: { authorization: `Bearer ${otherPicToken}` },
      });

      expect(res.statusCode).toBe(403);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('TENANT_FORBIDDEN');
    });

    it('harus mengembalikan 404 jika invoice tidak ditemukan', async () => {
      const res = await app.inject({
        method: 'GET',
        url: `/api/v1/invoices/REQ-NONEXISTENT-99999/audit-trail`,
        headers: { authorization: `Bearer ${reviewerToken}` },
      });

      expect(res.statusCode).toBe(404);
      const body = JSON.parse(res.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('INVOICE_NOT_FOUND');
    });
  });
});
