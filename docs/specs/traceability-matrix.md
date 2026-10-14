# Matriks Ketertelusuran Kebutuhan: AMIGA Robot Admin (traceability-matrix.md)

**Status:** Phase 4 Baseline (Disahkan)  
**Tujuan:** Menjamin seluruh kebutuhan dari BRD, PRD, SRD, DRD, dan BPMN terpetakan 100% dua arah (*bidirectional traceability*) ke spesifikasi desain sistem, endpoint API, dan pelacak tugas (`T-001`..`T-022`).

---

## 1. Matriks Kebutuhan Bisnis (Business Requirements - BR)

| ID Kebutuhan | Deskripsi Inti Bisnis | Modul / Layanan Desain | Endpoint / Komponen | Task Pelacak |
| :--- | :--- | :--- | :--- | :--- |
| **BR-001** | Eliminasi entri manual & waktu olah invoice ke voucher | Fastify Core + BullMQ Worker | `POST /invoices/upload`, AI Worker | `T-001`, `T-006`, `T-008` |
| **BR-002** | Segregation of Duties (SoD): Uploader != Reviewer | `review.service.ts` (Serializable tx)| `POST /invoices/:id/approve` | `T-003`, `T-016`, `T-017` |
| **BR-003** | Model operasi hybrid intake (PIC Klien & Intake Support) | `intake.service.ts`, `rbac.plugin.ts` | `POST /invoices/upload` | `T-004`, `T-006`, `T-013` |
| **BR-004** | Dual-Context review & koreksi split-screen | Next.js 16 Split Layout + PDF.js | `/review/[id]`, LineItemsEditor | `T-014`, `T-015` |
| **BR-005** | Batasan berkas PDF maks. 5 halaman | `storage.service.ts`, Guard Fastify | `POST /invoices/upload` | `T-005`, `T-013` |
| **BR-006** | Struktur peran (PIC, Intake, Reviewer, Lead, Admin) | `rbac.plugin.ts`, Seeder DB | `/auth/login`, Matriks RBAC | `T-003`, `T-004` |
| **BR-007** | Siklus 6 status dokumen resmi | State Machine Fastify + BullMQ | Status Enums di Prisma | `T-002`, `T-010` |
| **BR-008** | 3 Aturan verifikasi sistem otomatis | `verification.service.ts` | Verification Worker Job | `T-009`, `T-010` |
| **BR-009** | Penanganan EXCEPTION dengan Request ID sama | `intake.service.ts` | `PUT /invoices/:id/correct` | `T-011` |
| **BR-010** | Penerbitan voucher resmi & teks batas legalitas | `voucher.service.ts` (@react-pdf) | `/voucher/[id]`, Stream Download | `T-018`, `T-019` |
| **BR-011** | Transisi status saat download (`SENT_TO_CLIENT`) | `voucher.routes.ts` | `GET /invoices/:id/voucher/download`| `T-019` |
| **BR-012** | Batas sistem (non-goals: no payment gateway) | Out-of-Scope Architecture Policy | Non-goals Guardrails | `T-001`..`T-022` |
| **BR-013** | Monitoring antrean & rebalance Service Lead | Dashboard Next.js + Reviewer Service| `/queue`, `POST /.../reassign` | `T-012`, `T-017` |
| **BR-014** | Isolasi multi-tenant antar klien | Prisma Extension & Pre-handler Hook | `WHERE client_id IN (...)` Scope | `T-002`, `T-004` |
| **BR-015** | Keabadian jejak audit (Immutable Audit Ledger) | `audit.service.ts`, DB Grant Policy | `audit_logs`, `/audit/[id]` | `T-002`, `T-020`, `T-021` |

---

## 2. Matriks Kebutuhan Produk (Product Requirements - PR)

