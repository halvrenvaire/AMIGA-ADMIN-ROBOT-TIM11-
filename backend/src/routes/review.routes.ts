import { FastifyPluginAsync } from 'fastify';
import { UserRole, InvoiceStatus } from '@prisma/client';
import { requireRoles } from '../plugins/rbac.plugin.js';
import { ReviewService, ReviewError } from '../services/review.service.js';

export const reviewRoutes: FastifyPluginAsync = async (fastify) => {
  const reviewService = new ReviewService(fastify.prisma, fastify.storage);

  // 04: GET /api/v1/invoices/queue [PR-016, PR-017, DR-001]
  fastify.get(
    '/queue',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const query = request.query as {
          clientId?: string;
          status?: InvoiceStatus;
          search?: string;
          page?: string;
          limit?: string;
        };

        const result = await reviewService.getQueue(request.user, {
          clientId: query.clientId,
          status: query.status,
          search: query.search,
          page: query.page ? Number(query.page) : 1,
          limit: query.limit ? Number(query.limit) : 20,
        });

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 05: GET /api/v1/invoices/:requestId [SR-003, PF-011]
  fastify.get(
    '/:requestId',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const invoice = await reviewService.getInvoiceDetail(request.user, requestId);

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: invoice,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 06: GET /api/v1/invoices/:requestId/review-data [PR-018, DR-003, PF-013]
  fastify.get(
    '/:requestId/review-data',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([
          UserRole.FINANCE_REVIEWER,
          UserRole.SERVICE_LEAD,
          UserRole.SYSTEM_ADMIN,
        ]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const result = await reviewService.getReviewData(request.user, requestId);

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // STREAM PDF: GET /api/v1/invoices/:requestId/file [DR-003]
  fastify.get(
    '/:requestId/file',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const pdfBuffer = await reviewService.getPdfBuffer(request.user, requestId);

        return reply
          .header('Content-Type', 'application/pdf')
          .header('Content-Disposition', `inline; filename="${requestId}.pdf"`)
          .send(pdfBuffer);
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 07: PUT /api/v1/invoices/:requestId/line-items [PR-018, PF-014]
  fastify.put(
    '/:requestId/line-items',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.FINANCE_REVIEWER]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const body = request.body as {
          items: Array<{
            id?: string;
            description: string;
            quantity: number;
            unitPrice: number;
            subtotal: number;
          }>;
        };

        const result = await reviewService.updateLineItems(
          request.user,
          requestId,
          body.items,
          request.ip
        );

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 08: POST /api/v1/invoices/:requestId/approve [BR-002, SR-004, PF-015]
  fastify.post(
    '/:requestId/approve',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.FINANCE_REVIEWER]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const result = await reviewService.approveInvoice(
          request.user,
          requestId,
          request.ip
        );

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 09: POST /api/v1/invoices/:requestId/return [PR-018, PF-015]
  fastify.post(
    '/:requestId/return',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.FINANCE_REVIEWER]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const body = request.body as { returnReason: string };

        const result = await reviewService.returnInvoice(
          request.user,
          requestId,
          body?.returnReason,
          request.ip
        );

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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

  // 11: POST /api/v1/invoices/:requestId/reassign [PR-024, PF-016]
  fastify.post(
    '/:requestId/reassign',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.SERVICE_LEAD, UserRole.SYSTEM_ADMIN]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const body = request.body as { newReviewerId: string; reason: string };

        const result = await reviewService.reassignInvoice(
          request.user,
          requestId,
          body?.newReviewerId,
          body?.reason,
          request.ip
        );

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof ReviewError) {
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
