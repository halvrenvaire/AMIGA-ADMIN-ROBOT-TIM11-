import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'fs';
import path from 'path';
import { StorageService, LocalStorageProvider, StorageError } from '../storage.service.js';

// Minimal valid 1-page PDF
const sampleValid1PagePdf = Buffer.from(
  `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF`
);

// Minimal valid 6-page PDF (Count = 6)
function generateMultiPagePdf(pageCount: number): Buffer {
  let kids = '';
  let pageObjects = '';
  let objIndex = 3;

  for (let i = 1; i <= pageCount; i++) {
    kids += `${objIndex} 0 R `;
    pageObjects += `${objIndex} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n`;
    objIndex++;
  }

  const content = `%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [${kids.trim()}] /Count ${pageCount} >>
endobj
${pageObjects}
trailer
<< /Size ${objIndex} /Root 1 0 R >>
startxref
500
%%EOF`;

  return Buffer.from(content);
}

describe('T-005: File Storage & Magic Bytes PDF Validation', () => {
  const testStorageDir = path.resolve(process.cwd(), './test_storage_tmp');
  let storageService: StorageService;

  beforeEach(() => {
    const provider = new LocalStorageProvider(testStorageDir);
    storageService = new StorageService(provider);
  });

  afterEach(async () => {
    if (fs.existsSync(testStorageDir)) {
      await fs.promises.rm(testStorageDir, { recursive: true, force: true });
    }
  });

  describe('Magic Bytes & File Type Validation', () => {
    it('harus menolak berkas non-PDF (misal .exe atau plain text) dengan kode INVALID_FILE_TYPE', async () => {
      const fakeExecutable = Buffer.from('MZ\x90\x00\x03\x00\x00\x00fake_windows_exe_content');

      await expect(storageService.validatePdf(fakeExecutable)).rejects.toThrow(StorageError);
      try {
        await storageService.validatePdf(fakeExecutable);
      } catch (err: unknown) {
        expect((err as StorageError).code).toBe('INVALID_FILE_TYPE');
      }
    });

    it('harus menolak berkas kosong atau lebih pendek dari 5 bytes', async () => {
      const emptyBuffer = Buffer.from('');

      await expect(storageService.validatePdf(emptyBuffer)).rejects.toThrow(StorageError);
      try {
        await storageService.validatePdf(emptyBuffer);
      } catch (err: unknown) {
        expect((err as StorageError).code).toBe('INVALID_FILE_TYPE');
      }
    });

    it('harus meloloskan berkas PDF digital valid 1 halaman', async () => {
      const result = await storageService.validatePdf(sampleValid1PagePdf);
      expect(result.pageCount).toBe(1);
      expect(result.fileSize).toBe(sampleValid1PagePdf.length);
    });
  });

  describe('Page Limit & Size Limit Validation [PR-002, PR-003, BR-005]', () => {
    it('harus menolak berkas PDF lebih dari 5 halaman dengan kode PAGE_LIMIT_EXCEEDED', async () => {
      const sixPagesPdf = generateMultiPagePdf(6);

      await expect(storageService.validatePdf(sixPagesPdf)).rejects.toThrow(StorageError);
      try {
        await storageService.validatePdf(sixPagesPdf);
      } catch (err: unknown) {
        expect((err as StorageError).code).toBe('PAGE_LIMIT_EXCEEDED');
      }
    });

    it('harus meloloskan berkas PDF tepat 5 halaman', async () => {
      const fivePagesPdf = generateMultiPagePdf(5);
      const result = await storageService.validatePdf(fivePagesPdf);
      expect(result.pageCount).toBe(5);
    });

    it('harus menolak berkas melebihi 10MB dengan kode PAGE_LIMIT_EXCEEDED / FILE_SIZE_EXCEEDED', async () => {
      // Buat buffer tiruan PDF yang ukurannya 10.5 MB
      const oversizedHeader = Buffer.from('%PDF-1.4\n');
      const oversizedPayload = Buffer.alloc(10.5 * 1024 * 1024, 0x20); // 10.5 MB spasi
      const oversizedBuffer = Buffer.concat([oversizedHeader, oversizedPayload]);

      await expect(storageService.validatePdf(oversizedBuffer)).rejects.toThrow(StorageError);
      try {
        await storageService.validatePdf(oversizedBuffer);
      } catch (err: unknown) {
        expect(['PAGE_LIMIT_EXCEEDED', 'FILE_SIZE_EXCEEDED']).toContain((err as StorageError).code);
      }
    });
  });

  describe('Storage CRUD Operations', () => {
    it('harus berhasil menyimpan berkas PDF lokal dan membacanya kembali', async () => {
      const saveResult = await storageService.saveFile(
        sampleValid1PagePdf,
        'invoice_pt_sample.pdf',
        'invoices'
      );

      expect(saveResult.storageFilePath).toBeDefined();
      expect(saveResult.storageFilePath).toContain('invoices/');
      expect(saveResult.filePageCount).toBe(1);

      // Baca kembali buffer
      const readBuffer = await storageService.getFileBuffer(saveResult.storageFilePath);
      expect(readBuffer.equals(sampleValid1PagePdf)).toBe(true);

      // Baca stream
      const stream = await storageService.getFileStream(saveResult.storageFilePath);
      expect(stream).toBeDefined();
      await new Promise<void>((resolve, reject) => {
        stream.on('data', () => {});
        stream.on('end', () => resolve());
        stream.on('error', reject);
      });

      // Hapus berkas
      await storageService.deleteFile(saveResult.storageFilePath);
      await expect(storageService.getFileBuffer(saveResult.storageFilePath)).rejects.toThrow();
    });
  });
});
