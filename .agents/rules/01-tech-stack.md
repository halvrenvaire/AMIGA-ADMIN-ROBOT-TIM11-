---
trigger: always_on
description: "Stack teknologi resmi, versi paket, library yang diizinkan dan dilarang, serta konfigurasi environment."
---

# 01 — Tech Stack & Environment: AMIGA Robot Admin

Seluruh komponen aplikasi MUST mematuhi pilihan teknologi, versi teruji, dan batasan pustaka berikut ini (Unified TypeScript Stack dengan backend Fastify dan AWS Bedrock).

## 1. Stack Teknologi & Versi Terstandar [SR-001, SR-005..010]

| Layer / Komponen | Teknologi Terpilih | Versi Wajib | Rationale Teknis |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | **Next.js (App Router)** | `16.x` (Active LTS / React 19) | Server-Side Rendering untuk SLA antrean <= 2s, Turbopack default bundler, route handlers terisolasi. |
| **Styling & Tokens** | **Vanilla CSS + Tailwind CSS v4** | `4.x` | Desain berwibawa *"Navy Ink on Cool Marble"*, bebas bloat generic CSS. |
| **State Management** | **TanStack Query v5 + Zustand** | `5.x` / `4.x` | TanStack Query untuk server-state/polling; Zustand untuk split-screen UI state. |
| **PDF Viewer Engine** | **PDF.js (Mozilla) / React-PDF** | `latest` | Render canvas cepat di browser, koordinasi zoom, pan, dan sinkronisasi halaman. |
| **Backend Runtime** | **Node.js (Fastify)** | `20 LTS` / Fastify `4.x/5.x` | Arsitektur low-overhead, throughput tinggi (>60k req/s), skema ajv, unified TypeScript. |
| **ORM & Driver** | **Prisma ORM** | `5.x` | End-to-end type safety, migrasi deklaratif, atomic transaction untuk SoD. |
| **Database Primer** | **PostgreSQL** | `16.x` | Integritas ACID data keuangan, ekstensi `pg_trgm` untuk pencocokan duplikat. |
| **Message Broker** | **Redis + BullMQ** | `7.2` / `5.x` | Worker asinkron ekstraksi AI dan kompilasi PDF tanpa memblokir HTTP event loop. |
| **File Storage** | **Pluggable Local & S3 Storage** | Local / AWS SDK v3 | Default `STORAGE_BACKEND=local` (`../storage`) untuk demo cepat; fallback `s3`. |
| **AI Document Engine** | **AWS Bedrock (Titan Text Express)**| SDK v3 (`ap-southeast-1`) | `amazon.titan-text-express-v1` via `@aws-sdk/client-bedrock-runtime` + Mock fallback. |
| **AI Knowledge Base** | **AWS Bedrock Knowledge Base** | SDK v3 | `amazon.titan-embed-text-v1` via `@aws-sdk/client-bedrock-agent-runtime` (Vendor KB). |
| **PDF Text Extractor** | **`pdf-parse` / `unpdf`** | `latest` | Ekstraksi teks in-memory dari PDF digital sebelum diumpankan ke Titan Express. |
| **PDF Generator** | **@react-pdf/renderer** | `3.x` | Kompilasi voucher resmi React-to-PDF berbatas SLA <= 3 detik. |

## 2. Pustaka Diizinkan vs Dilarang (Allowed vs Forbidden Libraries)

### Diizinkan (ALLOWED)
- `@aws-sdk/client-bedrock-runtime` & `@aws-sdk/client-bedrock-agent-runtime` untuk integrasi AWS Bedrock.
- `zod`, `@fastify/type-provider-typebox`, atau `fluent-json-schema` untuk validasi schema Fastify.
- `date-fns` untuk manipulasi tanggal dan waktu.
- `@tanstack/react-query` untuk caching antrean dan auto-refetch.
- `zustand` untuk local UI state split-screen.
- `lucide-react` HANYA untuk ikon garis 1.5px yang fungsional (bukan dekoratif).
- `@prisma/client` untuk query database PostgreSQL.
- `bullmq` untuk manajemen antrean background job.
- `pdf-parse` atau `unpdf` untuk membaca teks PDF digital di Node.js.

### Dilarang Keras (FORBIDDEN)
- **DILARANG** menggunakan Tailwind CSS v3 atau menginstal utility framework lain (wajib Tailwind v4).
- **DILARANG** menggunakan `moment.js` (gunakan `date-fns`).
- **DILARANG** menggunakan `axios` di frontend jika `fetch` bawaan browser dengan TanStack Query sudah memadai.
- **DILARANG** menggunakan komponen UI serbaguna yang membawa style default hitam pekat `#000000` atau gradien neon AI ungu/cyan (pelanggaran `DR-004`).
- **DILARANG** memanggil LLM Bedrock sinkron langsung di HTTP route tanpa worker/asinkron jika berpotensi memblokir throughput.

## 3. Konfigurasi Environment & Secrets (.env)
Seluruh konfigurasi MUST dibaca melalui environment variables terpusat:

```bash
# === DATABASE (PostgreSQL 16) ===
DATABASE_URL="postgresql://postgres:password@localhost:5432/amiga_robot_admin"

# === AUTHENTICATION ===
JWT_SECRET="ganti-dengan-string-acak-panjang-minimum-256-bits"
JWT_EXPIRE_MINUTES=480

# === STORAGE BACKEND ("local" atau "s3") ===
STORAGE_BACKEND="local"
LOCAL_STORAGE_DIR="../storage"

# === SEEDING DEFAULT ===
SEED_DEFAULT_PASSWORD="password123!"

# === AWS & BEDROCK CONFIGURATION ===
AWS_ACCESS_KEY="xxx"
AWS_SECRET_ACCESS_KEY="xxx"
AWS_REGION="ap-southeast-1"
AWS_BUCKET="bedrock-kb-xxx-xxx"

# Text generation model (Titan Text Express)
BEDROCK_MODEL_ID="amazon.titan-text-express-v1"

# Embedding model (Titan Text Embeddings G1)
EMBEDDING_MODEL_ID="amazon.titan-embed-text-v1"

# === CONSTRAINTS & SLA ===
MAX_INVOICE_PAGES=5
WORKLOAD_MAX_THRESHOLD=10
AI_EXTRACTION_TIMEOUT_MS=15000
```

## 4. Wrong vs Right: Penanganan Upload & Ekstraksi Asinkron di Fastify

### WRONG (Memanggil AI Bedrock Sinkron di Route Handler)
```typescript
// SALAH: Menunggu respons AI Bedrock langsung di handler HTTP Fastify
fastify.post('/upload', async (request, reply) => {
  const file = await request.file();
  const text = await extractPdfText(await file.toBuffer());
  const aiResult = await bedrockService.extract(text); // BLOKIR SAMPAI 10 DETIK
  return reply.send({ status: 'DONE', data: aiResult });
});
```

### RIGHT (Simpan Berkas, Terbitkan QUEUED, Enqueue ke Background Worker)
```typescript
// BENAR: Respons instan status QUEUED dan proses ekstraksi didelegasikan ke queue
fastify.post('/upload', async (request, reply) => {
  const data = await intakeService.saveAndQueue(request);
  await aiQueue.add('extract-invoice', { requestId: data.id }, {
    attempts: 2,
    timeout: 15000,
    removeOnComplete: true,
  });
  return reply.status(201).send({
    success: true,
    data: { requestId: data.requestId, status: 'QUEUED' }
  });
});
```
