# INGESTION & REQUIREMENTS ANALYSIS (PHASE 0)

**Sistem:** AMIGA Robot Admin (Intelligent Vendor Invoice-to-Voucher Processing)  
**Dokumen:** `docs/specs/00-analysis.md`  
**Versi:** v1.0  
**Tanggal:** 13 Oktober 2026  
**Status:** Menunggu Konfirmasi Blocker (Phase 0 Review Gate)  
**Prinsip Utama:** Zero Fabrication, Absolute Traceability, Strict Document Hierarchy (BRD > PRD > SRD > DRD > BPMN)

---

## 1. Inventaris Dokumen (Document Inventory)

1. **`01-BRD.md` (Business Requirements Document v1.1 - 13/10/2026)**  
   Dokumen ini menetapkan visi bisnis, latar belakang masalah operasional manual (5–10 menit/invoice, 5–15 menit/voucher), batasan model operasi *hybrid intake*, 8 sasaran metrik (KPI/OKR), cakupan MVP 8 epics, batas luar sistem (tidak mencakup eksekusi pembayaran oleh Client Approver), 5 layar utama antarmuka, NFR inti, dan 8 skenario uji penerimaan (UAT).
2. **`02-PRD.md` (Product Requirements Document v1.1 - 13/10/2026)**  
   Dokumen ini menerjemahkan kebutuhan bisnis menjadi spesifikasi fungsional terinci (FR-1.1 hingga FR-8.4) berprioritas P0 dan P1, matriks kontrol hak akses 6 peran, 6 status siklus hidup dokumen, 3 aturan verifikasi otomatis oleh sistem, spesifikasi 5 layar antarmuka, serta penetapan resolusi kendala `CALCULATION_DISCREPANCY` dan batas beban kerja antrean.
3. **`03-SRD.md` (System Requirements Document v1.0 - 13/10/2026)**  
   Dokumen ini merumuskan arsitektur teknis modular monolith dengan background worker asinkron berbasis Redis BullMQ, stack teknologi terstandar (Next.js 16 LTS, Fastify 4.x/5.x, PostgreSQL 16, Prisma ORM, Pluggable Local/S3 Storage, AWS Bedrock), 10 skema tabel relasional (3NF), katalog 14 endpoint REST API beserta format payload, SLA performa (AI <= 15s, load <= 2s, PDF <= 3s), dan penegakan keamanan *Segregation of Duties* di level database transaction.
4. **`04-DRD.md` (Design Requirements Document v1.0 - 13/10/2026)**  
   Dokumen ini menetapkan sistem desain visual *"Navy Ink on Cool Marble"* (`#0B3558`, `#006BFF`, `#F8F9FB`), tipografi `Manrope` (angka tabular) dan `JetBrains Mono`, wireframe tata letak 5 layar utama (termasuk *Dual-Context Split Screen* 50:50), semantic status tokens, matriks 5 kondisi antarmuka (empty, loading, error, success, offline), responsivitas breakpoint, serta standar aksesibilitas WCAG 2.1 AA.
5. **`AMIGA_Robot_Admin_Invoice_to_Voucher ver3.bpmn` (BPMN 2.0 XML Model)**  
   Model proses formal berbasis XML yang memetakan kolaborasi end-to-end proses invoice-to-voucher, mencakup 2 partisipan (`P_amiga`, `P_client`), 5 *swimlanes* internal (`L_pic`, `L_sys`, `L_ai`, `L_fin`, `L_lead`), 12 *activities*, 4 *exclusive gateways*, 2 *start events*, 2 *end events*, 1 *message flow* ke Client Approver, dan 1 *data store reference* Jejak Audit.
6. **`DESIGN-examples.md` (Visual Style Reference Guide)**  
   Dokumen rujukan styling berbasis tema *"Navy ink on cool marble"* dari sistem Calendly yang diadaptasi menjadi fondasi tokens warna, bayangan bertingkat (*blue-tinted shadows*), radius sudut terkalibrasi (8px tombol, 12px card, 24px panel), dan aturan penolakan pola generic AI (*anti-slop directives*).

---

## 2. Katalog Kebutuhan (Requirement Catalog)

