# SYSTEM REQUIREMENTS DOCUMENT (SRD)

**AMIGA Robot Admin: Intelligent Vendor Invoice-to-Voucher Processing**

| Atribut Dokumen | Rincian Spesifikasi |
| :--- | :--- |
| **Versi Dokumen** | v1.0 (Arsitektur & Spesifikasi Teknis Lengkap) |
| **Tanggal Efektif** | 13 Oktober 2026 |
| **Status Dokumen** | Approved for Implementation (Sprint 0 - Sprint 3) |
| **Dokumen Acuan** | BRD v1.1, PRD v1.1, BPMN AMIGA_Robot_Admin_Invoice_to_Voucher |
| **Peran Penulis** | Lead Systems Architect & Technical Lead (Team 11 MAIN) |
| **Target Rilis** | MAIN Hackathon 2026 / Demo Day Milestone |

---

## 1. Arsitektur Sistem & Desain Komponen

### 1.1 Pola Arsitektur (Architecture Pattern)
Sistem dirancang menggunakan pendekatan **Modular Monolith dengan Event-Driven Background Worker**. Pola ini dipilih secara sadar untuk menyeimbangkan kecepatan pengembangan pada fase Hackathon/PoC tanpa mengorbankan isolasi domain, konkurensi pemrosesan file, dan kesiapan transisi menuju microservices di masa mendatang.

Prinsip teknis utama yang diterapkan:
1. **Stateless API Gateway & Core Backend**: Seluruh sesi dan autentikasi berbasis JWT terdesentralisasi, memungkinkan node backend di-scale secara horizontal di balik load balancer.
2. **Asynchronous Background Processing**: Pemrosesan intensif komputasi (ekstraksi AI/OCR dan kompilasi voucher PDF) dipisahkan dari HTTP threadpool utama menggunakan message queue terdistribusi (Redis BullMQ).
3. **Multi-Tenant Data Isolation**: Isolasi data antar-klien ditegakkan secara absolut pada middleware backend dan query filter level (Client Scope Boundary).
4. **Server-Enforced Segregation of Duties (SoD)**: Validasi pemisahan kewenangan dieksekusi secara atomik di dalam database transaction untuk mencegah race condition.

### 1.2 Diagram Komponen Sistem (System Architecture Diagram)

Komponen arsitektur teknis dan interaksinya dimodelkan melalui diagram Mermaid berikut:

```mermaid
graph TB
    subgraph Client_Tier [Client Presentation Layer]
        PIC[PIC Klien / Intake Support\nWeb Browser]
        REV[Finance Reviewer\nWeb Browser - Split Screen]
        LEAD[Service Lead & Admin\nWeb Browser - Dashboard]
    end

    subgraph Edge_Tier [Network & Security Edge]
        LB[Nginx Reverse Proxy / Load Balancer\nTLS 1.3 Termination]
        WAF[Rate Limiting & Security Headers]
    end

    subgraph App_Tier [Application Layer: Next.js + NestJS/Fastify Core]
        API[Core API Gateway / REST Controller\nAuth, RBAC, Multi-Tenant Guard]
        SVC_INTAKE[Intake & Queue Service]
        SVC_VAL[Business Verification Engine\nMath, Completeness, Duplicate]
        SVC_REVIEW[Review & SoD Enforcement Service]
        SVC_AUDIT[Immutable Audit Service]
    end

    subgraph Async_Tier [Worker & Queue Layer]
        QUEUE[Redis Queue / BullMQ\nJob Broker]
        W_AI[AI Document Extraction Worker]
        W_PDF[Voucher PDF Generator Worker]
    end

    subgraph Data_Tier [Persistence & Storage Layer]
        DB[(PostgreSQL 16\nACID, Trigram Index, Row Audit)]
        CACHE[(Redis 7.2\nSession, Rate Limit, Lock)]
        STORAGE[S3-Compatible Object Storage\nMinIO / AWS S3 - Encrypted at Rest]
    end

    subgraph External_Tier [Third-Party Services]
        AI_ENGINE[Enterprise Document AI / OCR\nZero Data Retention Policy]
    end

    PIC -->|HTTPS / REST| LB
    REV -->|HTTPS / REST| LB
    LEAD -->|HTTPS / REST| LB

    LB --> WAF --> API

    API --> SVC_INTAKE
    API --> SVC_VAL
    API --> SVC_REVIEW
    API --> SVC_AUDIT

    SVC_INTAKE -->|Upload PDF & Metadata| STORAGE
    SVC_INTAKE -->|Enqueue Job| QUEUE
    QUEUE --> W_AI
    QUEUE --> W_PDF

    W_AI -->|Stream Document| AI_ENGINE
    AI_ENGINE -->|Extracted JSON| W_AI
    W_AI -->|Save Draft & Trigger| SVC_VAL
    SVC_VAL --> DB

    SVC_REVIEW -->|Atomic Tx & SoD Check| DB
    SVC_REVIEW -->|Trigger Voucher PDF| QUEUE
    W_PDF -->|Upload PDF| STORAGE
    W_PDF -->|Update Voucher Path| DB

    SVC_AUDIT -->|Append-Only Log| DB
    API --> CACHE
```

### 1.3 Siklus Hidup Dokumen & Alur Data End-to-End

Setiap dokumen invoice melewati 6 status pasti dengan diagram sekuens teknis sebagai berikut:

