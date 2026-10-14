---
trigger: model_decision
description: "Disiplin git, konvensi commit konvensional, branching, serta protokol pembaruan tasks.md, CHANGELOG.md, dan dokumen desain."
---

# 06 — Git & Documentation Discipline: AMIGA Robot Admin

Integritas proyek bergantung pada ketertiban version control dan sinkronisasi dokumentasi. Setiap agent AI MUST mematuhi disiplin Git dan dokumen di bawah ini.

## 1. Strategi Branching (Branching Strategy)
- `main`: Branch stabil rilis resmi demo Hackathon / evaluasi juri.
- `feat/T-xxx-<nama-singkat>`: Branch untuk pengerjaan tugas atau fitur baru (misal: `feat/T-102-ai-bullmq-worker`).
- `fix/T-xxx-<nama-singkat>`: Branch untuk perbaikan cacat atau bug (misal: `fix/T-108-sod-race-condition`).

## 2. Format Pesan Commit (Conventional Commits dengan ID Tugas)
Setiap commit MUST mengikuti pola: `<type>(<scope>): [T-xxx] <deskripsi ringkas imperative>`
- Tipe Commit yang Diizinkan:
  - `feat`: Penambahan fitur atau kapabilitas baru.
  - `fix`: Perbaikan bug atau resolusi exception.
  - `test`: Penambahan atau pembaruan unit/integration test.
  - `refactor`: Restrukturisasi kode tanpa mengubah fungsionalitas.
  - `docs`: Pembaruan spesifikasi, tasks, atau dokumentasi SOP.
  - `chore`: Konfigurasi build, dependensi, atau skrip dev.

*Contoh:*
- `feat(verification): [T-105] implement calculation discrepancy business rule`
- `fix(review): [T-109] fix auto-reassign query for least-loaded reviewer`
- `docs(tasks): [T-102] mark AI worker task as completed in tracker`

## 3. Protokol Pembaruan Dokumentasi (Kapan Memperbarui Dokumen)
1. **Pembaruan `docs/specs/tasks.md`**:
   - MUST diperbarui sebelum memulai tugas: ubah checkbox status menjadi `[-]` (in progress) dan catat di "Next up".
   - MUST diperbarui segera setelah tugas selesai dan lulus DoD: ubah checkbox status menjadi `[x]` (completed).
2. **Pembaruan `CHANGELOG.md`**:
   - Setiap kali tugas selesai, tambahkan catatan entri pada bagian `[Unreleased]` mengikuti format Keep a Changelog (Added, Changed, Fixed, Security).
3. **Pembaruan `docs/specs/system-design.md`**:
   - Jika terdapat modifikasi skema DB, penambahan endpoint baru, atau perubahan alur status, dokumen desain sistem MUST diperbarui selaras sebelum kode di-merge.

## 4. Wrong vs Right: Format Commit & Log Entri

### WRONG (Pesan Ambigu Tanpa Traceability ID)
```bash
# SALAH: Tidak ada tipe, tidak ada scope, dan tidak merujuk ke task ID
git commit -m "update code and fix error"
git commit -m "wip changes"
```

### RIGHT (Terstruktur, Imperative, & Traceable)
```bash
# BENAR: Jelas jenis perubahannya, modul yang disentuh, dan ID task pelacaknya
git commit -m "feat(intake): [T-101] add multi-page validation for pdf uploads <= 5 pages"
git commit -m "test(sod): [T-107] add integration test for uploader approval rejection"
```