### 2.1 Business Requirements (`BR-xxx` — Sumber: `01-BRD.md`)
| ID | Deskripsi Kebutuhan | Sumber | Prioritas |
| :--- | :--- | :--- | :--- |
| **BR-001** | Mengotomatisasi pemrosesan invoice vendor PDF menjadi voucher pembayaran resmi guna menghapus beban pengetikan manual (5–10 menit per invoice) dan penyusunan voucher (5–15 menit). | BRD 1.1–1.3 | P0 (Mandatory) |
| **BR-002** | Menerapkan prinsip Segregation of Duties (SoD): pengunggah dokumen dilarang keras menyetujui dokumen yang sama. | BRD 1.5 | P0 (Mandatory) |
| **BR-003** | Memenuhi target performa PoC: ekstraksi AI <= 15 detik (hingga 5 halaman), muat antrean <= 2 detik, kompilasi voucher <= 3 detik. | BRD 2.0 | P0 (Mandatory) |
| **BR-004** | Memenuhi target akurasi dan kontrol risiko: 100% baris terbaca pada multi-line item, 0 kasus duplikat lolos, 0 pelanggaran SoD, 100% audit tercatat. | BRD 2.0 | P0 (Mandatory) |
| **BR-005** | Menyediakan intake unggah PDF (maks. 5 halaman) dengan metadata (klien, tipe, saluran, tanggal) dan penerbitan Request ID unik berstatus `QUEUED`. | BRD 3.0 / Epic 1 | P0 (Mandatory) |
| **BR-006** | Mendukung delegasi kerja kepada Intake Support untuk klien yang ditugaskan dengan pencatatan nama pengunggah sebenarnya pada jejak audit. | BRD Epic 1 (Story 1.2) | P0 (Mandatory) |
| **BR-007** | Ekstraksi otomatis draf voucher oleh AI mencakup header vendor, seluruh line items, total nilai, dan rekening tujuan transfer (status `PROCESSING`). | BRD Epic 2 (Story 2.1) | P0 (Mandatory) |
| **BR-008** | Menjalankan verifikasi sistem otomatis untuk kelengkapan rekening (`MISSING_EVIDENCE`), duplikasi (`POSSIBLE_DUPLICATE`), dan hitungan (`CALCULATION_DISCREPANCY`). | BRD Epic 3 (Story 3.1) | P0 (Mandatory) |
| **BR-009** | Dokumen berstatus `EXCEPTION` wajib menampilkan kode kendala dan alasan sederhana; perbaikan oleh PIC menggunakan Request ID yang sama. | BRD Epic 3 (Story 3.2) | P0 (Mandatory) |
| **BR-010** | Menyediakan layar split-screen bagi Finance Reviewer untuk meninjau, mengoreksi data, menyetujui (`AMIGA_REVIEWED`), atau mengembalikan (`EXCEPTION`). | BRD Epic 4 (Story 4.1) | P0 (Mandatory) |
| **BR-011** | Sistem wajib menolak persetujuan oleh uploader dan otomatis mengalihkan dokumen ke reviewer lain dengan pencatatan audit. | BRD Epic 4 (Story 4.2) | P0 (Mandatory) |
| **BR-012** | Menghasilkan voucher PDF resmi berstatus `SENT_TO_CLIENT` saat diunduh, memuat teks batas otorisasi legal permanen. | BRD Epic 5 (Story 5.1) | P0 (Mandatory) |
| **BR-013** | Dashboard antrean kerja dengan filter klien, status, SLA, dan fasilitas pengalihan dokumen oleh Service Lead saat beban berlebih. | BRD Epic 6 (Story 6.1) | P1 (Secondary) |
| **BR-014** | Menjamin isolasi data multi-klien di server (user Klien A ditolak mengakses data Klien B) dan membatasi hak System Admin dari persetujuan transaksi. | BRD Epic 7 (Story 7.1) | P0 (Mandatory) |
| **BR-015** | Jejak audit permanen yang tidak dapat diubah/dihapus (immutable), mencatat aktor, waktu, jenis aksi, status, dan riwayat revisi nilai awal vs baru. | BRD Epic 8 (Story 8.1) | P0 (Mandatory) |

### 2.2 Product Requirements (`PR-xxx` — Sumber: `02-PRD.md`)
| ID | Deskripsi Kebutuhan | Sumber | Prioritas |
| :--- | :--- | :--- | :--- |
| **PR-001** | (FR-1.1) Formulir unggah menerima 1 file PDF digital, maksimal 5 halaman dan ukuran maksimal 10MB. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-002** | (FR-1.2) Formulir wajib memvalidasi kelengkapan: nama klien, jenis permintaan, saluran pengajuan, dan tanggal pengajuan. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-003** | (FR-1.3) Sistem otomatis menerbitkan Request ID unik (`REQ-YYYYMMDD-XXXXX`) dan menetapkan status awal `QUEUED`. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-004** | (FR-1.4) Delegasi unggah oleh Intake Support dibatasi hanya untuk klien yang ditugaskan secara resmi. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-005** | (FR-1.5) Penolakan berkas non-PDF atau melebihi 5 halaman dengan pesan informatif dan pengembalian ke formulir intake. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-006** | (FR-2.1) Perubahan status dokumen menjadi `PROCESSING` secara otomatis saat AI Engine memulai proses pembacaan berkas. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-007** | (FR-2.2) AI Engine hanya bertindak mengekstrak data ke draf voucher tanpa kewenangan verifikasi logika maupun persetujuan. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-008** | (FR-2.3) Ekstraksi data selesai dalam durasi <= 15 detik untuk berkas hingga 5 halaman. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-009** | (FR-2.4) Dokumen hasil perbaikan pasca-EXCEPTION diproses ulang dengan Request ID yang sama tanpa menerbitkan ID baru. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-010** | (FR-2.5) Kegagalan ekstraksi AI tidak menghilangkan dokumen; berkas tetap tersimpan dan dapat diproses ulang atau diisi manual oleh Reviewer. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-011** | (FR-3.1) Sistem (bukan AI) mengeksekusi verifikasi angka (subtotal vs total), kelengkapan rekening, dan duplikasi invoice. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-012** | (FR-3.2) Dokumen lolos verifikasi berubah status menjadi `READY_FOR_REVIEW`; dokumen dengan kendala berubah menjadi `EXCEPTION`. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-013** | (FR-3.3) Status `EXCEPTION` wajib menampilkan kode kendala resmi dan alasan berbahasa Indonesia sederhana. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-014** | (FR-3.4) Fasilitas bagi PIC Klien untuk melengkapi atau memperbaiki data dokumen berstatus `EXCEPTION`. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-015** | (FR-4.1) Antarmuka split-screen: tampilan PDF asli pada panel kiri dan formulir data ekstraksi yang dapat diedit pada panel kanan. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-016** | (FR-4.2) Fasilitas koreksi data header, line items, dan rekening oleh Reviewer dengan penanda field yang bermasalah. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-017** | (FR-4.3) Opsi tindakan Reviewer: "Setujui" atau "Kembalikan ke PIC" (wajib mencantumkan alasan pengembalian tertulis). | PRD Bagian 4 | P0 (Mandatory) |
| **PR-018** | (FR-4.4) Pengecekan Segregation of Duties (SoD) otomatis saat tombol Setujui ditekan; penolakan SoD otomatis dialihkan ke reviewer lain. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-019** | (FR-4.5) Persetujuan yang valid mengubah status dokumen menjadi `AMIGA_REVIEWED` dan memicu pembuatan voucher PDF resmi. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-020** | (FR-5.1) Kompilasi berkas voucher PDF resmi selesai dalam durasi <= 3 detik pasca-persetujuan. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-021** | (FR-5.2) Layar pratinjau voucher menampilkan draf resmi dengan teks batas otorisasi legal yang tidak dapat dihapus. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-022** | (FR-5.3) Pengunduhan voucher resmi oleh PIC Klien otomatis memperbarui status dokumen menjadi `SENT_TO_CLIENT`. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-023** | (FR-6.1–6.4) Dashboard pemantauan antrean kerja per status, filter multi-klien, dan pengalihan dokumen oleh Service Lead saat beban berlebih. | PRD Bagian 4 | P1 (Secondary) |
| **PR-024** | (FR-7.1–7.3) Pengelolaan akun oleh System Admin, isolasi akses antar-klien, dan pelarangan hak persetujuan bagi System Admin. | PRD Bagian 4 | P0 (Mandatory) |
| **PR-025** | (FR-8.1–8.4) Perekaman jejak audit komprehensif, pencatatan mutasi nilai (old vs new), alasan pengembalian, dan penegakan immutability log. | PRD Bagian 4 | P0 (Mandatory) |

