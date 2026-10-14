import fp from 'fastify-plugin';
import { FastifyPluginAsync } from 'fastify';
import { AIExtractionWorker } from '../workers/ai-extraction.worker.js';
import { BedrockService } from '../services/bedrock.service.js';

declare module 'fastify' {
  interface FastifyInstance {
    extractionWorker: AIExtractionWorker;
  }
}

const workerPlugin: FastifyPluginAsync = async (fastify) => {
  const bedrockService = new BedrockService();
  const worker = new AIExtractionWorker(
    fastify.prisma,
    fastify.storage,
    bedrockService,
    { logger: fastify.log }
  );

  // Jika Redis aktif, jalankan BullMQ background worker
  await worker.startBullMQWorker();

  // Jika in-memory fallback aktif (Redis offline), pasang listener pemrosesan otomatis
  if (fastify.queue && typeof fastify.queue.registerHandler === 'function') {
    fastify.queue.registerHandler(async (payload) => {
      try {
        await worker.processExtractionJob(payload);
      } catch (err) {
        fastify.log.error({ err }, 'Gagal memproses in-memory background job ekstraksi AI');
      }
    });
  }

  fastify.decorate('extractionWorker', worker);

  fastify.addHook('onClose', async () => {
    await worker.close();
  });
};

export default fp(workerPlugin, {
  name: 'worker-plugin',
  dependencies: ['prisma-plugin', 'storage-plugin', 'queue-plugin'],
});
