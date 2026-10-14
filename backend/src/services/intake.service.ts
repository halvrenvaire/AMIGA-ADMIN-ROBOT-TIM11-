import { PrismaClient, InvoiceStatus, Prisma } from '@prisma/client';
import { randomBytes } from 'crypto';
import { StorageService } from './storage.service.js';
import { IQueueService } from './queue.service.js';
import { JwtPayload } from '../types/auth.types.js';
import { checkTenantAccess } from '../plugins/rbac.plugin.js';
import { normalizeText } from '../workers/ai-extraction.worker.js';

export class IntakeError extends Error {
  constructor(
    public code: string,
    message: string,
    public statusCode: number = 400,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'IntakeError';
  }
}

export interface UploadInvoiceParams {
  user: JwtPayload;
  clientId: string;
  fileBuffer: Buffer;
  originalFileName: string;
  requestType?: string;
  submissionChannel?: string;
  submissionDate?: string;
  ipAddress?: string;
}

export interface UploadInvoiceResult {
  id: string;
  requestId: string;
  status: InvoiceStatus;
  filePageCount: number;
  originalFileName: string;
}

export interface CorrectInvoiceParams {
  user: JwtPayload;
  requestId: string;
  paymentDetails?: {
    bankName?: string | null;
    accountNumber?: string | null;
    accountHolderName?: string | null;
  };
  metadata?: {
    vendorName?: string | null;
    invoiceNumber?: string | null;
    invoiceDate?: string | null;
    subtotalAmount?: number | null;
    taxAmount?: number | null;
    totalAmount?: number | null;
  };
  lineItems?: Array<{
    description: string;
    quantity: number;
    unitPrice: number;
    subtotal: number;
  }>;
  comments?: string;
  ipAddress?: string;
}

export interface CorrectInvoiceResult {
  id: string;
  requestId: string;
  status: InvoiceStatus;
  message: string;
}

export class IntakeService {
  constructor(
    private prisma: PrismaClient,
    private storage: StorageService,
    private queue: IQueueService
  ) {}

  generateRequestId(): string {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const randomSuffix = randomBytes(3).toString('hex').toUpperCase(); // 6 chars hex
    return `REQ-${today}-${randomSuffix}`;
  }

  async processUpload(params: UploadInvoiceParams): Promise<UploadInvoiceResult> {
    const {
      user,
      clientId,
      fileBuffer,
      originalFileName,
      requestType = 'Standard Vendor Invoice',
      submissionChannel = 'Portal',
      submissionDate = new Date().toISOString().slice(0, 10),
      ipAddress = '127.0.0.1',
    } = params;

    // 1. Validasi Keberadaan Organisasi Klien
    const client = await this.prisma.client.findUnique({
      where: { id: clientId },
    });

    if (!client || !client.isActive) {
      throw new IntakeError(
        'CLIENT_NOT_FOUND',
        'Organisasi klien target tidak ditemukan atau tidak aktif.',
        404,
        { clientId }
      );
    }

    // 2. Validasi Batas Isolasi Multi-Tenant [SR-003, BR-014]
    const hasAccess = checkTenantAccess(user.role, user.assignedClientIds, clientId);
    if (!hasAccess) {
      throw new IntakeError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki wewenang untuk mengunggah dokumen atas nama klien ini.',
        403,
        { clientId, userAssignedClients: user.assignedClientIds }
      );
    }

    // 3. Validasi & Simpan Berkas PDF (Magic Bytes, Max 10MB, Max 5 Halaman) [SR-008, PR-002, PR-003]
    const saveResult = await this.storage.saveFile(fileBuffer, originalFileName, 'invoices');

    // 4. Terbitkan Request ID Unik
    const requestId = this.generateRequestId();

    // 5. Transaksi Atomik Database: Simpan InvoiceRequest + Tulis Immutable AuditLog
    const parsedSubmissionDate = new Date(submissionDate);

