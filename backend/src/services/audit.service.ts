import { PrismaClient, Prisma } from '@prisma/client';
import { JwtPayload } from '../types/auth.types.js';
import { checkTenantAccess } from '../plugins/rbac.plugin.js';

export class AuditError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly statusCode: number = 400,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'AuditError';
  }
}

export interface CreateAuditLogParams {
  requestId: string;
  actorId?: string | null;
  actorName: string;
  actorRole: string;
  actionType: string;
  previousStatus?: string | null;
  newStatus?: string | null;
  changeDiff?: Record<string, unknown> | Prisma.InputJsonValue | null;
  ipAddress?: string | null;
}

/**
 * Mask nomor rekening bank untuk melindungi data sensitif finansial (PII) [SR-016, BR-015].
 * Contoh: "8800112233" -> "8800****33"
 */
export function maskSensitiveAccountNumber(acc: string | null | undefined): string | null {
  if (!acc) return null;
  const str = acc.trim();
  if (str.length <= 4) return '****';
  if (str.length <= 6) return str.slice(0, 2) + '****' + str.slice(-1);
  return str.slice(0, 4) + '****' + str.slice(-2);
}

/**
 * Sanitasi rekursif untuk menyamarkan nomor rekening sensitif dalam JSON diff [SR-016].
 */
export function sanitizeChangeDiff(diff: unknown): unknown {
  if (!diff || typeof diff !== 'object') return diff;
  if (Array.isArray(diff)) {
    return diff.map(sanitizeChangeDiff);
  }

  const result: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(diff as Record<string, unknown>)) {
    const lowerKey = key.toLowerCase();
    if (
      typeof val === 'string' &&
      (lowerKey.includes('accountnumber') ||
        lowerKey.includes('nomorrekening') ||
        lowerKey.includes('norek') ||
        lowerKey === 'account_number')
    ) {
      result[key] = maskSensitiveAccountNumber(val);
    } else if (typeof val === 'object' && val !== null) {
      result[key] = sanitizeChangeDiff(val);
    } else {
      result[key] = val;
    }
  }
  return result;
}

/**
 * Layanan Append-Only Immutable Audit Trail Logger [T-020].
 * Menegakkan aturan immutability (tidak ada operasi UPDATE atau DELETE) [BR-015, SR-016, PF-019].
 */
export class AuditService {
  constructor(private prisma: PrismaClient) {}

  /**
   * Mencatat aktivitas atau mutasi status ke audit_logs (HANYA INSERT).
   */
  async log(params: CreateAuditLogParams) {
    const sanitizedDiff = params.changeDiff
      ? (sanitizeChangeDiff(params.changeDiff) as Prisma.InputJsonValue)
      : undefined;

    return this.prisma.auditLog.create({
      data: {
        requestId: params.requestId,
        actorId: params.actorId || null,
        actorName: params.actorName,
        actorRole: params.actorRole,
        actionType: params.actionType,
        previousStatus: params.previousStatus || null,
        newStatus: params.newStatus || null,
        changeDiff: sanitizedDiff,
        ipAddress: params.ipAddress || null,
      },
    });
  }

  /**
   * Mengambil riwayat garis waktu jejak audit kronologis [PR-025, DR-005].
   * Diurutkan dari peristiwa paling awal (createdAt ASC), terisolasi tenant, dan BigInt di-cast ke string.
   */
  async getAuditTrail(user: JwtPayload, lookupId: string) {
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lookupId);
    const invoice = await this.prisma.invoiceRequest.findFirst({
      where: isUuid
        ? { OR: [{ id: lookupId }, { requestId: lookupId }] }
        : { requestId: lookupId },
      include: {
        client: true,
      },
    });

    if (!invoice) {
      throw new AuditError('INVOICE_NOT_FOUND', 'Dokumen invoice tidak ditemukan.', 404, {
        requestId: lookupId,
      });
    }

    const hasAccess = checkTenantAccess(user.role, user.assignedClientIds, invoice.clientId);
    if (!hasAccess) {
      throw new AuditError(
        'TENANT_FORBIDDEN',
        'Anda tidak memiliki izin mengakses jejak audit dokumen organisasi klien ini.',
        403,
        { clientId: invoice.clientId }
      );
    }

    const logs = await this.prisma.auditLog.findMany({
      where: {
        requestId: invoice.id,
      },
      orderBy: {
        createdAt: 'asc',
      },
      include: {
        actor: {
          select: {
            id: true,
            fullName: true,
            email: true,
            role: true,
          },
        },
      },
    });

    return {
      invoice: {
        id: invoice.id,
        requestId: invoice.requestId,
        clientId: invoice.clientId,
        clientName: invoice.client.clientName,
        clientCode: invoice.client.clientCode,
        vendorName: invoice.vendorName,
        invoiceNumber: invoice.invoiceNumber,
        status: invoice.status,
        submissionDate: invoice.submissionDate.toISOString(),
      },
      auditLogs: logs.map((log) => ({
        id: log.id.toString(),
        requestId: log.requestId,
        actorId: log.actorId,
        actorName: log.actorName,
        actorRole: log.actorRole,
        actionType: log.actionType,
        previousStatus: log.previousStatus,
        newStatus: log.newStatus,
        changeDiff: sanitizeChangeDiff(log.changeDiff),
        ipAddress: log.ipAddress,
        createdAt: log.createdAt.toISOString(),
        actor: log.actor,
      })),
    };
  }
}
