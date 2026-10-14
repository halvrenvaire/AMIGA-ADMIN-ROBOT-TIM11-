import { FastifyRequest, FastifyReply } from 'fastify';
import { UserRole } from '@prisma/client';

export function requireRoles(allowedRoles: UserRole[]) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const user = request.user;
    if (!user) {
      return reply.status(401).send({
        success: false,
        statusCode: 401,
        error: {
          code: 'AUTH_UNAUTHORIZED',
          message: 'Pengguna belum terautentikasi.',
        },
        timestamp: new Date().toISOString(),
      });
    }

    if (!allowedRoles.includes(user.role)) {
      return reply.status(403).send({
        success: false,
        statusCode: 403,
        error: {
          code: 'FORBIDDEN_ROLE',
          message: 'Anda tidak memiliki hak akses untuk fungsi ini.',
          details: {
            userRole: user.role,
            requiredRoles: allowedRoles,
          },
        },
        timestamp: new Date().toISOString(),
      });
    }
  };
}

export function checkTenantAccess(userRoles: UserRole, userAllowedClientIds: string[], targetClientId: string): boolean {
  // Peran internal AMIGA (Finance Reviewer, Service Lead, System Admin) memiliki akses lintas klien
  if (
    userRoles === UserRole.FINANCE_REVIEWER ||
    userRoles === UserRole.SERVICE_LEAD ||
    userRoles === UserRole.SYSTEM_ADMIN
  ) {
    return true;
  }

  // PIC Klien dan Intake Support hanya boleh mengakses klien yang ditugaskan kepada mereka
  return userAllowedClientIds.includes(targetClientId);
}

export function requireTenantAccess(extractClientId: (req: FastifyRequest) => string | undefined) {
  return async (request: FastifyRequest, reply: FastifyReply) => {
    const user = request.user;
    if (!user) {
      return reply.status(401).send({
        success: false,
        statusCode: 401,
        error: {
          code: 'AUTH_UNAUTHORIZED',
          message: 'Pengguna belum terautentikasi.',
        },
        timestamp: new Date().toISOString(),
      });
    }

    const clientId = extractClientId(request);
    if (!clientId) {
      return reply.status(400).send({
        success: false,
        statusCode: 400,
        error: {
          code: 'CLIENT_ID_REQUIRED',
          message: 'Parameter client_id diperlukan untuk validasi tenant.',
        },
        timestamp: new Date().toISOString(),
      });
    }

    const isAllowed = checkTenantAccess(user.role, user.assignedClientIds || [], clientId);
    if (!isAllowed) {
      return reply.status(403).send({
        success: false,
        statusCode: 403,
        error: {
          code: 'TENANT_FORBIDDEN',
          message: 'Akses ke data klien ini ditolak (pelanggaran isolasi multi-tenant).',
          details: {
            targetClientId: clientId,
            userAssignedClients: user.assignedClientIds,
          },
        },
        timestamp: new Date().toISOString(),
      });
    }
  };
}