```mermaid
sequenceDiagram
    autonumber
    actor PIC as PIC Klien / Intake
    participant API as API Server (NestJS)
    participant S3 as Object Storage (S3)
    participant Q as Redis Queue (BullMQ)
    participant W as AI Worker
    participant AI as Document AI Engine
    participant DB as PostgreSQL 16
    actor REV as Finance Reviewer

    PIC->>API: POST /invoices/upload (Multipart PDF + Metadata)
    API->>API: Validasi tipe file (PDF, <= 5 hal, <= 10MB)
    API->>S3: PutObject (original_invoice.pdf, AES-256)
    API->>DB: INSERT invoice_requests (Status: QUEUED, Request ID)
    API->>DB: INSERT audit_logs (Action: INTAKE_UPLOAD)
    API->>Q: Enqueue Extraction Job (requestId)
    API-->>PIC: 201 Created (Request ID, status: QUEUED)

    Q->>W: Process Job (requestId)
    W->>DB: UPDATE status = PROCESSING
    W->>S3: GetObject Stream
    W->>AI: Extract Document (Header, Line Items, Bank Info)
    AI-->>W: Raw Extraction Result (JSON)
    W->>DB: INSERT extracted_line_items & payment_details

    W->>API: Trigger Automated Business Verification
    API->>API: 1. Normalisasi Vendor & Invoice No
    API->>DB: 2. Cek Duplikasi (POSSIBLE_DUPLICATE)
    API->>API: 3. Cek Kelengkapan Rekening (MISSING_EVIDENCE)
    API->>API: 4. Cek Total vs Sum(Items) (CALCULATION_DISCREPANCY)

    alt Terdapat Kejanggalan Aturan Bisnis
        API->>DB: UPDATE status = EXCEPTION (Simpan issue codes)
        API->>DB: INSERT audit_logs (Action: VERIFICATION_FAILED)
    else Lolos Seluruh Validasi
        API->>DB: UPDATE status = READY_FOR_REVIEW
        API->>DB: INSERT audit_logs (Action: VERIFICATION_PASSED)
    end

    Note over REV, DB: Finance Reviewer membuka Split Screen
    REV->>API: GET /invoices/{requestId}/review-data
    API-->>REV: PDF Signed URL + Editable Extracted Data + Issue Badges

    alt Reviewer Melakukan Koreksi
        REV->>API: PUT /invoices/{requestId}/line-items (Payload Koreksi)
        API->>DB: UPDATE values & INSERT audit_logs (old_value, new_value)
    end

    REV->>API: POST /invoices/{requestId}/approve
    API->>DB: BEGIN TRANSACTION (SELECT uploader_id, reviewer_id)
    alt Pelanggaran Segregation of Duties (Reviewer == Uploader)
        API->>DB: Tolak Persetujuan (SoD Conflict)
        API->>DB: Otomatis alihkan assignment ke reviewer lain
        API->>DB: INSERT audit_logs (Action: SOD_REJECT_AND_REASSIGN)
        API->>DB: COMMIT TRANSACTION
        API-->>REV: 403 Forbidden (SoD Violation, Auto-reassigned)
    else Lolos SoD Check
        API->>DB: UPDATE status = AMIGA_REVIEWED
        API->>DB: INSERT audit_logs (Action: REVIEW_APPROVED)
        API->>Q: Enqueue Voucher PDF Generation Job
        API->>DB: COMMIT TRANSACTION
        API-->>REV: 200 OK (Status: AMIGA_REVIEWED)
    end

    Q->>W: Generate Voucher PDF (Template + Auth Boundary Text)
    W->>S3: PutObject (voucher.pdf)
    W->>DB: INSERT payment_vouchers

    PIC->>API: GET /invoices/{requestId}/voucher/download
    API->>DB: UPDATE status = SENT_TO_CLIENT
    API->>DB: INSERT audit_logs (Action: VOUCHER_DOWNLOADED)
    API-->>PIC: Stream PDF Voucher (Official Document)
```

---

## 2. Environment & Technology Stack Selection

Keputusan teknologi diambil dengan pertimbangan matang atas persyaratan efisiensi waktu pemrosesan, keamanan data perbankan, kepatuhan UU PDP, serta kecepatan rilis PoC hackathon menuju produksi.

### 2.1 Ringkasan Pilihan Stack & Rationale

| Komponen | Pilihan Teknologi | Versi | Rationale & Justifikasi Teknis |
| :--- | :--- | :--- | :--- |
| **Frontend Framework** | **Next.js (App Router)** | `16.x` (Active LTS / React 19) | Server-Side Rendering (SSR) untuk load dashboard cepat (SLA <= 2 detik), Turbopack bawaan stabil, ekosistem TypeScript terpadu, route handlers, dan layouting terisolasi per peran. |
| **Styling & Design Tokens** | **Vanilla CSS + Tailwind CSS v4** | `4.x` | Menghindari class bloat generic. Custom properties CSS terstandar untuk desain profesional (Ink Navy, Signal Blue, Marble Canvas) sesuai `DESIGN-examples.md`. |
| **State Management** | **TanStack Query v5 + Zustand** | `5.x` / `4.x` | TanStack Query menangani server state, caching antrean, optimistik update dan auto-refetch; Zustand menangani client-side state pada split-screen editor. |
| **PDF Viewer Engine** | **PDF.js (Mozilla) / React-PDF** | `latest` | Rendering PDF invoice berkinerja tinggi langsung di canvas browser tanpa dependensi plugin eksternal; mendukung sinkronisasi zoom, scroll, dan field highlight. |
| **Backend Runtime** | **Node.js (NestJS)** | `20 LTS` / NestJS 10 | Framework enterprise berbasis TypeScript dengan arsitektur modular, dependency injection, DTO validation otomatis (class-validator), dan guard RBAC terstruktur. |
| **ORM & Database Driver** | **Prisma ORM** | `5.x` | Type-safety penuh dari skema DB ke API responses; migrasi skema deklaratif; penanganan atomic transaction yang kokoh untuk pengecekan SoD. |
| **Primary Database** | **PostgreSQL** | `16.x` | Integritas data finansial ACID; dukungan ekstensi `pg_trgm` untuk pencocokan teks fuzzy nomor invoice/vendor; enkripsi data-at-rest. |
| **Message Broker & Cache** | **Redis + BullMQ** | `7.2` / `5.x` | Queue engine berkecepatan tinggi dengan retry logic otomatis, job event emission, dead-letter queue, serta distributed locking untuk mencegah race condition. |
| **Object Storage** | **S3-Compatible (MinIO / Cloudflare R2)** | API S3 v4 | Penyimpanan berkas invoice PDF dan voucher PDF terenkripsi (AES-256-GCM) dengan presigned URL berbatas waktu (maksimal 15 menit per link akses). |
| **AI Document Extraction** | **Claude 3.5 Sonnet / Azure Document Intelligence** | API v2024 | Kemampuan pembacaan multi-line table zero-shot yang superior pada invoice format tidak terstruktur; SLA ekstraksi <= 15 detik; mendukung Enterprise Zero Data Retention (ZDR). |
| **PDF Generation Engine** | **@react-pdf/renderer + Puppeteer fallback** | `3.x` | Kompilasi voucher pembayaran resmi berbasis komponen React ke PDF dalam tempo <= 3 detik dengan presisi visual teks batas otorisasi. |

