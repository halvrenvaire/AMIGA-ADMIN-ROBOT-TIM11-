import { FastifyPluginAsync } from 'fastify';
import { Type } from '@sinclair/typebox';
import { AuthService } from '../services/auth.service.js';

export const LoginBodySchema = Type.Object({
  email: Type.String({ format: 'email' }),
  password: Type.String({ minLength: 1 }),
});

export const UserResponseSchema = Type.Object({
  id: Type.String(),
  email: Type.String(),
  fullName: Type.String(),
  role: Type.String(),
  defaultClientId: Type.Union([Type.String(), Type.Null()]),
  assignedClientIds: Type.Array(Type.String()),
});

export const LoginResponseSchema = Type.Object({
  success: Type.Boolean(),
  statusCode: Type.Integer(),
  data: Type.Object({
    accessToken: Type.String(),
    expiresIn: Type.Integer(),
    user: UserResponseSchema,
  }),
});

export const MeResponseSchema = Type.Object({
  success: Type.Boolean(),
  statusCode: Type.Integer(),
  data: Type.Object({
    user: UserResponseSchema,
  }),
});

export const authRoutes: FastifyPluginAsync = async (fastify) => {
  const authService = new AuthService(fastify.prisma);
  const expireMinutes = parseInt(process.env.JWT_EXPIRE_MINUTES || '480', 10);
  const expiresInSeconds = expireMinutes * 60;

  // POST /api/v1/auth/login
  fastify.post(
    '/login',
    {
      schema: {
        body: LoginBodySchema,
      },
    },
    async (request, reply) => {
      const { email, password } = request.body as { email: string; password: string };

      const userPayload = await authService.validateUserCredentials(email, password);
      if (!userPayload) {
        return reply.status(401).send({
          success: false,
          statusCode: 401,
          error: {
            code: 'AUTH_INVALID_CREDENTIALS',
            message: 'Email atau kata sandi tidak valid.',
          },
          timestamp: new Date().toISOString(),
        });
      }

      // Terbitkan JWT token menggunakan Fastify JWT decorator
      const token = fastify.jwt.sign(userPayload);

      return reply.status(200).send({
        success: true,
        statusCode: 200,
        data: {
          accessToken: token,
          expiresIn: expiresInSeconds,
          user: userPayload,
        },
      });
    }
  );

  // GET /api/v1/auth/me
  fastify.get(
    '/me',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      const userPayload = request.user;
      const freshUser = await authService.getUserProfile(userPayload.id);

      if (!freshUser) {
        return reply.status(401).send({
          success: false,
          statusCode: 401,
          error: {
            code: 'AUTH_UNAUTHORIZED',
            message: 'Pengguna tidak ditemukan atau sudah dinonaktifkan.',
          },
          timestamp: new Date().toISOString(),
        });
      }

      return reply.status(200).send({
        success: true,
        statusCode: 200,
        data: {
          user: freshUser,
        },
      });
    }
  );

  // GET /api/v1/auth/clients [SR-003, DR-002]
  fastify.get(
    '/clients',
    {
      preHandler: [fastify.authenticate],
    },
    async (request, reply) => {
      const user = request.user;
      const isInternal =
        user.role === 'FINANCE_REVIEWER' ||
        user.role === 'SERVICE_LEAD' ||
        user.role === 'SYSTEM_ADMIN';

      const clients = await fastify.prisma.client.findMany({
        where: isInternal
          ? { isActive: true }
          : { id: { in: user.assignedClientIds }, isActive: true },
        select: {
          id: true,
          clientCode: true,
          clientName: true,
        },
        orderBy: { clientCode: 'asc' },
      });

      return reply.status(200).send({
        success: true,
        statusCode: 200,
        data: clients,
      });
    }
  );
};
