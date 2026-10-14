import { PrismaClient, Prisma, InvoiceStatus, UserRole, IssueCode, IssueCategory, AssignmentTriggerReason } from '@prisma/client';
import { StorageService } from './storage.service.js';
import { VoucherService } from './voucher.service.js';
import { checkTenantAccess } from '../plugins/rbac.plugin.js';
import { JwtPayload } from '../types/auth.types.js';

export class ReviewError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly statusCode: number = 400,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'ReviewError';
  }
}

export interface QueueQueryParams {
  clientId?: string;
  status?: InvoiceStatus;
  search?: string;
  page?: number;
  limit?: number;
}

export interface UpdateLineItemsParam {
  id?: string;
  description: string;
  quantity: number;
  unitPrice: number;
  subtotal: number;
}

export class ReviewService {
  private readonly voucherService: VoucherService;

  constructor(
    private readonly prisma: PrismaClient,
    private readonly storage: StorageService,
    voucherService?: VoucherService
  ) {
    this.voucherService = voucherService || new VoucherService(prisma, storage);
  }

  /**
   * Mengambil antrean invoice dengan filtering, pagination, status summary, dan beban reviewer [PR-016, PR-017, DR-001].
   */
  async getQueue(user: JwtPayload, query: QueueQueryParams) {
    const page = Math.max(1, Number(query.page) || 1);
    const limit = Math.min(100, Math.max(1, Number(query.limit) || 20));
    const skip = (page - 1) * limit;

    // Batas isolasi multi-tenant [SR-003, BR-014]
    const where: Prisma.InvoiceRequestWhereInput = {};

    if (user.role === UserRole.PIC_KLIEN || user.role === UserRole.INTAKE_SUPPORT) {
      if (query.clientId) {
        if (!user.assignedClientIds.includes(query.clientId)) {
          throw new ReviewError(
            'TENANT_FORBIDDEN',
            'Anda tidak memiliki akses ke organisasi klien ini.',
            403,
            { clientId: query.clientId }
          );
        }
        where.clientId = query.clientId;
      } else {
        where.clientId = { in: user.assignedClientIds };
      }
    } else if (query.clientId) {
      where.clientId = query.clientId;
    }

    if (query.status) {
      where.status = query.status;
    }

    if (query.search && query.search.trim()) {
      const q = query.search.trim();
      where.OR = [
        { requestId: { contains: q, mode: 'insensitive' } },
        { vendorName: { contains: q, mode: 'insensitive' } },
        { invoiceNumber: { contains: q, mode: 'insensitive' } },
        { originalFileName: { contains: q, mode: 'insensitive' } },
      ];
    }

    // Eksekusi query antrean, total count, dan ringkasan status dalam paralel promise
    const [invoices, totalCount, rawStatusCounts] = await Promise.all([
      this.prisma.invoiceRequest.findMany({
        where,
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
        include: {
          client: {
            select: { id: true, clientCode: true, clientName: true },
          },
          currentReviewer: {
            select: { id: true, fullName: true, email: true },
          },
          uploader: {
            select: { id: true, fullName: true, email: true },
          },
          issues: {
            where: { isResolved: false },
            select: { id: true, issueCode: true, issueCategory: true },
          },
        },
      }),
      this.prisma.invoiceRequest.count({ where }),
      this.prisma.invoiceRequest.groupBy({
        by: ['status'],
        where: user.role === UserRole.PIC_KLIEN || user.role === UserRole.INTAKE_SUPPORT
          ? { clientId: { in: user.assignedClientIds } }
          : {},
        _count: { status: true },
      }),
    ]);

    // Format status counts untuk 6 status resmi + ALL
    const statusCounts: Record<string, number> = {
      QUEUED: 0,
      PROCESSING: 0,
      READY_FOR_REVIEW: 0,
      EXCEPTION: 0,
      AMIGA_REVIEWED: 0,
      SENT_TO_CLIENT: 0,
      ALL: 0,
    };

    let totalAllStatuses = 0;
    for (const sc of rawStatusCounts) {
      statusCounts[sc.status] = sc._count.status;
      totalAllStatuses += sc._count.status;
    }
    statusCounts.ALL = totalAllStatuses;

    // Reviewer workloads monitoring [PR-017, DR-001]
    const maxThreshold = Number(process.env.WORKLOAD_MAX_THRESHOLD) || 10;
    const activeReviewers = await this.prisma.user.findMany({
      where: { role: UserRole.FINANCE_REVIEWER, isActive: true },
      select: {
        id: true,
        fullName: true,
        email: true,
        reviewedInvoices: {
          where: {
            status: { in: [InvoiceStatus.READY_FOR_REVIEW, InvoiceStatus.PROCESSING] },
          },
          select: { id: true },
        },
      },
    });

    const reviewerWorkloads = activeReviewers.map((r) => {
      const activeCount = r.reviewedInvoices.length;
      return {
        id: r.id,
        fullName: r.fullName,
        email: r.email,
        activeCount,
        isOverloaded: activeCount >= maxThreshold,
      };
    });

    return {
      items: invoices.map((inv) => ({
        id: inv.id,
        requestId: inv.requestId,
        clientId: inv.clientId,
        clientName: inv.client.clientName,
        clientCode: inv.client.clientCode,
        vendorName: inv.vendorName,
        invoiceNumber: inv.invoiceNumber,
        invoiceDate: inv.invoiceDate?.toISOString() || null,
        totalAmount: inv.totalAmount ? inv.totalAmount.toNumber() : null,
        subtotalAmount: inv.subtotalAmount ? inv.subtotalAmount.toNumber() : null,
        taxAmount: inv.taxAmount ? inv.taxAmount.toNumber() : null,
        status: inv.status,
        requestType: inv.requestType,
        submissionChannel: inv.submissionChannel,
        submissionDate: inv.submissionDate.toISOString(),
        originalFileName: inv.originalFileName,
        filePageCount: inv.filePageCount,
        uploaderId: inv.uploaderId,
        uploaderName: inv.uploader.fullName,
        currentReviewerId: inv.currentReviewerId,
        currentReviewerName: inv.currentReviewer?.fullName || null,
        activeIssuesCount: inv.issues.length,
        issues: inv.issues,
        createdAt: inv.createdAt.toISOString(),
      })),
      totalCount,
      page,
      limit,
      totalPages: Math.ceil(totalCount / limit) || 1,
      statusCounts,
      reviewerWorkloads,
    };
  }

