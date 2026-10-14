import { FastifyPluginAsync } from 'fastify';
import { AuditService, AuditError } from '../services/audit.service.js';

/**
 * Route handler untuk Jejak Audit Dokumen Permanen [T-020].
 * Memenuhi kebutuhan BR-015, PR-025, SR-016, PF-019.
 */
export const auditRoutes: FastifyPluginAsync = async (fastify) => {
  const auditService = new AuditService(fastify.prisma);

  // 14: GET /api/v1/invoices/:requestId/audit-trail [BR-015, PR-025, SR-016, PF-019]
  fastify.get(
    '/:requestId/audit-trail',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const result = await auditService.getAuditTrail(request.user, requestId);

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof AuditError) {
          return reply.status(err.statusCode).send({
            success: false,
            statusCode: err.statusCode,
            error: {
              code: err.code,
              message: err.message,
              details: err.details,
            },
            timestamp: new Date().toISOString(),
          });
        }
        throw err;
      }
    }
  );
};
