---
trigger: always_on
description: "Arsitektur guardrails: layering, arah dependensi, pola terlarang, batas isolasi multi-tenant, dan baseline keamanan SRD."
---

# 04 — Architecture Guardrails: AMIGA Robot Admin

Dokumen ini mendefinisikan batasan arsitektur inti (*hard architectural boundaries*). Pelanggaran terhadap guardrails ini diklasifikasikan sebagai cacat arsitektur kritis (CRITICAL DEFECT).

## 1. Arah Ketergantungan & Layering (Dependency Direction)
Arsitektur MUST mematuhi arah aliran dependensi berikut:
`Presentation (Next.js) -> REST API Gateway -> Domain Application Service -> Infrastructure (Prisma DB, BullMQ, MinIO)`
- Domain Services DILARANG bergantung langsung pada HTTP Request/Response objects.
- Komponen Presentasi DILARANG mengakses database atau S3 secara langsung tanpa melalui API Gateway.
- DILARANG menciptakan dependensi melingkar (*circular dependency*) antar-modul.

## 2. Batas Isolasi Multi-Tenant (Multi-Tenant Isolation Boundary) [SR-003, BR-014]
- Setiap query database yang mengambil atau mengubah data invoice MUST menyertakan klausa `client_id` milik pengguna yang terautentikasi:
  `WHERE client_id IN (:allowedClientIds)`
- User Klien A yang mencoba mengakses atau memanipulasi dokumen Klien B MUST ditolak dengan respon `403 Forbidden` atau `404 Not Found`.

## 3. Penegakan Segregation of Duties (SoD) di Server [BR-002, PR-018, SR-004]
- Validasi `uploader_id != reviewer_id` MUST ditegakkan di sisi server di dalam serializable database transaction.
- Menonaktifkan tombol di frontend HANYA berfungsi sebagai pencegah visual, BUKAN pengganti validasi server.
- Jika terjadi pelanggaran SoD: sistem MUST membatalkan transaksi persetujuan, mengalihkan penugasan ke reviewer lain dengan antrean tersedikit (*least-loaded active reviewer*), dan mencatat aksi penolakan ke `audit_logs`.

## 4. Keabadian Jejak Audit (Audit Ledger Immutability) [BR-015, PR-025, SR-016]
- Tabel `audit_logs` bersifat append-only.
- DILARANG mengeksekusi operasi `UPDATE` atau `DELETE` pada tabel `audit_logs` di seluruh service backend.
- Role pengguna database aplikasi HANYA diberikan izin `GRANT SELECT, INSERT ON audit_logs`.

## 5. Batasan Peran AI (AI Scope Restriction) [PR-007, BR-007]
- AI Engine HANYA bertindak sebagai pembaca dokumen (OCR & JSON extraction).
- AI Engine DILARANG memvalidasi aturan bisnis (matematika/duplikasi) dan DILARANG menyetujui transaksi secara otomatis. Seluruh persetujuan voucher wajib ditinjau manusia (*Human-in-the-Loop*).

## 6. Wrong vs Right: Isolasi Multi-Tenant & SoD

### WRONG (Akses Langsung Berdasarkan ID Tanpa Tenant Guard)
```typescript
// SALAH: Mengambil invoice hanya berdasarkan ID; rentan IDOR lintas klien
@Get(':requestId')
async getInvoice(@Param('requestId') reqId: string) {
  return this.prisma.invoiceRequest.findUnique({
    where: { requestId: reqId } // Rentan: Klien A bisa melihat invoice Klien B
  });
}
```

### RIGHT (Query Terisolasi dengan Tenant Boundary)
```typescript
// BENAR: Query secara ketat mengunci akses pada daftar client_id yang diizinkan pengguna
@Get(':requestId')
async getInvoice(@Param('requestId') reqId: string, @CurrentUser() user: UserEntity) {
  const invoice = await this.prisma.invoiceRequest.findFirst({
    where: {
      requestId: reqId,
      clientId: { in: user.allowedClientIds } // Isolasi multi-klien terjamin
    }
  });
  if (!invoice) throw new NotFoundException('Dokumen tidak ditemukan atau akses ditolak.');
  return invoice;
}
```
