# Workflow: Review and Audit

**Slash Command:** `/review-and-audit`  
**Deskripsi:** Prosedur audit dan peninjauan menyeluruh (*deep architectural & security audit*) untuk memeriksa kepatuhan implementasi terhadap guardrails arsitektur, isolasi multi-tenant, penegakan SoD, kelengkapan jejak audit, dan standar anti-slop sebelum rilis milestone atau presentasi demo.

---

## 1. Inputs
- Seluruh basis kode pada `apps/web/` dan `apps/api/`.
- Skema dan migrasi database pada `apps/api/prisma/`.
- Dokumen spesifikasi aktif: `docs/specs/00-analysis.md`, `system-design.md`, `tasks.md`, `traceability-matrix.md`.
- Aturan kualitas: `03-coding-standards.md`, `04-architecture-guardrails.md`, `05-testing-quality.md`.

## 2. Outputs
- Laporan audit mandiri komprehensif pada `docs/specs/99-audit-report.md`.
- Daftar temuan cacat (*defect findings*) dengan level keparahan (CRITICAL, HIGH, MEDIUM, LOW).
- Status kelayakan rilis (*Pass / Fail Gate Decision*).

---

## 3. Langkah-Langkah Eksekusi (Numbered Steps)

1. **Audit Penegakan Segregation of Duties (SoD Check)**  
   - Periksa seluruh controller dan service yang menangani persetujuan invoice (`/approve`).
   - Verifikasi bahwa validasi `uploader_id != reviewer_id` berjalan di sisi server di dalam serializable database transaction.
   - Verifikasi bahwa penolakan SoD memicu pengalihan penugasan otomatis ke reviewer lain yang aktif dan mencatat event ke `audit_logs`.

2. **Audit Batas Isolasi Multi-Tenant (Multi-Tenant Boundary Check)**  
   - Jalankan pencarian statis (`grep`) pada seluruh query Prisma di `apps/api/src/modules/`.
   - Pastikan TIDAK ADA query ke tabel `invoice_requests` atau turunannya yang tidak menyaring `client_id` milik user yang terautentikasi.
   - Verifikasi penanganan error: akses dokumen klien lain wajib menghasilkan 403 atau 404.

3. **Audit Immutability Jejak Audit (Audit Ledger Check)**  
   - Periksa file schema Prisma dan migration scripts: pastikan tabel `audit_logs` tidak memiliki mutasi via `UPDATE` atau `DELETE`.
   - Verifikasi bahwa setiap perubahan nilai nominal mencatat `old_value`, `new_value`, nama aktor, peran, dan waktu presisi.

4. **Audit Integritas Model Data (DRD/SRD Field-by-Field Match)**  
   - Bandingkan 10 tabel di `prisma/schema.prisma` terhadap kamus data `03-SRD.md` Bagian 3:
     - Verifikasi constraint foreign key, tipe data decimal untuk uang, dan index duplikasi.
     - Verifikasi 6 status resmi dokumen dan 4 issue codes.

5. **Audit Eksekusi Pengujian Otomatis & Skenario UAT**  
   - Jalankan `pnpm test:coverage`. Pastikan coverage memenuhi target (>= 80% global, 100% verification engine & SoD).
   - Verifikasi bahwa 8 skenario UAT telah memiliki test case integrasi/E2E yang berstatus PASS.

6. **Audit Desain Visual & Anti-Slop Filter**  
   - Pindai kode CSS dan TSX frontend:
     - Pastikan tidak ada warna hitam pekat `#000000` (wajib Ink Navy `#0B3558`).
     - Pastikan tidak ada karakter em dash (`—`) pada copy UI.
     - Pastikan tombol tidak berbentuk pill 9999px tanpa alasan fungsional.
     - Pastikan seluruh teks memenuhi rasio kontras WCAG AA (>= 4.5:1).

7. **Penyusunan Laporan Audit & Rekomendasi**  
   - Tulis seluruh temuan, bukti kode, dan perbaikan yang telah dilakukan ke `docs/specs/99-audit-report.md`.
   - Tetapkan keputusan gate: **PASS** jika 0 Critical & 0 High defect; **FAIL** jika masih ada kendala kritis.

---

## 4. Kondisi Berhenti (Stop Conditions)
Audit dinyatakan **GAGAL (FAIL)** dan menghentikan pengesahan rilis jika:
- Ditemukan celah kebocoran data antar-klien (IDOR lintas tenant).
- Validasi Segregation of Duties dapat dibypass melalui API langsung.
- Jejak audit gagal mencatat perubahan nilai pada pengujian integrasi.
- Salah satu dari 8 skenario UAT gagal dieksekusi.
