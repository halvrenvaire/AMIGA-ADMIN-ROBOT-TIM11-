---
trigger: model_decision
description: "Struktur direktori monorepo/modular, penamaan berkas, batas modul, dan panduan penempatan kode baru (Fastify & Next.js)."
---

# 02 — Project Structure & Module Boundaries: AMIGA Robot Admin

Seluruh file dan direktori kode MUST mengikuti struktur modular yang terdefinisi di bawah ini untuk menjamin isolasi domain, kemudahan navigasi agen AI, dan kesiapan transisi arsitektur.

## 1. Pohon Direktori Repositori (Unified TypeScript Monorepo)

```
apps-2/
├── .agents/                        # Antigravity project operating system
│   ├── rules/                      # Steering rules (always_on, glob, model_decision)
│   ├── workflows/                  # Executable slash-command procedures
│   └── skills/                     # Domain & design skills
├── storage/                        # Direktori penyimpanan berkas PDF lokal (STORAGE_BACKEND=local)
├── frontend/                       # Next.js 16 Frontend (App Router, Tailwind v4)
│   ├── src/
│   │   ├── app/                    # Route groups terisolasi per peran
│   │   │   ├── (auth)/login/
│   │   │   ├── (dashboard)/queue/          # Layar 01: Antrean & Beban
│   │   │   ├── (intake)/upload/            # Layar 02: Form Unggah
│   │   │   ├── (review)/review/[id]/       # Layar 03: Split Screen
│   │   │   ├── (voucher)/voucher/[id]/     # Layar 04: Pratinjau Voucher
│   │   │   └── (audit)/audit/[id]/         # Layar 05: Jejak Audit
│   │   ├── components/             # Komponen UI modular
│   │   │   ├── ui/                 # Buttons, inputs, modals, status-badge
│   │   │   ├── pdf/                # PDF.js dual-context canvas viewer
│   │   │   └── layout/             # Header, nav, split-container
│   │   ├── hooks/                  # TanStack Query & Zustand stores
│   │   └── lib/                    # API client fetchers, formatters, tokens
│   └── tailwind.config.ts          # Tailwind CSS v4 design tokens
├── backend/                        # Fastify Backend Core (TypeScript)
│   ├── src/
│   │   ├── plugins/                # Fastify plugins (prisma, jwt, rbac, storage)
│   │   ├── routes/                 # Route modules terdaftar per domain
│   │   │   ├── auth.routes.ts
│   │   │   ├── intake.routes.ts
│   │   │   ├── review.routes.ts (SoD check)
│   │   │   ├── voucher.routes.ts
│   │   │   └── audit.routes.ts
│   │   ├── services/               # Domain business logic
│   │   │   ├── bedrock.service.ts      # AWS Bedrock Titan Express & KB
│   │   │   ├── verification.service.ts # 3 aturan verifikasi sistem
│   │   │   ├── review.service.ts       # Transaksi atomik SoD
│   │   │   ├── storage.service.ts      # Local / S3 pluggable storage
│   │   │   └── voucher.service.ts      # Kompilasi PDF resmi
│   │   ├── workers/                # BullMQ background workers
│   │   ├── schemas/                # Skema validasi request & response (ajv / TypeBox)
│   │   └── app.ts                  # Inisialisasi Fastify app instance
│   └── prisma/
│       ├── schema.prisma           # 10 tabel model relasional
│       ├── migrations/             # Migrasi deklaratif PostgreSQL
│       └── seed.ts                 # Seeding script akun & data awal
├── docs/                           # Dokumentasi proyek & SOP
│   ├── requirements/               # BRD, PRD, SRD, DRD, BPMN
│   ├── specs/                      # Analisis (00-analysis), design, tasks, traceability-matrix
│   └── sop/                        # Prosedur operasional standar (SOP)
├── CHANGELOG.md                    # Riwayat perubahan proyek standar Keep a Changelog
└── GEMINI.md                       # Master index & 10 non-negotiable behaviors
```

## 2. Aturan Penamaan (Naming Conventions)
- **Nama Berkas & Direktori**: MUST menggunakan `kebab-case`  
  *Contoh:* `bedrock.service.ts`, `split-screen-editor.tsx`, `status-badge.tsx`.
- **Nama Kelas & Interface**: MUST menggunakan `PascalCase`  
  *Contoh:* `BedrockService`, `InvoiceRequest`, `AuditLogDto`.
- **Tabel & Kolom Database**: MUST menggunakan `snake_case`  
  *Contoh:* `invoice_requests`, `current_reviewer_id`, `subtotal_amount`.
- **Enum & Nilai Status Konstan**: MUST menggunakan `SCREAMING_SNAKE_CASE`  
  *Contoh:* `READY_FOR_REVIEW`, `CALCULATION_DISCREPANCY`, `MISSING_EVIDENCE`.

## 3. Panduan Penempatan Kode Baru (Where New Code Goes)

| Jika Anda Ingin Menambahkan... | Tempatkan File di... | Pola Penulisan Wajib |
| :--- | :--- | :--- |
| Endpoint REST API Baru | `backend/src/routes/<domain>.routes.ts` | Daftarkan Fastify plugin route dengan skema validasi. |
| Aturan Verifikasi Bisnis Baru | `backend/src/services/verification.service.ts` | Tambahkan fungsi validasi murni yang mengembalikan issue code. |
| Integrasi AI / Prompt Baru | `backend/src/services/bedrock.service.ts` | Panggil `@aws-sdk/client-bedrock-runtime` dengan JSON schema. |
| Background Job / Worker Baru | `backend/src/workers/` | Definisikan BullMQ Worker processor terisolasi. |
| Komponen UI Layar | `frontend/src/components/<domain>/` | Pakai token CSS `--color-ink-navy`, `--surface-canvas`. |
| Hook Query / Mutation | `frontend/src/hooks/queries/` | Bungkus via `useQuery` / `useMutation` TanStack Query v5. |
| Skema Database Baru | `backend/prisma/schema.prisma` | Jalankan `prisma migrate dev` dan perbarui `seed.ts`. |

## 4. Wrong vs Right: Penempatan Logika Bisnis di Fastify Route

### WRONG (Logika Transaksi Tercampur di Handler Route)
```typescript
// SALAH: Menempatkan query database dan validasi SoD langsung di route handler
fastify.post('/invoices/:id/approve', async (request, reply) => {
  const { id } = request.params as any;
  const invoice = await prisma.invoiceRequest.findUnique({ where: { id } });
  if (invoice.uploaderId === request.user.id) {
    return reply.status(403).send({ error: 'SoD Error' }); // Logika rapuh
  }
  await prisma.invoiceRequest.update({ where: { id }, data: { status: 'AMIGA_REVIEWED' } });
  return reply.send({ success: true });
});
```

### RIGHT (Handler Bersih Mendelegasikan ke Service Transaksional)
```typescript
// BENAR: Route handler hanya menangani HTTP I/O; logika SoD diisolasi di ReviewService
fastify.post('/invoices/:requestId/approve', {
  preHandler: [fastify.authenticate, fastify.requireRole('FINANCE_REVIEWER')],
  schema: approveInvoiceSchema,
}, async (request, reply) => {
  const { requestId } = request.params;
  const result = await reviewService.approveWithSodCheck(requestId, request.user);
  return reply.status(200).send({ success: true, data: result });
});
```
