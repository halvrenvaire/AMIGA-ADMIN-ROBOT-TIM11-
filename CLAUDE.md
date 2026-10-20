# CLAUDE.md

Panduan untuk asisten AI yang bekerja di repo AMIGA Robot Admin. Detail fitur, arsitektur, dan cara menjalankan ada di [README.md](README.md).

## Tracking tugas: `docs/TASKS.md`

`docs/TASKS.md` adalah daftar tugas kecil dari feedback owner AMIGA, dipakai tim untuk memantau progres.

- **Setiap perubahan kode yang menyelesaikan, memulai, atau mengubah tugas di `docs/TASKS.md` wajib ikut memperbarui file itu dalam commit yang sama**: centang status, isi hash commit, perbarui tabel "Ringkasan progres", tanggal "Terakhir diperbarui", dan baris "Riwayat pembaruan".
- Feedback owner baru → tambahkan sebagai tugas baru (ID berikutnya, mis. `T9.1`) sebelum dikerjakan.
- Jawaban owner atas pertanyaan terbuka (Tahap 7) → isi kolom Jawaban dan sesuaikan tugas terkait.
- Bila perubahan memengaruhi isi BRD/PRD/BPMN/SOP, catat di Tahap 8 bahwa dokumen tersebut perlu diperbarui.
- Hash commit belum ada saat commit dibuat: isi `belum di-commit` dulu, lalu ganti dengan hash di commit berikutnya.

## Commit dan push

- Setelah memperbarui `docs/TASKS.md`, commit lalu **push ke GitHub** (`origin main`).
- **Jangan pernah commit `.env`** atau file rahasia lain, `backups/`, maupun `storage/`.
- **Jangan menambahkan atribusi AI** (mis. `Co-Authored-By: Claude`) di pesan commit atau PR.
- Pesan commit dalam Bahasa Indonesia, format `feat:` / `fix:` / `docs:` / `chore:`.
- Hanya commit file yang memang bagian dari perubahan; jangan ikut meng-commit pekerjaan orang lain yang belum selesai.

## Bahasa

Dokumen dan teks antarmuka memakai Bahasa Indonesia yang sederhana.
