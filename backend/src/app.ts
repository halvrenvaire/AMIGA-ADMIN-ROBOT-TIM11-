import fastify, { FastifyInstance, FastifyError } from 'fastify';
import cors from '@fastify/cors';
import { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import { Type } from '@sinclair/typebox';
import prismaPlugin from './plugins/prisma.plugin.js';
import authPlugin from './plugins/auth.plugin.js';
import storagePlugin from './plugins/storage.plugin.js';
import queuePlugin from './plugins/queue.plugin.js';
import workerPlugin from './plugins/worker.plugin.js';
import { authRoutes } from './routes/auth.routes.js';
import { intakeRoutes } from './routes/intake.routes.js';
import { reviewRoutes } from './routes/review.routes.js';
import { voucherRoutes } from './routes/voucher.routes.js';
import { auditRoutes } from './routes/audit.routes.js';

export function buildApp(): FastifyInstance {
  const app = fastify({
    logger: {
      level: process.env.LOG_LEVEL || 'info',
    },
  }).withTypeProvider<TypeBoxTypeProvider>();

  // Global RFC 7807 Error Handler
  app.setErrorHandler((error: FastifyError, _request, reply) => {
    const statusCode = error.statusCode || 500;
    app.log.error(error);

    return reply.status(statusCode).send({
      success: false,
      statusCode,
      error: {
        code: error.code || 'INTERNAL_SERVER_ERROR',
        message: error.message || 'Terjadi kesalahan internal pada server.',
        ...(process.env.NODE_ENV === 'development' ? { stack: error.stack } : {}),
      },
      timestamp: new Date().toISOString(),
    });
  });

  // CORS configuration
  app.register(cors, {
    origin: true,
    credentials: true,
  });

  // Core Plugins
  app.register(prismaPlugin);
  app.register(authPlugin);
  app.register(storagePlugin);
  app.register(queuePlugin);
  app.register(workerPlugin);

  // Root health check endpoint
  app.get('/health', async () => {
    return {
      status: 'ok',
      service: 'amiga-robot-admin-api',
      timestamp: new Date().toISOString(),
    };
  });

  // API v1 health check endpoint
  app.get(
    '/api/v1/health',
    {
      schema: {
        response: {
          200: Type.Object({
            success: Type.Boolean(),
            statusCode: Type.Integer(),
            data: Type.Object({
              status: Type.String(),
              uptime: Type.Number(),
              timestamp: Type.String(),
            }),
          }),
        },
      },
    },
    async () => {
      return {
        success: true,
        statusCode: 200,
        data: {
          status: 'ok',
          uptime: process.uptime(),
          timestamp: new Date().toISOString(),
        },
      };
    }
  );

  // Register Domain Routes
  app.register(authRoutes, { prefix: '/api/v1/auth' });
  app.register(intakeRoutes, { prefix: '/api/v1/invoices' });
  app.register(reviewRoutes, { prefix: '/api/v1/invoices' });
  app.register(voucherRoutes, { prefix: '/api/v1/invoices' });
  app.register(auditRoutes, { prefix: '/api/v1/invoices' });

  return app;
}