    const invoice = await this.prisma.$transaction(async (tx) => {
      const createdInvoice = await tx.invoiceRequest.create({
        data: {
          requestId,
          clientId,
          uploaderId: user.id,
          requestType,
          submissionChannel,
          submissionDate: parsedSubmissionDate,
          originalFileName,
          storageFilePath: saveResult.storageFilePath,
          filePageCount: saveResult.filePageCount,
          status: InvoiceStatus.QUEUED,
        },
      });

      await tx.auditLog.create({
        data: {
          requestId: createdInvoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'INVOICE_UPLOADED',
          previousStatus: null,
          newStatus: InvoiceStatus.QUEUED,
          changeDiff: {
            originalFileName,
            filePageCount: saveResult.filePageCount,
            fileSize: saveResult.fileSize,
            submissionChannel,
            requestType,
          },
          ipAddress,
        },
      });

      return createdInvoice;
    });

    // 6. Masukkan Job ke Antrean Asinkron BullMQ [SR-001, PR-005]
    await this.queue.addExtractionJob({
      invoiceId: invoice.id,
      requestId: invoice.requestId,
      clientId: invoice.clientId,
      storageFilePath: invoice.storageFilePath,
    });

    return {
      id: invoice.id,
      requestId: invoice.requestId,
      status: invoice.status,
      filePageCount: invoice.filePageCount,
      originalFileName: invoice.originalFileName,
    };
  }

  /**
   * Mengoreksi dokumen invoice berstatus EXCEPTION oleh PIC Klien [PR-014, PR-015, SR-011, PF-010].
   * Mempertahankan Request ID TETAP SAMA dan memicu verifikasi ulang.
   */
  async correctInvoice(params: CorrectInvoiceParams): Promise<CorrectInvoiceResult> {
    const {
      user,
      requestId: lookupId,
      paymentDetails,
      metadata,
      lineItems,
      comments,
      ipAddress = '127.0.0.1',
    } = params;

    // 1. Cari invoice berdasarkan requestId atau ID (hanya cek id jika format UUID valid agar PostgreSQL tidak melempar error 22P02)
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lookupId);
    const invoice = await this.prisma.invoiceRequest.findFirst({
      where: isUuid
        ? { OR: [{ requestId: lookupId }, { id: lookupId }] }
        : { requestId: lookupId },
      include: {
        paymentDetails: true,
      },
    });

    if (!invoice) {
      throw new IntakeError(
        'INVOICE_NOT_FOUND',
        'Dokumen invoice target tidak ditemukan.',
        404,
        { requestId: lookupId }
      );
    }

    // 2. Validasi Batas Isolasi Multi-Tenant [SR-003, BR-014]
    const hasAccess = checkTenantAccess(user.role, user.assignedClientIds, invoice.clientId);
    if (!hasAccess) {
      throw new IntakeError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki wewenang untuk mengoreksi dokumen klien ini.',
        403,
        { clientId: invoice.clientId, userAssignedClients: user.assignedClientIds }
      );
    }

    // 3. Validasi status harus EXCEPTION [PR-014, SR-011]
    if (invoice.status !== InvoiceStatus.EXCEPTION) {
      throw new IntakeError(
        'NOT_AN_EXCEPTION',
        `Hanya dokumen berstatus EXCEPTION yang dapat dikoreksi. Status dokumen saat ini adalah ${invoice.status}.`,
        409,
        { currentStatus: invoice.status }
      );
    }

    // 4. Update data koreksi dan catat audit log dalam transaksi atomik
    await this.prisma.$transaction(async (tx) => {
      // Siapkan update metadata jika ada
      const invoiceUpdateData: Prisma.InvoiceRequestUpdateInput = {
        status: InvoiceStatus.PROCESSING,
      };

      if (metadata) {
        if (metadata.vendorName !== undefined) {
          invoiceUpdateData.vendorName = metadata.vendorName;
          invoiceUpdateData.vendorNameNormalized = normalizeText(metadata.vendorName);
        }
        if (metadata.invoiceNumber !== undefined) {
          invoiceUpdateData.invoiceNumber = metadata.invoiceNumber;
          invoiceUpdateData.invoiceNumberNormalized = normalizeText(metadata.invoiceNumber);
        }
        if (metadata.invoiceDate) {
          const parsedDate = new Date(metadata.invoiceDate);
          if (!isNaN(parsedDate.getTime())) {
            invoiceUpdateData.invoiceDate = parsedDate;
          }
        }
        if (metadata.subtotalAmount !== undefined && metadata.subtotalAmount !== null) {
          invoiceUpdateData.subtotalAmount = new Prisma.Decimal(metadata.subtotalAmount);
        }
        if (metadata.taxAmount !== undefined && metadata.taxAmount !== null) {
          invoiceUpdateData.taxAmount = new Prisma.Decimal(metadata.taxAmount);
        }
        if (metadata.totalAmount !== undefined && metadata.totalAmount !== null) {
          invoiceUpdateData.totalAmount = new Prisma.Decimal(metadata.totalAmount);
        }
      }

      await tx.invoiceRequest.update({
        where: { id: invoice.id },
        data: invoiceUpdateData,
      });

      // Update paymentDetails jika ada
      if (paymentDetails) {
        await tx.invoicePaymentDetail.upsert({
          where: { requestId: invoice.id },
          create: {
            requestId: invoice.id,
            bankName: paymentDetails.bankName ?? null,
            accountNumber: paymentDetails.accountNumber ?? null,
            accountHolderName: paymentDetails.accountHolderName ?? null,
            isManuallyEdited: true,
          },
          update: {
            bankName:
              paymentDetails.bankName !== undefined ? paymentDetails.bankName : undefined,
            accountNumber:
              paymentDetails.accountNumber !== undefined ? paymentDetails.accountNumber : undefined,
            accountHolderName:
              paymentDetails.accountHolderName !== undefined
                ? paymentDetails.accountHolderName
                : undefined,
            isManuallyEdited: true,
          },
        });
      }

      // Update line items jika ada
      if (lineItems && lineItems.length > 0) {
        await tx.invoiceLineItem.deleteMany({
          where: { requestId: invoice.id },
        });

        await tx.invoiceLineItem.createMany({
          data: lineItems.map((item, idx) => ({
            requestId: invoice.id,
            itemIndex: idx + 1,
            description: item.description,
            quantity: new Prisma.Decimal(item.quantity),
            unitPrice: new Prisma.Decimal(item.unitPrice),
            subtotal: new Prisma.Decimal(item.subtotal),
            isManuallyEdited: true,
          })),
        });
      }

      // Catat ke Immutable Audit Log [SR-016, BR-015]
      await tx.auditLog.create({
        data: {
          requestId: invoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'INVOICE_CORRECTED',
          previousStatus: InvoiceStatus.EXCEPTION,
          newStatus: InvoiceStatus.PROCESSING,
          changeDiff: {
            comments: comments || 'Koreksi data dokumen oleh PIC Klien',
            paymentDetails,
            metadata,
            lineItemsCount: lineItems?.length,
          },
          ipAddress,
        },
      });
    });

    // 5. Masukkan kembali ke antrean BullMQ untuk verifikasi ulang [PR-014, PF-010]
    await this.queue.addExtractionJob({
      invoiceId: invoice.id,
      requestId: invoice.requestId, // REQUEST ID IDENTIK
      clientId: invoice.clientId,
      storageFilePath: invoice.storageFilePath,
    });

    return {
      id: invoice.id,
      requestId: invoice.requestId,
      status: InvoiceStatus.PROCESSING,
      message: 'Data invoice berhasil dikoreksi dan dikirim untuk verifikasi ulang.',
    };
  }
}

