import fs from 'fs';
import path from 'path';
import { Readable } from 'stream';
import { randomUUID } from 'crypto';
import pdfParse from 'pdf-parse';
import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  DeleteObjectCommand,
} from '@aws-sdk/client-s3';

export class StorageError extends Error {
  constructor(
    public code: string,
    message: string,
    public statusCode: number = 400,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'StorageError';
  }
}

export interface StorageSaveResult {
  storageFilePath: string;
  filePageCount: number;
  fileSize: number;
}

export interface IStorageProvider {
  save(buffer: Buffer, targetKey: string, contentType: string): Promise<string>;
  getBuffer(storageFilePath: string): Promise<Buffer>;
  getStream(storageFilePath: string): Promise<Readable>;
  delete(storageFilePath: string): Promise<void>;
}

export class LocalStorageProvider implements IStorageProvider {
  private baseDir: string;

  constructor(baseDir?: string) {
    const configuredDir = baseDir || process.env.LOCAL_STORAGE_DIR || '../storage';
    this.baseDir = path.isAbsolute(configuredDir)
      ? configuredDir
      : path.resolve(process.cwd(), configuredDir);

    if (!fs.existsSync(this.baseDir)) {
      fs.mkdirSync(this.baseDir, { recursive: true });
    }
  }

  async save(buffer: Buffer, targetKey: string): Promise<string> {
    const fullPath = path.join(this.baseDir, targetKey);
    const parentDir = path.dirname(fullPath);
    if (!fs.existsSync(parentDir)) {
      fs.mkdirSync(parentDir, { recursive: true });
    }

    await fs.promises.writeFile(fullPath, buffer);
    return targetKey;
  }

  async getBuffer(storageFilePath: string): Promise<Buffer> {
    const fullPath = path.join(this.baseDir, storageFilePath);
    if (!fs.existsSync(fullPath)) {
      throw new StorageError(
        'FILE_NOT_FOUND',
        `Berkas tidak ditemukan pada direktori penyimpanan lokal: ${storageFilePath}`,
        404
      );
    }
    return fs.promises.readFile(fullPath);
  }

  async getStream(storageFilePath: string): Promise<Readable> {
    const fullPath = path.join(this.baseDir, storageFilePath);
    if (!fs.existsSync(fullPath)) {
      throw new StorageError(
        'FILE_NOT_FOUND',
        `Berkas tidak ditemukan pada direktori penyimpanan lokal: ${storageFilePath}`,
        404
      );
    }
    return fs.createReadStream(fullPath);
  }

  async delete(storageFilePath: string): Promise<void> {
    const fullPath = path.join(this.baseDir, storageFilePath);
    if (fs.existsSync(fullPath)) {
      await fs.promises.unlink(fullPath);
    }
  }
}

export class S3StorageProvider implements IStorageProvider {
  private s3Client: S3Client;
  private bucket: string;

  constructor() {
    this.bucket = process.env.AWS_BUCKET || 'default-amiga-bucket';
    this.s3Client = new S3Client({
      region: process.env.AWS_REGION || 'ap-southeast-1',
      credentials: {
        accessKeyId: process.env.AWS_ACCESS_KEY || '',
        secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY || '',
      },
    });
  }

  async save(buffer: Buffer, targetKey: string, contentType: string): Promise<string> {
    const command = new PutObjectCommand({
      Bucket: this.bucket,
      Key: targetKey,
      Body: buffer,
      ContentType: contentType,
    });
    await this.s3Client.send(command);
    return targetKey;
  }

  async getBuffer(storageFilePath: string): Promise<Buffer> {
    const command = new GetObjectCommand({
      Bucket: this.bucket,
      Key: storageFilePath,
    });
    const response = await this.s3Client.send(command);
    if (!response.Body) {
      throw new StorageError('FILE_NOT_FOUND', 'Berkas kosong dari S3 storage', 404);
    }
    const byteArray = await response.Body.transformToByteArray();
    return Buffer.from(byteArray);
  }

  async getStream(storageFilePath: string): Promise<Readable> {
    const command = new GetObjectCommand({
      Bucket: this.bucket,
      Key: storageFilePath,
    });
    const response = await this.s3Client.send(command);
    if (!response.Body) {
      throw new StorageError('FILE_NOT_FOUND', 'Berkas kosong dari S3 storage', 404);
    }
    return response.Body as unknown as Readable;
  }

  async delete(storageFilePath: string): Promise<void> {
    const command = new DeleteObjectCommand({
      Bucket: this.bucket,
      Key: storageFilePath,
    });
    await this.s3Client.send(command);
  }
}

export class StorageService {
  private provider: IStorageProvider;
  private readonly maxPages: number;
  private readonly maxSizeBytes: number;