### 2.3 System Requirements (`SR-xxx` — Sumber: `03-SRD.md`)
| ID | Deskripsi Kebutuhan | Sumber | Prioritas |
| :--- | :--- | :--- | :--- |
| **SR-001** | Pola arsitektur Modular Monolith dengan Event-Driven Background Worker berbasis Redis 7.2 dan BullMQ 5.x. | SRD 1.1 | P0 (Mandatory) |
| **SR-002** | Stateless API Gateway dengan autentikasi JWT terdesentralisasi (Access Token 8 jam, Refresh Token 7 hari). | SRD 1.1, 2.3 | P0 (Mandatory) |
| **SR-003** | Penegakan isolasi multi-tenant di sisi server via middleware dan query scope `WHERE client_id IN (...)`. | SRD 1.1, 5.2 | P0 (Mandatory) |
| **SR-004** | Validasi SoD dieksekusi secara atomik dalam database transaction serializable untuk mencegah race condition. | SRD 1.1, 5.2 | P0 (Mandatory) |
| **SR-005** | Frontend stack: Next.js 16 (Active LTS, React 19), Vanilla CSS + Tailwind CSS v4, TanStack Query v5, Zustand, PDF.js. | SRD 2.1 | P0 (Mandatory) |
| **SR-006** | Backend stack: Node.js 20 LTS, Fastify 4.x/5.x, Prisma ORM 5.x, TypeBox schema validation. | SRD 2.1 (ADR Fastify) | P0 (Mandatory) |
| **SR-007** | Database stack: PostgreSQL 16 dengan ekstensi `pg_trgm` untuk pencocokan teks duplikasi fuzzy. | SRD 2.1, 3.1 | P0 (Mandatory) |
| **SR-008** | Object & file storage: Pluggable storage backend (`STORAGE_BACKEND=local` / `s3`) dengan fallback AWS S3. | SRD 2.1, 4.3 (ADR Storage) | P0 (Mandatory) |
| **SR-009** | Integrasi Document AI (AWS Bedrock Titan Text Express `amazon.titan-text-express-v1` via SDK v3) dengan zero retention policy dan mock fallback. | SRD 2.1, 4.3 (ADR Bedrock) | P0 (Mandatory) |
| **SR-010** | Mesin pembuatan PDF: `@react-pdf/renderer` (timeout <= 3 detik) untuk kompilasi voucher pembayaran resmi. | SRD 2.1 | P0 (Mandatory) |
| **SR-011** | Skema 10 tabel relasional 3NF: `clients`, `users`, `user_client_assignments`, `invoice_requests`, `invoice_line_items`, `invoice_payment_details`, `verification_issues`, `reviewer_assignments`, `payment_vouchers`, `audit_logs`. | SRD 3.1, 3.2 | P0 (Mandatory) |
| **SR-012** | Format API response: Envelope sukses standar dan RFC 7807 problem details untuk penanganan error. | SRD 4.1 | P0 (Mandatory) |
| **SR-013** | Algoritma normalisasi vendor dan nomor invoice: lowercase, alfanumerik murni tanpa spasi dan simbol sebelum pengecekan duplikasi. | SRD 1.3, 3.2 | P0 (Mandatory) |
| **SR-014** | Ambang batas beban antrean Service Lead dikonfigurasi dinamis melalui environment variable `WORKLOAD_MAX_THRESHOLD`. | SRD 2.3, 6.2 | P0 (Mandatory) |
| **SR-015** | Enkripsi end-to-end: protokol TLS 1.3 saat transit dan enkripsi kolom rekening serta berkas via AES-256-GCM saat disimpan. | SRD 5.2 | P0 (Mandatory) |
| **SR-016** | Hak akses tabel `audit_logs` dibatasi hanya `SELECT` dan `INSERT` di level izin database pengguna aplikasi (tamper-proof). | SRD 3.2, 5.3 | P0 (Mandatory) |
| **SR-017** | Formula penomoran voucher: `VCH/YYYYMM/CLI/XXXXX` dan teks batas otorisasi legal tertera permanen. | SRD 3.2, 6.7 | P0 (Mandatory) |

