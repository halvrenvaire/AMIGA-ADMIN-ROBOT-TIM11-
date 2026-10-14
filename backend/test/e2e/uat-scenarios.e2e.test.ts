import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import dotenv from 'dotenv';

dotenv.config();
if (process.env.DATABASE_URL?.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, 'postgresql://');
}

import { FastifyInstance } from 'fastify';
import { InvoiceStatus, UserRole } from '@prisma/client';
import bcrypt from 'bcryptjs';
import { buildApp } from '../../src/app.js';
import { normalizeText } from '../../src/workers/ai-extraction.worker.js';

/**
 * Helper untuk menyusun berkas digital PDF 1-halaman valid secara in-memory
 * yang memuat teks invoice dan dikenali secara sempurna oleh parser PDF digital (pdf-parse).
 */
function generateInvoicePdf(lines: string[]): Buffer {
  const streamLines = lines
    .map((l, i) => `${i === 0 ? '72 712 Td' : '0 -20 Td'}\n(${l}) Tj`)
    .join('\n');
  const stream = `BT\n/F1 12 Tf\n${streamLines}\nET\n`;
  const streamLen = Buffer.byteLength(stream);

  const header = `%PDF-1.4\n`;
  const obj1 = `1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n`;
  const obj2 = `2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n`;
  const obj3 = `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n`;
  const obj4 = `4 0 obj\n<< /Length ${streamLen} >>\nstream\n${stream}endstream\nendobj\n`;

  const off1 = Buffer.byteLength(header);
  const off2 = off1 + Buffer.byteLength(obj1);
  const off3 = off2 + Buffer.byteLength(obj2);
  const off4 = off3 + Buffer.byteLength(obj3);
  const xrefOff = off4 + Buffer.byteLength(obj4);

  const pad = (n: number) => n.toString().padStart(10, '0');

  const xref = `xref\n0 5\n0000000000 65535 f \n${pad(off1)} 00000 n \n${pad(off2)} 00000 n \n${pad(off3)} 00000 n \n${pad(off4)} 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n${xrefOff}\n%%EOF`;

  return Buffer.from(`${header}${obj1}${obj2}${obj3}${obj4}${xref}`);
}

