import { Worker, Job } from 'bullmq';
import { Redis } from 'ioredis';
import { PrismaClient, InvoiceStatus, Prisma } from '@prisma/client';
import pdfParse from 'pdf-parse';
import { StorageService } from '../services/storage.service.js';
import { BedrockService, InvoiceExtractionResult } from '../services/bedrock.service.js';
import { ExtractionJobPayload } from '../services/queue.service.js';
import { VerificationService } from '../services/verification.service.js';

/**
 * Normalisasi string teks: huruf kecil, hanya alfanumerik tanpa spasi & tanda baca [SRD, DRD]
 * Digunakan untuk kolom vendor_name_normalized dan invoice_number_normalized.
 */
export function normalizeText(text: string | null | undefined): string | null {
  if (!text) return null;
  const normalized = text.toLowerCase().replace(/[^a-z0-9]/g, '');
  return normalized.length > 0 ? normalized : null;
}

/**
 * Ekstraksi teks in-memory dari berkas PDF digital.
 * Menggunakan pdf-parse sebagai parser utama, dengan fallback ke ekstraksi stream
 * untuk ketahanan pengujian dan integritas parsing.
 */
export async function extractTextFromPdfBuffer(buffer: Buffer): Promise<string> {
  try {
    const data = await pdfParse(buffer);
    if (data && data.text && data.text.trim().length > 0) {
      return data.text;
    }
  } catch {
    // pdf-parse fallback untuk synthetic buffers
  }

  const rawString = buffer.toString('latin1');
  const streamMatches = rawString.match(/BT[\s\S]*?ET/g);
  if (streamMatches) {
    const extractedWords: string[] = [];
    for (const block of streamMatches) {
      const tjMatches = block.match(/\(([^)]+)\)\s*Tj/g);
      if (tjMatches) {
        for (const tj of tjMatches) {
          const textInside = tj.replace(/^\(/, '').replace(/\)\s*Tj$/, '');
          extractedWords.push(textInside);
        }
      }
    }
    if (extractedWords.length > 0) {
      return extractedWords.join('\n');
    }
  }

  return rawString;
}

/**
 * Membungkus promise dengan batas waktu timeout (SLA guard)
 */
export async function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  operationName: string
): Promise<T> {
  let timer: NodeJS.Timeout;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error(`Timeout: ${operationName} melebihi batas waktu SLA ${timeoutMs}ms`));
    }, timeoutMs);
  });

  try {
    return await Promise.race([promise, timeoutPromise]);
  } finally {
    clearTimeout(timer!);
  }
}

export interface ProcessJobResult {
  invoiceId: string;
  requestId: string;
  status: InvoiceStatus;
  vendorName: string | null;
  invoiceNumber: string | null;
  lineItemsCount: number;
  totalAmount: number | null;
  durationMs: number;
  isMockFallback: boolean;
  slaExceeded: boolean;
}

export interface WorkerOptions {
  redisHost?: string;
  redisPort?: number;
  timeoutMs?: number;
  skipVerification?: boolean;
  logger?: {
    info: (obj: unknown, msg?: string) => void;
    warn: (obj: unknown, msg?: string) => void;
    error: (obj: unknown, msg?: string) => void;
  };
}

export class AIExtractionWorker {
  private bullmqWorker: Worker | null = null;
  private redisClient: Redis | null = null;
  private timeoutMs: number;
  private verificationService: VerificationService;
  private options: WorkerOptions;

  constructor(
    private prisma: PrismaClient,
    private storage: StorageService,
    private bedrock: BedrockService,
    verificationOrOptions?: VerificationService | WorkerOptions,
    options?: WorkerOptions
  ) {
    if (verificationOrOptions instanceof VerificationService) {
      this.verificationService = verificationOrOptions;
      this.options = options || {};
    } else {
      this.verificationService = new VerificationService(this.prisma);
      this.options = (verificationOrOptions as WorkerOptions) || {};
    }
    this.timeoutMs = this.options.timeoutMs || parseInt(process.env.AI_EXTRACTION_TIMEOUT_MS || '15000', 10);
  }