### 2.2 Topologi Lingkungan (Environment Topology)

1. **Development Environment (Local Machine)**:
   - Docker Compose mendalangi PostgreSQL 16, Redis 7.2, dan MinIO S3.
   - Hot-reload Next.js dan NestJS backend.
   - Mock AI service connector untuk pengujian offline tanpa biaya API kuota.
2. **Staging Environment (Hackathon Evaluation / Pre-Prod)**:
   - Containerized deployment di Linux VM (Ubuntu 24.04 LTS).
   - Nginx Reverse Proxy dengan sertifikat SSL Let's Encrypt TLS 1.3.
   - Integrasi langsung ke live AI Service (dengan data dummy tersensor sesuai kepatuhan).
3. **Production Readiness (Enterprise Baseline)**:
   - Managed PostgreSQL (AWS RDS / Cloud SQL) dengan automated continuous backup.
   - S3 Bucket dengan lifecycle rule dan Object Lock (Compliance mode) untuk berkas audit.

### 2.3 Skema Konfigurasi Variabel Lingkungan (.env.example)

```bash
# === SERVER & RUNTIME CONFIGURATION ===
NODE_ENV=development
PORT=4000
API_PREFIX=/api/v1
APP_BASE_URL=http://localhost:3000

# === DATABASE & PERSISTENCE (POSTGRESQL 16) ===
DATABASE_URL="postgresql://amiga_user:SecurePass123!@localhost:5432/amiga_robot_admin?schema=public&sslmode=prefer"
DB_MAX_CONNECTIONS=20
DB_TIMEOUT_MS=5000

# === REDIS & BULLMQ BROKER ===
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=""
REDIS_DB_QUEUE=0
REDIS_DB_CACHE=1

# === AUTHENTICATION & SECURITY (JWT) ===
JWT_SECRET="super-secret-hex-key-minimum-256-bits-amiga-robot-admin"
JWT_EXPIRES_IN="8h"
JWT_REFRESH_SECRET="another-super-secret-hex-key-refresh"
JWT_REFRESH_EXPIRES_IN="7d"

# === OBJECT STORAGE (S3 COMPATIBLE / MINIO) ===
STORAGE_ENDPOINT="http://localhost:9000"
STORAGE_REGION="us-east-1"
STORAGE_ACCESS_KEY="minioadmin"
STORAGE_SECRET_KEY="minioadmin"
STORAGE_BUCKET_INVOICES="amiga-invoices"
STORAGE_BUCKET_VOUCHERS="amiga-vouchers"
STORAGE_FORCE_PATH_STYLE=true

# === DOCUMENT AI & OCR CONNECTOR ===
AI_PROVIDER=anthropic # Options: anthropic | azure_document_intelligence | mock
AI_API_KEY="sk-ant-api-key-here"
AI_EXTRACTION_TIMEOUT_MS=15000
AI_ZERO_DATA_RETENTION=true

# === BUSINESS RULES & SYSTEM CONSTRAINTS ===
MAX_INVOICE_PAGES=5
MAX_FILE_SIZE_MB=10
WORKLOAD_MAX_THRESHOLD=10 # Ambang batas beban dinamis per reviewer (fleksibel dan dapat diubah sesuai kalibrasi operasional)
```

---

## 3. Skema Database Lengkap & Data Modeling (ERD)

Struktur data dirancang secara normal (3NF) dengan penegakan integritas referensial, constraint relasional yang ketat, dan penanda waktu audit otomatis.