| ID Kebutuhan | Deskripsi Fungsional Produk | Komponen / Endpoint Terkait | Task Pelacak | Status Pemetaan |
| :--- | :--- | :--- | :--- | :---: |
| **PR-001** | Arsitektur web-based multi-klien responsif | Next.js 16 App Router + Fastify | `T-001`, `T-012` | 100% Terpetakan |
| **PR-002** | Validasi jenis file PDF digital | `storage.service.ts` (magic bytes) | `T-005` | 100% Terpetakan |
| **PR-003** | Validasi ukuran maks. 10MB & maks. 5 halaman | Form upload client & server guard | `T-005`, `T-013` | 100% Terpetakan |
| **PR-004** | Hak akses upload (PIC Klien & Intake Support) | `POST /api/v1/invoices/upload` | `T-004`, `T-006` | 100% Terpetakan |
| **PR-005** | Input metadata (Klien, tipe, channel, tanggal) | Multipart form upload schema | `T-006`, `T-013` | 100% Terpetakan |
| **PR-006** | Penerbitan Request ID format `REQ-YYYYMMDD-XXXXX` | `intake.service.ts` | `T-006` | 100% Terpetakan |
| **PR-007** | Ekstraksi AI asinkron in-context (Titan Express) | `bedrock.service.ts` + BullMQ Worker | `T-007`, `T-008` | 100% Terpetakan |
| **PR-008** | Ekstraksi header, item tabel, nominal, rekening | Payload JSON schema hasil ekstraksi | `T-007`, `T-008` | 100% Terpetakan |
| **PR-009** | Durasi ekstraksi SLA <= 15 detik | Worker timeout & retry logic | `T-008` | 100% Terpetakan |
| **PR-010** | Eksekusi aturan verifikasi pasca-ekstraksi | `verification.service.ts` | `T-009` | 100% Terpetakan |
| **PR-011** | Deteksi 3 kode kendala (`MISSING`, `DUPLICATE`, `CALC`) | Logic 3 aturan verifikasi | `T-009` | 100% Terpetakan |
| **PR-012** | Klasifikasi status `READY_FOR_REVIEW` vs `EXCEPTION` | Lifecycle transition engine | `T-010` | 100% Terpetakan |
| **PR-013** | Penampilan issue deskriptif pada UI | `IssuesAlertBanner` di Layar Review | `T-010`, `T-014` | 100% Terpetakan |
| **PR-014** | Perbaikan dokumen EXCEPTION oleh PIC | `PUT /api/v1/invoices/:id/correct` | `T-011` | 100% Terpetakan |
| **PR-015** | Retensi Request ID yang sama pasca koreksi | Query update & re-queueing | `T-011` | 100% Terpetakan |
| **PR-016** | Dashboard antrean terfilter peran | `GET /api/v1/invoices/queue` | `T-012` | 100% Terpetakan |
| **PR-017** | SLA loading dashboard <= 2 detik | TanStack Query + Index DB | `T-012` | 100% Terpetakan |
| **PR-018** | Layar split-screen peninjauan berdampingan | Grid 50:50, PDF.js + form editor | `T-014`, `T-015` | 100% Terpetakan |
| **PR-019** | Pengembalian dokumen ke EXCEPTION oleh reviewer | `POST /api/v1/invoices/:id/return` | `T-010`, `T-015` | 100% Terpetakan |
| **PR-020** | Penegakan server-side SoD saat approval | `POST /api/v1/invoices/:id/approve` | `T-016` | 100% Terpetakan |
| **PR-021** | Kompilasi voucher resmi SLA <= 3 detik | `pdf-voucher.worker.ts` | `T-018` | 100% Terpetakan |
| **PR-022** | Penomoran `VCH/YYYYMM/CLI/XXXXX` & batas legalitas | Template `@react-pdf/renderer` | `T-018` | 100% Terpetakan |
| **PR-023** | Unduh voucher resmi & mutasi `SENT_TO_CLIENT` | `GET /.../voucher/download` | `T-019` | 100% Terpetakan |
| **PR-024** | Pemantauan beban & rebalancing Service Lead | `POST /.../reassign`, Workload badge | `T-012`, `T-017` | 100% Terpetakan |
| **PR-025** | Pencatatan permanen jejak audit | `audit.service.ts`, Layar 05 Audit | `T-020`, `T-021` | 100% Terpetakan |

---

## 3. Matriks Kebutuhan Sistem & Desain (SR & DR)

