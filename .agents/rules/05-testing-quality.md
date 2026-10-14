---
trigger: glob
globs: "**/*.{test,spec}.*,**/tests/**"
description: "Disiplin pengujian mutu: piramida tes, target cakupan, konvensi penamaan, skenario wajib per task, dan Definition of Done."
---

# 05 — Testing & Quality Standards: AMIGA Robot Admin

Seluruh perubahan kode MUST menyertakan pengujian otomatis yang dapat diverifikasi secara mandiri. Kualitas dan integritas finansial diverifikasi melalui piramida tes berikut.

## 1. Piramida Pengujian & Target Cakupan (Coverage Targets)

| Tingkat Pengujian | Cakupan Area | Target Coverage | Alat Uji |
| :--- | :--- | :--- | :--- |
| **Unit Tests** | Business Verification Engine (3 aturan), normalisasi string, kalkulator pajak/total, formatters. | **100% Branch Coverage** | Vitest / Jest |
| **Integration Tests** | Atomic SoD transaction, isolasi multi-tenant query, worker BullMQ, upload S3/MinIO. | **100% Critical Paths** | Vitest + Testcontainers (Postgres, Redis) |
| **End-to-End Tests** | 8 Skenario UAT Hackathon dari intake hingga unduh voucher resmi. | **100% 8 Skenario Lolos** | Playwright / Supertest |
| **Global Target** | Rata-rata cakupan kode aplikasi secara keseluruhan. | **Minimal >= 80%** | Vitest Coverage |

## 2. Pemetaan 8 Skenario Uji Penerimaan Wajib (UAT Scenarios) [BRD 8.0, PRD 8.0]
Setiap tugas implementasi yang menyentuh alur dokumen MUST memverifikasi skenario terkait:
1. **UAT-1 (Alur Normal)**: Unggah PDF -> AI Ekstrak -> Lolos Verifikasi -> Reviewer Setujui -> Unduh Voucher (`SENT_TO_CLIENT`).
2. **UAT-2 (Multi-line Items)**: Invoice dengan >= 3 jenis barang terbaca lengkap dan total terhitung benar secara matematis.
3. **UAT-3 (Missing Evidence)**: Invoice tanpa nomor rekening bank ditandai `MISSING_EVIDENCE` dan status menjadi `EXCEPTION`.
4. **UAT-4 (Deteksi Duplikasi)**: Invoice dengan vendor & nomor yang sama ditandai `POSSIBLE_DUPLICATE` dan status menjadi `EXCEPTION`.
5. **UAT-5 (Segregation of Duties)**: User A mengunggah lalu mencoba menyetujui -> sistem menolak dan otomatis mengalihkan tugas ke reviewer lain.
6. **UAT-6 (Isolasi Multi-Klien)**: User Klien A mencoba membuka dokumen Klien B -> ditolak sepenuhnya (`403 Forbidden` / `404 Not Found`).
7. **UAT-7 (Penelusuran Audit)**: Reviewer mengubah nominal pada split-screen -> sistem mencatat nilai lama, baru, nama, dan waktu ke `audit_logs`.
8. **UAT-8 (Perbaikan Dokumen)**: PIC Klien memperbaiki kendala dokumen EXCEPTION -> diproses ulang dengan **Request ID yang sama**.

## 3. Konvensi Penamaan Berkas Tes
- Unit Test: `*.spec.ts` (misal: `verification-engine.spec.ts`)
- Integration Test: `*.integration.spec.ts` (misal: `sod-enforcement.integration.spec.ts`)
- Format Penamaan Test Case: `it('should <hasil yang diharapkan> when <kondisi pemicu>')`

## 4. Definition of Done (DoD)
Sebuah tugas atau user story dinyatakan **SELESAI (DONE)** hanya jika:
1. Kode bebas dari error compiler TypeScript (`tsc --noEmit` lolos).
2. Lolos seluruh unit test dan integration test terkait tanpa regresi.
3. Seluruh skenario UAT yang terikat dinyatakan PASS dengan bukti audit log.
4. Tidak ada hardcoded credentials atau pelanggaran isolasi multi-tenant.
5. Task tracker pada `docs/specs/tasks.md` dan `CHANGELOG.md` telah diperbarui.

## 5. Wrong vs Right: Pola Pengujian Segregation of Duties

### WRONG (Pengujian Palsu / Mocking Logika Utama)
```typescript
// SALAH: Me-mock controller sehingga logika transaksi database SoD tidak benar-benar diuji
it('should reject same user approval', async () => {
  const serviceMock = { approve: vi.fn().mockRejectedValue(new Error('SoD Error')) };
  await expect(serviceMock.approve()).rejects.toThrow(); // Tes rapuh, tidak memvalidasi DB
});
```

### RIGHT (Integration Test Transaksi Sebenarnya)
```typescript
// BENAR: Menguji eksekusi atomik database bahwa uploader_id == reviewer_id ditolak dan dialihkan
it('should reject approval and reassign when reviewer is the uploader', async () => {
  const uploader = await createTestUser({ role: Role.FINANCE_REVIEWER });
  const otherReviewer = await createTestUser({ role: Role.FINANCE_REVIEWER });
  const invoice = await createTestInvoice({ uploaderId: uploader.id, status: 'READY_FOR_REVIEW' });

  await expect(
    reviewService.approveWithSodCheck(invoice.requestId, uploader)
  ).rejects.toThrow(SodViolationException);

  const updatedInvoice = await prisma.invoiceRequest.findUnique({ where: { id: invoice.id } });
  expect(updatedInvoice.currentReviewerId).toBe(otherReviewer.id); // Terbukti dialihkan
  expect(updatedInvoice.status).toBe('READY_FOR_REVIEW');

  const auditLog = await prisma.auditLog.findFirst({
    where: { requestId: invoice.id, actionType: 'SOD_REJECT_AND_REASSIGN' }
  });
  expect(auditLog).toBeDefined();
});
```