### 2.4 Design Requirements (`DR-xxx` — Sumber: `04-DRD.md`)
| ID | Deskripsi Kebutuhan | Sumber | Prioritas |
| :--- | :--- | :--- | :--- |
| **DR-001** | Arah visual mengusung tema *"Navy Ink on Cool Marble"* sebagai financial control tower berpresisi tinggi. | DRD 1.2 | P0 (Mandatory) |
| **DR-002** | Prinsip D-1 (Dual-Context Split Screen): dokumen PDF asli dan form data digital berdampingan tanpa memory strain. | DRD 2.0 | P0 (Mandatory) |
| **DR-003** | Prinsip D-2 (Preventive Guardrails): penegakan visual SoD transparan dan tombol aksi yang mencegah salah eksekusi. | DRD 2.0 | P0 (Mandatory) |
| **DR-004** | Prinsip D-3 (Calm Authority): penggunaan Ink Navy (`#0B3558`) dan Signal Blue (`#006BFF`), bebas warna hitam pekat `#000000`. | DRD 2.0, 3.1 | P0 (Mandatory) |
| **DR-005** | Prinsip D-4 (Actionable Error States): status EXCEPTION memuat kode, alasan bahasa manusia, dan aksi perbaikan langsung. | DRD 2.0 | P0 (Mandatory) |
| **DR-006** | Semantic tokens warna status: `QUEUED` (#F1F5F9), `PROCESSING` (#EFF6FF), `READY_FOR_REVIEW` (#FFFBEB), `EXCEPTION` (#FEF2F2), `AMIGA_REVIEWED` (#ECFDF5), `SENT_TO_CLIENT` (#EFF6FF). | DRD 3.1 | P0 (Mandatory) |
| **DR-007** | Hirarki tipografi: Font keluarga `Manrope` (tabular figures untuk angka finansial) dan `JetBrains Mono` (ID & kode). | DRD 3.2 | P0 (Mandatory) |
| **DR-008** | Anti-slop constraints: Larangan ikon generic AI (sparkles/robot), larangan pill-buttons 9999px pada tabel, dan larangan glassmorphism berlebih. | DRD 3.3 | P0 (Mandatory) |
| **DR-009** | Spacing grid 8px, border radius terstandar (8px tombol/input, 12px card, 24px panel), dan blue-tinted elevation shadows. | DRD 3.4 | P0 (Mandatory) |
| **DR-010** | Tata letak 5 layar utama: 01 Dashboard, 02 Intake Upload, 03 Split Review, 04 Voucher Preview, 05 Audit Trail. | DRD 5.0 | P0 (Mandatory) |
| **DR-011** | State matrix 5 kondisi di setiap layar kunci: Empty State, Loading State, Error State, Success State, dan Offline State. | DRD 7.0 | P0 (Mandatory) |
| **DR-012** | Responsivitas multi-breakpoint: Desktop split 50:50, Tablet tab-toggle/stacked, Mobile single-column (tap target >= 44px). | DRD 8.0 | P0 (Mandatory) |
| **DR-013** | Kepatuhan aksesibilitas WCAG 2.1 AA: Rasio kontras minimal 4.5:1, urutan fokus keyboard logis, dan pembaca layar (ARIA roles). | DRD 9.0 | P0 (Mandatory) |

---

## 3. BPMN Process Flow Digest (`PF-xxx` — Sumber: `AMIGA_Robot_Admin_Invoice_to_Voucher ver3.bpmn`)

### 3.1 Partisipan & Swimlanes
- **Partisipan 1 (`P_amiga`):** AMIGA Robot Admin (Proses Invoice-to-Voucher internal)
  - `L_pic` (PIC Klien / Intake): Pengunggah invoice, penyelesai kendala EXCEPTION, pengunduh voucher resmi.
  - `L_sys` (Sistem): Engine otomatis penerbit Request ID, validator aturan bisnis, pengawas SoD, kompilator voucher.
  - `L_ai` (AI Engine): Pembaca dan pengekstrak draf data berkas PDF invoice.
  - `L_fin` (Finance Reviewer): Peninjau independen berkas split-screen, korektor data, pemberi persetujuan/pengembalian.
  - `L_lead` (Service Lead): Pemantau beban antrean reviewer dan penyeimbang alokasi dokumen.
- **Partisipan 2 (`P_client`):** Client Approver (Eksternal — penerima voucher resmi, di luar sistem AMIGA).

### 3.2 Katalog Langkah Alur Proses (Step List)
| ID | Elemen BPMN | Pelaku (Lane) | Nama Langkah & Deskripsi | Sequence Flows |
| :--- | :--- | :--- | :--- | :--- |
| **PF-001** | `S1` (StartEvent) | `L_pic` | Invoice vendor diterima oleh PIC Klien. | Out: `F1` |
| **PF-002** | `T1` (UserTask) | `L_pic` | Unggah invoice PDF & isi formulir metadata awal. | In: `F1`, `F4` \| Out: `F2` |
| **PF-003** | `G1` (ExclusiveGateway)| `L_sys` | Gerbang validasi: Apakah file valid (PDF <= 5 halaman)? | In: `F2` \| Out: `F3` (Ya), `F4` (Tidak) |
| **PF-004** | `T2` (ServiceTask) | `L_sys` | Terbitkan Request ID unik dan set status `QUEUED`. | In: `F3` \| Out: `F5` |
| **PF-005** | `T3` (ServiceTask) | `L_ai` | Ekstraksi draf data invoice oleh AI (status `PROCESSING`). | In: `F5`, `F10` \| Out: `F6` |
| **PF-006** | `T4` (BusinessRuleTask)| `L_sys` | Verifikasi sistem otomatis: angka, kelengkapan, duplikasi. | In: `F6` \| Out: `F7` |
| **PF-007** | `G2` (ExclusiveGateway)| `L_sys` | Gerbang hasil verifikasi: Apakah lolos seluruh validasi? | In: `F7` \| Out: `F8` (Tidak), `F11` (Ya) |
| **PF-008** | `T5` (ServiceTask) | `L_sys` | Tandai `EXCEPTION`, simpan kode kendala & alasan informatif. | In: `F8` \| Out: `F9` |
| **PF-009** | `T6` (UserTask) | `L_pic` | PIC Klien melengkapi atau memperbaiki data invoice. | In: `F9`, `F13` \| Out: `F10` |
| **PF-010** | `T7` (UserTask) | `L_fin` | Reviewer meninjau & mengoreksi hasil ekstraksi (split-screen). | In: `F11`, `F17` \| Out: `F12` |
| **PF-011** | `G3` (ExclusiveGateway)| `L_fin` | Gerbang keputusan reviewer: Setujui atau Kembalikan ke PIC? | In: `F12` \| Out: `F13` (Return), `F14` (Approve) |
| **PF-012** | `T8` (ServiceTask) | `L_sys` | Pengecekan aturan Segregation of Duties di sisi server. | In: `F14` \| Out: `F15` |
| **PF-013** | `G4` (ExclusiveGateway)| `L_sys` | Gerbang SoD: Apakah Penyetuju == Pengunggah Dokumen? | In: `F15` \| Out: `F16` (Ya), `F18` (Tidak) |
| **PF-014** | `T9` (ServiceTask) | `L_sys` | Tolak persetujuan & otomatis alihkan ke reviewer lain. | In: `F16` \| Out: `F17` |
| **PF-015** | `T11` (ServiceTask) | `L_sys` | Set status `AMIGA_REVIEWED` & kompilasi voucher PDF resmi. | In: `F18` \| Out: `F19` |
| **PF-016** | `T12` (UserTask) | `L_pic` | Unduh voucher PDF resmi (status `SENT_TO_CLIENT`). | In: `F19` \| Out: `F20`, `M1` |
| **PF-017** | `E1` (EndEvent) | `L_pic` | Voucher pembayaran diserahkan ke Client Approver. | In: `F20` |
| **PF-018** | `S2` (StartEvent) | `L_lead` | Pemicu: Beban kerja seorang reviewer melebihi ambang batas. | Out: `F21` |
| **PF-019** | `T10` (UserTask) | `L_lead` | Service Lead mengalihkan dokumen ke reviewer lain yang luang. | In: `F21` \| Out: `F22` |
| **PF-020** | `E2` (EndEvent) | `L_lead` | Beban kerja antrean seimbang. | In: `F22` |
| **PF-021** | `DS1` (DataStore) | Global | Jejak Audit permanen mencatat setiap perubahan nilai & aksi. | Anotasi `TA1` via `A1` |

### 3.3 Jalur Alur Proses (Paths)
- **Happy Path:** `PF-001` (S1) -> `PF-002` (T1) -> `PF-003` (G1-Ya) -> `PF-004` (T2) -> `PF-005` (T3) -> `PF-006` (T4) -> `PF-007` (G2-Ya: READY_FOR_REVIEW) -> `PF-010` (T7) -> `PF-011` (G3-Setujui) -> `PF-012` (T8) -> `PF-013` (G4-Tidak: SoD Lolos) -> `PF-015` (T11: AMIGA_REVIEWED) -> `PF-016` (T12: SENT_TO_CLIENT) -> `PF-017` (E1).
- **Exception Path 1 (File Tidak Valid):** `PF-002` (T1) -> `PF-003` (G1-Tidak) -> kembali ke `PF-002` (T1) dengan pesan error file.
- **Exception Path 2 (Gagal Verifikasi Sistem):** `PF-006` (T4) -> `PF-007` (G2-Tidak) -> `PF-008` (T5: EXCEPTION) -> `PF-009` (T6) -> loop re-ekstraksi via `F10` (Request ID sama) -> `PF-005` (T3) -> `PF-006` (T4).
- **Exception Path 3 (Dikembalikan oleh Reviewer):** `PF-010` (T7) -> `PF-011` (G3-Kembalikan) -> `PF-009` (T6) -> loop re-ekstraksi via `F10` -> `PF-005` (T3).
- **Exception Path 4 (Pelanggaran SoD):** `PF-012` (T8) -> `PF-013` (G4-Ya) -> `PF-014` (T9: Tolak & Alihkan Otomatis) -> loop tinjau ulang via `F17` -> `PF-010` (T7 oleh Reviewer Baru).
- **Secondary Path (Workload Balancing):** `PF-018` (S2) -> `PF-019` (T10) -> `PF-020` (E2).

---

## 4. Glosarium Domain (Domain Glossary)

| Istilah Domain | Definisi & Konteks Operasional |
| :--- | :--- |
| **Request ID** | Pengenal alfanumerik unik berseri (`REQ-YYYYMMDD-XXXXX`) yang diterbitkan sistem saat invoice berhasil diunggah; tidak berubah selama siklus hidup dokumen. |
| **QUEUED** | Status saat berkas invoice PDF dan metadata telah tersimpan di sistem dan masuk ke dalam antrean antarmuka ekstraksi AI. |
| **PROCESSING** | Status ketika AI Document Engine sedang mengekstrak informasi berkas PDF dan mengisi draf data (target SLA <= 15 detik). |
| **READY_FOR_REVIEW** | Status saat draf hasil ekstraksi telah lolos seluruh verifikasi otomatis sistem (angka, kelengkapan, duplikasi) dan siap ditinjau Reviewer. |
| **EXCEPTION** | Status dokumen tertahan akibat ditemukannya kejanggalan sistematis atau pengembalian dokumen oleh Finance Reviewer disertai alasan. |
| **AMIGA_REVIEWED** | Status persetujuan resmi oleh Finance Reviewer independen yang telah diverifikasi lolos pengecekan Segregation of Duties. |
| **SENT_TO_CLIENT** | Status akhir dokumen ketika berkas voucher pembayaran PDF resmi telah diunduh oleh PIC Klien untuk diteruskan ke Client Approver. |
| **Segregation of Duties (SoD)** | Kontrol integritas tata kelola yang melarang seorang pengguna menyetujui transaksi yang diunggah oleh dirinya sendiri. |
| **MISSING_EVIDENCE** | Kode kendala verifikasi saat informasi wajib tidak ditemukan pada dokumen (khususnya nomor rekening bank tujuan transfer). |
| **CALCULATION_DISCREPANCY** | Kode kendala verifikasi resmi saat ditemukan ketidaksesuaian matematis antara penjumlahan subtotal rincian line item dengan total invoice. |
| **POSSIBLE_DUPLICATE** | Kode kendala verifikasi saat terdeteksi invoice lain dengan nomor dan vendor yang identik pada klien yang sama. |
| **REVIEWER_RETURNED** | Kode kendala saat Finance Reviewer secara manual menolak draf ekstraksi dan mengembalikannya ke PIC Klien disertai alasan tertulis. |
| **Voucher Number** | Penomoran resmi voucher pembayaran format AMIGA (`VCH/YYYYMM/CLI/XXXXX`) yang mengikat secara legal. |
| **Authorization Boundary Text**| Klausul legalitas permanen pada voucher PDF yang menegaskan bahwa otorisasi dan transfer dana merupakan kewenangan mutlak Client Approver. |

---

## 5. Daftar Entitas Data (Derived from SRD Database Modeling)

Berdasarkan `03-SRD.md` Bagian 3, model data relasional mencakup 10 entitas 3NF:

1. **`clients`**
   - Fields: `id` (UUID PK), `client_code` (VARCHAR(20) UK), `client_name` (VARCHAR(150)), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
   - Constraints: `client_code` unik, `client_name` not null.
   - Relasi: 1:N ke `users`, 1:N ke `invoice_requests`, 1:N ke `user_client_assignments`.
2. **`users`**
   - Fields: `id` (UUID PK), `email` (VARCHAR(120) UK), `full_name` (VARCHAR(150)), `password_hash` (VARCHAR(255)), `role` (VARCHAR(30)), `default_client_id` (UUID FK Nullable), `is_active` (BOOLEAN), `created_at` (TIMESTAMPTZ).
   - Constraints: `email` unik, `role` enum (`PIC_KLIEN`, `INTAKE_SUPPORT`, `FINANCE_REVIEWER`, `SERVICE_LEAD`, `SYSTEM_ADMIN`).
   - Relasi: N:1 ke `clients`, 1:N ke `invoice_requests` (uploader/reviewer), 1:N ke `audit_logs`.
3. **`user_client_assignments`**
   - Fields: `id` (UUID PK), `user_id` (UUID FK), `client_id` (UUID FK), `delegated_by` (UUID FK), `created_at` (TIMESTAMPTZ).
   - Constraints: UNIQUE (`user_id`, `client_id`), ON DELETE CASCADE.
   - Relasi: N:1 ke `users`, N:1 ke `clients`.
4. **`invoice_requests`**
   - Fields: `id` (UUID PK), `request_id` (VARCHAR(30) UK), `client_id` (UUID FK), `uploader_id` (UUID FK), `current_reviewer_id` (UUID FK Nullable), `request_type` (VARCHAR(50)), `submission_channel` (VARCHAR(50)), `submission_date` (DATE), `original_file_name` (VARCHAR(255)), `storage_file_path` (VARCHAR(500)), `file_page_count` (INTEGER), `status` (VARCHAR(30)), `vendor_name` (VARCHAR(150) Nullable), `vendor_name_normalized` (VARCHAR(150) Nullable), `invoice_number` (VARCHAR(80) Nullable), `invoice_number_normalized` (VARCHAR(80) Nullable), `invoice_date` (DATE Nullable), `subtotal_amount` (NUMERIC(15,2) Nullable), `tax_amount` (NUMERIC(15,2)), `total_amount` (NUMERIC(15,2) Nullable), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ).
   - Constraints: `file_page_count <= 5`, `status` enum, index komposit (`client_id`, `status`), index duplikasi (`client_id`, `vendor_name_normalized`, `invoice_number_normalized`).
   - Relasi: N:1 ke `clients`, N:1 ke `users` (uploader), N:1 ke `users` (reviewer), 1:N ke `invoice_line_items`, 1:1 ke `invoice_payment_details`, 1:N ke `verification_issues`, 1:1 ke `payment_vouchers`, 1:N ke `audit_logs`.