  /**
   * Pemrosesan inti ekstraksi data invoice asinkron [SR-001, SR-009, PR-009, PF-007].
   * Dapat dipanggil langsung (in-memory/testing) atau melalui BullMQ worker.
   */
  async processExtractionJob(payload: ExtractionJobPayload): Promise<ProcessJobResult> {
    const startTime = Date.now();
    const { invoiceId, requestId, storageFilePath } = payload;

    // 1. Verifikasi keberadaan invoice di database
    const invoice = await this.prisma.invoiceRequest.findUnique({
      where: { id: invoiceId },
    });

    if (!invoice) {
      throw new Error(`Dokumen invoice dengan ID ${invoiceId} tidak ditemukan.`);
    }

    // 2. Transisi status awal ke PROCESSING jika masih QUEUED + Audit Log [PF-004 -> PF-006]
    if (invoice.status === InvoiceStatus.QUEUED) {
      await this.prisma.$transaction(async (tx) => {
        await tx.invoiceRequest.update({
          where: { id: invoiceId },
          data: { status: InvoiceStatus.PROCESSING },
        });

        await tx.auditLog.create({
          data: {
            requestId: invoiceId,
            actorId: null,
            actorName: 'AI Engine (Titan Text Express)',
            actorRole: 'SYSTEM',
            actionType: 'STATUS_CHANGED',
            previousStatus: InvoiceStatus.QUEUED,
            newStatus: InvoiceStatus.PROCESSING,
            changeDiff: {
              event: 'EXTRACTION_STARTED',
              timestamp: new Date().toISOString(),
            },
          },
        });
      });
    }

    // 3. Baca berkas PDF in-memory dari storage pluggable
    const fileBuffer = await this.storage.getFileBuffer(storageFilePath);

    // 4. Ekstraksi teks PDF in-memory (pdf-parse)
    const pdfText = await extractTextFromPdfBuffer(fileBuffer);

    // 5. Ekstraksi terstruktur via AWS Bedrock Titan Express v1 dengan SLA Timeout 15000ms
    const extractionResult: InvoiceExtractionResult = await withTimeout(
      this.bedrock.extractInvoiceData(pdfText),
      this.timeoutMs,
      `AI Extraction untuk ${requestId}`
    );

    // 6. Normalisasi bidang teks dan tanggal
    const vendorNameNormalized = normalizeText(extractionResult.vendorName);
    const invoiceNumberNormalized = normalizeText(extractionResult.invoiceNumber);

    let parsedInvoiceDate: Date | null = null;
    if (extractionResult.invoiceDate) {
      const parsed = new Date(extractionResult.invoiceDate);
      if (!isNaN(parsed.getTime())) {
        parsedInvoiceDate = parsed;
      }
    }

    // 7. Transaksi Atomik Database: Perbarui Invoice + Simpan Line Items + Payment Details + Audit Log
    await this.prisma.$transaction(async (tx) => {
      // A. Perbarui Invoice Request dengan field hasil ekstraksi
      await tx.invoiceRequest.update({
        where: { id: invoiceId },
        data: {
          status: InvoiceStatus.PROCESSING,
          vendorName: extractionResult.vendorName,
          vendorNameNormalized,
          invoiceNumber: extractionResult.invoiceNumber,
          invoiceNumberNormalized,
          invoiceDate: parsedInvoiceDate,
          subtotalAmount:
            extractionResult.subtotalAmount !== null
              ? new Prisma.Decimal(extractionResult.subtotalAmount)
              : null,
          taxAmount: new Prisma.Decimal(extractionResult.taxAmount),
          totalAmount:
            extractionResult.totalAmount !== null
              ? new Prisma.Decimal(extractionResult.totalAmount)
              : null,
        },
      });

      // B. Hapus line items lama jika ada (idempotency re-run), lalu masukkan line items baru
      await tx.invoiceLineItem.deleteMany({
        where: { requestId: invoiceId },
      });

      if (extractionResult.lineItems && extractionResult.lineItems.length > 0) {
        await tx.invoiceLineItem.createMany({
          data: extractionResult.lineItems.map((item, index) => ({
            requestId: invoiceId,
            itemIndex: index + 1,
            description: item.description,
            quantity: new Prisma.Decimal(item.quantity),
            unitPrice: new Prisma.Decimal(item.unitPrice),
            subtotal: new Prisma.Decimal(item.subtotal),
            isManuallyEdited: false,
          })),
        });
      }

      // C. Upsert payment details (rekening bank transfer)
      const pd = extractionResult.paymentDetails;
      if (pd) {
        await tx.invoicePaymentDetail.upsert({
          where: { requestId: invoiceId },
          create: {
            requestId: invoiceId,
            bankName: pd.bankName,
            accountNumber: pd.accountNumber,
            accountHolderName: pd.accountHolderName,
            isManuallyEdited: false,
          },
          update: {
            bankName: pd.bankName,
            accountNumber: pd.accountNumber,
            accountHolderName: pd.accountHolderName,
          },
        });
      }

      // D. Simpan ke Immutable Audit Log [SR-016, BR-015]
      const durationMs = Date.now() - startTime;
      await tx.auditLog.create({
        data: {
          requestId: invoiceId,
          actorId: null,
          actorName: 'AI Engine (Titan Text Express)',
          actorRole: 'SYSTEM',
          actionType: 'AI_EXTRACTION_COMPLETED',
          previousStatus: InvoiceStatus.PROCESSING,
          newStatus: InvoiceStatus.PROCESSING,
          changeDiff: {
            vendorName: extractionResult.vendorName,
            invoiceNumber: extractionResult.invoiceNumber,
            totalAmount: extractionResult.totalAmount,
            lineItemsCount: extractionResult.lineItems.length,
            extractionDurationMs: durationMs,
            isMockFallback: extractionResult.isMockFallback,
          },
        },
      });
    });

    // 8. Evaluasi 3 Aturan Sistem & Transisi Siklus Hidup (T-009, T-010) [BR-008, PR-012, PF-009]
    let finalStatus: InvoiceStatus = InvoiceStatus.PROCESSING;
    if (!this.options.skipVerification) {
      const verifResult = await this.verificationService.verifyAndTransition(invoiceId);
      finalStatus = verifResult.newStatus;
    }

    const totalDurationMs = Date.now() - startTime;
    const slaExceeded = totalDurationMs > 15000;

    // 9. Pencatatan log terstruktur dan pemantauan SLA [PF-007]
    const logData = {
      invoiceId,
      requestId,
      status: finalStatus,
      durationMs: totalDurationMs,
      slaLimitMs: 15000,
      slaExceeded,
      isMockFallback: extractionResult.isMockFallback,
      lineItemsCount: extractionResult.lineItems.length,
    };

    if (slaExceeded) {
      if (this.options.logger) {
        this.options.logger.warn(logData, 'Ekstraksi AI melebihi batas target SLA 15000ms');
      } else {
        console.warn('⚠️ [AIExtractionWorker] Ekstraksi AI melebihi batas target SLA 15000ms:', logData);
      }
    } else {
      if (this.options.logger) {
        this.options.logger.info(logData, 'Ekstraksi AI selesai sesuai target SLA');
      }
    }

    return {
      invoiceId,
      requestId,
      status: finalStatus,
      vendorName: extractionResult.vendorName,
      invoiceNumber: extractionResult.invoiceNumber,
      lineItemsCount: extractionResult.lineItems.length,
      totalAmount: extractionResult.totalAmount,
      durationMs: totalDurationMs,
      isMockFallback: extractionResult.isMockFallback,
      slaExceeded,
    };
  }

