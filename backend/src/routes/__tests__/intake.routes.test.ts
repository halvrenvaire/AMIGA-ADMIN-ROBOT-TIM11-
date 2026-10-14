import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { FastifyInstance } from 'fastify';
import { InvoiceStatus } from '@prisma/client';
import { buildApp } from '../../app.js';

// Minimal valid 1-page PDF
const sampleValid1PagePdf = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF`
);

// 6-page PDF helper
function generateMultiPagePdf(pageCount: number): Buffer {
  let kids = '';
  let pageObjects = '';
  let objIndex = 3;

  for (let i = 1; i <= pageCount; i++) {
    kids += `${objIndex} 0 R `;
    pageObjects += `${objIndex} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n`;
    objIndex++;
  }

  const content = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [${kids.trim()}] /Count ${pageCount} >>
endobj
${pageObjects}
trailer
<< /Size ${objIndex} /Root 1 0 R >>
startxref
500
%%EOF`;

  return Buffer.from(content);
}

function buildMultipartPayload(
  fields: Record<string, string>,
  fileBuffer?: Buffer,
  fileName: string = 'sample.pdf'
): { body: Buffer; boundary: string } {
  const boundary = '----AmigaFormBoundary' + Math.random().toString(36).substring(2);
  const chunks: Buffer[] = [];

  for (const [key, value] of Object.entries(fields)) {
    chunks.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${key}"\r\n\r\n${value}\r\n`
      )
    );
  }

  if (fileBuffer) {
    chunks.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${fileName}"\r\nContent-Type: application/pdf\r\n\r\n`
      )
    );
    chunks.push(fileBuffer);
    chunks.push(Buffer.from('\r\n'));
  }

  chunks.push(Buffer.from(`--${boundary}--\r\n`));

  return {
    body: Buffer.concat(chunks),
    boundary,
  };
}