5. **`invoice_line_items`**
   - Fields: `id` (UUID PK), `request_id` (UUID FK), `item_index` (INTEGER), `description` (TEXT), `quantity` (NUMERIC(12,4)), `unit_price` (NUMERIC(15,2)), `subtotal` (NUMERIC(15,2)), `is_manually_edited` (BOOLEAN), `updated_at` (TIMESTAMPTZ).
   - Constraints: ON DELETE CASCADE ke `invoice_requests`.
   - Relasi: N:1 ke `invoice_requests`.
6. **`invoice_payment_details`**
   - Fields: `id` (UUID PK), `request_id` (UUID FK UK), `bank_name` (VARCHAR(100) Nullable), `account_number` (VARCHAR(50) Nullable), `account_holder_name` (VARCHAR(150) Nullable), `is_manually_edited` (BOOLEAN), `updated_at` (TIMESTAMPTZ).
   - Constraints: `request_id` unique (relasi 1:1), ON DELETE CASCADE.
   - Relasi: 1:1 ke `invoice_requests`.
7. **`verification_issues`**
   - Fields: `id` (UUID PK), `request_id` (UUID FK), `issue_code` (VARCHAR(50)), `issue_category` (VARCHAR(50)), `message_id` (TEXT), `is_resolved` (BOOLEAN), `detected_at` (TIMESTAMPTZ), `resolved_at` (TIMESTAMPTZ Nullable).
   - Constraints: `issue_code` enum (`MISSING_EVIDENCE`, `POSSIBLE_DUPLICATE`, `CALCULATION_DISCREPANCY`, `REVIEWER_RETURNED`).
   - Relasi: N:1 ke `invoice_requests`.