  constructor(provider?: IStorageProvider) {
    this.maxPages = parseInt(process.env.MAX_INVOICE_PAGES || '5', 10);
    this.maxSizeBytes = 10 * 1024 * 1024; // 10MB maks [PR-002]

    if (provider) {
      this.provider = provider;
    } else {
      const backend = (process.env.STORAGE_BACKEND || 'local').toLowerCase();
      if (backend === 's3' && process.env.AWS_ACCESS_KEY && process.env.AWS_ACCESS_KEY !== 'xxx') {
        this.provider = new S3StorageProvider();
      } else {
        this.provider = new LocalStorageProvider();
      }
    }
  }

  /**
   * Memvalidasi magic bytes PDF (%PDF-), batas ukuran 10MB, dan batas 5 halaman.
   */
  async validatePdf(buffer: Buffer): Promise<{ pageCount: number; fileSize: number }> {
    const fileSize = buffer.length;

    // 1. Cek Magic Bytes (%PDF-)
    if (!buffer || buffer.length < 5) {
      throw new StorageError(
        'INVALID_FILE_TYPE',
        'Berkas terlalu kecil atau bukan PDF digital yang valid.',
        400
      );
    }

    const isPdfHeader =
      buffer[0] === 0x25 && // %
      buffer[1] === 0x50 && // P
      buffer[2] === 0x44 && // D
      buffer[3] === 0x46 && // F
      buffer[4] === 0x2d; // -

    if (!isPdfHeader) {
      throw new StorageError(
        'INVALID_FILE_TYPE',
        'Berkas yang diunggah bukan PDF digital yang valid (magic bytes mismatch).',
        400
      );
    }

    // 2. Cek Ukuran Maksimal 10MB [PR-002]
    if (fileSize > this.maxSizeBytes) {
      throw new StorageError(
        'PAGE_LIMIT_EXCEEDED', // atau FILE_SIZE_EXCEEDED
        `Ukuran berkas (${(fileSize / (1024 * 1024)).toFixed(2)}MB) melebihi batas maksimum 10MB.`,
        400,
        { fileSize, maxSizeBytes: this.maxSizeBytes }
      );
    }

    // 3. Cek Batas Halaman Menggunakan struktur PDF katalog dan pdf-parse [PR-003, BR-005]
    const rawStr = buffer.toString('latin1');
    const countMatch = rawStr.match(/\/Count\s+(\d+)/);
    const pageMatches = rawStr.match(/\/Type\s*\/Page\b/g);

    let pageCount = 1;
    if (countMatch && countMatch[1]) {
      pageCount = parseInt(countMatch[1], 10);
    } else if (pageMatches && pageMatches.length > 0) {
      pageCount = pageMatches.length;
    } else {
      try {
        const parsed = await pdfParse(buffer);
        pageCount = parsed.numpages || 1;
      } catch (err) {
        throw new StorageError(
          'INVALID_FILE_TYPE',
          'Struktur berkas PDF rusak atau tidak dapat diparsing sebagai dokumen digital.',
          400,
          { cause: (err as Error).message }
        );
      }
    }

    if (pageCount > this.maxPages) {
      throw new StorageError(
        'PAGE_LIMIT_EXCEEDED',
        `Jumlah halaman dokumen (${pageCount} halaman) melebihi batas maksimum ${this.maxPages} halaman.`,
        400,
        { pageCount, maxPages: this.maxPages }
      );
    }

    return { pageCount, fileSize };
  }

  /**
   * Menyimpan berkas setelah validasi lolos.
   */
  async saveFile(
    buffer: Buffer,
    originalFileName: string,
    subfolder: string = 'invoices'
  ): Promise<StorageSaveResult> {
    const { pageCount, fileSize } = await this.validatePdf(buffer);

    // Bersihkan nama berkas asli dari karakter berbahaya
    const sanitizedName = originalFileName.replace(/[^a-zA-Z0-9._-]/g, '_');
    const uniqueId = randomUUID();
    const datePrefix = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const storageKey = `${subfolder}/${datePrefix}/${uniqueId}_${sanitizedName}`;

    const storageFilePath = await this.provider.save(buffer, storageKey, 'application/pdf');

    return {
      storageFilePath,
      filePageCount: pageCount,
      fileSize,
    };
  }

  async getFileBuffer(storageFilePath: string): Promise<Buffer> {
    return this.provider.getBuffer(storageFilePath);
  }

  async getFileStream(storageFilePath: string): Promise<Readable> {
    return this.provider.getStream(storageFilePath);
  }

  async deleteFile(storageFilePath: string): Promise<void> {
    return this.provider.delete(storageFilePath);
  }
}
