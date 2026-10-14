import { FastifyPluginAsync } from 'fastify';
import { UserRole } from '@prisma/client';
import { requireRoles } from '../plugins/rbac.plugin.js';
import { IntakeService, IntakeError } from '../services/intake.service.js';
import { StorageError } from '../services/storage.service.js';

export const intakeRoutes: FastifyPluginAsync = async (fastify) => {
  const intakeService = new IntakeService(fastify.prisma, fastify.storage, fastify.queue);

  // POST /api/v1/invoices/upload
  fastify.post(
    '/upload',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.PIC_KLIEN, UserRole.INTAKE_SUPPORT]),
      ],
    },
    async (request, reply) => {
      try {
        const parts = request.parts();
        let fileBuffer: Buffer | null = null;
        let originalFileName = '';
        const fields: Record<string, string> = {};

        for await (const part of parts) {
          if (part.type === 'file') {
            originalFileName = part.filename;
            fileBuffer = await part.toBuffer();
          } else {
            fields[part.fieldname] = part.value as string;
          }
        }

        if (!fileBuffer || !originalFileName) {
          return reply.status(400).send({
            success: false,
            statusCode: 400,
            error: {
              code: 'FILE_REQUIRED',
              message: 'Berkas invoice PDF wajib diunggah.',
            },
            timestamp: new Date().toISOString(),
          });
        }

        const clientId = fields.clientId;
        if (!clientId) {
          return reply.status(400).send({
            success: false,
            statusCode: 400,
            error: {
              code: 'CLIENT_ID_REQUIRED',
              message: 'Field clientId wajib diisi.',
            },
            timestamp: new Date().toISOString(),
          });
        }

        const result = await intakeService.processUpload({
          user: request.user,
          clientId,
          fileBuffer,
          originalFileName,
          requestType: fields.requestType,
          submissionChannel: fields.submissionChannel,
          submissionDate: fields.submissionDate,
          ipAddress: request.ip,
        });

        return reply.status(201).send({
          success: true,
          statusCode: 201,
          data: result,
        });
      } catch (err: unknown) {
        if (err instanceof IntakeError || err instanceof StorageError) {
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

  // PUT /api/v1/invoices/:requestId/correct [PR-014, PR-015, SR-011, PF-010]
  fastify.put(
    '/:requestId/correct',
    {
      preHandler: [
        fastify.authenticate,
        requireRoles([UserRole.PIC_KLIEN, UserRole.INTAKE_SUPPORT]),
      ],
    },
    async (request, reply) => {
      try {
        const { requestId } = request.params as { requestId: string };
        const body = (request.body || {}) as {
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
        };

        const result = await intakeService.correctInvoice({
          user: request.user,
          requestId,
          paymentDetails: body.paymentDetails,
          metadata: body.metadata,
          lineItems: body.lineItems,
          comments: body.comments,
          ipAddress: request.ip,
        });

        return reply.status(200).send({
          success: true,
          statusCode: 200,
          data: result,
        });
      } catch (err: unknown) {
        if (err instanceof IntakeError) {
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