8. **`reviewer_assignments`**
   - Fields: `id` (UUID PK), `request_id` (UUID FK), `previous_reviewer_id` (UUID FK Nullable), `assigned_reviewer_id` (UUID FK), `assigned_by_user_id` (UUID FK Nullable), `trigger_reason` (VARCHAR(50)), `reason_notes` (TEXT Nullable), `created_at` (TIMESTAMPTZ).
   - Constraints: `trigger_reason` enum (`INITIAL_ASSIGNMENT`, `SOD_AUTO_REASSIGN`, `WORKLOAD_REBALANCE_LEAD`).
   - Relasi: N:1 ke `invoice_requests`, N:1 ke `users`.
9. **`payment_vouchers`**
   - Fields: `id` (UUID PK), `request_id` (UUID FK UK), `voucher_number` (VARCHAR(50) UK), `voucher_file_path` (VARCHAR(500)), `authorization_boundary_text` (TEXT), `generated_by` (UUID FK), `generated_at` (TIMESTAMPTZ).
   - Constraints: `voucher_number` unik, ON DELETE RESTRICT ke `invoice_requests`.
   - Relasi: 1:1 ke `invoice_requests`, N:1 ke `users`.
10. **`audit_logs`**
    - Fields: `id` (BIGSERIAL PK), `request_id` (UUID FK), `actor_id` (UUID FK Nullable), `actor_name` (VARCHAR(150)), `actor_role` (VARCHAR(50)), `action_type` (VARCHAR(50)), `previous_status` (VARCHAR(30) Nullable), `new_status` (VARCHAR(30) Nullable), `change_diff` (JSONB Nullable), `ip_address` (VARCHAR(45) Nullable), `created_at` (TIMESTAMPTZ).
    - Constraints: Append-only, database-level denial of `UPDATE` & `DELETE`.
    - Relasi: N:1 ke `invoice_requests`, N:1 ke `users`.

