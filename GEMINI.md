# GEMINI.md — Master Index & Project Operating System

**Proyek:** AMIGA Robot Admin (Intelligent Vendor Invoice-to-Voucher Processing)  
**Tipe Rilis:** Proof of Concept (PoC) — MAIN Hackathon 2026  
**Arsitektur:** Spec-Driven Development (Kiro-style) & Modular Monolith Event-Driven Worker  
**Status:** Sistem Operasi Proyek Aktif (Phase 1 Baseline)

---

## 1. Ikhtisar Sistem Operasi Proyek (Project Operating System)

AMIGA Robot Admin mengotomatisasi pemrosesan invoice vendor (PDF maks. 5 halaman) menjadi voucher pembayaran resmi terverifikasi dalam hitungan detik. Seluruh agen AI dan software engineer yang beroperasi di repositori ini terikat oleh aturan operasional sistem berikut:

```
apps-2/
├── .agents/
│   ├── rules/                      # Steering Rules (Antigravity YAML frontmatter)
│   │   ├── 00-product-context.md   # [always_on] Visi produk, peran, 6 status, non-goals
│   │   ├── 01-tech-stack.md        # [always_on] Versi stack, allowed/forbidden libs, env
│   │   ├── 02-project-structure.md # [model_decision] Struktur direktori & batas modul
│   │   ├── 03-coding-standards.md  # [glob] Standar TS, RFC 7807 error, DB rules, audit
│   │   ├── 04-architecture-guardrails.md # [always_on] Layering, SoD, multi-tenant boundary
│   │   ├── 05-testing-quality.md   # [glob] Piramida tes, 8 skenario UAT, Definition of Done
│   │   └── 06-git-and-docs-discipline.md # [model_decision] Branching, commits, tasks sync
│   ├── workflows/                  # Prosedur aksi runnable via slash commands
│   │   ├── spec-new-feature.md     # /spec-new-feature
│   │   ├── implement-task.md       # /implement-task
│   │   ├── fix-bug.md              # /fix-bug
│   │   ├── requirement-change.md   # /requirement-change
│   │   └── review-and-audit.md     # /review-and-audit
│   └── skills/                     # Pustaka skill lokal (antislop, codebase-design, frontend-design)
├── frontend/                   # Next.js 16 Frontend (App Router, Tailwind v4, React 19)
├── backend/                    # Fastify Backend Core (TypeScript, Prisma ORM, BullMQ, PostgreSQL 16, AWS Bedrock)
├── docs/
│   ├── requirements/               # Sumber kebenaran: BRD, PRD, SRD, DRD, BPMN
│   ├── specs/                      # Spesifikasi hulu-hilir: 00-analysis, system-design, tasks, traceability-matrix
│   └── sop/                        # Prosedur operasional teruji (onboarding, release, migration, dll)
├── CHANGELOG.md                    # Riwayat perubahan proyek standar Keep a Changelog
└── GEMINI.md                       # Master index repositori & 10 aturan tanpa kompromi
```

---

## 2. Urutan Membaca Wajib bagi AI Agent (Reading Order)

Sebelum memulai perencanaan, desain, atau pengeditan kode apa pun, agen AI MUST membaca berkas-berkas berikut secara berurutan:

1. **`GEMINI.md`** (Berkas ini): Memahami batas proyek dan 10 perilaku tanpa kompromi.
2. [`.agents/rules/00-product-context.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/00-product-context.md): Memahami apa yang kita bangun, 6 status siklus hidup dokumen, batasan peran pengguna, dan non-goals.
3. [`.agents/rules/01-tech-stack.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/01-tech-stack.md): Memahami versi pustaka resmi, pustaka yang diizinkan vs dilarang, dan variabel lingkungan.
4. [`.agents/rules/04-architecture-guardrails.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/04-architecture-guardrails.md): Memahami batas isolasi multi-tenant, penegakan SoD di server, dan immutability audit log.
5. [`docs/specs/00-analysis.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/00-analysis.md): Menelaah katalog kebutuhan ber-ID stabil (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`, `PF-xxx`), digest BPMN, dan skema data relasional.
6. [`docs/specs/system-design.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/system-design.md): Mempelajari kontrak API, ERD, dan diagram sekuens (setelah Phase 2 selesai).
7. [`docs/specs/tasks.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/tasks.md): Mengambil tugas target ber-ID `T-xxx` beserta Acceptance Criteria-nya.
8. Aturan kontekstual tambahan saat menulis kode:
   - Menulis/mengedit TypeScript: [`.agents/rules/03-coding-standards.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/03-coding-standards.md)
   - Menulis/mengedit unit/E2E test: [`.agents/rules/05-testing-quality.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/05-testing-quality.md)
   - Menata letak file dan commit Git: [`.agents/rules/02-project-structure.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/02-project-structure.md) & [`.agents/rules/06-git-and-docs-discipline.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/rules/06-git-and-docs-discipline.md)

---

## 3. Eksekusi Workflow Melalui Slash Commands

Gunakan slash commands berikut untuk menjalankan prosedur otomasi standar:

- **`/spec-new-feature`** ([`.agents/workflows/spec-new-feature.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/workflows/spec-new-feature.md)):  
  Merumuskan spesifikasi fitur baru dari kebutuhan bisnis ke katalog requirement, desain sistem, dan task tracker tanpa kontradiksi.
