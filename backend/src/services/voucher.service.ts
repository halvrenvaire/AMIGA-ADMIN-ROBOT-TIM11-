import React from 'react';
import { Document, Page, Text, View, StyleSheet, renderToBuffer } from '@react-pdf/renderer';
import { PrismaClient, InvoiceStatus, PaymentVoucher, UserRole } from '@prisma/client';
import { StorageService } from './storage.service.js';
import { checkTenantAccess } from '../plugins/rbac.plugin.js';
import { JwtPayload } from '../types/auth.types.js';

export class VoucherError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly statusCode: number = 400,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'VoucherError';
  }
}

export const LEGAL_AUTHORIZATION_BOUNDARY_TEXT =
  'Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin atas dasar verifikasi independen tim Keuangan AMIGA. Otorisasi pembayaran akhir dan eksekusi transfer dana merupakan kewenangan mutlak Client Approver di luar sistem AMIGA.';

/**
 * Konversi angka ke kalimat terbilang bahasa Indonesia [DR-004].
 */
export function terbilang(n: number): string {
  const bilangan = [
    '',
    'Satu',
    'Dua',
    'Tiga',
    'Empat',
    'Lima',
    'Enam',
    'Tujuh',
    'Delapan',
    'Sembilan',
    'Sepuluh',
    'Sebelas',
  ];
  const num = Math.floor(Math.abs(n));
  if (num === 0) return 'Nol Rupiah';

  function convert(x: number): string {
    if (x < 12) return bilangan[x];
    if (x < 20) return convert(x - 10) + ' Belas';
    if (x < 100) return convert(Math.floor(x / 10)) + ' Puluh ' + (x % 10 ? convert(x % 10) : '');
    if (x < 200) return 'Seratus ' + (x - 100 ? convert(x - 100) : '');
    if (x < 1000) return convert(Math.floor(x / 100)) + ' Ratus ' + (x % 100 ? convert(x % 100) : '');
    if (x < 2000) return 'Seribu ' + (x - 1000 ? convert(x - 1000) : '');
    if (x < 1000000) return convert(Math.floor(x / 1000)) + ' Ribu ' + (x % 1000 ? convert(x % 1000) : '');
    if (x < 1000000000) return convert(Math.floor(x / 1000000)) + ' Juta ' + (x % 1000000 ? convert(x % 1000000) : '');
    if (x < 1000000000000) return convert(Math.floor(x / 1000000000)) + ' Miliar ' + (x % 1000000000 ? convert(x % 1000000000) : '');
    return convert(Math.floor(x / 1000000000000)) + ' Triliun ' + (x % 1000000000000 ? convert(x % 1000000000000) : '');
  }

  const result = convert(num).replace(/\s+/g, ' ').trim();
  return `${result} Rupiah`;
}

/**
 * Format mata uang Rupiah standar.
 */
function formatRupiah(amount: number): string {
  return 'Rp ' + amount.toLocaleString('id-ID');
}

