# Workflow: Implement Task

**Slash Command:** `/implement-task`  
**Deskripsi:** Prosedur langkah-demi-langkah bagi AI agent untuk mengimplementasikan satu unit tugas terisolasi ber-ID `T-xxx` dari `docs/specs/tasks.md` secara presisi, mematuhi guardrails arsitektur, dan memverifikasi Definition of Done (DoD).

---

## 1. Inputs
- Target Task ID (`T-xxx`) yang terdaftar di `docs/specs/tasks.md`.
- Persyaratan yang ditautkan (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`).
- Bagian arsitektur terkait di `docs/specs/system-design.md`.
- Aturan steering: `01-tech-stack.md`, `03-coding-standards.md`, `04-architecture-guardrails.md`, `05-testing-quality.md`.

## 2. Outputs
- Kode sumber fungsional pada direktori yang tepat (`frontend/` atau `backend/`).
- Berkas pengujian otomatis (`*.spec.ts` / `*.integration.spec.ts`) yang lulus 100%.
- Pembaruan status tugas menjadi `[x]` pada `docs/specs/tasks.md`.
- Catatan entri baru pada `CHANGELOG.md` di bawah bagian `[Unreleased]`.

---

## 3. Langkah-Langkah Eksekusi (Numbered Steps)

1. **Inspeksi Tugas & Prasyarat (Dependency Check)**  
   - Buka `docs/specs/tasks.md` dan cari `T-xxx`.
   - Pastikan seluruh tugas prasyarat (*dependencies*) telah berstatus selesai `[x]`. Jika belum, STOP.
   - Ubah status checkbox tugas menjadi in-progress `[-]` dan perbarui seksi "Next up" di bagian atas `tasks.md`.

2. **Pahami Kontrak Desain & Guardrails**  
   - Periksa model data, skema DTO, dan endpoint terkait pada `docs/specs/system-design.md`.
   - Jika tugas memodifikasi status invoice, pastikan hanya menggunakan 6 status resmi (`00-product-context.md`).
   - Jika tugas menyentuh query database, pastikan klausa `WHERE client_id IN (...)` ditegakkan (`04-architecture-guardrails.md`).

3. **Penyusunan Pengujian Otomatis (Test-Driven Vertical Slice)**  
   - Tulis unit test atau integration test sebelum atau bersamaan dengan kode implementasi.
   - Gunakan nama pengujian yang deskriptif: `it('should <expected> when <condition>')`.
   - Pastikan skenario UAT yang terikat (UAT-1 s.d. UAT-8) tercakup di dalam test suite.

4. **Implementasi Kode Minimal & Presisi**  
   - Implementasikan fitur HANYA pada berkas yang ditargetkan di deskripsi task.
   - Hindari over-engineering atau menambahkan pustaka di luar `01-tech-stack.md`.
   - Pastikan tidak ada penggunaan `any` dan tidak ada teks hitam `#000000` atau em dash (`—`).

5. **Verifikasi Kualitas & Eksekusi Pengujian**  
   - Jalankan pengecekan tipe: `pnpm typecheck` / `tsc --noEmit`. Wajib 0 error.
   - Jalankan pengujian lokal: `pnpm test`. Seluruh test case wajib berstatus PASS.
   - Periksa tidak adanya console log yang mengekspos nomor rekening atau data sensitif.

6. **Penyelesaian Tugas & Dokumentasi**  
   - Ubah status tugas di `docs/specs/tasks.md` menjadi `[x]`.
   - Tambahkan entri ringkas pada `CHANGELOG.md` di bawah kategori yang sesuai (Added / Changed / Fixed).
   - Buat Git commit dengan format: `<type>(<scope>): [T-xxx] <deskripsi>`.

---

## 4. Kondisi Berhenti (Stop Conditions)
Agent MUST segera menghentikan eksekusi dan melapor jika:
- Pengujian gagal dan membutuhkan modifikasi skema data di luar cakupan task.
- Ditemukan potensi race-condition pada logika Segregation of Duties.
- Tugas prasyarat belum selesai dikerjakan.
