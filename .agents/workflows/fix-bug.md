# Workflow: Fix Bug

**Slash Command:** `/fix-bug`  
**Deskripsi:** Prosedur investigasi sistematis untuk mendiagnosis akar masalah (*root cause*), menulis tes regresi otomatis, memperbaiki cacat tanpa merusak arsitektur yang ada, dan memastikan bug tidak terulang kembali.

---

## 1. Inputs
- Laporan bug, kode kendala tak terduga, atau log kegagalan sistem.
- Request ID atau kondisi pemicu bug.
- Aturan arsitektur: `03-coding-standards.md`, `04-architecture-guardrails.md`, `05-testing-quality.md`.

## 2. Outputs
- Minimal 1 test regresi otomatis baru yang mereproduksi cacat (gagal sebelum perbaikan, lulus setelah perbaikan).
- Perbaikan kode minimal terisolasi pada modul terkait.
- Pembaruan `CHANGELOG.md` di bawah sub-seksi `[Fixed]`.

---

## 3. Langkah-Langkah Eksekusi (Numbered Steps)

1. **Analisis Akar Masalah (Root Cause Analysis)**  
   - Periksa alur eksekusi dari input controller hingga query database.
   - Periksa apakah bug terkait dengan normalisasi string vendor/nomor invoice, perhitungan pembulatan subtotal, batas multi-tenant, atau race-condition SoD.
   - Jangan berasumsi; temukan baris kode spesifik penyebab kegagalan.

2. **Penyusunan Tes Regresi Pereproduksi Bug (Failing Test First)**  
   - Buat test case baru yang mensimulasikan payload atau skenario pemicu error.
   - Jalankan tes dan pastikan tes GAGAL (RED) dengan pesan error yang identik dengan laporan bug.

3. **Uji Dampak Terhadap Guardrails Arsitektur**  
   - Pastikan solusi perbaikan TIDAK mengorbankan isolasi multi-tenant (`SR-003`).
   - Pastikan solusi TIDAK melonggarkan aturan Segregation of Duties (`SR-004`).
   - Pastikan setiap mutasi data tetap menulis jejak audit lengkap (`SR-016`).

4. **Eksekusi Perbaikan Kode Minimal**  
   - Perbaiki kode sumber hanya pada titik kegagalan (*patch the root cause, not the symptoms*).
   - Dilarang membungkus error dengan try-catch kosong atau menyembunyikan exception.
   - Pastikan kode perbaikan mematuhi aturan strict typing dan RFC 7807 problem details.

5. **Verifikasi Tes Regresi & Seluruh Test Suite**  
   - Jalankan kembali tes regresi yang sebelumnya gagal; pastikan sekarang LULUS (GREEN).
   - Jalankan seluruh test suite proyek untuk memastikan tidak ada efek samping regresi (*no regressions*).
   - Jalankan `pnpm typecheck` untuk menjamin tidak ada kerusakan tipe.

6. **Pencatatan Dokumen & Git Commit**  
   - Dokumentasikan rincian bug dan solusi pada `CHANGELOG.md` bagian `[Fixed]`.
   - Lakukan commit dengan format: `fix(<scope>): [T-xxx] <deskripsi perbaikan bug>`.

---

## 4. Kondisi Berhenti (Stop Conditions)
Agent MUST berhenti dan meminta konfirmasi jika:
- Perbaikan bug membutuhkan perubahan destruktif pada skema database yang sudah berjalan.
- Bug terjadi akibat pertentangan antara dua dokumen sumber (misal perbedaan logika antara BRD dan BPMN).
- Perbaikan berpotensi melanggar privasi data atau mengekspos PII pada audit log.