// Style PDF tema Navy Ink on Cool Marble
const pdfStyles = StyleSheet.create({
  page: {
    padding: 36,
    backgroundColor: '#FFFFFF',
    fontFamily: 'Helvetica',
    fontSize: 9,
    color: '#0B3558',
  },
  headerContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderBottomWidth: 2,
    borderBottomColor: '#0B3558',
    paddingBottom: 12,
    marginBottom: 16,
  },
  orgTitle: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#0B3558',
    letterSpacing: 0.5,
  },
  orgSubtitle: {
    fontSize: 8,
    color: '#476788',
    marginTop: 2,
  },
  docTitle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#006BFF',
    textAlign: 'right',
  },
  docMeta: {
    fontSize: 8,
    color: '#476788',
    textAlign: 'right',
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#0B3558',
    marginBottom: 6,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
    paddingBottom: 2,
  },
  infoGrid: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  infoCol: {
    flex: 1,
  },
  infoRow: {
    flexDirection: 'row',
    marginBottom: 4,
  },
  label: {
    width: 110,
    color: '#476788',
    fontSize: 8.5,
  },
  value: {
    flex: 1,
    color: '#0B3558',
    fontWeight: 'bold',
    fontSize: 8.5,
  },
  table: {
    marginTop: 6,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 3,
  },
  tableHeader: {
    flexDirection: 'row',
    backgroundColor: '#F1F5F9',
    borderBottomWidth: 1,
    borderBottomColor: '#CBD5E1',
    paddingVertical: 5,
    paddingHorizontal: 8,
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 0.5,
    borderBottomColor: '#E2E8F0',
    paddingVertical: 4.5,
    paddingHorizontal: 8,
  },
  thIndex: { width: 24, fontSize: 8, fontWeight: 'bold', color: '#0B3558' },
  thDesc: { flex: 1, fontSize: 8, fontWeight: 'bold', color: '#0B3558' },
  thQty: { width: 45, fontSize: 8, fontWeight: 'bold', textAlign: 'right', color: '#0B3558' },
  thPrice: { width: 85, fontSize: 8, fontWeight: 'bold', textAlign: 'right', color: '#0B3558' },
  thSubtotal: { width: 95, fontSize: 8, fontWeight: 'bold', textAlign: 'right', color: '#0B3558' },
  tdIndex: { width: 24, fontSize: 8, color: '#476788' },
  tdDesc: { flex: 1, fontSize: 8, color: '#0B3558' },
  tdQty: { width: 45, fontSize: 8, textAlign: 'right', color: '#0B3558' },
  tdPrice: { width: 85, fontSize: 8, textAlign: 'right', color: '#0B3558' },
  tdSubtotal: { width: 95, fontSize: 8, textAlign: 'right', fontWeight: 'bold', color: '#0B3558' },
  totalSection: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginBottom: 12,
  },
  totalBox: {
    width: 250,
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 2.5,
  },
  grandTotalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderTopWidth: 1.5,
    borderTopColor: '#0B3558',
    marginTop: 3,
  },
  terbilangBox: {
    backgroundColor: '#F8FAFC',
    borderLeftWidth: 3,
    borderLeftColor: '#006BFF',
    padding: 7,
    marginBottom: 14,
    borderRadius: 2,
  },
  terbilangText: {
    fontSize: 8,
    fontStyle: 'italic',
    color: '#0B3558',
  },
  verificationBox: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 3,
    padding: 8,
    marginBottom: 12,
  },
  legalBoundaryContainer: {
    borderWidth: 1,
    borderColor: '#0B3558',
    borderRadius: 4,
    padding: 8,
    backgroundColor: '#F8FAFC',
    marginTop: 'auto',
  },
  legalHeader: {
    fontSize: 8,
    fontWeight: 'bold',
    color: '#0B3558',
    marginBottom: 3,
    textTransform: 'uppercase',
  },
  legalText: {
    fontSize: 7.5,
    color: '#476788',
    lineHeight: 1.35,
  },
});

interface VoucherRenderProps {
  voucherNumber: string;
  generatedDate: string;
  clientName: string;
  clientCode: string;
  requestId: string;
  vendorName: string;
  invoiceNumber: string;
  invoiceDate: string | null;
  bankName: string;
  accountNumber: string;
  accountHolderName: string;
  subtotalAmount: number;
  taxAmount: number;
  totalAmount: number;
  terbilangText: string;
  reviewerName: string;
  reviewerRole: string;
  approvalDate: string;
  lineItems: Array<{
    itemIndex: number;
    description: string;
    quantity: number;
    unitPrice: number;
    subtotal: number;
  }>;
}

const Doc = Document as unknown as React.ElementType;
const Pg = Page as unknown as React.ElementType;
const Vw = View as unknown as React.ElementType;
const Txt = Text as unknown as React.ElementType;

