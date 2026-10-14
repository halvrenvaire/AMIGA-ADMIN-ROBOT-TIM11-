import fp from 'fastify-plugin';
import { FastifyPluginAsync } from 'fastify';
import { ResilientQueueService, IQueueService } from '../services/queue.service.js';

declare module 'fastify' {
  interface FastifyInstance {
    queue: IQueueService;
  }
}

const queuePlugin: FastifyPluginAsync = async (fastify) => {
  const queueService = new ResilientQueueService();
  await queueService.initialize();

  fastify.decorate('queue', queueService);

  fastify.addHook('onClose', async () => {
    await queueService.close();
  });
};

export default fp(queuePlugin, {
  name: 'queue-plugin',
});
