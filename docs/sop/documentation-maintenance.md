# SOP — Pemeliharaan & Sinkronisasi Dokumentasi Proyek

**Nomor SOP:** SOP-AMIGA-DOC-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0  
**Dokumen Acuan:** `06-git-and-docs-discipline.md`, Global Rules SDD

---

## 1. Peran Penanggung Jawab (Owner Role)
**Lead Systems Architect / Technical Lead**

## 2. Pemicu (Trigger)
Penyelesaian tugas implementasi (`T-xxx`), penggabungan pull request, persetujuan keputusan arsitektur baru (ADR), atau revisi spesifikasi produk.

## 3. Langkah-Langkah Prosedur (Steps)
1. **Pemeriksaan Batas Panjang & Fokus Dokumen**:
   - Pastikan setiap berkas panduan dan spesifikasi di `docs/specs/` serta `.agents/rules/` tetap fokus dan berukuran di bawah ~400 baris.
   - Jika berkas melebihi batas, lakukan pemecahan modul secara logis tanpa menghilangkan konteks.
2. **Penegakan Aturan Ketertelusuran (Traceability Enforcement)**:
   - Setiap fitur atau tugas baru MUST mencantumkan ID kebutuhan yang valid (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`, `PF-xxx`).
   - DILARANG menyisipkan teks placeholder, seperti "TBD", "etc.", "dan lain-lain", atau "sama seperti di atas".
3. **Pembaruan Task Tracker (`docs/specs/tasks.md`)**:
   - Perbarui status checkbox tugas (`[-]` saat dikerjakan, `[x]` saat selesai dan lulus DoD).
   - Perbarui tabel cakupan kebutuhan (*coverage table*) di bagian bawah berkas.
4. **Pembaruan Berkas Riwayat (`CHANGELOG.md`)**:
   - Catat setiap penambahan atau perbaikan di bawah bagian `[Unreleased]` mengikuti format *Keep a Changelog* (Added, Changed, Fixed, Security).
5. **Pemeriksaan Keputusan Arsitektur (`system-design.md`)**:
   - Jika ada perubahan skema database, penambahan endpoint API, atau pemilihan pustaka baru, catat di bagian *Key Decisions Log (ADR)*.
6. **Verifikasi Tautan Berkas Markdown**:
   - Periksa seluruh link tautan berkas (`file:///...`) agar tidak ada broken links.

## 4. Verifikasi (Verification)
1. Periksa bahwa `git diff` dokumentasi secara akurat mencerminkan perubahan pada `git diff` kode sumber.
2. Jalankan pencarian pola terlarang (`grep -i "tbd" docs/`) untuk memastikan 0 temuan placeholder.
3. Seluruh dokumen tersusun dalam Bahasa Indonesia yang profesional dan presisi.

## 5. Prosedur Rollback (Rollback)
Jika pembaruan dokumentasi menimbulkan kontradiksi atau ketidaksinkronan spesifikasi:
1. Batalkan perubahan pada direktori dokumen:
   ```bash
   git checkout -- docs/specs/ CHANGELOG.md
   ```
2. Jalankan kembali workflow `/requirement-change` untuk menyelaraskan kembali dokumen dari sumber kebenaran utama.
