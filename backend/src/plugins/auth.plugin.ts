import fp from 'fastify-plugin';
import fastifyJwt from '@fastify/jwt';
import { FastifyPluginAsync, FastifyRequest, FastifyReply } from 'fastify';
import '../types/auth.types.js';

declare module 'fastify' {
  interface FastifyInstance {
    authenticate: (request: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}

const authPlugin: FastifyPluginAsync = async (fastify) => {
  const secret = process.env.JWT_SECRET || 'ganti-dengan-string-acak-panjang-minimum-256-bits-super-secret-amiga';
  const expireMinutes = parseInt(process.env.JWT_EXPIRE_MINUTES || '480', 10);

  await fastify.register(fastifyJwt, {
    secret,
    sign: {
      expiresIn: `${expireMinutes}m`,
    },
  });

  fastify.decorate(
    'authenticate',
    async (request: FastifyRequest, reply: FastifyReply) => {
      try {
        await request.jwtVerify();
      } catch (err) {
        reply.status(401).send({
          success: false,
          statusCode: 401,
          error: {
            code: 'AUTH_UNAUTHORIZED',
            message: 'Sesi tidak valid atau telah kedaluwarsa.',
            details: (err as Error).message,
          },
          timestamp: new Date().toISOString(),
        });
      }
    }
  );
};

export default fp(authPlugin, {
  name: 'auth-plugin',
});