  /**
   * Menyalakan listener antrean BullMQ pada Redis [SR-001].
   * Aman dijalankan meskipun Redis sedang offline (tidak menyebabkan fatal exit).
   */
  async startBullMQWorker(): Promise<Worker | null> {
    const redisHost = this.options.redisHost || process.env.REDIS_HOST || 'localhost';
    const redisPort = this.options.redisPort || parseInt(process.env.REDIS_PORT || '6379', 10);

    try {
      this.redisClient = new Redis({
        host: redisHost,
        port: redisPort,
        maxRetriesPerRequest: null,
        lazyConnect: true,
        retryStrategy: () => null,
      });

      this.redisClient.on('error', () => {
        // Redam unhandled error saat Redis offline
      });

      await this.redisClient.connect();

      this.bullmqWorker = new Worker<ExtractionJobPayload>(
        'ai_extraction_queue',
        async (job: Job<ExtractionJobPayload>) => {
          return await this.processExtractionJob(job.data);
        },
        {
          connection: this.redisClient,
          concurrency: 2,
        }
      );

      this.bullmqWorker.on('completed', (job) => {
        if (this.options.logger) {
          this.options.logger.info({ jobId: job.id }, 'BullMQ job ekstraksi berhasil diselesaikan');
        }
      });

      this.bullmqWorker.on('failed', (job, err) => {
        if (this.options.logger) {
          this.options.logger.error(
            { jobId: job?.id, attemptsMade: job?.attemptsMade, err: err.message },
            'BullMQ job ekstraksi gagal dieksekusi'
          );
        }
      });

      return this.bullmqWorker;
    } catch {
      // Redis offline: fallback logging
      return null;
    }
  }

  async close(): Promise<void> {
    if (this.bullmqWorker) {
      try {
        await this.bullmqWorker.close();
      } catch {
        // Abaikan jika sudah ditutup
      }
      this.bullmqWorker = null;
    }
    if (this.redisClient) {
      try {
        if (this.redisClient.status === 'ready') {
          await this.redisClient.quit();
        } else {
          this.redisClient.disconnect();
        }
      } catch {
        // Abaikan jika koneksi sudah ditutup sebelumnya
      }
      this.redisClient = null;
    }
  }
}
