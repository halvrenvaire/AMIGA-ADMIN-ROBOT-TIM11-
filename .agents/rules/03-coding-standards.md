---
trigger: glob
globs: "**/*.{ts,tsx,js,jsx}"
description: "Standar penulisan kode TypeScript/React: typing, error handling RFC 7807, logging, API conventions, dan migrasi database."
---

# 03 — Coding Standards: AMIGA Robot Admin

Aturan ini berlaku untuk seluruh berkas kode TypeScript (`.ts`, `.tsx`). Seluruh kode MUST mematuhi standar pengetikan, penanganan error, sanitasi data, dan konvensi API di bawah ini.

## 1. Type Safety & Strict Typing (Dilarang Menggunakan `any`)
- **DILARANG KERAS** menggunakan tipe `any`. Jika tipe dinamis diperlukan, gunakan `unknown` dengan type-guard atau skema validasi TypeBox / Zod.
- Seluruh DTO request dan response API MUST memiliki interface atau class TypeScript yang terdefinisi secara eksplisit.
- Nilai status dan kode kendala MUST menggunakan `enum` atau `const assertion` (`as const`), bukan string mentah.

## 2. Standar Error Handling (RFC 7807 Problem Details) [SR-012]
Seluruh penanganan kesalahan pada API MUST menghasilkan format standar RFC 7807:
```json
{
  "success": false,
  "statusCode": 403,
  "error": {
    "code": "SOD_VIOLATION",
    "message": "Segregation of Duties: Anda tidak dapat menyetujui dokumen yang Anda unggah sendiri.",
    "details": { "uploaderId": "uuid-1", "actionTaken": "Auto-reassigned" }
  },
  "timestamp": "2026-10-13T14:30:00.000Z"
}
```

## 3. Konvensi Database & Transaksi Atomik [SR-004, SR-011]
- Setiap operasi yang mengubah status dokumen, penugasan reviewer, atau pembuatan voucher MUST dieksekusi di dalam `prisma.$transaction`.
- Foreign key pada tabel relasional MUST memiliki indeks database pendukung untuk mencegah full table scan.
- Perubahan skema database HANYA boleh dilakukan melalui migrasi resmi Prisma (`prisma migrate dev`). Dilarang memodifikasi skema langsung di database production.

## 4. Keamanan Data & PII Masking pada Logging [SR-015]
- DILARANG mencetak data sensitif finansial (nomor rekening bank lengkap, token auth, password hash) pada console log.
- Gunakan fungsi masking saat mencatat nomor rekening pada log: `accountNumber.slice(0, 2) + '****' + accountNumber.slice(-2)`.

## 5. Wrong vs Right: Type Safety & Penanganan Error

### WRONG (Penggunaan `any` dan Error Mentah)
```typescript
// SALAH: Tipe any, status code generik 500, error message teknis bocor ke client
export async function handleApproval(req: any, res: any) {
  try {
    const data: any = req.body;
    if (data.reviewerId === data.uploaderId) {
      return res.status(500).json({ err: "DB integrity check failed on user match" });
    }
  } catch (e: any) {
    return res.status(500).send(e.message);
  }
}
```

### RIGHT (Strict Fastify Schema, TypeBox, RFC 7807)
```typescript
// BENAR: Type safety ketat dengan Fastify TypeBox, skema tervalidasi ajv
import { Type, Static } from '@sinclair/typebox';

export const ApproveInvoiceParamsSchema = Type.Object({
  requestId: Type.String({ format: 'uuid' }),
});
export type ApproveInvoiceParams = Static<typeof ApproveInvoiceParamsSchema>;

export function createSodViolationError(uploaderId: string, reassignedReviewerId: string) {
  const err = new Error('Pemisahan Tugas: Penyetuju tidak boleh sama dengan pengunggah dokumen.') as any;
  err.statusCode = 403;
  err.code = 'SOD_VIOLATION';
  err.details = { uploaderId, reassignedReviewerId };
  return err;
}
```

## 6. Wrong vs Right: Mutasi Data & Jejak Audit

### WRONG (Update Data Tanpa Mencatat Jejak Audit)
```typescript
// SALAH: Mengubah nominal tanpa mencatat nilai lama dan nilai baru ke audit_logs
await prisma.invoiceRequest.update({
  where: { id: invoiceId },
  data: { totalAmount: newTotal },
});
```

### RIGHT (Transaksi Bersama Pencatatan Audit)
```typescript
// BENAR: Mengupdate nilai di dalam transaksi sekaligus menulis record audit immutable
await prisma.$transaction(async (tx) => {
  const current = await tx.invoiceRequest.findUniqueOrThrow({ where: { id: invoiceId } });
  
  await tx.invoiceRequest.update({
    where: { id: invoiceId },
    data: { totalAmount: newTotal },
  });

  await tx.auditLog.create({
    data: {
      requestId: invoiceId,
      actorId: user.id,
      actorName: user.fullName,
      actorRole: user.role,
      actionType: 'FIELD_VALUE_MODIFIED',
      changeDiff: {
        field: 'total_amount',
        old_value: current.totalAmount,
        new_value: newTotal,
      },
    },
  });
});
```