describe('T-006: Fastify Intake Route & Queue Integration Tests', () => {
  let app: FastifyInstance;
  let picToken: string;
  let reviewerToken: string;
  let clientMainId: string;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();

    // Login sebagai PIC Klien
    const picLogin = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: {
        email: 'pic_client@amiga.co.id',
        password: 'password123!',
      },
    });
    const picBody = JSON.parse(picLogin.body);
    picToken = picBody.data.accessToken;
    clientMainId = picBody.data.user.assignedClientIds[0];

    // Login sebagai Reviewer
    const revLogin = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: {
        email: 'reviewer1@amiga.co.id',
        password: 'password123!',
      },
    });
    reviewerToken = JSON.parse(revLogin.body).data.accessToken;
  });

  afterAll(async () => {
    await app.close();
  });

  describe('POST /api/v1/invoices/upload', () => {
    it('harus berhasil mengunggah PDF valid, menerbitkan Request ID, dan mengembalikan status QUEUED (201)', async () => {
      const { body, boundary } = buildMultipartPayload(
        {
          clientId: clientMainId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
        },
        sampleValid1PagePdf,
        'invoice_pt_main_001.pdf'
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect(response.statusCode).toBe(201);
      const resBody = JSON.parse(response.body);
      expect(resBody.success).toBe(true);
      expect(resBody.data.status).toBe('QUEUED');
      expect(resBody.data.requestId).toMatch(/^REQ-\d{8}-[A-F0-9]{6}$/);
      expect(resBody.data.filePageCount).toBe(1);

      // Verifikasi record di database
      const dbInvoice = await app.prisma.invoiceRequest.findUnique({
        where: { id: resBody.data.id },
      });
      expect(dbInvoice).toBeDefined();
      expect(dbInvoice?.status).toBe('QUEUED');

      // Verifikasi audit log tercatat
      const auditLog = await app.prisma.auditLog.findFirst({
        where: { requestId: resBody.data.id, actionType: 'INVOICE_UPLOADED' },
      });
      expect(auditLog).toBeDefined();
      expect(auditLog?.actorRole).toBe('PIC_KLIEN');
    });

    it('harus menolak unggahan tanpa token otentikasi (401)', async () => {
      const { body, boundary } = buildMultipartPayload(
        { clientId: clientMainId },
        sampleValid1PagePdf
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect(response.statusCode).toBe(401);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('AUTH_UNAUTHORIZED');
    });

    it('harus menolak Finance Reviewer yang mencoba mengunggah invoice (403 FORBIDDEN_ROLE)', async () => {
      const { body, boundary } = buildMultipartPayload(
        { clientId: clientMainId },
        sampleValid1PagePdf
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          authorization: `Bearer ${reviewerToken}`,
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect(response.statusCode).toBe(403);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('FORBIDDEN_ROLE');
    });

    it('harus menolak unggahan untuk klien yang tidak diizinkan bagi PIC (403 TENANT_FORBIDDEN)', async () => {
      const foreignClientId = '00000000-0000-0000-0000-000000000999';
      const { body, boundary } = buildMultipartPayload(
        { clientId: foreignClientId },
        sampleValid1PagePdf
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect([403, 404]).toContain(response.statusCode);
      const resBody = JSON.parse(response.body);
      expect(['TENANT_FORBIDDEN', 'CLIENT_NOT_FOUND']).toContain(resBody.error.code);
    });

    it('harus menolak jika file PDF melebihi 5 halaman (400 PAGE_LIMIT_EXCEEDED)', async () => {
      const sixPagesPdf = generateMultiPagePdf(6);
      const { body, boundary } = buildMultipartPayload(
        { clientId: clientMainId },
        sixPagesPdf
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect(response.statusCode).toBe(400);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('PAGE_LIMIT_EXCEEDED');
    });

    it('harus menolak jika berkas bukan PDF valid (400 INVALID_FILE_TYPE)', async () => {
      const fakeTextFile = Buffer.from('Ini bukan file PDF melainkan teks biasa');
      const { body, boundary } = buildMultipartPayload(
        { clientId: clientMainId },
        fakeTextFile,
        'bukan_pdf.pdf'
      );

      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/invoices/upload',
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': `multipart/form-data; boundary=${boundary}`,
        },
        payload: body,
      });

      expect(response.statusCode).toBe(400);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('INVALID_FILE_TYPE');
    });
  });

  describe('T-011: PUT /api/v1/invoices/:requestId/correct', () => {
    let testUploaderId: string;
    let foreignClientObjId: string;
    const testInvoiceIds: string[] = [];

    beforeAll(async () => {
      const uploader = await app.prisma.user.findUnique({
        where: { email: 'pic_client@amiga.co.id' },
      });
      testUploaderId = uploader!.id;

      const foreignClient = await app.prisma.client.findUnique({
        where: { clientCode: 'CLI-002' },
      });
      foreignClientObjId = foreignClient!.id;
    });

    afterAll(async () => {
      for (const id of testInvoiceIds) {
        await app.prisma.auditLog.deleteMany({ where: { requestId: id } }).catch(() => {});
        await app.prisma.invoicePaymentDetail.deleteMany({ where: { requestId: id } }).catch(() => {});
        await app.prisma.invoiceLineItem.deleteMany({ where: { requestId: id } }).catch(() => {});
        await app.prisma.invoiceRequest.delete({ where: { id } }).catch(() => {});
      }
    });

    it('harus berhasil mengoreksi invoice EXCEPTION, mempertahankan Request ID, dan mengubah status ke PROCESSING (200)', async () => {
      const originalReqId = `REQ-CORRECT-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: originalReqId,
          clientId: clientMainId,
          uploaderId: testUploaderId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'exception_invoice.pdf',
          storageFilePath: 'invoices/exception_invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.EXCEPTION,
          vendorName: 'PT Mitra Sukses',
        },
      });
      testInvoiceIds.push(invoice.id);

      const response = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/${originalReqId}/correct`,
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': 'application/json',
        },
        payload: {
          paymentDetails: {
            bankName: 'Bank Central Asia (BCA)',
            accountNumber: '8820192831',
            accountHolderName: 'PT Mitra Sukses',
          },
          comments: 'Melengkapi nomor rekening bank vendor yang kurang',
        },
      });

      expect(response.statusCode).toBe(200);
      const resBody = JSON.parse(response.body);
      expect(resBody.success).toBe(true);
      expect(resBody.data.requestId).toBe(originalReqId); // REQUEST ID IDENTIK
      expect(resBody.data.status).toBe('PROCESSING');

      // Verifikasi database: paymentDetails terupdate dan berflag isManuallyEdited
      const pd = await app.prisma.invoicePaymentDetail.findUnique({
        where: { requestId: invoice.id },
      });
      expect(pd?.accountNumber).toBe('8820192831');
      expect(pd?.bankName).toBe('Bank Central Asia (BCA)');
      expect(pd?.isManuallyEdited).toBe(true);

      // Verifikasi status invoice di database menjadi PROCESSING
      const updatedInvoice = await app.prisma.invoiceRequest.findUnique({
        where: { id: invoice.id },
      });
      expect(updatedInvoice?.status).toBe(InvoiceStatus.PROCESSING);

      // Verifikasi Audit Log immutable mencatat INVOICE_CORRECTED
      const auditLog = await app.prisma.auditLog.findFirst({
        where: { requestId: invoice.id, actionType: 'INVOICE_CORRECTED' },
      });
      expect(auditLog).toBeDefined();
      expect(auditLog?.previousStatus).toBe('EXCEPTION');
      expect(auditLog?.newStatus).toBe('PROCESSING');
      expect(auditLog?.actorName).toContain('PIC Klien');
    });

    it('harus menolak koreksi jika status dokumen bukan EXCEPTION (409 NOT_AN_EXCEPTION)', async () => {
      const originalReqId = `REQ-NON-EXC-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: originalReqId,
          clientId: clientMainId,
          uploaderId: testUploaderId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'ready_invoice.pdf',
          storageFilePath: 'invoices/ready_invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
        },
      });
      testInvoiceIds.push(invoice.id);

      const response = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/${originalReqId}/correct`,
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': 'application/json',
        },
        payload: {
          comments: 'Coba koreksi invoice bukan EXCEPTION',
        },
      });

      expect(response.statusCode).toBe(409);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('NOT_AN_EXCEPTION');
    });

    it('harus menolak koreksi untuk klien yang tidak diizinkan bagi PIC (403 TENANT_FORBIDDEN)', async () => {
      const foreignReqId = `REQ-FOREIGN-${Date.now()}`;
      const invoice = await app.prisma.invoiceRequest.create({
        data: {
          requestId: foreignReqId,
          clientId: foreignClientObjId,
          uploaderId: testUploaderId,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date(),
          originalFileName: 'foreign_exception.pdf',
          storageFilePath: 'invoices/foreign.pdf',
          filePageCount: 1,
          status: InvoiceStatus.EXCEPTION,
        },
      });
      testInvoiceIds.push(invoice.id);

      const response = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/${foreignReqId}/correct`,
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': 'application/json',
        },
        payload: {
          comments: 'Koreksi lintas organisasi klien',
        },
      });

      expect(response.statusCode).toBe(403);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('TENANT_FORBIDDEN');
    });

    it('harus menolak koreksi jika role adalah Finance Reviewer (403 FORBIDDEN_ROLE)', async () => {
      const response = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/REQ-ANY/correct`,
        headers: {
          authorization: `Bearer ${reviewerToken}`,
          'content-type': 'application/json',
        },
        payload: {},
      });

      expect(response.statusCode).toBe(403);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('FORBIDDEN_ROLE');
    });

    it('harus mengembalikan 404 jika invoice target tidak ditemukan', async () => {
      const response = await app.inject({
        method: 'PUT',
        url: `/api/v1/invoices/REQ-NOT-FOUND-9999/correct`,
        headers: {
          authorization: `Bearer ${picToken}`,
          'content-type': 'application/json',
        },
        payload: {},
      });

      expect(response.statusCode).toBe(404);
      const resBody = JSON.parse(response.body);
      expect(resBody.error.code).toBe('INVOICE_NOT_FOUND');
    });
  });
});