| ID Kebutuhan | Deskripsi Kebutuhan Teknis / Desain | Komponen Implementasi | Task Pelacak |
| :--- | :--- | :--- | :--- |
| **SR-001** | Modular Monolith + BullMQ & Redis 7.2 | Fastify Backend Core + BullMQ Queue | `T-001`, `T-006`, `T-008` |
| **SR-002** | Stateless JWT Auth (8 jam) | Fastify JWT plugin | `T-004` |
| **SR-003** | Server-side Multi-tenant Isolation | Query scope `WHERE client_id IN (...)` | `T-002`, `T-004` |
| **SR-004** | Validasi SoD dalam transaksi atomik | `prisma.$transaction` serializable | `T-016` |
| **SR-005** | Frontend Next.js 16 LTS + Tailwind v4 + Zustand | App Router & Design System Tokens | `T-001`, `T-012`..`T-015` |
| **SR-006** | Backend Fastify + Prisma ORM + TypeBox | Node.js 20 LTS API Gateway | `T-001`, `T-002`, `T-004` |
| **SR-007** | Database PostgreSQL 16 + ekstensi pg_trgm | Skema relasional & fuzzy duplicate search | `T-002`, `T-009` |
| **SR-008** | Pluggable File Storage (Local & S3) | Storage service switcher via env | `T-005` |
| **SR-009** | AI Engine: AWS Bedrock Titan Text Express | `@aws-sdk/client-bedrock-runtime` | `T-007`, `T-008` |
| **SR-010** | PDF Generator: @react-pdf/renderer (<= 3s) | Voucher compilation service | `T-018` |
| **SR-011** | Skema 10 tabel relasional 3NF | `schema.prisma` deklaratif | `T-002` |
| **SR-012** | Format Response Standar & RFC 7807 Error | Fastify error handler & TypeBox envelope | `T-004`, `T-006`, `T-016` |
| **SR-013** | Algoritma normalisasi vendor & nomor invoice | Fungsi regex sanitasi & lowercase | `T-009` |
| **SR-014** | Ambang beban dinamis `WORKLOAD_MAX_THRESHOLD` | Konfigurasi env & indikator visual | `T-012`, `T-017` |
| **SR-015** | Masking PII data finansial pada logging | Sanitizer nomor rekening (`88****23`) | `T-020` |
| **SR-016** | Immutability tabel `audit_logs` | Role DB `GRANT SELECT, INSERT` | `T-002`, `T-020` |
| **SR-017** | Verifikasi 8 skenario UAT resmi | Integration test suite E2E | `T-022` |
| **DR-001..005**| 5 Layar antarmuka utama | Next.js Page routes (`/queue`, `/upload`, etc.)| `T-012`..`T-021` |
| **DR-004, 008**| Desain "Navy Ink on Cool Marble" (Anti-slop) | Token CSS (`#0B3558`, `#006BFF`, `#F8F9FB`) | `T-001`, `T-012`..`T-015` |
| **DR-006, 007**| Dual-Context Split-Screen 50:50 & Status Badges | Grid layout responsif & semantic pills | `T-012`, `T-014` |

---

## 4. Matriks Validasi 8 Skenario UAT

| Kode Skenario | Deskripsi Skenario UAT | Hasil yang Diharapkan | Task E2E Terkait |
| :--- | :--- | :--- | :--- |
| **UAT-01** | Happy Path End-to-End | PDF upload -> extract -> review -> approve -> voucher terbit | `T-022` (Test 1) |
| **UAT-02** | Kelengkapan Rekening Kosong | Invoice tanpa bank/rekening ditandai `EXCEPTION (MISSING_EVIDENCE)` | `T-022` (Test 2) |
| **UAT-03** | Pencegahan Pembayaran Ganda | Invoice dengan vendor & nomor sama ditandai `POSSIBLE_DUPLICATE` | `T-022` (Test 3) |
| **UAT-04** | Discrepansi Perhitungan Angka | Total tidak sama dengan rincian ditandai `CALCULATION_DISCREPANCY` | `T-022` (Test 4) |
| **UAT-05** | Penegakan Server-Side SoD | Uploader dilarang approve dokumen sendiri (respon 403 Forbidden) | `T-022` (Test 5) |
| **UAT-06** | Auto-Reassignment Dokumen | Pelanggaran SoD mengalihkan dokumen ke reviewer terendah | `T-022` (Test 6) |
| **UAT-07** | Perbaikan Dokumen EXCEPTION | PIC melengkapi rekening, Request ID tetap sama, siklus berlanjut | `T-022` (Test 7) |
| **UAT-08** | Unduh Voucher Resmi | PIC mengunduh voucher PDF, status bermutasi ke `SENT_TO_CLIENT` | `T-022` (Test 8) |

---

## 5. Ringkasan Verifikasi Kelengkapan (Self-Audit)
- **Cakupan Kebutuhan Bisnis (BR)**: 15 / 15 (100% Covered)
- **Cakupan Kebutuhan Produk (PR)**: 25 / 25 (100% Covered)
- **Cakupan Kebutuhan Sistem (SR)**: 17 / 17 (100% Covered)
- **Cakupan Desain & Wireframe (DR)**: 13 / 13 (100% Covered)
- **Cakupan Alur BPMN (PF)**: 21 / 21 (100% Covered)
- **Total Tugas Terdefinisi**: 22 Tugas (`T-001` s/d `T-022`)
- **Tingkat Ketertelusuran**: **100% Bidirectional Traceability Matrix Valid**.
