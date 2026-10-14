import { PrismaClient, InvoiceStatus, IssueCode, IssueCategory } from '@prisma/client';
import { normalizeText } from '../workers/ai-extraction.worker.js';

export interface VerificationIssueResult {
  issueCode: IssueCode;
  issueCategory: IssueCategory;
  messageId: string;
}

export interface VerificationEvaluationResult {
  invoiceId: string;
  requestId: string;
  hasIssues: boolean;
  issues: VerificationIssueResult[];
  newStatus: InvoiceStatus;
}

export class VerificationService {
  constructor(private prisma: PrismaClient) {}

  /**
   * Fungsi normalisasi teks alfanumerik huruf kecil [SR-013, BR-008]
   */
  normalizeText(text: string | null | undefined): string | null {
    return normalizeText(text);
  }

  /**
   * Mengevaluasi 3 aturan sistem verifikasi otomatis:
   * 1. Kelengkapan Rekening (MISSING_EVIDENCE)
   * 2. Duplikasi Tagihan (POSSIBLE_DUPLICATE)
   * 3. Discrepansi Perhitungan (CALCULATION_DISCREPANCY)
   * [BR-008, PR-010, PR-011, SR-013, PF-008]
   */
  async evaluateRules(invoiceId: string): Promise<VerificationIssueResult[]> {
    const invoice = await this.prisma.invoiceRequest.findUnique({
      where: { id: invoiceId },
      include: {
        lineItems: true,
        paymentDetails: true,
      },
    });

    if (!invoice) {
      throw new Error(`Dokumen invoice dengan ID ${invoiceId} tidak ditemukan.`);
    }

    const issues: VerificationIssueResult[] = [];

    // Aturan 1: Kelengkapan Rekening (MISSING_EVIDENCE) [BR-008, PR-011]
    const pd = invoice.paymentDetails;
    const isBankEmpty = !pd?.bankName || pd.bankName.trim().length === 0;
    const isAccountEmpty = !pd?.accountNumber || pd.accountNumber.trim().length === 0;

    if (isBankEmpty || isAccountEmpty) {
      issues.push({
        issueCode: IssueCode.MISSING_EVIDENCE,
        issueCategory: IssueCategory.COMPLETENESS,
        messageId:
          'Informasi nomor rekening atau nama bank tujuan transfer tidak ditemukan pada dokumen invoice.',
      });
    }

    // Aturan 2: Duplikasi Tagihan (POSSIBLE_DUPLICATE) [BR-008, PR-011, SR-013]
    const vendorNorm = invoice.vendorNameNormalized || this.normalizeText(invoice.vendorName);
    const invNumNorm = invoice.invoiceNumberNormalized || this.normalizeText(invoice.invoiceNumber);

    if (vendorNorm && invNumNorm) {
      const duplicateMatch = await this.prisma.invoiceRequest.findFirst({
        where: {
          clientId: invoice.clientId,
          id: { not: invoice.id },
          vendorNameNormalized: vendorNorm,
          invoiceNumberNormalized: invNumNorm,
        },
      });

      if (duplicateMatch) {
        issues.push({
          issueCode: IssueCode.POSSIBLE_DUPLICATE,
          issueCategory: IssueCategory.INTEGRITY,
          messageId: `Terdeteksi invoice dengan nomor '${invoice.invoiceNumber || invNumNorm}' dan vendor '${invoice.vendorName || vendorNorm}' sudah pernah diunggah sebelumnya pada klien ini (Request ID: ${duplicateMatch.requestId}).`,
        });
      }
    }

    // Aturan 3: Discrepansi Perhitungan (CALCULATION_DISCREPANCY) [BR-008, PR-011]
    const sumLineItems = invoice.lineItems.reduce((acc, item) => acc + Number(item.subtotal), 0);
    const taxAmount = Number(invoice.taxAmount || 0);
    const expectedTotal = sumLineItems + taxAmount;
    const actualTotal = invoice.totalAmount !== null ? Number(invoice.totalAmount) : null;

    if (actualTotal === null || Math.abs(expectedTotal - actualTotal) > 0.01) {
      const diff = actualTotal !== null ? Math.abs(expectedTotal - actualTotal) : expectedTotal;
      issues.push({
        issueCode: IssueCode.CALCULATION_DISCREPANCY,
        issueCategory: IssueCategory.ARITHMETIC,
        messageId: `Total invoice (${actualTotal ?? 0}) tidak sama dengan penjumlahan subtotal rincian (${sumLineItems}) ditambah pajak (${taxAmount}). Terdapat selisih Rp ${diff.toLocaleString('id-ID')}.`,
      });
    }

    return issues;
  }

  /**
   * Menjalankan evaluasi verifikasi, menyimpan issue, dan mengeksekusi transisi state:
   * - Jika ada isu -> status EXCEPTION [PR-012, PF-009]
   * - Jika bersih -> status READY_FOR_REVIEW [PR-012, PF-009]
   * Mencatat mutasi ke immutable audit_logs [SR-016, BR-015]
   */
  async verifyAndTransition(invoiceId: string): Promise<VerificationEvaluationResult> {
    const invoice = await this.prisma.invoiceRequest.findUnique({
      where: { id: invoiceId },
    });

    if (!invoice) {
      throw new Error(`Dokumen invoice dengan ID ${invoiceId} tidak ditemukan.`);
    }

    const issues = await this.evaluateRules(invoiceId);
    const hasIssues = issues.length > 0;
    const newStatus: InvoiceStatus = hasIssues
      ? InvoiceStatus.EXCEPTION
      : InvoiceStatus.READY_FOR_REVIEW;

    // Transaksi Atomik: simpan isu + mutasi status + catat audit log
    await this.prisma.$transaction(async (tx) => {
      // 1. Hapus isu verifikasi lama yang belum terselesaikan
      await tx.verificationIssue.deleteMany({
        where: {
          requestId: invoiceId,
          isResolved: false,
        },
      });

      // 2. Simpan isu verifikasi baru jika ada
      if (hasIssues) {
        await tx.verificationIssue.createMany({
          data: issues.map((iss) => ({
            requestId: invoiceId,
            issueCode: iss.issueCode,
            issueCategory: iss.issueCategory,
            messageId: iss.messageId,
            isResolved: false,
          })),
        });
      }

      // 3. Mutasi status invoice
      await tx.invoiceRequest.update({
        where: { id: invoiceId },
        data: { status: newStatus },
      });

      // 4. Catat ke immutable audit log [SR-016, BR-015]
      await tx.auditLog.create({
        data: {
          requestId: invoiceId,
          actorId: null,
          actorName: 'Sistem AMIGA (Verification Engine)',
          actorRole: 'SYSTEM',
          actionType: 'STATUS_CHANGED',
          previousStatus: invoice.status,
          newStatus,
          changeDiff: {
            hasIssues,
            issuesCount: issues.length,
            issueCodes: issues.map((i) => i.issueCode),
            verifiedAt: new Date().toISOString(),
          },
          ipAddress: '127.0.0.1',
        },
      });
    });

    return {
      invoiceId,
      requestId: invoice.requestId,
      hasIssues,
      issues,
      newStatus,
    };
  }
}