function buildVoucherPdfDocument(props: VoucherRenderProps) {
  return React.createElement(
    Doc,
    null,
    React.createElement(
      Pg,
      { size: 'A4', style: pdfStyles.page },
      // Header
      React.createElement(
        Vw,
        { style: pdfStyles.headerContainer },
        React.createElement(
          Vw,
          null,
          React.createElement(Txt, { style: pdfStyles.orgTitle }, 'AMIGA OPERATING PARTNER'),
          React.createElement(Txt, { style: pdfStyles.orgSubtitle }, `Organisasi Klien: ${props.clientName} (${props.clientCode})`)
        ),
        React.createElement(
          Vw,
          null,
          React.createElement(Txt, { style: pdfStyles.docTitle }, 'OFFICIAL PAYMENT VOUCHER'),
          React.createElement(Txt, { style: pdfStyles.docMeta }, `No. Voucher: ${props.voucherNumber}`),
          React.createElement(Txt, { style: pdfStyles.docMeta }, `Tanggal Terbit: ${props.generatedDate}`)
        )
      ),

      // Informasi Pembayaran & Tagihan (2 Kolom)
      React.createElement(
        Vw,
        { style: pdfStyles.infoGrid },
        React.createElement(
          Vw,
          { style: pdfStyles.infoCol },
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Dibayarkan Kepada:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.vendorName)
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Bank Tujuan:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.bankName)
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Nomor Rekening:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.accountNumber)
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Nama Rekening:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.accountHolderName)
          )
        ),
        React.createElement(
          Vw,
          { style: pdfStyles.infoCol },
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Referensi Request ID:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.requestId)
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'No. Invoice Vendor:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.invoiceNumber)
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Tanggal Invoice:'),
            React.createElement(Txt, { style: pdfStyles.value }, props.invoiceDate || '-')
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.infoRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Status Verifikasi:'),
            React.createElement(Txt, { style: [pdfStyles.value, { color: '#16A34A' }] }, 'VERIFIED & APPROVED')
          )
        )
      ),

      // Tabel Rincian Line Items
      React.createElement(
        Vw,
        { style: pdfStyles.table },
        React.createElement(
          Vw,
          { style: pdfStyles.tableHeader },
          React.createElement(Txt, { style: pdfStyles.thIndex }, 'No'),
          React.createElement(Txt, { style: pdfStyles.thDesc }, 'Deskripsi Barang / Jasa'),
          React.createElement(Txt, { style: pdfStyles.thQty }, 'Qty'),
          React.createElement(Txt, { style: pdfStyles.thPrice }, 'Harga Satuan'),
          React.createElement(Txt, { style: pdfStyles.thSubtotal }, 'Subtotal')
        ),
        ...props.lineItems.map((item) =>
          React.createElement(
            Vw,
            { key: item.itemIndex, style: pdfStyles.tableRow },
            React.createElement(Txt, { style: pdfStyles.tdIndex }, String(item.itemIndex)),
            React.createElement(Txt, { style: pdfStyles.tdDesc }, item.description),
            React.createElement(Txt, { style: pdfStyles.tdQty }, item.quantity.toString()),
            React.createElement(Txt, { style: pdfStyles.tdPrice }, formatRupiah(item.unitPrice)),
            React.createElement(Txt, { style: pdfStyles.tdSubtotal }, formatRupiah(item.subtotal))
          )
        )
      ),

      // Ringkasan Subtotal, Pajak, dan Grand Total
      React.createElement(
        Vw,
        { style: pdfStyles.totalSection },
        React.createElement(
          Vw,
          { style: pdfStyles.totalBox },
          React.createElement(
            Vw,
            { style: pdfStyles.totalRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Subtotal Rincian:'),
            React.createElement(Txt, { style: pdfStyles.value }, formatRupiah(props.subtotalAmount))
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.totalRow },
            React.createElement(Txt, { style: pdfStyles.label }, 'Pajak (PPN/PPh):'),
            React.createElement(Txt, { style: pdfStyles.value }, formatRupiah(props.taxAmount))
          ),
          React.createElement(
            Vw,
            { style: pdfStyles.grandTotalRow },
            React.createElement(Txt, { style: [pdfStyles.label, { fontWeight: 'bold', color: '#0B3558' }] }, 'Jumlah Transfer:'),
            React.createElement(Txt, { style: [pdfStyles.value, { fontSize: 11, color: '#006BFF' }] }, formatRupiah(props.totalAmount))
          )
        )
      ),

      // Terbilang
      React.createElement(
        Vw,
        { style: pdfStyles.terbilangBox },
        React.createElement(Txt, { style: pdfStyles.terbilangText }, `Terbilang: ${props.terbilangText}`)
      ),

      // Informasi Peninjau / Approval
      React.createElement(
        Vw,
        { style: pdfStyles.verificationBox },
        React.createElement(
          Vw,
          null,
          React.createElement(Txt, { style: pdfStyles.label }, 'Diverifikasi Oleh:'),
          React.createElement(Txt, { style: pdfStyles.value }, `${props.reviewerName} (${props.reviewerRole})`)
        ),
        React.createElement(
          Vw,
          null,
          React.createElement(Txt, { style: [pdfStyles.label, { textAlign: 'right' }] }, 'Waktu Persetujuan:'),
          React.createElement(Txt, { style: [pdfStyles.value, { textAlign: 'right' }] }, props.approvalDate)
        )
      ),

      // BATAS OTORISASI (Legal Authorization Boundary Text)
      React.createElement(
        Vw,
        { style: pdfStyles.legalBoundaryContainer },
        React.createElement(Txt, { style: pdfStyles.legalHeader }, 'BATAS OTORISASI LEGAL:'),
        React.createElement(Txt, { style: pdfStyles.legalText }, LEGAL_AUTHORIZATION_BOUNDARY_TEXT)
      )
    )
  );
}