---

## 6. Register Kontradiksi & Celah Spesifikasi (Conflicts & Gaps)

| ID | Kategori | Temuan Kontradiksi / Kesenjangan Antar Dokumen | Tingkat Keparahan | Rekomendasi Resolusi Terpilih (Sesuai Hirarki) |
| :--- | :--- | :--- | :--- | :--- |
| **CG-001** | Terminologi Dokumen | Dokumen `04-DRD.md` diberi judul *"DESIGN REQUIREMENTS DOCUMENT"* (UI/UX), sedangkan prompt mendefinisikan DRD sebagai *"Data Requirements"*. | LOW | **Resolusi:** Model data primer diambil 1:1 dari `03-SRD.md` Bagian 3 dan `02-PRD.md` Bagian 6, sedangkan `04-DRD.md` menjadi sumber tunggal desain antarmuka, tokens, dan layout. |
| **CG-002** | Alur BPMN vs PRD/SRD | Pada BPMN, transisi pengembalian reviewer (G3 -> T6) langsung menuju input PIC tanpa melalui service task pengubah status. PRD & SRD menegaskan status berubah ke `EXCEPTION` dengan issue code `REVIEWER_RETURNED`. | MEDIUM | **Resolusi:** Mengikuti hirarki BRD/PRD di atas BPMN untuk intensi bisnis. Saat reviewer memilih "Kembalikan", sistem secara atomik mengupdate status invoice menjadi `EXCEPTION` dan mencatat kendala `REVIEWER_RETURNED`. |
| **CG-003** | Algoritma Reassign SoD | BPMN menggambarkan flow F17 langsung kembali ke lane Reviewer tanpa mendefinisikan kriteria pemilihan reviewer baru. | LOW | **Resolusi:** Mengadopsi spesifikasi teknis SRD Bagian 6.6: sistem mengalokasikan dokumen kepada *least-loaded active reviewer* (reviewer aktif dengan jumlah dokumen antrean aktif paling sedikit). |
| **CG-004** | Watermark Voucher | PRD & SRD menempatkan watermark "DRAFT INTERNAL" sebagai fitur backlog P1, sedangkan BRD tidak menyinggung watermark namun mewajibkan teks batas otorisasi permanen. | LOW | **Resolusi:** Teks batas otorisasi legal bersifat P0 wajib; watermark visual pada canvas pratinjau diklasifikasikan sebagai P1 backlog non-blocking. |
| **CG-005** | Ambang Batas Beban | PRD dan SRD mencatat batas antrean Service Lead bersifat dinamis via `WORKLOAD_MAX_THRESHOLD` (default 10 di SRD .env). | LOW | **Resolusi:** Nilai ambang batas dikonfigurasi melalui variabel lingkungan backend `WORKLOAD_MAX_THRESHOLD=10` dan dapat di-override melalui konfigurasi sistem. |
| **CG-006** | NFR: Aksesibilitas & i18n | PRD dan SRD menetapkan bahasa Indonesia non-teknis, namun standar kontras dan navigasi keyboard terinci hanya ada di DRD. | LOW | **Resolusi:** Adopsi penuh standar WCAG 2.1 AA dari DRD (kontras 10.8:1, outline fokus 2px, screen reader ARIA labels). Bahasa sistem dibatasi penuh Bahasa Indonesia untuk PoC. |