  /**
   * Mendapatkan detail lengkap invoice berdasarkan requestId atau ID [SR-003, PF-011].
   */
  async getInvoiceDetail(user: JwtPayload, lookupId: string) {
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lookupId);
    const invoice = await this.prisma.invoiceRequest.findFirst({
      where: isUuid
        ? { OR: [{ requestId: lookupId }, { id: lookupId }] }
        : { requestId: lookupId },
      include: {
        client: true,
        uploader: { select: { id: true, fullName: true, email: true, role: true } },
        currentReviewer: { select: { id: true, fullName: true, email: true, role: true } },
        lineItems: { orderBy: { itemIndex: 'asc' } },
        paymentDetails: true,
        issues: { orderBy: { detectedAt: 'desc' } },
        paymentVoucher: true,
      },
    });

    if (!invoice) {
      throw new ReviewError('INVOICE_NOT_FOUND', 'Dokumen invoice tidak ditemukan.', 404, {
        requestId: lookupId,
      });
    }

    const hasAccess = checkTenantAccess(user.role, user.assignedClientIds, invoice.clientId);
    if (!hasAccess) {
      throw new ReviewError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki wewenang untuk melihat dokumen klien ini.',
        403,
        { clientId: invoice.clientId }
      );
    }

    return invoice;
  }

  /**
   * Mengambil data khusus layar review split-screen [PR-018, DR-003, PF-013].
   */
  async getReviewData(user: JwtPayload, lookupId: string) {
    const invoice = await this.getInvoiceDetail(user, lookupId);

    const isUploader = invoice.uploaderId === user.id;
    const unresolvedIssues = invoice.issues.filter((i) => !i.isResolved);
    const canApprove =
      !isUploader &&
      invoice.status === InvoiceStatus.READY_FOR_REVIEW &&
      unresolvedIssues.length === 0;

    return {
      invoice: {
        id: invoice.id,
        requestId: invoice.requestId,
        clientId: invoice.clientId,
        clientName: invoice.client.clientName,
        clientCode: invoice.client.clientCode,
        vendorName: invoice.vendorName,
        invoiceNumber: invoice.invoiceNumber,
        invoiceDate: invoice.invoiceDate?.toISOString() || null,
        subtotalAmount: invoice.subtotalAmount ? invoice.subtotalAmount.toNumber() : 0,
        taxAmount: invoice.taxAmount ? invoice.taxAmount.toNumber() : 0,
        totalAmount: invoice.totalAmount ? invoice.totalAmount.toNumber() : 0,
        status: invoice.status,
        originalFileName: invoice.originalFileName,
        filePageCount: invoice.filePageCount,
        submissionDate: invoice.submissionDate.toISOString(),
        uploader: invoice.uploader,
        currentReviewer: invoice.currentReviewer,
      },
      lineItems: invoice.lineItems.map((item) => ({
        id: item.id,
        itemIndex: item.itemIndex,
        description: item.description,
        quantity: item.quantity.toNumber(),
        unitPrice: item.unitPrice.toNumber(),
        subtotal: item.subtotal.toNumber(),
        isManuallyEdited: item.isManuallyEdited,
      })),
      paymentDetails: invoice.paymentDetails
        ? {
            id: invoice.paymentDetails.id,
            bankName: invoice.paymentDetails.bankName,
            accountNumber: invoice.paymentDetails.accountNumber,
            accountHolderName: invoice.paymentDetails.accountHolderName,
            isManuallyEdited: invoice.paymentDetails.isManuallyEdited,
          }
        : null,
      issues: unresolvedIssues.map((issue) => ({
        id: issue.id,
        issueCode: issue.issueCode,
        issueCategory: issue.issueCategory,
        messageId: issue.messageId,
        detectedAt: issue.detectedAt.toISOString(),
      })),
      pdfStreamUrl: `/api/v1/invoices/${invoice.requestId}/file`,
      isUploader,
      canApprove,
      sodWarning: isUploader
        ? 'Pemberitahuan SoD: Anda adalah pengunggah dokumen ini. Sesuai aturan Segregation of Duties, persetujuan harus dilakukan oleh Finance Reviewer lain.'
        : null,
    };
  }

  /**
   * Mengambil file PDF binary buffer untuk viewer canvas [DR-003].
   */
  async getPdfBuffer(user: JwtPayload, lookupId: string): Promise<Buffer> {
    const invoice = await this.getInvoiceDetail(user, lookupId);
    return await this.storage.getFileBuffer(invoice.storageFilePath);
  }

  /**
   * Memperbarui rincian line items dan kalkulasi ulang subtotal & total finansial [PR-018, PF-014].
   */
  async updateLineItems(
    user: JwtPayload,
    lookupId: string,
    items: UpdateLineItemsParam[],
    ipAddress: string = '127.0.0.1'
  ) {
    const invoice = await this.getInvoiceDetail(user, lookupId);

    if (
      invoice.status !== InvoiceStatus.READY_FOR_REVIEW &&
      invoice.status !== InvoiceStatus.EXCEPTION
    ) {
      throw new ReviewError(
        'INVOICE_LOCKED',
        `Invoice dengan status ${invoice.status} tidak dapat disunting rincian barang/jasanya.`,
        409,
        { currentStatus: invoice.status }
      );
    }

    if (!items || items.length === 0) {
      throw new ReviewError('ITEMS_REQUIRED', 'Minimal 1 item barang/jasa harus disertakan.', 400);
    }

    // Validasi nilai matematis setiap item (non-negatif)
    let calculatedSubtotal = 0;
    for (const item of items) {
      if (item.quantity <= 0) {
        throw new ReviewError('INVALID_QUANTITY', 'Kuantitas barang harus lebih dari 0.', 400, {
          item,
        });
      }
      if (item.unitPrice < 0 || item.subtotal < 0) {
        throw new ReviewError('INVALID_PRICE', 'Harga satuan dan subtotal tidak boleh negatif.', 400, {
          item,
        });
      }
      calculatedSubtotal += item.subtotal;
    }

    const currentTax = invoice.taxAmount ? invoice.taxAmount.toNumber() : 0;
    const newTotal = calculatedSubtotal + currentTax;

    const previousSubtotal = invoice.subtotalAmount ? invoice.subtotalAmount.toNumber() : 0;
    const previousTotal = invoice.totalAmount ? invoice.totalAmount.toNumber() : 0;

    // Transaksi atomik update line items & invoice subtotal
    await this.prisma.$transaction(async (tx) => {
      await tx.invoiceLineItem.deleteMany({
        where: { requestId: invoice.id },
      });

      await tx.invoiceLineItem.createMany({
        data: items.map((item, idx) => ({
          requestId: invoice.id,
          itemIndex: idx + 1,
          description: item.description,
          quantity: new Prisma.Decimal(item.quantity),
          unitPrice: new Prisma.Decimal(item.unitPrice),
          subtotal: new Prisma.Decimal(item.subtotal),
          isManuallyEdited: true,
        })),
      });

      await tx.invoiceRequest.update({
        where: { id: invoice.id },
        data: {
          subtotalAmount: new Prisma.Decimal(calculatedSubtotal),
          totalAmount: new Prisma.Decimal(newTotal),
        },
      });

      // Selesaikan issue CALCULATION_DISCREPANCY jika ada
      await tx.verificationIssue.updateMany({
        where: {
          requestId: invoice.id,
          issueCode: IssueCode.CALCULATION_DISCREPANCY,
          isResolved: false,
        },
        data: {
          isResolved: true,
          resolvedAt: new Date(),
        },
      });

      // Catat ke Immutable Audit Log [SR-016, BR-015]
      await tx.auditLog.create({
        data: {
          requestId: invoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'LINE_ITEMS_UPDATED',
          previousStatus: invoice.status,
          newStatus: invoice.status,
          changeDiff: {
            previousSubtotal,
            newSubtotal: calculatedSubtotal,
            previousTotal,
            newTotal,
            updatedItemsCount: items.length,
          },
          ipAddress,
        },
      });
    });

    return {
      success: true,
      requestId: invoice.requestId,
      updatedCount: items.length,
      subtotalAmount: calculatedSubtotal,
      taxAmount: currentTax,
      totalAmount: newTotal,
    };
  }

  /**
   * Mengembalikan dokumen ke PIC Klien dengan catatan alasan kendala [PR-018, PF-015].
   */
  async returnInvoice(
    user: JwtPayload,
    lookupId: string,
    returnReason: string,
    ipAddress: string = '127.0.0.1'
  ) {
    if (!returnReason || returnReason.trim().length < 10) {
      throw new ReviewError(
        'REASON_REQUIRED',
        'Alasan pengembalian wajib diisi minimal 10 karakter.',
        400
      );
    }

    const invoice = await this.getInvoiceDetail(user, lookupId);

    if (invoice.status !== InvoiceStatus.READY_FOR_REVIEW) {
      throw new ReviewError(
        'INVALID_LIFECYCLE_STATE',
        `Hanya dokumen berstatus READY_FOR_REVIEW yang dapat dikembalikan. Status saat ini: ${invoice.status}.`,
        409,
        { currentStatus: invoice.status }
      );
    }

    await this.prisma.$transaction(async (tx) => {
      await tx.invoiceRequest.update({
        where: { id: invoice.id },
        data: { status: InvoiceStatus.EXCEPTION },
      });

      await tx.verificationIssue.create({
        data: {
          requestId: invoice.id,
          issueCode: IssueCode.REVIEWER_RETURNED,
          issueCategory: IssueCategory.MANUAL_REVIEW,
          messageId: returnReason.trim(),
        },
      });

      await tx.auditLog.create({
        data: {
          requestId: invoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'INVOICE_RETURNED',
          previousStatus: InvoiceStatus.READY_FOR_REVIEW,
          newStatus: InvoiceStatus.EXCEPTION,
          changeDiff: { returnReason: returnReason.trim() },
          ipAddress,
        },
      });
    });

    return {
      requestId: invoice.requestId,
      status: InvoiceStatus.EXCEPTION,
      issueCode: IssueCode.REVIEWER_RETURNED,
      message: 'Dokumen invoice berhasil dikembalikan ke PIC Klien.',
    };
  }

  /**
   * Penegakan Segregation of Duties (SoD) dan persetujuan voucher resmi secara atomik [BR-002, SR-004, PF-015].
   */
  async approveInvoice(user: JwtPayload, lookupId: string, ipAddress: string = '127.0.0.1') {
    const invoice = await this.getInvoiceDetail(user, lookupId);

    if (invoice.status !== InvoiceStatus.READY_FOR_REVIEW) {
      throw new ReviewError(
        'INVALID_LIFECYCLE_STATE',
        `Hanya dokumen berstatus READY_FOR_REVIEW yang dapat disetujui. Status saat ini: ${invoice.status}.`,
        409,
        { currentStatus: invoice.status }
      );
    }

    // PENEGAKAN MUTLAK SEGREGATION OF DUTIES (SoD) DI SERVER [BR-002, SR-004]
    if (invoice.uploaderId === user.id) {
      // 1. Cari reviewer aktif dengan antrean tersedikit (least-loaded reviewer) selain uploader
      const leastLoaded = await this.getLeastLoadedReviewer(user.id);

      // 2. Transaksi atomik: alihkan penugasan dokumen dan catat pelanggaran SoD
      await this.prisma.$transaction(async (tx) => {
        if (leastLoaded) {
          await tx.invoiceRequest.update({
            where: { id: invoice.id },
            data: { currentReviewerId: leastLoaded.id },
          });

          await tx.reviewerAssignment.create({
            data: {
              requestId: invoice.id,
              previousReviewerId: user.id,
              assignedReviewerId: leastLoaded.id,
              triggerReason: AssignmentTriggerReason.SOD_AUTO_REASSIGN,
            },
          });
        }

        await tx.auditLog.create({
          data: {
            requestId: invoice.id,
            actorId: user.id,
            actorName: user.fullName,
            actorRole: user.role,
            actionType: 'SOD_VIOLATION_BLOCKED',
            previousStatus: invoice.status,
            newStatus: invoice.status,
            changeDiff: {
              attemptedBy: user.email,
              reassignedTo: leastLoaded?.email || 'UNASSIGNED',
              rule: 'BR-002 Segregation of Duties',
            },
            ipAddress,
          },
        });
      });

      throw new ReviewError(
        'SOD_VIOLATION',
        'Pelanggaran Segregation of Duties (SoD): Anda tidak diizinkan menyetujui dokumen yang Anda unggah sendiri. Dokumen telah otomatis dialihkan ke reviewer lain.',
        403,
        {
          reassignedToReviewer: leastLoaded ? leastLoaded.fullName : null,
        }
      );
    }

    // Cek apakah masih ada kendala verifikasi yang belum diselesaikan
    const unresolvedIssues = invoice.issues.filter((i) => !i.isResolved);
    if (unresolvedIssues.length > 0) {
      throw new ReviewError(
        'UNRESOLVED_ISSUES',
        'Dokumen masih memiliki kendala verifikasi yang belum terselesaikan.',
        409,
        { unresolvedIssuesCount: unresolvedIssues.length }
      );
    }

    // Persetujuan sukses: terbitkan voucher pembayaran resmi via VoucherService [PR-020, PR-021, SR-010, PF-017]
    const { voucher } = await this.voucherService.generateVoucher(user, invoice.id, ipAddress);

    return {
      requestId: invoice.requestId,
      status: InvoiceStatus.AMIGA_REVIEWED,
      voucherNumber: voucher.voucherNumber,
      message: 'Dokumen invoice berhasil disetujui. Status resmi: AMIGA_REVIEWED.',
    };
  }

  /**
   * Rebalancing beban penugasan dokumen oleh Service Lead [PR-024, PF-016].
   */
  async reassignInvoice(
    user: JwtPayload,
    lookupId: string,
    newReviewerId: string,
    reason: string,
    ipAddress: string = '127.0.0.1'
  ) {
    const invoice = await this.getInvoiceDetail(user, lookupId);

    const targetReviewer = await this.prisma.user.findUnique({
      where: { id: newReviewerId },
    });

    if (!targetReviewer || targetReviewer.role !== UserRole.FINANCE_REVIEWER || !targetReviewer.isActive) {
      throw new ReviewError(
        'USER_NOT_REVIEWER',
        'Target pengguna bukan Finance Reviewer aktif.',
        400,
        { newReviewerId }
      );
    }

    await this.prisma.$transaction(async (tx) => {
      await tx.invoiceRequest.update({
        where: { id: invoice.id },
        data: { currentReviewerId: newReviewerId },
      });

      await tx.reviewerAssignment.create({
        data: {
          requestId: invoice.id,
          previousReviewerId: invoice.currentReviewerId,
          assignedReviewerId: newReviewerId,
          triggerReason: AssignmentTriggerReason.WORKLOAD_REBALANCE_LEAD,
        },
      });

      await tx.auditLog.create({
        data: {
          requestId: invoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'WORKLOAD_REASSIGNED',
          previousStatus: invoice.status,
          newStatus: invoice.status,
          changeDiff: {
            previousReviewerId: invoice.currentReviewerId,
            newReviewerId,
            reason,
          },
          ipAddress,
        },
      });
    });

    return {
      requestId: invoice.requestId,
      previousReviewerId: invoice.currentReviewerId,
      currentReviewerId: newReviewerId,
      message: 'Penugasan dokumen berhasil dialihkan.',
    };
  }

  /**
   * Mencari Finance Reviewer aktif dengan beban kerja terkecil untuk auto-reassign [SR-014].
   */
  private async getLeastLoadedReviewer(excludedUserId?: string) {
    const reviewers = await this.prisma.user.findMany({
      where: {
        role: UserRole.FINANCE_REVIEWER,
        isActive: true,
        ...(excludedUserId ? { id: { not: excludedUserId } } : {}),
      },
      include: {
        reviewedInvoices: {
          where: {
            status: { in: [InvoiceStatus.READY_FOR_REVIEW, InvoiceStatus.PROCESSING] },
          },
          select: { id: true },
        },
      },
    });

    if (reviewers.length === 0) return null;

    reviewers.sort((a, b) => a.reviewedInvoices.length - b.reviewedInvoices.length);
    return reviewers[0];
  }
}
