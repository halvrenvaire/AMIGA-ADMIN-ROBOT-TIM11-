# AMIGA Robot Admin (Intelligent Vendor Invoice-to-Voucher Processing)

> **Proof of Concept (PoC) - MAIN Hackathon 2026**  
> Unified Full-Stack TypeScript Monorepo: Next.js 16 LTS (Turbopack) &bull; Fastify 5.x &bull; PostgreSQL 16 &bull; Prisma ORM &bull; BullMQ &bull; AWS Bedrock Titan Express

[![Node.js](https://img.shields.io/badge/Node.js-20_LTS-339933?logo=node.js&logoColor=white)](#)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)](#)
[![Fastify](https://img.shields.io/badge/Fastify-5.2-000000?logo=fastify&logoColor=white)](#)
[![Next.js](https://img.shields.io/badge/Next.js-16.4_LTS-000000?logo=next.js&logoColor=white)](#)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](#)
[![Prisma](https://img.shields.io/badge/Prisma-5.22-2D3748?logo=prisma&logoColor=white)](#)
[![Tests Passing](https://img.shields.io/badge/Tests-74%2F74_Passing_100%25-success)](#)
[![Design](https://img.shields.io/badge/Theme-Navy_Ink_on_Cool_Marble-0B3558)](#)

---

## 1. Ikhtisar & Prinsip 5W + 1H

AMIGA Robot Admin adalah platform otomasi cerdas yang bertindak sebagai *Back Office Operating Partner* multi-industri untuk mentransformasikan berkas tagihan invoice vendor (berkas digital PDF maks. 5 halaman) menjadi voucher pembayaran resmi terverifikasi (*invoice-to-voucher*) secara instan, aman, dan patuh regulasi.

```
+-------------------------------------------------------------------------------------------------------+
|                                      PRINSIP 5W + 1H SISTEM AMIGA                                     |
+-------------------------------------------------------------------------------------------------------+
|  WHAT   | Platform otomatisasi intake invoice vendor menjadi voucher pembayaran resmi siap transfer.  |
|  WHY    | Menghapus input manual 10-25 menit/dokumen, mencegah salah transfer, duplikasi, & SoD leak. |
|  WHO    | PIC Klien, Intake Support, Finance Reviewer AMIGA, Service Lead, dan System Admin.          |
|  WHEN   | Setiap kali vendor menerbitkan tagihan digital PDF yang perlu diverifikasi dan dibayarkan.  |
|  WHERE  | Lingkungan web multi-tenant terisolasi (Cloud AWS Bedrock ap-southeast-1 atau on-premises). |
|  HOW    | Siklus 6 status dokumen dengan AI extraction, 3 aturan verifikasi, SoD guard, & audit log.  |
+-------------------------------------------------------------------------------------------------------+
```

### Penjelasan Rinci 5W + 1H

- **What (Apa itu AMIGA Robot Admin)**:  
  Sistem otomasi pemrosesan faktur digital yang membaca dokumen invoice PDF secara in-memory, mengekstrak data finansial (header, line items, nominal, data rekening bank tujuan) menggunakan model pondasi LLM AWS Bedrock Titan Express v1, memverifikasi kepatuhan transaksi, dan mengompilasi berkas voucher PDF resmi dengan batas otorisasi legal permanen.
- **Why (Mengapa aplikasi ini dibangun)**:  
  Proses pemrosesan invoice manual konvensional memiliki tiga kelemahan kritis:
  1. *Inefisiensi Waktu*: Membutuhkan 5–10 menit pengetikan ulang dan 5–15 menit penyusunan voucher per dokumen.
  2. *Risiko Finansial*: Rawan salah ketik nomor rekening/nama bank, salah hitung subtotal/pajak, serta risiko pembayaran ganda (*duplicate payment*).
  3. *Ketiadaan Akuntabilitas*: Tidak memiliki pemisahan tugas (*Segregation of Duties*) yang terbukti di server serta minim jejak audit yang tidak dapat dimanipulasi (*tamper-proof*).
- **Who (Siapa yang menggunakan sistem)**:  
  Sistem melayani 6 peran pengguna manusia dan 2 entitas otomatis:
  - *PIC Klien*: Mengunggah invoice PDF, memperbaiki dokumen berstatus `EXCEPTION`, dan mengunduh voucher resmi.
  - *Intake Support / Backup*: Membantu operasional intake atas penugasan delegasi resmi.
  - *Finance Reviewer AMIGA*: Memeriksa draf pada layar *split-screen*, mengoreksi nilai, dan menyetujui transaksi. Dilarang menyetujui dokumen yang diunggahnya sendiri (Pencegahan SoD).
  - *Service Lead*: Memantau antrean kerja antar-reviewer dan menyeimbangkan alokasi beban kerja (*rebalancing*).
  - *System Admin*: Mengelola akun, peran, dan penugasan delegasi klien.
  - *Client Approver (Eksternal)*: Menyetujui otorisasi pencairan dana akhir di perbankan klien (di luar sistem AMIGA).
  - *AI Engine & AMIGA Core (Otomatis)*: Ekstraksi teks OCR/LLM, evaluasi 3 aturan sistem, dan penerbitan berkas voucher resmi.
- **When (Kapan sistem ini digunakan)**:  
  Digunakan pada jam operasional bisnis saat faktur vendor masuk melalui web portal, email, atau penyerahan digital, hingga voucher pembayaran resmi diserahkan kembali kepada klien untuk dieksekusi pembayarannya.
- **Where (Di mana sistem beroperasi)**:  
  Beroperasi pada arsitektur web modern terisolasi multi-tenant (`WHERE client_id IN (...)`), menjamin data Organisasi Klien A tidak dapat diakses atau diintip oleh Organisasi Klien B.
- **How (Bagaimana siklus hidup 6 status dokumen berjalan)**:  
  Alur dokumen mengikuti state machine atomik tanpa deviasi:
  ```
  [1. QUEUED]            Dokumen PDF diunggah oleh PIC Klien (SLA <= 2s)
        |
  [2. PROCESSING]        AI Titan Express mengekstrak teks ke draf finansial (SLA <= 15s)
        |
  [Verifikasi Sistem]    Sistem mengevaluasi: Rekening (MISSING_EVIDENCE), Duplikasi
        |                (POSSIBLE_DUPLICATE), dan Aritmatika (CALCULATION_DISCREPANCY)
        +----------------------------+
        | (Jika Ada Isu)             | (Jika Lolos Bersih)
        v                            v
  [4. EXCEPTION]               [3. READY_FOR_REVIEW]
  PIC Klien memperbaiki data   Reviewer memeriksa split-screen 50:50, koreksi data,
  dengan Request ID sama.      lalu Approve dengan proteksi SoD (Uploader != Reviewer)
        |                            |
        +----------------------------+
                                     |
                               [5. AMIGA_REVIEWED]
                               Voucher resmi terbit (SLA <= 3s) berbatas legalitas
                                     |
                               [6. SENT_TO_CLIENT]
                               PIC Klien mengunduh voucher PDF resmi (audit logged)
  ```

---

## 2. Arsitektur & Tumpukan Teknologi

Aplikasi dibangun di atas arsitektur **Unified TypeScript Monorepo** yang memisahkan boundary secara jelas antara API Server berkecepatan tinggi dan antarmuka pengguna:

| Lapisan / Modul | Pilihan Teknologi | Versi Teruji | Catatan Arsitektur |
| :--- | :--- | :--- | :--- |
| **Frontend Web** | Next.js (App Router, Turbopack) | `16.4 LTS` / React 19 | SSR antrean cepat, dual-context split-screen, Zustand & TanStack Query v5. |
| **Desain & Token** | Vanilla CSS + Tailwind CSS v4 | `4.x` | Tema *"Navy Ink on Cool Marble"* (`#0B3558`, `#006BFF`, `#F8F9FB`), anti-slop. |
| **Backend Core** | Fastify Framework | `5.2` (Node.js 20 LTS) | Arsitektur skema TypeBox low-overhead (>60k req/s), RFC 7807 error format. |
| **Database Primer** | PostgreSQL 16 + Prisma ORM | `16.x` / `5.22` | Relasi 10 tabel 3NF, isolasi multi-tenant, transaksi atomik serializable. |
| **Antrean Background**| Redis + BullMQ (Resilient fallback)| `7.2` / `5.41` | Pemrosesan ekstraksi asinkron tanpa memblokir HTTP event loop. |
| **AI Document Engine**| AWS Bedrock (Titan Text Express) | SDK v3 (`ap-southeast-1`)| Prompt zero-retention dengan fallback deterministik offline otomatis. |
| **Generator Voucher** | @react-pdf/renderer | `3.4` | Kompilasi voucher resmi React-to-PDF berbatas SLA <= 3 detik (~64ms rata-rata). |
| **Jejak Audit** | Append-Only Ledger (`audit_logs`)| PostgreSQL Table | Immutability ketat, zero update/delete, masking PII nomor rekening bank. |

---

## 3. Konfigurasi Variabel Lingkungan (.env Setup)

Sebelum menjalankan aplikasi, pastikan berkas konfigurasi variabel lingkungan telah disiapkan.

### A. Konfigurasi Backend (`apps-2/backend/.env`)

Salin berkas acuan `apps-2/backend/.env.example` menjadi `apps-2/backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Isi dan sesuaikan variabel berikut di `backend/.env`:

```ini
# =========================================================================
# 1. DATABASE POSTGRESQL 16 (WAJIB)
# Format URL koneksi: postgresql://[user]:[password]@[host]:[port]/[database]
# =========================================================================
DATABASE_URL="postgresql://postgres:password123!@localhost:5432/amiga_robot_admin"

# =========================================================================
# 2. AUTENTIKASI JWT & KEAMANAN (WAJIB)
# Kunci rahasia minimal 256-bit dan masa berlaku token dalam menit (default 8 jam)
# =========================================================================
JWT_SECRET="ganti-dengan-string-acak-panjang-minimum-256-bits-super-secret-amiga-production"
JWT_EXPIRE_MINUTES=480

# =========================================================================
# 3. PENYIMPANAN BERKAS PDF (STORAGE BACKEND)
# Nilai: "local" (disimpan di disk lokal) atau "s3" (disimpan di AWS S3)
# =========================================================================
STORAGE_BACKEND="local"
LOCAL_STORAGE_DIR="../storage"

# =========================================================================
# 4. KREDENSIAL DEFAULT DATABASE SEEDING
# Password default untuk seluruh 6 akun pengujian bawaan
# =========================================================================
SEED_DEFAULT_PASSWORD="password123!"

# =========================================================================
# 5. INTEGRASI AWS BEDROCK (OPSIONAL / AUTO-FALLBACK)
# Jika kredensial AWS tidak diisi, sistem otomatis beralih ke mesin
# Deterministic Mock Fallback sehingga aplikasi tetap berjalan 100% normal.
# =========================================================================
AWS_ACCESS_KEY="kredensial-aws-access-key-anda"
AWS_SECRET_ACCESS_KEY="kredensial-aws-secret-anda"
AWS_REGION="ap-southeast-1"
AWS_BUCKET="bedrock-kb-amiga-documents"
BEDROCK_MODEL_ID="amazon.titan-text-express-v1"
EMBEDDING_MODEL_ID="amazon.titan-embed-text-v1"

# =========================================================================
# 6. BATASAN SISTEM & TARGET SLA OPERASIONAL
# =========================================================================
MAX_INVOICE_PAGES=5
WORKLOAD_MAX_THRESHOLD=10
AI_EXTRACTION_TIMEOUT_MS=15000
```

> [!NOTE]
> **Mode Offline / Tanpa Akun AWS**:  
> Sistem AMIGA Robot Admin dirancang mandiri (*resilient*). Jika Anda tidak memiliki kredensial AWS aktif atau Redis belum menyala, sistem otomatis beralih ke **In-Memory Queue** dan **Deterministic Mock Extractor Engine**. Seluruh 5 layar UI, 22 tugas, dan 8 skenario UAT tetap lulus 100% tanpa memerlukan akses internet ke AWS.

### B. Konfigurasi Frontend (`apps-2/frontend/.env.local`)

Salin berkas acuan `apps-2/frontend/.env.example` menjadi `apps-2/frontend/.env.local`:

```bash
cp frontend/.env.example frontend/.env.local
```

Isi variabel URL endpoint backend API:

```ini
# URL Base Backend Fastify API
NEXT_PUBLIC_API_URL="http://localhost:4000"
```

---

## 4. Panduan Step-by-Step Memulai Aplikasi (Getting Started)

Ikuti langkah-langkah presisi di bawah ini untuk memulai aplikasi dari awal:

### Langkah 1: Prasyarat Sistem
Pastikan perangkat Anda telah terinstal:
- **Node.js**: Versi `20.x LTS` atau lebih baru (`node -v`).
- **pnpm**: Versi `9.x` atau `10.x` (`npm install -g pnpm`).
- **PostgreSQL**: Versi `16.x` aktif pada port `5432`.

### Langkah 2: Instalasi Seluruh Dependensi Monorepo
Jalankan perintah berikut di direktori root `apps-2/`:

```bash
cd apps-2
pnpm install
```

### Langkah 3: Setup Database PostgreSQL & Migrasi Prisma
Pastikan database PostgreSQL dengan nama `amiga_robot_admin` telah dibuat. Lalu jalankan migrasi skema deklaratif:

```bash
# Menjalankan migrasi deklaratif 10 tabel 3NF ke PostgreSQL
pnpm db:migrate
```

*(Atau jika di lingkungan CI/CD / deployment: `pnpm --filter backend db:deploy`)*

### Langkah 4: Eksekusi Seeding Data Multi-Peran & Multi-Klien
Jalankan skrip seed idempotent untuk mengisi organisasi klien awal dan akun pengujian multi-peran:

```bash
pnpm db:seed
```

### Langkah 5: Menjalankan Development Server (Full-Stack)
Jalankan backend Fastify dan frontend Next.js secara simultan menggunakan Turbo:

```bash
pnpm dev
```

Sistem akan aktif pada alamat berikut:
- **Frontend Next.js**: [http://localhost:3000](http://localhost:3000)
- **Backend Fastify API**: [http://localhost:4000](http://localhost:4000)
- **Health Check Endpoint**: [http://localhost:4000/health](http://localhost:4000/health)

---

## 5. Akun Pengujian Bawaan (Default Test Accounts)

Skrip seeding telah menyiapkan akun terdaftar untuk setiap peran pengguna. Seluruh akun menggunakan password bawaan: `password123!`

| Role / Peran | Alamat Email Login | Akses Organisasi Klien | Kewenangan Utama |
| :--- | :--- | :--- | :--- |
| **PIC Klien** | `pic_client@amiga.co.id` | PT Klien Mandiri Utama (`CLI-MAIN`) | Unggah invoice PDF, perbaiki dokumen `EXCEPTION`, unduh voucher resmi. |
| **Intake Support** | `intake_support@amiga.co.id` | Multi-Klien (`CLI-MAIN`, `CLI-001`) | Mengunggah invoice digital atas nama klien yang didelegasikan. |
| **Finance Reviewer 1** | `reviewer1@amiga.co.id` | Internal AMIGA (Semua Klien) | Peninjauan split-screen, koreksi rincian line item, setujui dokumen (SoD Guard). |
| **Finance Reviewer 2** | `reviewer2@amiga.co.id` | Internal AMIGA (Semua Klien) | Reviewer alternatif penampung dokumen auto-reassignment SoD. |
| **Service Lead** | `service_lead@amiga.co.id` | Internal AMIGA (Manajemen) | Memantau dashboard beban kerja antrean reviewer dan rebalancing tugas. |
| **System Admin** | `sysadmin@amiga.co.id` | Sistem Penuh | Konfigurasi sistem dan manajemen master data akun delegasi. |

---

## 6. Verifikasi Kualitas & Eksekusi Suite Pengujian Otomatis

Seluruh modul dilengkapi pengujian integrasi otomatis menyeluruh tanpa kompromi:

### Menjalankan Rangkaian Pengujian Lengkap (74 Tests)
```bash
# Menjalankan seluruh 11 test suite backend Fastify
pnpm --filter backend test
```
*Hasil: 11 test files passed, 74 passed (100% green).*

### Menjalankan Suite Pengujian End-to-End 8 Skenario UAT Resmi
Suite pengujian otomatis yang memverifikasi 8 skenario UAT resmi (`backend/test/e2e/uat-scenarios.e2e.test.ts`):

```bash
pnpm test:e2e
```

| Kode Skenario | Skenario Pengujian UAT Resmi | Verifikasi Sistem |
| :--- | :--- | :--- |
| **`UAT-01`** | **Happy Path End-to-End** | Unggah digital PDF -> AI extract -> review data -> approval reviewer -> voucher PDF resmi terbit. |
| **`UAT-02`** | **Kelengkapan Rekening Kosong** | Deteksi invoice tanpa nomor rekening bank, otomatis ditandai `EXCEPTION (MISSING_EVIDENCE)`. |
| **`UAT-03`** | **Pencegahan Pembayaran Ganda** | Deteksi invoice kedua dengan vendor & nomor faktur identik pada klien yang sama -> flag `POSSIBLE_DUPLICATE`. |
| **`UAT-04`** | **Discrepansi Perhitungan Angka** | Selisih total invoice vs penjumlahan line item + PPN 11% otomatis ditandai `CALCULATION_DISCREPANCY`. |
| **`UAT-05`** | **Penegakan Server-Side SoD** | Reviewer dilarang menyetujui dokumen yang diunggahnya sendiri. Transaksi ditolak respon `403 Forbidden` (`SOD_VIOLATION`). |
| **`UAT-06`** | **Auto-Reassignment Dokumen** | Pasca pelanggaran SoD, dokumen otomatis dialihkan ke reviewer aktif dengan antrean tersedikit (`reviewer2`). |
| **`UAT-07`** | **Alur Koreksi PIC Klien** | PIC melengkapi rekening pada dokumen `EXCEPTION` via `PUT /correct`. Request ID tetap sama persis, status berlanjut hingga selesai. |
| **`UAT-08`** | **Unduh Voucher Resmi** | PIC Klien mengunduh voucher PDF resmi via stream `GET /voucher/download`, status otomatis bermutasi menjadi `SENT_TO_CLIENT`. |

### Verifikasi Kompilasi Produksi (Production Build & Typecheck)
```bash
# Kompilasi frontend Next.js 16 (Turbopack) & backend Fastify TypeScript
pnpm build
```

---

## 7. Peta Antarmuka 5 Layar Utama (Layar 01 s/d Layar 05)

1. **Layar 01: Dashboard Antrean & Monitoring Beban Kerja** (`/queue`):
   - Tabel antrean real-time (polling interval 5 detik TanStack Query).
   - Metrik kartu status (`QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `EXCEPTION`, `AMIGA_REVIEWED`, `SENT_TO_CLIENT`).
   - Widget pemantauan kapasitas reviewer aktif dengan indikator ambang batas `WORKLOAD_MAX_THRESHOLD`.
2. **Layar 02: Formulir Pengunggahan Dokumen Intake** (`/upload`):
   - Zona drag-and-drop berkas digital PDF (maks. 5 halaman, maks. 10MB) dengan validasi magic bytes.
   - Isian metadata pengajuan (Organisasi Klien, Jenis Tagihan, Saluran Penyerahan, Tanggal).
   - Penerbitan Request ID unik instan berformat `REQ-YYYYMMDD-XXXXX`.
3. **Layar 03: Peninjauan Dual-Context Split-Screen 50:50** (`/review/[id]`):
   - Panel kiri: Pratinjau berkas PDF digital asli (canvas zoom, fit-to-width, navigasi halaman).
   - Panel kanan: Editor rincian line item interaktif dengan kalkulasi matematika live subtotal, pajak, dan grand total.
   - Peringatan banner kendala verifikasi dan tombol aksi Approve / Kembalikan.
4. **Layar 04: Pratinjau & Alur Unduh Berkas Voucher Resmi** (`/voucher/[id]`):
   - Pratinjau tata letak resmi voucher pembayaran bernomor `VCH/YYYYMM/CLI/XXXXX`.
   - Kalimat nominal terbilang otomatis bahasa Indonesia.
   - Klausul batas otorisasi legal permanen verbatim.
   - Tombol unduh berkas PDF resmi (memicu mutasi atomik ke `SENT_TO_CLIENT`).
5. **Layar 05: Garis Waktu Riwayat & Jejak Audit** (`/audit/[id]`):
   - Visualisasi garis waktu kronologis vertikal tidak dapat diubah (*immutable ledger*).
   - Badge peran aktor, nama, alamat IP, dan waktu presisi detik WIB.
   - Panel diff viewer delta perbandingan nilai lama (*merah/line-through*) vs nilai baru (*hijau*).
   - Sensor PII nomor rekening bank (`8800****33`).
   - Ekspor laporan jejak audit ke format CSV dan JSON terstruktur.

---

## 8. Ketertelusuran Spesifikasi & Dokumen Acuan

Seluruh implementasi terikat oleh dokumen acuan spesifikasi hulu-hilir:
- **Master Index & 10 Aturan Tanpa Kompromi**: [`GEMINI.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/GEMINI.md)
- **Katalog Kebutuhan Ber-ID Stabil**: [`docs/specs/00-analysis.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/00-analysis.md)
- **Desain Sistem & Kontrak REST RFC 7807**: [`docs/specs/system-design.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/system-design.md)
- **Pelacak Tugas Target (T-001 s/d T-022)**: [`docs/specs/tasks.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/tasks.md)
- **Matriks Ketertelusuran Dua Arah**: [`docs/specs/traceability-matrix.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/traceability-matrix.md)
- **Riwayat Perubahan Proyek**: [`CHANGELOG.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/CHANGELOG.md)
- **Dokumen Kebutuhan Bisnis & Desain**:
  - [`01-BRD.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/requirements/01-BRD.md)
  - [`02-PRD.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/requirements/02-PRD.md)
  - [`03-SRD.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/requirements/03-SRD.md)
  - [`04-DRD.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/requirements/04-DRD.md)
  - [`05-BPMN.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/requirements/05-BPMN.md)

---

## 9. Lisensi & Hak Cipta

Proyek ini dikembangkan secara eksklusif untuk ajang **MAIN Hackathon 2026** oleh Tim Pengembang AMIGA Robot Admin. Seluruh hak cipta dan merek dagang dilindungi undang-undang.