describe('T-022: Suite Pengujian Otomasi E2E & Validasi 8 Skenario UAT Resmi', () => {
  let app: FastifyInstance;
  let reviewer1Token: string;
  let reviewer1Id: string;
  let reviewer2Token: string;
  let reviewer2Id: string;
  let picClientToken: string;
  let picClientId: string;
  let clientMainId: string;
  const createdInvoiceIds: string[] = [];

  beforeAll(async () => {
    app = buildApp();
    await app.ready();

    // 1. Ambil data klien CLI-MAIN
    const clientMain = await app.prisma.client.findUniqueOrThrow({
      where: { clientCode: 'CLI-MAIN' },
    });
    clientMainId = clientMain.id;

    // 2. Login Reviewer 1 (Finance Reviewer)
    const resRev1 = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'reviewer1@amiga.co.id', password: 'password123!' },
    });
    const rev1Data = JSON.parse(resRev1.body).data;
    reviewer1Token = rev1Data.accessToken;
    reviewer1Id = rev1Data.user.id;

    // 3. Login Reviewer 2 (Finance Reviewer - SoD Alternate)
    const resRev2 = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'reviewer2@amiga.co.id', password: 'password123!' },
    });
    const rev2Data = JSON.parse(resRev2.body).data;
    reviewer2Token = rev2Data.accessToken;
    reviewer2Id = rev2Data.user.id;

    // 4. Login PIC Klien
    const resPic = await app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { email: 'pic_client@amiga.co.id', password: 'password123!' },
    });
    const picData = JSON.parse(resPic.body).data;
    picClientToken = picData.accessToken;
    picClientId = picData.user.id;
  });

  afterAll(async () => {
    // Cleanup seluruh data invoice, voucher, audit logs dari database pengujian
    for (const invId of createdInvoiceIds) {
      await app.prisma.paymentVoucher.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.verificationIssue.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.invoiceLineItem.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.invoicePaymentDetail.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.reviewerAssignment.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.auditLog.deleteMany({ where: { requestId: invId } }).catch(() => {});
      await app.prisma.invoiceRequest.delete({ where: { id: invId } }).catch(() => {});
    }
    await app.close();
  });

  // =========================================================================
  // UAT-01: Happy Path End-to-End
  // PDF upload -> extract -> review -> approve -> voucher terbit [PF-001..PF-017]
  // =========================================================================
  it('UAT-01: Happy Path — Upload PDF digital, Ekstraksi AI, Persetujuan Reviewer, dan Penerbitan Voucher Resmi', async () => {
    const uat01InvNo = `INV/2026/04/UAT01-${Date.now()}`;
    const pdfBuffer = generateInvoicePdf([
      'Vendor: PT Nusantara Teknologi Mandiri',
      `Invoice No: ${uat01InvNo}`,
      'Tanggal: 2026-04-15',
      'Item 1: Jasa Konsultasi TI 1 x Rp 15.000.000 = Rp 15.000.000',
      'Nama Bank: Bank Central Asia BCA',
      'No. Rekening: 8820192831',
      'Atas Nama: PT Nusantara Teknologi Mandiri',
    ]);

    // 1. Upload via PIC Klien
    const boundary = '----WebKitFormBoundaryUAT01';
    const body = Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="invoice_uat01.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
      pdfBuffer,
      Buffer.from(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="clientId"\r\n\r\n${clientMainId}\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="requestType"\r\n\r\nREGULAR\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionChannel"\r\n\r\nWEB_PORTAL\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionDate"\r\n\r\n2026-04-15T00:00:00.000Z\r\n`),
      Buffer.from(`--${boundary}--\r\n`),
    ]);

    const uploadRes = await app.inject({
      method: 'POST',
      url: '/api/v1/invoices/upload',
      headers: {
        authorization: `Bearer ${picClientToken}`,
        'content-type': `multipart/form-data; boundary=${boundary}`,
      },
      payload: body,
    });

    expect(uploadRes.statusCode).toBe(201);
    const uploadData = JSON.parse(uploadRes.body).data;
    expect(uploadData.requestId).toMatch(/^REQ-\d{8}-[A-F0-9]{5,6}$/i);
    expect(uploadData.status).toBe(InvoiceStatus.QUEUED);
    createdInvoiceIds.push(uploadData.id);

    // 2. Jalankan background worker ekstraksi AI
    const invoice = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: uploadData.id },
    });
    await app.extractionWorker.processExtractionJob({
      invoiceId: invoice.id,
      requestId: invoice.requestId,
      storageFilePath: invoice.storageFilePath,
    });

    // 3. Verifikasi status bertransisi ke READY_FOR_REVIEW
    const extractedInvoice = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: uploadData.id },
      include: { lineItems: true, paymentDetails: true, issues: true },
    });
    expect(extractedInvoice.status).toBe(InvoiceStatus.READY_FOR_REVIEW);
    expect(extractedInvoice.issues.length).toBe(0);
    expect(extractedInvoice.paymentDetails?.accountNumber).toBe('8820192831');

    // 4. Finance Reviewer memeriksa data via GET /review-data
    const reviewDataRes = await app.inject({
      method: 'GET',
      url: `/api/v1/invoices/${extractedInvoice.requestId}/review-data`,
      headers: { authorization: `Bearer ${reviewer1Token}` },
    });
    expect(reviewDataRes.statusCode).toBe(200);
    const reviewData = JSON.parse(reviewDataRes.body).data;
    expect(reviewData.canApprove).toBe(true);

    // 5. Reviewer menyetujui invoice (Approve)
    const approveRes = await app.inject({
      method: 'POST',
      url: `/api/v1/invoices/${extractedInvoice.requestId}/approve`,
      headers: { authorization: `Bearer ${reviewer1Token}` },
    });
    expect(approveRes.statusCode).toBe(200);
    const approveData = JSON.parse(approveRes.body).data;
    expect(approveData.status).toBe(InvoiceStatus.AMIGA_REVIEWED);

    // 6. Verifikasi voucher pembayaran resmi terbit di database
    const voucher = await app.prisma.paymentVoucher.findUnique({
      where: { requestId: extractedInvoice.id },
    });
    expect(voucher).not.toBeNull();
    expect(voucher?.voucherNumber).toMatch(/^VCH\/\d{6}\/CLI-MAIN\/\d{5}$/);
    expect(voucher?.authorizationBoundaryText).toContain('Otorisasi pembayaran akhir');
  });

  // =========================================================================
  // UAT-02: Missing Bank Evidence (MISSING_EVIDENCE)
  // Invoice tanpa nomor rekening / bank tujuan transfer ditandai EXCEPTION [BR-008]
  // =========================================================================
  it('UAT-02: Kelengkapan Rekening — Deteksi dan Flag EXCEPTION (MISSING_EVIDENCE) jika rekening tidak terdeteksi', async () => {
    // PDF tanpa info nomor rekening dan bank
    const pdfBuffer = generateInvoicePdf([
      'Vendor: PT Global Mitra Inovasi',
      'Invoice No: INV/2026/04/UAT02',
      'Tanggal: 2026-04-15',
      'Item 1: Pengadaan Perangkat Jaringan 1 x Rp 10.000.000 = Rp 10.000.000',
    ]);

    const boundary = '----WebKitFormBoundaryUAT02';
    const body = Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="invoice_uat02.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
      pdfBuffer,
      Buffer.from(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="clientId"\r\n\r\n${clientMainId}\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="requestType"\r\n\r\nREGULAR\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionChannel"\r\n\r\nWEB_PORTAL\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionDate"\r\n\r\n2026-04-15T00:00:00.000Z\r\n`),
      Buffer.from(`--${boundary}--\r\n`),
    ]);

    const uploadRes = await app.inject({
      method: 'POST',
      url: '/api/v1/invoices/upload',
      headers: {
        authorization: `Bearer ${picClientToken}`,
        'content-type': `multipart/form-data; boundary=${boundary}`,
      },
      payload: body,
    });
    const invData = JSON.parse(uploadRes.body).data;
    createdInvoiceIds.push(invData.id);

    // Jalankan ekstraksi AI
    const invoice = await app.prisma.invoiceRequest.findUniqueOrThrow({ where: { id: invData.id } });
    await app.extractionWorker.processExtractionJob({
      invoiceId: invoice.id,
      requestId: invoice.requestId,
      storageFilePath: invoice.storageFilePath,
    });

    // Verifikasi status otomatis mutasi ke EXCEPTION dan memuat kendala MISSING_EVIDENCE
    const checked = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: invData.id },
      include: { issues: true },
    });
    expect(checked.status).toBe(InvoiceStatus.EXCEPTION);
    const missingIssue = checked.issues.find((i) => i.issueCode === 'MISSING_EVIDENCE');
    expect(missingIssue).toBeDefined();
    expect(missingIssue?.issueCategory).toBe('COMPLETENESS');
  });

  // =========================================================================
  // UAT-03: Duplicate Invoice (POSSIBLE_DUPLICATE)
  // Deteksi nomor invoice & vendor identik pada klien yang sama [BR-008, SR-013]
  // =========================================================================
  it('UAT-03: Pencegahan Pembayaran Ganda — Deteksi dan Flag EXCEPTION (POSSIBLE_DUPLICATE)', async () => {
    // 1. Buat invoice pertama yang sudah ada di database untuk vendor PT Alpha Grafika
    const inv1 = await app.prisma.invoiceRequest.create({
      data: {
        requestId: `REQ-20260415-${Date.now().toString().slice(-5)}`,
        clientId: clientMainId,
        uploaderId: picClientId,
        requestType: 'REGULAR',
        submissionChannel: 'WEB_PORTAL',
        status: InvoiceStatus.READY_FOR_REVIEW,
        originalFileName: 'inv_original.pdf',
        storageFilePath: 'storage/inv_original.pdf',
        filePageCount: 1,
        vendorName: 'PT Alpha Grafika',
        vendorNameNormalized: normalizeText('PT Alpha Grafika'),
        invoiceNumber: 'INV/2026/04/DUPL',
        invoiceNumberNormalized: normalizeText('INV/2026/04/DUPL'),
        totalAmount: 5000000,
        submissionDate: new Date(),
      },
    });
    createdInvoiceIds.push(inv1.id);

    // 2. Upload invoice kedua dengan vendor dan nomor invoice sama (variasi huruf besar/tanda baca)
    const pdfBuffer = generateInvoicePdf([
      'Vendor: pt alpha grafika',
      'Invoice No: INV-2026-04-DUPL',
      'Tanggal: 2026-04-15',
      'Item 1: Cetak Banner 1 x Rp 5.000.000 = Rp 5.000.000',
      'Nama Bank: BCA',
      'No. Rekening: 9918237123',
    ]);

    const boundary = '----WebKitFormBoundaryUAT03';
    const body = Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="invoice_uat03_dupl.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
      pdfBuffer,
      Buffer.from(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="clientId"\r\n\r\n${clientMainId}\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="requestType"\r\n\r\nREGULAR\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionChannel"\r\n\r\nWEB_PORTAL\r\n`),
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="submissionDate"\r\n\r\n2026-04-15T00:00:00.000Z\r\n`),
      Buffer.from(`--${boundary}--\r\n`),
    ]);

    const uploadRes = await app.inject({
      method: 'POST',
      url: '/api/v1/invoices/upload',
      headers: {
        authorization: `Bearer ${picClientToken}`,
        'content-type': `multipart/form-data; boundary=${boundary}`,
      },
      payload: body,
    });
    const inv2Data = JSON.parse(uploadRes.body).data;
    createdInvoiceIds.push(inv2Data.id);

    const invoice2 = await app.prisma.invoiceRequest.findUniqueOrThrow({ where: { id: inv2Data.id } });
    await app.extractionWorker.processExtractionJob({
      invoiceId: invoice2.id,
      requestId: invoice2.requestId,
      storageFilePath: invoice2.storageFilePath,
    });

    // Verifikasi invoice kedua tertandai POSSIBLE_DUPLICATE
    const checked = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: inv2Data.id },
      include: { issues: true },
    });
    expect(checked.status).toBe(InvoiceStatus.EXCEPTION);
    const duplIssue = checked.issues.find((i) => i.issueCode === 'POSSIBLE_DUPLICATE');
    expect(duplIssue).toBeDefined();
    expect(duplIssue?.issueCategory).toBe('INTEGRITY');
  });

  // =========================================================================
  // UAT-04: Calculation Discrepancy (CALCULATION_DISCREPANCY)
  // Selisih hitungan subtotal + pajak vs total ditandai EXCEPTION [BR-008]
  // =========================================================================
  it('UAT-04: Discrepansi Perhitungan Angka — Deteksi dan Flag EXCEPTION (CALCULATION_DISCREPANCY)', async () => {
    // Buat invoice dengan selisih nominal: Subtotal 10.000.000 + Tax 1.100.000 != Total 20.000.000
    const inv = await app.prisma.invoiceRequest.create({
      data: {
        requestId: `REQ-20260415-${Date.now().toString().slice(-5)}`,
        clientId: clientMainId,
        uploaderId: picClientId,
        requestType: 'REGULAR',
        submissionChannel: 'WEB_PORTAL',
        status: InvoiceStatus.PROCESSING,
        originalFileName: 'inv_calc.pdf',
        storageFilePath: 'storage/inv_calc.pdf',
        filePageCount: 1,
        vendorName: 'PT Matriks Logika',
        vendorNameNormalized: 'pt matriks logika',
        invoiceNumber: 'INV/2026/04/CALC',
        invoiceNumberNormalized: 'inv202604calc',
        subtotalAmount: 10000000,
        taxAmount: 1100000,
        totalAmount: 20000000, // Selisih disengaja (Rp 8.900.000)
        submissionDate: new Date(),
        lineItems: {
          create: [
            {
              itemIndex: 1,
              description: 'Item 1',
              quantity: 1,
              unitPrice: 10000000,
              subtotal: 10000000,
            },
          ],
        },
        paymentDetails: {
          create: {
            bankName: 'BCA',
            accountNumber: '8819283123',
            accountHolderName: 'PT Matriks Logika',
          },
        },
      },
    });
    createdInvoiceIds.push(inv.id);

    // Jalankan verifikasi sistem
    const verifResult = await app.extractionWorker.verificationService.verifyAndTransition(inv.id);
    expect(verifResult.newStatus).toBe(InvoiceStatus.EXCEPTION);

    const checked = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: inv.id },
      include: { issues: true },
    });
    expect(checked.status).toBe(InvoiceStatus.EXCEPTION);
    const calcIssue = checked.issues.find((i) => i.issueCode === 'CALCULATION_DISCREPANCY');
    expect(calcIssue).toBeDefined();
    expect(calcIssue?.issueCategory).toBe('ARITHMETIC');
  });

  // =========================================================================
  // UAT-05: Server-Side SoD Enforcement
  // Uploader dilarang approve dokumen sendiri (respon 403 Forbidden) [BR-002, SR-004]
  // =========================================================================
  it('UAT-05: Penegakan Server-Side SoD — Ditolak 403 Forbidden jika Uploader mencoba approve invoice sendiri', async () => {
    // Reviewer 1 bertindak sebagai pengunggah invoice
    const inv = await app.prisma.invoiceRequest.create({
      data: {
        requestId: `REQ-20260415-${Date.now().toString().slice(-5)}`,
        clientId: clientMainId,
        uploaderId: reviewer1Id, // Uploader adalah Reviewer 1
        currentReviewerId: reviewer1Id,
        requestType: 'REGULAR',
        submissionChannel: 'WEB_PORTAL',
        status: InvoiceStatus.READY_FOR_REVIEW,
        originalFileName: 'inv_sod.pdf',
        storageFilePath: 'storage/inv_sod.pdf',
        filePageCount: 1,
        vendorName: 'PT Self Approval Inc',
        vendorNameNormalized: 'pt self approval inc',
        invoiceNumber: 'INV/2026/04/SOD01',
        invoiceNumberNormalized: 'inv202604sod01',
        totalAmount: 10000000,
        submissionDate: new Date(),
        paymentDetails: {
          create: {
            bankName: 'BCA',
            accountNumber: '8819283123',
            accountHolderName: 'PT Self Approval Inc',
          },
        },
      },
    });
    createdInvoiceIds.push(inv.id);

    // Reviewer 1 mencoba menyetujui invoice yang diunggahnya sendiri
    const approveRes = await app.inject({
      method: 'POST',
      url: `/api/v1/invoices/${inv.requestId}/approve`,
      headers: { authorization: `Bearer ${reviewer1Token}` },
    });

    // Harus ditolak dengan status 403 Forbidden dan kode error SOD_VIOLATION
    expect(approveRes.statusCode).toBe(403);
    const errBody = JSON.parse(approveRes.body);
    expect(errBody.error.code).toBe('SOD_VIOLATION');

    // Verifikasi audit log mencatat pemblokiran SoD
    const auditLogs = await app.prisma.auditLog.findMany({
      where: { requestId: inv.id, actionType: 'SOD_VIOLATION_BLOCKED' },
    });
    expect(auditLogs.length).toBeGreaterThan(0);
    expect(auditLogs[0].actorId).toBe(reviewer1Id);
  });

  // =========================================================================
  // UAT-06: Auto-Reassignment Dokumen Pasca Pelanggaran SoD
  // Dokumen dialihkan otomatis ke reviewer alternatif yang aktif [BR-002, PR-018]
  // =========================================================================
  it('UAT-06: Auto-Reassignment — Dokumen dialihkan ke Reviewer alternatif setelah pelanggaran SoD', async () => {
    // Ambil invoice dari UAT-05 yang baru saja mengalami pelanggaran SoD
    const lastInvId = createdInvoiceIds[createdInvoiceIds.length - 1];
    const reassignedInvoice = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: lastInvId },
    });

    // Penugasan harus sudah dialihkan dari reviewer 1 ke reviewer 2
    expect(reassignedInvoice.currentReviewerId).not.toBe(reviewer1Id);
    expect(reassignedInvoice.currentReviewerId).toBe(reviewer2Id);

    // Sekarang Reviewer 2 (independen, bukan uploader) menyetujui invoice ini
    const approveRes = await app.inject({
      method: 'POST',
      url: `/api/v1/invoices/${reassignedInvoice.requestId}/approve`,
      headers: { authorization: `Bearer ${reviewer2Token}` },
    });

    // Approval oleh Reviewer 2 harus berhasil 200 OK
    expect(approveRes.statusCode).toBe(200);
    const approveData = JSON.parse(approveRes.body).data;
    expect(approveData.status).toBe(InvoiceStatus.AMIGA_REVIEWED);

    // Status di database terverifikasi AMIGA_REVIEWED
    const finalInvoice = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: lastInvId },
    });
    expect(finalInvoice.status).toBe(InvoiceStatus.AMIGA_REVIEWED);
  });

  // =========================================================================
  // UAT-07: Perbaikan Dokumen EXCEPTION oleh PIC dengan Request ID Sama
  // Melengkapi rekening bank, siklus verifikasi ulang berlanjut [BR-009, PR-014]
  // =========================================================================
  it('UAT-07: Perbaikan EXCEPTION — PIC melengkapi rekening, Request ID tetap identik, dan invoice siap direview', async () => {
    // 1. Buat invoice berstatus EXCEPTION karena data rekening belum ada
    const originalRequestId = `REQ-20260415-${Date.now().toString().slice(-5)}`;
    const excInv = await app.prisma.invoiceRequest.create({
      data: {
        requestId: originalRequestId,
        clientId: clientMainId,
        uploaderId: picClientId,
        requestType: 'REGULAR',
        submissionChannel: 'WEB_PORTAL',
        status: InvoiceStatus.EXCEPTION,
        originalFileName: 'inv_correc.pdf',
        storageFilePath: 'storage/inv_correc.pdf',
        filePageCount: 1,
        vendorName: 'PT Sukses Bersama',
        vendorNameNormalized: normalizeText('PT Sukses Bersama'),
        invoiceNumber: 'INV/2026/04/CORR',
        invoiceNumberNormalized: normalizeText('INV/2026/04/CORR'),
        subtotalAmount: 12000000,
        taxAmount: 0,
        totalAmount: 12000000,
        submissionDate: new Date(),
        lineItems: {
          create: [
            {
              itemIndex: 1,
              description: 'Jasa Pemeliharaan Sistem TI',
              quantity: 1,
              unitPrice: 12000000,
              subtotal: 12000000,
            },
          ],
        },
        issues: {
          create: {
            issueCode: 'MISSING_EVIDENCE',
            issueCategory: 'COMPLETENESS',
            messageId: 'Nomor rekening bank tujuan transfer tidak ditemukan.',
          },
        },
      },
    });
    createdInvoiceIds.push(excInv.id);

    // 2. PIC Klien mengirim koreksi data via PUT /correct
    const correctRes = await app.inject({
      method: 'PUT',
      url: `/api/v1/invoices/${originalRequestId}/correct`,
      headers: { authorization: `Bearer ${picClientToken}` },
      payload: {
        paymentDetails: {
          bankName: 'Bank Mandiri',
          accountNumber: '140001928312',
          accountHolderName: 'PT Sukses Bersama',
        },
        comments: 'Rekening vendor telah dilengkapi sesuai lampiran bukti transfer.',
      },
    });

    expect(correctRes.statusCode).toBe(200);
    const correctData = JSON.parse(correctRes.body).data;
    // Request ID MUST tetap sama persis (tidak menerbitkan ID baru)
    expect(correctData.requestId).toBe(originalRequestId);

    // 3. Jalankan verifikasi sistem ulang
    const verifRes = await app.extractionWorker.verificationService.verifyAndTransition(excInv.id);
    expect(verifRes.newStatus).toBe(InvoiceStatus.READY_FOR_REVIEW);

    // 4. Periksa rekening tersimpan dengan tanda isManuallyEdited = true
    const updatedInv = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: excInv.id },
      include: { paymentDetails: true },
    });
    expect(updatedInv.status).toBe(InvoiceStatus.READY_FOR_REVIEW);
    expect(updatedInv.paymentDetails?.bankName).toBe('Bank Mandiri');
    expect(updatedInv.paymentDetails?.accountNumber).toBe('140001928312');
    expect(updatedInv.paymentDetails?.isManuallyEdited).toBe(true);

    // 5. Reviewer 1 sekarang dapat menyetujuinya
    const approveRes = await app.inject({
      method: 'POST',
      url: `/api/v1/invoices/${originalRequestId}/approve`,
      headers: { authorization: `Bearer ${reviewer1Token}` },
    });
    expect(approveRes.statusCode).toBe(200);
    expect(JSON.parse(approveRes.body).data.status).toBe(InvoiceStatus.AMIGA_REVIEWED);
  });

  // =========================================================================
  // UAT-08: Unduh Voucher Resmi Memicu Mutasi ke SENT_TO_CLIENT
  // PIC mengunduh voucher PDF resmi dan status bermutasi otomatis [BR-011, PR-023]
  // =========================================================================
  it('UAT-08: Unduh Voucher Resmi — PIC mengunduh PDF voucher resmi dan status bermutasi menjadi SENT_TO_CLIENT', async () => {
    // Ambil invoice dari UAT-07 atau buat invoice AMIGA_REVIEWED dengan voucher aktif
    const lastInvId = createdInvoiceIds[createdInvoiceIds.length - 1];
    const invoiceApproved = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: lastInvId },
    });
    expect(invoiceApproved.status).toBe(InvoiceStatus.AMIGA_REVIEWED);

    // PIC Klien mengunduh voucher resmi via GET /voucher/download
    const downloadRes = await app.inject({
      method: 'GET',
      url: `/api/v1/invoices/${invoiceApproved.requestId}/voucher/download`,
      headers: { authorization: `Bearer ${picClientToken}` },
    });

    // 1. Verifikasi response header dan status
    expect(downloadRes.statusCode).toBe(200);
    expect(downloadRes.headers['content-type']).toBe('application/pdf');
    expect(downloadRes.headers['content-disposition']).toContain('attachment; filename=');

    // 2. Verifikasi konten binary PDF
    expect(downloadRes.rawPayload.subarray(0, 4).toString()).toBe('%PDF');

    // 3. Verifikasi status di database termutasi menjadi SENT_TO_CLIENT
    const finalInvoice = await app.prisma.invoiceRequest.findUniqueOrThrow({
      where: { id: lastInvId },
    });
    expect(finalInvoice.status).toBe(InvoiceStatus.SENT_TO_CLIENT);

    // 4. Verifikasi jejak audit mencatat aksi VOUCHER_DOWNLOADED
    const downloadLog = await app.prisma.auditLog.findFirst({
      where: { requestId: lastInvId, actionType: 'VOUCHER_DOWNLOADED' },
    });
    expect(downloadLog).not.toBeNull();
    expect(downloadLog?.actorRole).toBe('PIC_KLIEN');
    expect(downloadLog?.previousStatus).toBe(InvoiceStatus.AMIGA_REVIEWED);
    expect(downloadLog?.newStatus).toBe(InvoiceStatus.SENT_TO_CLIENT);
  });
});