export class VoucherService {
  constructor(
    private readonly prisma: PrismaClient,
    private readonly storage: StorageService
  ) {}

  /**
   * Mengompilasi voucher pembayaran resmi dari invoice yang disetujui [PR-020, PR-021, SR-010, PF-017].
   * Memenuhi SLA kompilasi <= 3000ms.
   */
  async generateVoucher(
    user: JwtPayload,
    lookupId: string,
    ipAddress: string = '127.0.0.1'
  ): Promise<{ voucher: PaymentVoucher; pdfBuffer: Buffer }> {
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lookupId);
    const invoice = await this.prisma.invoiceRequest.findFirst({
      where: isUuid
        ? { OR: [{ requestId: lookupId }, { id: lookupId }] }
        : { requestId: lookupId },
      include: {
        client: true,
        uploader: true,
        currentReviewer: true,
        lineItems: { orderBy: { itemIndex: 'asc' } },
        paymentDetails: true,
        issues: { where: { isResolved: false } },
        paymentVoucher: true,
      },
    });

    if (!invoice) {
      throw new VoucherError('INVOICE_NOT_FOUND', 'Dokumen invoice tidak ditemukan.', 404, {
        lookupId,
      });
    }

    // Isolasi multi-tenant [SR-003, BR-014]
    const hasAccess = checkTenantAccess(user.role, user.assignedClientIds, invoice.clientId);
    if (!hasAccess) {
      throw new VoucherError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki akses ke dokumen organisasi klien ini.',
        403,
        { clientId: invoice.clientId }
      );
    }

    // Jika voucher sudah pernah dibuat, kembalikan voucher yang sudah ada
    if (invoice.paymentVoucher) {
      const existingBuffer = await this.storage.getFileBuffer(
        invoice.paymentVoucher.voucherFilePath
      );
      return {
        voucher: invoice.paymentVoucher,
        pdfBuffer: existingBuffer,
      };
    }

    // Cek kendala verifikasi yang belum tuntas
    if (invoice.issues && invoice.issues.length > 0) {
      throw new VoucherError(
        'UNRESOLVED_ISSUES',
        'Voucher tidak dapat diterbitkan karena dokumen masih memiliki kendala verifikasi yang aktif.',
        409,
        { activeIssuesCount: invoice.issues.length }
      );
    }

    // 1. Terbitkan nomor voucher unik format VCH/YYYYMM/CLI/XXXXX [SR-017, PR-022]
    const now = new Date();
    const yearMonth = now.toISOString().slice(0, 7).replace('-', ''); // e.g. 202610
    const clientCode = invoice.client.clientCode;

    const countThisMonth = await this.prisma.paymentVoucher.count({
      where: {
        voucherNumber: {
          startsWith: `VCH/${yearMonth}/${clientCode}/`,
        },
      },
    });

    const nextSeq = countThisMonth + 1;
    const voucherNumber = `VCH/${yearMonth}/${clientCode}/${String(nextSeq).padStart(5, '0')}`;

    // 2. Siapkan data kompilasi PDF
    const totalAmount = invoice.totalAmount ? invoice.totalAmount.toNumber() : 0;
    const subtotalAmount = invoice.subtotalAmount ? invoice.subtotalAmount.toNumber() : 0;
    const taxAmount = invoice.taxAmount ? invoice.taxAmount.toNumber() : 0;
    const terbilangText = terbilang(totalAmount);

    const docProps: VoucherRenderProps = {
      voucherNumber,
      generatedDate: now.toISOString().split('T')[0],
      clientName: invoice.client.clientName,
      clientCode: invoice.client.clientCode,
      requestId: invoice.requestId,
      vendorName: invoice.vendorName || 'Vendor Belum Terdefinisi',
      invoiceNumber: invoice.invoiceNumber || '-',
      invoiceDate: invoice.invoiceDate ? invoice.invoiceDate.toISOString().split('T')[0] : null,
      bankName: invoice.paymentDetails?.bankName || 'Tidak Tersedia',
      accountNumber: invoice.paymentDetails?.accountNumber || 'Tidak Tersedia',
      accountHolderName: invoice.paymentDetails?.accountHolderName || invoice.vendorName || '-',
      subtotalAmount,
      taxAmount,
      totalAmount,
      terbilangText,
      reviewerName: user.fullName,
      reviewerRole: user.role,
      approvalDate: now.toISOString().replace('T', ' ').slice(0, 19) + ' UTC',
      lineItems: invoice.lineItems.map((item) => ({
        itemIndex: item.itemIndex,
        description: item.description,
        quantity: item.quantity.toNumber(),
        unitPrice: item.unitPrice.toNumber(),
        subtotal: item.subtotal.toNumber(),
      })),
    };

    // 3. Kompilasi PDF via @react-pdf/renderer
    const pdfDoc = buildVoucherPdfDocument(docProps);
    const pdfBuffer = await renderToBuffer(pdfDoc);

    // 4. Simpan berkas PDF ke Storage
    const sanitizedVoucherName = `${voucherNumber.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
    const savedResult = await this.storage.saveFile(pdfBuffer, sanitizedVoucherName, 'vouchers');

    // 5. Transaksi Atomik: Simpan PaymentVoucher, Update Status Invoice, Catat Audit Log
    const paymentVoucher = await this.prisma.$transaction(async (tx) => {
      const createdVoucher = await tx.paymentVoucher.create({
        data: {
          requestId: invoice.id,
          voucherNumber,
          voucherFilePath: savedResult.storageFilePath,
          authorizationBoundaryText: LEGAL_AUTHORIZATION_BOUNDARY_TEXT,
          generatedBy: user.id,
        },
      });

      await tx.invoiceRequest.update({
        where: { id: invoice.id },
        data: {
          status: InvoiceStatus.AMIGA_REVIEWED,
          currentReviewerId: user.id,
        },
      });

      await tx.auditLog.create({
        data: {
          requestId: invoice.id,
          actorId: user.id,
          actorName: user.fullName,
          actorRole: user.role,
          actionType: 'VOUCHER_GENERATED',
          previousStatus: invoice.status,
          newStatus: InvoiceStatus.AMIGA_REVIEWED,
          changeDiff: {
            voucherNumber,
            voucherFilePath: savedResult.storageFilePath,
            totalApprovedAmount: totalAmount,
          },
          ipAddress,
        },
      });

      return createdVoucher;
    });

    return {
      voucher: paymentVoucher,
      pdfBuffer,
    };
  }

  /**
   * Mengambil detail voucher pembayaran resmi berdasarkan requestId atau voucherNumber.
   */
  async getVoucherDetail(user: JwtPayload, lookupId: string) {
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lookupId);
    const voucher = await this.prisma.paymentVoucher.findFirst({
      where: isUuid
        ? {
            OR: [
              { id: lookupId },
              { requestId: lookupId },
              { voucherNumber: lookupId },
              { invoiceRequest: { requestId: lookupId } },
            ],
          }
        : {
            OR: [
              { voucherNumber: lookupId },
              { invoiceRequest: { requestId: lookupId } },
            ],
          },
      include: {
        invoiceRequest: {
          include: {
            client: true,
            uploader: { select: { id: true, fullName: true, email: true } },
            currentReviewer: { select: { id: true, fullName: true, email: true } },
            paymentDetails: true,
            lineItems: { orderBy: { itemIndex: 'asc' } },
          },
        },
        generator: { select: { id: true, fullName: true, email: true, role: true } },
      },
    });

    if (!voucher) {
      throw new VoucherError('VOUCHER_NOT_FOUND', 'Voucher pembayaran tidak ditemukan.', 404, {
        lookupId,
      });
    }

    const hasAccess = checkTenantAccess(
      user.role,
      user.assignedClientIds,
      voucher.invoiceRequest.clientId
    );
    if (!hasAccess) {
      throw new VoucherError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki akses ke dokumen organisasi klien ini.',
        403,
        { clientId: voucher.invoiceRequest.clientId }
      );
    }

    return voucher;
  }

  /**
   * Mengambil binary buffer berkas PDF voucher dari storage.
   */
  async getVoucherPdfBuffer(user: JwtPayload, lookupId: string): Promise<Buffer> {
    const voucher = await this.getVoucherDetail(user, lookupId);
    return this.storage.getFileBuffer(voucher.voucherFilePath);
  }

  /**
   * Mengunduh berkas PDF voucher pembayaran resmi.
   * Jika diunduh oleh PIC Klien dan status masih AMIGA_REVIEWED,
   * otomatis bermutasi menjadi SENT_TO_CLIENT dalam transaksi atomik dan dicatat di audit log [BR-011, PR-022, PR-023].
   */
  async downloadVoucher(
    user: JwtPayload,
    lookupId: string,
    ipAddress?: string
  ): Promise<{ buffer: Buffer; fileName: string; voucherNumber: string; status: InvoiceStatus }> {
    const voucher = await this.getVoucherDetail(user, lookupId);
    const pdfBuffer = await this.storage.getFileBuffer(voucher.voucherFilePath);
    const fileName = `${voucher.voucherNumber.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;

    let currentStatus = voucher.invoiceRequest.status;

    if (user.role === UserRole.PIC_KLIEN && voucher.invoiceRequest.status === InvoiceStatus.AMIGA_REVIEWED) {
      await this.prisma.$transaction(async (tx) => {
        await tx.invoiceRequest.update({
          where: { id: voucher.invoiceRequest.id },
          data: { status: InvoiceStatus.SENT_TO_CLIENT },
        });

        await tx.auditLog.create({
          data: {
            requestId: voucher.invoiceRequest.id,
            actorId: user.id,
            actorName: user.fullName,
            actorRole: user.role,
            actionType: 'VOUCHER_DOWNLOADED',
            previousStatus: InvoiceStatus.AMIGA_REVIEWED,
            newStatus: InvoiceStatus.SENT_TO_CLIENT,
            changeDiff: {
              voucherNumber: voucher.voucherNumber,
              action: 'DOWNLOAD_OFFICIAL_VOUCHER',
            },
            ipAddress,
          },
        });
      });

      currentStatus = InvoiceStatus.SENT_TO_CLIENT;
    }

    return {
      buffer: pdfBuffer,
      fileName,
      voucherNumber: voucher.voucherNumber,
      status: currentStatus,
    };
  }
}