- **`/implement-task`** ([`.agents/workflows/implement-task.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/workflows/implement-task.md)):  
  Mengimplementasikan satu tugas target ber-ID `T-xxx` dari `docs/specs/tasks.md`, menulis tes regresi, memverifikasi DoD, dan memperbarui changelog.
- **`/fix-bug`** ([`.agents/workflows/fix-bug.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/workflows/fix-bug.md)):  
  Investigasi akar masalah (*root cause*), penulisan failing test terlebih dahulu, perbaikan kode minimal, dan pencegahan regresi.
- **`/requirement-change`** ([`.agents/workflows/requirement-change.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/workflows/requirement-change.md)):  
  Audit dampak perubahan (*change impact analysis*), pembaruan hirarki dokumen hulu-hilir, dan sinkronisasi status task.
- **`/review-and-audit`** ([`.agents/workflows/review-and-audit.md`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/.agents/workflows/review-and-audit.md)):  
  Audit menyeluruh terhadap kepatuhan arsitektur, SoD server-side, isolasi multi-tenant, coverage pengujian, dan filter anti-slop sebelum rilis milestone.

---

## 4. Sepuluh Perilaku Tanpa Kompromi (10 Non-Negotiable Behaviors)

1. **Penegakan Mutlak Segregation of Duties (SoD)**:  
   Pengunggah dokumen DILARANG MENYETUJUI dokumennya sendiri di sisi server dalam transaksi database atomik. Jika terjadi pelanggaran, persetujuan wajib ditolak dan dokumen otomatis dialihkan ke reviewer lain (`BR-002`, `SR-004`).
2. **Nol Fabrikasi (Zero Fabrication)**:  
   DILARANG mengarang kebutuhan, aturan bisnis, atau format payload. Segala hal yang tidak tertera di dokumen acuan wajib dicatat sebagai Asumsi atau Pertanyaan Terbuka.
3. **Isolasi Mutlak Multi-Tenant**:  
   Seluruh query pembacaan dan modifikasi invoice MUST memuat filter tenant `WHERE client_id IN (...)`. Akses lintas klien wajib ditolak dengan respon 403 atau 404 (`SR-003`, `BR-014`).
4. **Ketertelusuran Berbasis ID Stabil (Mandatory Traceability)**:  
   Setiap fungsi, endpoint, task, dan test case wajib mencantumkan ID kebutuhan yang dipenuhinya (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`, `PF-xxx`).
5. **Keabadian Jejak Audit (Immutable Audit Ledger)**:  
   Tabel `audit_logs` bersifat append-only. Dilarang mengeksekusi operasi `UPDATE` atau `DELETE` pada tabel audit (`SR-016`, `BR-015`).
6. **AI Tidak Mengambil Keputusan Bisnis**:  
   AI Engine HANYA mengekstrak teks; validasi logika dijalankan oleh sistem, dan persetujuan voucher wajib ditinjau manusia (*Human-in-the-Loop*) (`PR-007`).
7. **Pemberlakuan Hirarki Sumber Kebenaran**:  
   `BRD > PRD > SRD > DRD > BPMN` untuk intent; `DRD` untuk token/tata letak antarmuka; `BPMN` untuk urutan sekuens; `SRD` untuk definisi skema data.
8. **Disiplin Desain & Anti-Slop**:  
   Dilarang menggunakan warna hitam pekat `#000000` (wajib Ink Navy `#0B3558`), dilarang teks em dash (`—`), dilarang tombol kapsul 9999px tanpa guna, dan dilarang klaim tanpa bukti pengujian (`DR-004`, `DR-008`).
9. **Bebas Placeholder & Konten Lengkap**:  
   Dilarang menggunakan teks "TBD", "TODO nanti", "etc.", "dan lain-lain", atau "sama seperti di atas". Setiap berkas wajib lengkap, presisi, dan langsung dapat dieksekusi.
10. **Kepatuhan Terhadap Definition of Done (DoD)**:  
    Tidak ada tugas yang dianggap selesai tanpa lulus kompilasi tipe (`tsc --noEmit`), 100% lulus tes otomatis, verifikasi 8 skenario UAT, dan pembaruan `tasks.md` serta `CHANGELOG.md`.

---

<!-- antislop:start -->
## antislop
For UI, copy, people, mobile layout, or code comments work, read `.agents/skills/antislop/SKILL.md` (core) and then the skill for the task:
- UI / visual: `skills/antislop-ui/SKILL.md`
- Copy & text: `skills/antislop-copywriting/SKILL.md`
- People: `skills/antislop-human/SKILL.md`
- Mobile / responsive: `skills/antislop-layoutmobile/SKILL.md`
- Code comments: `skills/antislop-code/SKILL.md`
Before starting, follow the core's "Two Usage Modes" section in strict order: explicit session instruction first, then global preference, then ask. A session instruction always wins. For a resolved mode, say `antislop active: <mode> (session override).` or `antislop active: <mode> (global preference).` once before presenting findings or making edits, using the actual mode and source. Acknowledging the user's request without naming the source does not replace this notice.
<!-- antislop:end -->