---

## 7. Pertanyaan Terbuka & Keputusan Resmi (Decisions Log)

### 7.1 Kategori Blocker (Telah Diputuskan & Disahkan)

1. **[Q-01 - Blocker] Strategi Fallback Ekstraksi AI pada Demo Day:**  
   - **Pertanyaan:** Bagaimana strategi penanganan kegagalan atau limitasi kuota API AI saat live demo/evaluasi?  
   - **Status:** **TERSELESAIKAN (RESOLVED)**.  
   - **Keputusan:** Sediakan fallback otomatis ke *High-Fidelity Deterministic Mock Extractor* jika API live mengalami kegagalan teknis, timeout, atau kehabisan kuota, sehingga 8 skenario evaluasi UAT tetap 100% andal.

2. **[Q-02 - Blocker] Konfigurasi Akun Pengujian Segregation of Duties (SoD):**  
   - **Pertanyaan:** Apakah disetujui penyediaan default seed data minimal 2 akun Finance Reviewer untuk pengujian Segregation of Duties (SoD)?  
   - **Status:** **TERSELESAIKAN (RESOLVED)**.  
   - **Keputusan:** Sediakan default seed data dengan minimal 2 akun Finance Reviewer aktif (`reviewer1@amiga.co.id` dan `reviewer2@amiga.co.id`), serta akun lengkap untuk seluruh peran (`pic_client@amiga.co.id`, `intake_support@amiga.co.id`, `service_lead@amiga.co.id`, `sysadmin@amiga.co.id`).

3. **[Q-03 - Blocker] Mekanisme Re-processing Pasca-EXCEPTION:**  
   - **Pertanyaan:** Saat PIC Klien melengkapi data pada dokumen EXCEPTION (misal nomor rekening), bagaimana alur re-processing yang diinginkan?  
   - **Status:** **TERSELESAIKAN (RESOLVED)**.  
   - **Keputusan:** Panggil ulang AI Engine untuk OCR berkas PDF dari awal setiap kali PIC mengirim koreksi kendala EXCEPTION (selaras 1:1 dengan alur BPMN F10: *"Ekstraksi & verifikasi ulang (Request ID sama)"*).

4. **[Q-06 - Blocker] Pilihan Backend Runtime, File Storage, & AI Model:**  
   - **Pertanyaan:** Apakah menggunakan FastAPI (Python) atau Fastify (Node.js/TypeScript), bagaimana penyimpanan file, dan model AI apa yang dipakai?  
   - **Status:** **TERSELESAIKAN (RESOLVED)**.  
   - **Keputusan:** Backend disahkan menggunakan **Fastify (Node.js 20 LTS / TypeScript)** untuk mewujudkan Unified Full-Stack TypeScript Monorepo bersama Next.js 16 (Active LTS), validasi TypeBox berkecepatan tinggi (>60k req/s), penyimpanan pluggable `STORAGE_BACKEND=local` (`../storage`) dan `s3`, serta integrasi **AWS Bedrock (`amazon.titan-text-express-v1`)** via `@aws-sdk/client-bedrock-runtime` dengan fallback mock deterministic.

### 7.2 Kategori Non-Blocker (Berjalan dengan Default Rekomendasi Arsitektur)

4. **[Q-04 - Non-Blocker] Siklus Penomoran Urut Voucher Pembayaran:**  
   - **Pertanyaan:** Apakah nomor urut lima digit `XXXXX` pada `VCH/YYYYMM/CLI/XXXXX` direset setiap awal bulan atau kontinu per klien?  
   - **Status:** Berjalan dengan default rekomendasi arsitek (reset bulanan per format `YYYYMM` standar pembukuan akuntansi).

5. **[Q-05 - Non-Blocker] Mekanisme Notifikasi Pengalihan Dokumen:**  
   - **Pertanyaan:** Apakah pengalihan tugas SoD / Service Lead memerlukan WebSocket/SSE atau cukup polling/invalidation?  
   - **Status:** Berjalan dengan default rekomendasi arsitek (auto-refetch / query invalidation TanStack Query interval 5 detik pada antrean aktif).
