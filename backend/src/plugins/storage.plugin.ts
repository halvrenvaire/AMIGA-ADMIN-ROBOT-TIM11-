import fp from 'fastify-plugin';
import multipart from '@fastify/multipart';
import { FastifyPluginAsync } from 'fastify';
import { StorageService } from '../services/storage.service.js';

declare module 'fastify' {
  interface FastifyInstance {
    storage: StorageService;
  }
}

const storagePlugin: FastifyPluginAsync = async (fastify) => {
  const storageService = new StorageService();

  // Register multipart support for file uploads (max 10MB per file)
  await fastify.register(multipart, {
    limits: {
      fileSize: 10 * 1024 * 1024, // 10MB
      files: 1,
    },
  });

  fastify.decorate('storage', storageService);
};

export default fp(storagePlugin, {
  name: 'storage-plugin',
});
