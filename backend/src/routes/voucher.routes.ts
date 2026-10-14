import { FastifyPluginAsync } from 'fastify';
import { VoucherService, VoucherError } from '../services/voucher.service.js';

/**
 * Route handler untuk pratinjau dan pengunduhan berkas voucher pembayaran resmi [T-019].
 * Memenuhi kebutuhan PR-022, PR-023, BR-011, DR-004, PF-018.
 */
export const voucherRoutes: FastifyPluginAsync = async (fastify) => {
  const voucherService = new VoucherService(fastify.prisma, fastify.storage);

  // 12: GET /api/v1/invoices/:requestId/voucher [PR-022, DR-004]
  fastify.get(
    '/:requestId/voucher',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const voucher = await voucherService.getVoucherDetail(request.user, requestId);

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: voucher,
          meta: {
            timestamp: new Date().toISOString(),
          },
        });
      } catch (err: unknown) {
        if (err instanceof VoucherError) {
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

  // 13: GET /api/v1/invoices/:requestId/voucher/download [BR-011, PR-022, PR-023, PF-018]
  fastify.get(
    '/:requestId/voucher/download',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const result = await voucherService.downloadVoucher(
          request.user,
          requestId,
          request.ip
        );

        return reply
          .status(200)
          .header('Content-Type', 'application/pdf')
          .header('Content-Disposition', `attachment; filename="${result.fileName}"`)
          .send(result.buffer);
      } catch (err: unknown) {
        if (err instanceof VoucherError) {
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