### 3.1 Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    CLIENTS ||--o{ USERS : "memiliki relasi default"
    CLIENTS ||--o{ USER_CLIENT_ASSIGNMENTS : "didelegasikan ke"
    USERS ||--o{ USER_CLIENT_ASSIGNMENTS : "menerima delegasi"

    CLIENTS ||--o{ INVOICE_REQUESTS : "memiliki transaksi"
    USERS ||--o{ INVOICE_REQUESTS : "diunggah oleh (uploader)"
    USERS ||--o{ INVOICE_REQUESTS : "ditugaskan ke (current_reviewer)"

    INVOICE_REQUESTS ||--o{ INVOICE_LINE_ITEMS : "memuat rincian"
    INVOICE_REQUESTS ||--o| INVOICE_PAYMENT_DETAILS : "memuat info rekening"
    INVOICE_REQUESTS ||--o{ VERIFICATION_ISSUES : "memiliki catatan kendala"
    INVOICE_REQUESTS ||--o{ REVIEWER_ASSIGNMENTS : "memiliki riwayat mutasi tugas"
    INVOICE_REQUESTS ||--o| PAYMENT_VOUCHERS : "menghasilkan voucher resmi"
    INVOICE_REQUESTS ||--o{ AUDIT_LOGS : "mencatat jejak aktivitas"

    CLIENTS {
        uuid id PK
        varchar client_code UK
        varchar client_name
        boolean is_active
        timestamp created_at
    }

    USERS {
        uuid id PK
        varchar email UK
        varchar full_name
        varchar password_hash
        varchar role
        uuid default_client_id FK
        boolean is_active
        timestamp created_at
    }

    USER_CLIENT_ASSIGNMENTS {
        uuid id PK
        uuid user_id FK
        uuid client_id FK
        uuid delegated_by FK
        timestamp created_at
    }

    INVOICE_REQUESTS {
        uuid id PK
        varchar request_id UK
        uuid client_id FK
        uuid uploader_id FK
        uuid current_reviewer_id FK
        varchar request_type
        varchar submission_channel
        date submission_date
        varchar original_file_name
        varchar storage_file_path
        integer file_page_count
        varchar status
        varchar vendor_name
        varchar vendor_name_normalized
        varchar invoice_number
        varchar invoice_number_normalized
        date invoice_date
        decimal subtotal_amount
        decimal tax_amount
        decimal total_amount
        timestamp created_at
        timestamp updated_at
    }

    INVOICE_LINE_ITEMS {
        uuid id PK
        uuid request_id FK
        integer item_index
        text description
        decimal quantity
        decimal unit_price
        decimal subtotal
        boolean is_manually_edited
        timestamp updated_at
    }

    INVOICE_PAYMENT_DETAILS {
        uuid id PK
        uuid request_id FK
        varchar bank_name
        varchar account_number
        varchar account_holder_name
        boolean is_manually_edited
        timestamp updated_at
    }

    VERIFICATION_ISSUES {
        uuid id PK
        uuid request_id FK
        varchar issue_code
        varchar issue_category
        text message_id
        boolean is_resolved
        timestamp detected_at
        timestamp resolved_at
    }

    REVIEWER_ASSIGNMENTS {
        uuid id PK
        uuid request_id FK
        uuid previous_reviewer_id FK
        uuid assigned_reviewer_id FK
        uuid assigned_by_user_id FK
        varchar trigger_reason
        text reason_notes
        timestamp created_at
    }

    PAYMENT_VOUCHERS {
        uuid id PK
        uuid request_id FK
        varchar voucher_number UK
        varchar voucher_file_path
        text authorization_boundary_text
        uuid generated_by FK
        timestamp generated_at
    }

    AUDIT_LOGS {
        bigserial id PK
        uuid request_id FK
        uuid actor_id FK
        varchar actor_name
        varchar actor_role
        varchar action_type
        varchar previous_status
        varchar new_status
        jsonb change_diff
        varchar ip_address
        timestamp created_at
    }
```

### 3.2 Kamus Data & Definisi Struktur Tabel (Data Dictionary)

#### Tabel: `clients`
Menyimpan organisasi klien multi-industri yang dikelola AMIGA.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `client_code` (VARCHAR(20), Unique, Not Null) - Contoh: `CLI-001`, `CLI-MAIN`
- `client_name` (VARCHAR(150), Not Null) - Contoh: `PT Teknologi Maju Bangsa`
- `is_active` (BOOLEAN, Default: `true`)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `users`
Menyimpan kredensial dan hak akses seluruh pengguna sistem.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `email` (VARCHAR(120), Unique, Not Null)
- `full_name` (VARCHAR(150), Not Null)
- `password_hash` (VARCHAR(255), Not Null) - Menggunakan algoritma Argon2id / bcrypt (work factor 12)
- `role` (VARCHAR(30), Not Null) - Enum: `PIC_KLIEN`, `INTAKE_SUPPORT`, `FINANCE_REVIEWER`, `SERVICE_LEAD`, `SYSTEM_ADMIN`
- `default_client_id` (UUID, Nullable, Foreign Key -> `clients.id`) - Khusus untuk peran `PIC_KLIEN`
- `is_active` (BOOLEAN, Default: `true`)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `user_client_assignments`
Memfasilitasi delegasi kerja multi-klien untuk peran `INTAKE_SUPPORT`.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `user_id` (UUID, Not Null, Foreign Key -> `users.id` ON DELETE CASCADE)
- `client_id` (UUID, Not Null, Foreign Key -> `clients.id` ON DELETE CASCADE)
- `delegated_by` (UUID, Not Null, Foreign Key -> `users.id`)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)
- *Index*: UNIQUE (`user_id`, `client_id`)

#### Tabel: `invoice_requests`
Tabel entitas transaksional utama yang menyimpan seluruh metadata dan status pemrosesan.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (VARCHAR(30), Unique, Not Null) - Format: `REQ-YYYYMMDD-XXXXX`
- `client_id` (UUID, Not Null, Foreign Key -> `clients.id`)
- `uploader_id` (UUID, Not Null, Foreign Key -> `users.id`)
- `current_reviewer_id` (UUID, Nullable, Foreign Key -> `users.id`)
- `request_type` (VARCHAR(50), Not Null) - Contoh: `Vendor Payment`, `Operational Reimbursement`
- `submission_channel` (VARCHAR(50), Not Null) - Contoh: `Email`, `WhatsApp Portal`, `Direct Web Upload`
- `submission_date` (DATE, Not Null)
- `original_file_name` (VARCHAR(255), Not Null)
- `storage_file_path` (VARCHAR(500), Not Null)
- `file_page_count` (INTEGER, Not Null, Constraint: `<= 5`)
- `status` (VARCHAR(30), Not Null) - Enum: `QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `EXCEPTION`, `AMIGA_REVIEWED`, `SENT_TO_CLIENT`
- `vendor_name` (VARCHAR(150), Nullable)
- `vendor_name_normalized` (VARCHAR(150), Nullable) - Hasil lowercase, alfanumerik tanpa spasi & simbol
- `invoice_number` (VARCHAR(80), Nullable)
- `invoice_number_normalized` (VARCHAR(80), Nullable) - Hasil lowercase & pembersihan karakter non-alfanumerik
- `invoice_date` (DATE, Nullable)
- `subtotal_amount` (NUMERIC(15, 2), Nullable)
- `tax_amount` (NUMERIC(15, 2), Default: `0.00`)
- `total_amount` (NUMERIC(15, 2), Nullable)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)
- `updated_at` (TIMESTAMPTZ, Default: `NOW()`)
- *Index*: `idx_invoice_client_status` (`client_id`, `status`), `idx_invoice_duplicate_lookup` (`client_id`, `vendor_name_normalized`, `invoice_number_normalized`)

#### Tabel: `invoice_line_items`
Menyimpan setiap baris barang/jasa hasil ekstraksi AI yang dapat diedit oleh Reviewer.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (UUID, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE CASCADE)
- `item_index` (INTEGER, Not Null)
- `description` (TEXT, Not Null)
- `quantity` (NUMERIC(12, 4), Not Null)
- `unit_price` (NUMERIC(15, 2), Not Null)
- `subtotal` (NUMERIC(15, 2), Not Null)
- `is_manually_edited` (BOOLEAN, Default: `false`)
- `updated_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `invoice_payment_details`
Menyimpan data tujuan transfer pembayaran hasil ekstraksi AI.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (UUID, Unique, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE CASCADE)
- `bank_name` (VARCHAR(100), Nullable)
- `account_number` (VARCHAR(50), Nullable) - Di-hash atau dienkripsi parsial
- `account_holder_name` (VARCHAR(150), Nullable)
- `is_manually_edited` (BOOLEAN, Default: `false`)
- `updated_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `verification_issues`
Menyimpan temuan kejanggalan otomatis sistem atau catatan pengembalian reviewer.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (UUID, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE CASCADE)
- `issue_code` (VARCHAR(50), Not Null) - Enum: `MISSING_EVIDENCE`, `POSSIBLE_DUPLICATE`, `CALCULATION_DISCREPANCY`, `REVIEWER_RETURNED`
- `issue_category` (VARCHAR(50), Not Null) - Enum: `COMPLETENESS`, `INTEGRITY`, `ARITHMETIC`, `MANUAL_REVIEW`
- `message_id` (TEXT, Not Null) - Penjelasan kendala dalam bahasa Indonesia non-teknis
- `is_resolved` (BOOLEAN, Default: `false`)
- `detected_at` (TIMESTAMPTZ, Default: `NOW()`)
- `resolved_at` (TIMESTAMPTZ, Nullable)

#### Tabel: `reviewer_assignments`
Mencatat riwayat distribusi tugas, pengalihan otomatis akibat SoD, dan penyeimbangan beban oleh Service Lead.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (UUID, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE CASCADE)
- `previous_reviewer_id` (UUID, Nullable, Foreign Key -> `users.id`)
- `assigned_reviewer_id` (UUID, Not Null, Foreign Key -> `users.id`)
- `assigned_by_user_id` (UUID, Nullable, Foreign Key -> `users.id`) - NULL jika otomatis oleh sistem
- `trigger_reason` (VARCHAR(50), Not Null) - Enum: `INITIAL_ASSIGNMENT`, `SOD_AUTO_REASSIGN`, `WORKLOAD_REBALANCE_LEAD`
- `reason_notes` (TEXT, Nullable)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `payment_vouchers`
Menyimpan rincian voucher pembayaran resmi yang dihasilkan sistem.
- `id` (UUID, Primary Key, Default: `gen_random_uuid()`)
- `request_id` (UUID, Unique, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE RESTRICT)
- `voucher_number` (VARCHAR(50), Unique, Not Null) - Format: `VCH/YYYYMM/CLI/XXXXX`
- `voucher_file_path` (VARCHAR(500), Not Null)
- `authorization_boundary_text` (TEXT, Not Null) - Kalimat batas legalitas otorisasi
- `generated_by` (UUID, Not Null, Foreign Key -> `users.id`)
- `generated_at` (TIMESTAMPTZ, Default: `NOW()`)

#### Tabel: `audit_logs` (Append-Only Immutable Ledger)
Tabel jejak audit permanen. Tidak diberikan hak akses `UPDATE` maupun `DELETE` di level izin database (Grant SELECT, INSERT only).
- `id` (BIGSERIAL, Primary Key)
- `request_id` (UUID, Not Null, Foreign Key -> `invoice_requests.id` ON DELETE RESTRICT)
- `actor_id` (UUID, Nullable, Foreign Key -> `users.id`) - NULL jika sistem otomatis
- `actor_name` (VARCHAR(150), Not Null)
- `actor_role` (VARCHAR(50), Not Null)
- `action_type` (VARCHAR(50), Not Null) - Contoh: `UPLOAD`, `AI_EXTRACT`, `FIELD_CORRECTION`, `APPROVE`, `RETURN`, `SOD_REASSIGN`, `DOWNLOAD`
- `previous_status` (VARCHAR(30), Nullable)
- `new_status` (VARCHAR(30), Nullable)
- `change_diff` (JSONB, Nullable) - Format: `{"field": "total_amount", "old_value": 1500000, "new_value": 1550000}`
- `ip_address` (VARCHAR(45), Nullable)
- `created_at` (TIMESTAMPTZ, Default: `NOW()`)

---

## 4. Spesifikasi API & Integrasi Pihak Ketiga

Seluruh endpoint RESTful beroperasi di atas protokol HTTPS, bertukar payload format `application/json` (kecuali upload multipart file), dan mengikuti struktur respon seragam.

### 4.1 Standar Format Response & Error Handling

Respon sukses mengikuti skema:
```json
{
  "success": true,
  "statusCode": 200,
  "data": {},
  "meta": {
    "requestId": "REQ-20261013-00042",
    "timestamp": "2026-10-13T14:30:00.000Z"
  }
}
```

Respon error mengikuti standar RFC 7807:
```json
{
  "success": false,
  "statusCode": 403,
  "error": {
    "code": "SOD_VIOLATION",
    "message": "Segregation of Duties: Anda tidak dapat menyetujui dokumen yang Anda unggah sendiri.",
    "details": {
      "uploaderId": "usr_998811",
      "actionTaken": "Document automatically reassigned to reviewer usr_443322"
    }
  },
  "timestamp": "2026-10-13T14:30:00.000Z"
}
```

### 4.2 Katalog Endpoint API Utama

#### A. Autentikasi & Pengguna
1. `POST /api/v1/auth/login`
   - **Deskripsi**: Autentikasi pengguna, menerbitkan Access Token (JWT) dan Refresh Token.
   - **Request**: `{"email": "reviewer@amiga.co.id", "password": "Password123!"}`
   - **Response (200)**: `{"accessToken": "...", "expiresIn": 28800, "user": {"id": "...", "role": "FINANCE_REVIEWER", ...}}`
2. `GET /api/v1/auth/me`
   - **Deskripsi**: Mengambil profil aktif pengguna beserta daftar klien yang didelegasikan.

#### B. Intake & Pengunggahan Dokumen
3. `POST /api/v1/invoices/upload`
   - **Hak Akses**: `PIC_KLIEN`, `INTAKE_SUPPORT`
   - **Content-Type**: `multipart/form-data`
   - **Request Body**:
     - `file`: Binary PDF file (wajib, <= 5 halaman, <= 10MB)
     - `clientId`: UUID Klien
     - `requestType`: String (misal: "Tagihan Vendor")
     - `submissionChannel`: String (misal: "Email", "WhatsApp")
     - `submissionDate`: Date (ISO format `YYYY-MM-DD`)
   - **Logika Server**:
     - Memverifikasi hak akses uploader terhadap `clientId`.
     - Mengecek ekstensi dan magic bytes berkas PDF asli.
     - Menyimpan file ke S3 Storage.
     - Menghasilkan `request_id` unik (`REQ-YYYYMMDD-XXXXX`).
     - Menyimpan data ke DB dengan status `QUEUED`.
     - Meneruskan ID ke antrean BullMQ `ai_extraction_queue`.
   - **Response (201 Created)**:
     ```json
     {
       "requestId": "REQ-20261013-00042",
       "status": "QUEUED",
       "message": "Invoice berhasil diunggah dan masuk antrean ekstraksi AI."
     }
     ```

#### C. Antrean Kerja & Dashboard
4. `GET /api/v1/invoices/queue`
   - **Hak Akses**: `FINANCE_REVIEWER`, `SERVICE_LEAD`, `PIC_KLIEN`, `INTAKE_SUPPORT`
   - **Query Params**: `?clientId=...&status=...&page=1&limit=20&search=...`
   - **Logika Server**:
     - Mengisolasi data: PIC hanya melihat data kliennya; Intake hanya klien yang ditugaskan; Reviewer melihat semua klien yang berhak ditinjau.
   - **Response (200 OK)**: Daftar array dokumen, jumlah per status, dan metrik antrean.
5. `GET /api/v1/invoices/:requestId`
   - **Deskripsi**: Mengambil detail lengkap dokumen untuk status tracker atau peninjauan.

#### D. Peninjauan, Koreksi, & Persetujuan (Human-in-the-Loop)
6. `GET /api/v1/invoices/:requestId/review-data`
   - **Hak Akses**: `FINANCE_REVIEWER`
   - **Response (200 OK)**:
     - `pdfSignedUrl`: URL berumur 15 menit untuk rendering PDF di canvas kiri.
     - `extractedData`: Header vendor, tanggal, nomor invoice.
     - `lineItems`: Rincian tabel baris barang.
     - `paymentDetails`: Bank, nomor rekening, nama pemilik rekening.
     - `issues`: Daftar kode kendala aktif (`MISSING_EVIDENCE`, `POSSIBLE_DUPLICATE`, dsb).
     - `canApprove`: Boolean (bernilai `false` jika reviewer sama dengan uploader).
7. `PUT /api/v1/invoices/:requestId/line-items`
   - **Hak Akses**: `FINANCE_REVIEWER`
   - **Request Body**: Array line items yang telah dimodifikasi oleh reviewer.
   - **Logika Server**:
     - Membandingkan nilai lama dan nilai baru.
     - Mengupdate record di `invoice_line_items`.
     - Mencatat setiap delta perubahan ke `audit_logs` (`old_value`, `new_value`, reviewer ID, timestamp).
8. `POST /api/v1/invoices/:requestId/approve`
   - **Hak Akses**: `FINANCE_REVIEWER`
   - **Logika Server (SoD Enforcement)**:
     - Memeriksa kondisi: `IF invoice.uploader_id == current_user.id`:
       - **BATALKAN PERSETUJUAN**.
       - Cari reviewer aktif lain di sistem (pilih reviewer dengan beban terendah).
       - Alihkan penugasan dokumen ke reviewer baru.
       - Catat ke `reviewer_assignments` dan `audit_logs` dengan kode `SOD_AUTO_REASSIGN`.
       - Kembalikan response 403 Forbidden.
     - `ELSE`:
       - Ubah status menjadi `AMIGA_REVIEWED`.
       - Kirim job kompilasi voucher PDF ke BullMQ `pdf_voucher_queue`.
       - Catat ke `audit_logs`.
       - Kembalikan response 200 OK.
9. `POST /api/v1/invoices/:requestId/return`
   - **Hak Akses**: `FINANCE_REVIEWER`
   - **Request Body**: `{"returnReason": "Nomor rekening pada invoice buram dan bukti pendukung belum terlampir."}`
   - **Logika Server**:
     - Mengubah status dokumen menjadi `EXCEPTION`.
     - Menambahkan issue code `REVIEWER_RETURNED`.
     - Mencatat alasan ke `audit_logs`.

#### E. Perbaikan Dokumen EXCEPTION
10. `PUT /api/v1/invoices/:requestId/correct`
    - **Hak Akses**: `PIC_KLIEN`, `INTAKE_SUPPORT`
    - **Request Body**: Data koreksi (misalnya melengkapi nomor rekening atau merevisi metadata).
    - **Logika Server**:
      - Memastikan **Request ID TETAP SAMA** (tidak menerbitkan Request ID baru).
      - Mengupdate data invoice.
      - Mengembalikan status ke `PROCESSING` (re-ekstraksi & verifikasi ulang aturan bisnis).
      - Mencatat aktivitas perbaikan ke `audit_logs`.

#### F. Pengalihan Beban oleh Service Lead
11. `POST /api/v1/invoices/:requestId/reassign`
    - **Hak Akses**: `SERVICE_LEAD`
    - **Request Body**: `{"newReviewerId": "uuid-reviewer", "reason": "Beban reviewer sebelumnya melebihi 10 dokumen"}`
    - **Logika Server**:
      - Mengupdate `current_reviewer_id`.
      - Status dokumen tidak berubah.
      - Mencatat pengalihan manual ke `reviewer_assignments` dan `audit_logs`.

#### G. Voucher PDF & Serah Terima Klien
12. `GET /api/v1/invoices/:requestId/voucher/preview`
    - **Hak Akses**: `FINANCE_REVIEWER`, `PIC_KLIEN`
    - **Response**: Mengembalikan pratinjau data voucher resmi dan teks batas otorisasi.
13. `GET /api/v1/invoices/:requestId/voucher/download`
    - **Hak Akses**: `PIC_KLIEN`, `INTAKE_SUPPORT`, `FINANCE_REVIEWER`
    - **Logika Server**:
      - Stream berkas voucher PDF resmi.
      - Jika diunduh oleh PIC Klien dan status masih `AMIGA_REVIEWED`, otomatis ubah status menjadi `SENT_TO_CLIENT`.
      - Catat pengunduhan ke `audit_logs`.

#### H. Penelusuran Jejak Audit
14. `GET /api/v1/invoices/:requestId/audit-trail`
    - **Hak Akses**: Seluruh pengguna yang memiliki hak akses terhadap dokumen klien terkait.
    - **Response**: Array kronologis permanen berisi setiap aktivitas, nilai awal, nilai akhir, aktor, dan penanda waktu.

### 4.3 Spesifikasi Integrasi Layanan Pihak Ketiga

1. **AI Document Extraction Engine**:
   - Integrasi menggunakan REST API via HTTPS dengan timeout ketat 15 detik.
   - Header request wajib menyertakan flag `X-Privacy-No-Retention: true` (memastikan data invoice dummy/klien tidak dijadikan training data AI).
   - Skema ekstraksi mengharuskan struktur JSON berformat:
     ```json
     {
       "vendor": { "name": "PT Sumber Berkah", "address": "Jakarta" },
       "invoice": { "number": "INV/2026/089", "date": "2026-10-10" },
       "lineItems": [
         { "index": 1, "description": "Lisensi Cloud Server", "qty": 1, "unitPrice": 12000000, "subtotal": 12000000 },
         { "index": 2, "description": "Maintenance Support Q3", "qty": 1, "unitPrice": 3000000, "subtotal": 3000000 }
       ],
       "totals": { "subtotal": 15000000, "tax": 1650000, "total": 16650000 },
       "payment": { "bankName": "Bank Central Asia", "accountNumber": "8800112233", "accountHolderName": "PT Sumber Berkah" }
     }
     ```
2. **Object Storage Engine (MinIO / S3)**:
   - File PDF asli disimpan pada path: `/invoices/{clientId}/{year}/{month}/{requestId}/original.pdf`.
   - Voucher PDF resmi disimpan pada path: `/vouchers/{clientId}/{year}/{month}/{voucherNumber}.pdf`.
   - Akses client-side selalu melalui presigned URL dengan durasi hidup maksimal 900 detik (15 menit).

---

## 5. Persyaratan Non-Fungsional (NFRs) & Enforcements

### 5.1 Kinerja & Latensi (Performance Benchmarks & SLAs)
1. **Waktu Ekstraksi Dokumen AI**: Waktu pemrosesan dokumen maksimal 5 halaman tidak boleh melebihi 15 detik (SLA target PoC). Worker BullMQ dikonfigurasi dengan retry 2 kali dan timeout 15 detik.
2. **Pemuatan Antrean & Layar Review**: Halaman antrean dashboard dan split-screen review wajib ter-render secara interaktif di browser dalam tempo <= 2 detik. Hal ini dicapai melalui:
   - Indexing database pada kolom `status`, `client_id`, dan `request_id`.
   - Paginasi server-side default 20 baris per halaman.
   - Kompresi Brotli/Gzip pada respon payload API.
3. **Pembuatan Voucher PDF**: Kompilasi voucher pembayaran resmi setelah persetujuan reviewer wajib selesai dalam tempo <= 3 detik.

### 5.2 Keamanan & Kontrol Akses (Security & RBAC)
1. **Pemberlakuan SoD di Sisi Server (Server-Side Enforced)**:
   - Larangan persetujuan oleh pengunggah dokumen wajib divalidasi langsung di controller dan service backend, bukan semata-mata menyembunyikan tombol "Setujui" di UI.
   - Pengecekan dijalankan dalam serializable transaction untuk mencegah double-action.
2. **Isolasi Multi-Klien (Multi-Tenant Boundary)**:
   - Setiap query yang mengambil data dokumen wajib memuat klausa `WHERE client_id IN (:userAllowedClientIds)`.
   - Pengguna Klien A yang mencoba menebak URL atau Request ID Klien B akan menerima respon 404 Not Found atau 403 Forbidden secara konsisten.
3. **Kerahasiaan Data Perbankan & Enkripsi**:
   - Seluruh komunikasi data antar-komponen wajib menggunakan TLS 1.3.
   - File PDF dan kolom nomor rekening bank dienkripsi saat disimpan (Encryption-at-Rest) menggunakan algoritma standar AES-256-GCM.
4. **Proteksi Serangan Siber**:
   - Rate limiting 100 request/menit per IP pada public endpoint.
   - Sanitasi input terhadap SQL Injection, XSS, dan Path Traversal pada upload file.

### 5.3 Kepatuhan Regulasi & Jejak Audit (Compliance & Auditability)
1. **Kepatuhan UU PDP**:
   - Seluruh data pemrosesan invoice pada PoC menggunakan data dummy atau data yang telah dianonimkan (anonymized/masked).
   - Pengiriman berkas ke layanan AI pihak ketiga mematuhi kebijakan no-training model.
2. **Immutability Jejak Audit (Tamper-Proof Audit)**:
   - Tabel `audit_logs` bersifat append-only.
   - Role database yang digunakan aplikasi backend tidak memiliki privilege `UPDATE` atau `DELETE` pada tabel audit, mencegah modifikasi log bahkan oleh level System Admin.

### 5.4 Skalabilitas & Keandalan (Scalability & Reliability)
1. **Pemisahan Beban Kerja (Decoupling)**:
   - Lonjakan pengunggahan invoice tidak akan memperlambat operasional reviewer karena proses ekstraksi ditampung dalam queue terpisah.
2. **Penanganan Kegagalan AI Graceful**:
   - Jika service AI eksternal mengalami timeout atau kegagalan parsing, dokumen tidak boleh hilang dari sistem. Dokumen akan berstatus `EXCEPTION` dengan kode kendala `AI_PARSING_FAILED` atau otomatis dapat diinput manual langsung oleh Finance Reviewer.

---

## 6. Keputusan Arsitektur & Resolusi Kebutuhan Teknis

Bagian ini mencatat resolusi resmi atas kebutuhan dan keputusan teknis yang disepakati bersama Product Owner dan Sponsor:

1. **Kode Kendala Perhitungan (CALCULATION_DISCREPANCY)**:
   - *Status*: Disetujui resmi dan telah ditambahkan ke glosarium BRD v1.1. Kode kendala resmi untuk selisih antara penjumlahan rincian line item dengan total invoice ditetapkan sebagai `CALCULATION_DISCREPANCY` (Kategori: `ARITHMETIC`), dengan status dokumen otomatis menjadi `EXCEPTION`.
2. **Ambang Batas Beban Antrean Service Lead (WORKLOAD_MAX_THRESHOLD)**:
   - *Status*: Ditetapkan dinamis dan dapat diubah secara fleksibel. Sistem tidak meng-hardcode nilai ambang batas beban di logika inti bisnis, melainkan menggunakan konfigurasi variabel lingkungan (`WORKLOAD_MAX_THRESHOLD`) atau pengaturan sistem yang dapat diubah kapan saja sesuai kebutuhan operasional lapangan.
3. **Watermark pada Pratinjau Voucher**:
   - *Status*: Diklasifikasikan sebagai fitur tambahan (*backlog / P1*) yang akan dikerjakan pada iterasi berikutnya setelah alur inti verifikasi dan unduh voucher resmi selesai diimplementasikan.
4. **Sorotan Bounding Box pada PDF Viewer**:
   - *Status*: Mengadopsi rekomendasi teknis arsitek. Untuk kestabilan dan performa demo PoC, peninjauan mengandalkan sinkronisasi nomor halaman dan dokumen asli berdampingan. Fitur penyorotan koordinat kotak otomatis (*bounding box highlight*) dicadangkan sebagai peningkatan pada tahap lanjutan.
5. **Perlakuan Duplikasi Invoice (POSSIBLE_DUPLICATE)**:
   - *Status*: Invoice dengan nomor dan vendor yang identik otomatis berstatus `EXCEPTION` untuk memitigasi risiko pembayaran ganda (*duplicate payment*).
6. **Algoritma Pengalihan Otomatis SoD**:
   - *Status*: Saat persetujuan ditolak karena pengunggah == penyetuju, sistem otomatis mengalihkan dokumen ke reviewer lain dengan antrean aktif paling sedikit (*least-loaded active reviewer*).
7. **Teks Batas Otorisasi Voucher**:
   - *Status*: Ditetapkan resmi: "Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin atas dasar verifikasi independen tim Keuangan AMIGA. Otorisasi pembayaran akhir dan eksekusi transfer dana merupakan kewenangan mutlak Client Approver di luar sistem AMIGA."
8. **Frontend Framework & Versi LTS (Next.js 16 LTS)**:
   - *Status*: Ditetapkan resmi menggunakan Next.js 16 (Active LTS) dengan App Router, Turbopack default bundler, dan React 19 untuk performa maksimal dan stabilitas jangka panjang.
