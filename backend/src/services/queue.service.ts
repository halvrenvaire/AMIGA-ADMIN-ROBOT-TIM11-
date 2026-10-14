import { Queue } from 'bullmq';
import { Redis } from 'ioredis';
import { randomUUID } from 'crypto';

export interface ExtractionJobPayload {
  invoiceId: string;
  requestId: string;
  clientId: string;
  storageFilePath: string;
}

export type ExtractionJobHandler = (data: ExtractionJobPayload) => Promise<unknown>;

export interface IQueueService {
  addExtractionJob(data: ExtractionJobPayload): Promise<string>;
  registerHandler?(handler: ExtractionJobHandler): void;
  close(): Promise<void>;
  isRedisConnected(): boolean;
}

export class InMemoryQueueService implements IQueueService {
  private jobs: Map<string, ExtractionJobPayload> = new Map();
  private handler?: ExtractionJobHandler;

  registerHandler(handler: ExtractionJobHandler): void {
    this.handler = handler;
  }

  async addExtractionJob(data: ExtractionJobPayload): Promise<string> {
    const jobId = `job_${randomUUID()}`;
    this.jobs.set(jobId, data);
    if (this.handler) {
      setImmediate(async () => {
        try {
          await this.handler!(data);
        } catch (err) {
          console.error('[InMemoryQueue] Error processing extraction job:', err);
        }
      });
    }
    return jobId;
  }

  async close(): Promise<void> {
    this.jobs.clear();
  }

  isRedisConnected(): boolean {
    return false;
  }

  getPendingJobs(): ExtractionJobPayload[] {
    return Array.from(this.jobs.values());
  }
}

export class BullMQQueueService implements IQueueService {
  private queue: Queue;
  private redisClient: Redis;
  private connected: boolean = false;

  constructor(redisHost: string = 'localhost', redisPort: number = 6379) {
    this.redisClient = new Redis({
      host: redisHost,
      port: redisPort,
      maxRetriesPerRequest: null,
      lazyConnect: true,
      retryStrategy: () => null, // Jangan retry terus menerus jika Redis offline
    });

    this.redisClient.on('error', () => {
      // Redam unhandled error saat Redis offline
    });

    this.queue = new Queue('ai_extraction_queue', {
      connection: this.redisClient,
    });
  }

  async init(): Promise<boolean> {
    try {
      await this.redisClient.connect();
      this.connected = true;
      return true;
    } catch {
      this.connected = false;
      return false;
    }
  }

  async addExtractionJob(data: ExtractionJobPayload): Promise<string> {
    const job = await this.queue.add('extract-invoice', data, {
      attempts: 2,
      removeOnComplete: true,
    });
    return job.id || randomUUID();
  }

  async close(): Promise<void> {
    await this.queue.close();
    await this.redisClient.quit();
  }

  isRedisConnected(): boolean {
    return this.connected;
  }
}

export class ResilientQueueService implements IQueueService {
  private activeService: IQueueService;

  constructor() {
    this.activeService = new InMemoryQueueService();
  }

  async initialize(): Promise<void> {
    const redisHost = process.env.REDIS_HOST || 'localhost';
    const redisPort = parseInt(process.env.REDIS_PORT || '6379', 10);

    const bullmq = new BullMQQueueService(redisHost, redisPort);
    const isOnline = await bullmq.init();

    if (isOnline) {
      this.activeService = bullmq;
    } else {
      this.activeService = new InMemoryQueueService();
    }
  }

  async addExtractionJob(data: ExtractionJobPayload): Promise<string> {
    return this.activeService.addExtractionJob(data);
  }

  async close(): Promise<void> {
    return this.activeService.close();
  }

  registerHandler(handler: ExtractionJobHandler): void {
    if ('registerHandler' in this.activeService && typeof this.activeService.registerHandler === 'function') {
      this.activeService.registerHandler(handler);
    }
  }

  isRedisConnected(): boolean {
    return this.activeService.isRedisConnected();
  }
}
