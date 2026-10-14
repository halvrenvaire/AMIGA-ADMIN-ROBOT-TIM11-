# SOP — Rilis Aplikasi & Deployment Milestone

**Nomor SOP:** SOP-AMIGA-OPS-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0  
**Dokumen Acuan:** `01-BRD.md` Bagian 7 & 8, `03-SRD.md` Bagian 5

---

## 1. Peran Penanggung Jawab (Owner Role)
**Technical Lead / Release Manager**

## 2. Pemicu (Trigger)
Penyelesaian sprint milestone (Sprint 0 - 3), persiapan evaluasi juri Demo Day MAIN Hackathon 2026, atau deployment rilis versi baru.

## 3. Langkah-Langkah Prosedur (Steps)
1. **Pemeriksaan Prasyarat Rilis (Release Gate Audit)**:
   - Pastikan seluruh task pada `docs/specs/tasks.md` telah berstatus `[x]` (selesai).
   - Jalankan workflow `/review-and-audit` dan pastikan hasil laporan di `docs/specs/99-audit-report.md` berstatus **PASS**.
2. **Pemeriksaan Tipe & Pengujian Menyeluruh**:
   ```bash
   pnpm typecheck
   pnpm test
   pnpm test:e2e
   ```
   *(Seluruh pengujian unit, integrasi, dan 8 skenario UAT wajib 100% lulus tanpa kegagalan).*
3. **Pemberian Tag Versi & Pembaruan Changelog**:
   - Pindahkan entri `[Unreleased]` pada `CHANGELOG.md` ke versi rilis baru (misal: `[v1.0.0-poc] - 2026-10-13`).
   - Buat Git tag resmi:
     ```bash
     git tag -a v1.0.0-poc -m "Release v1.0.0 PoC Demo Day AMIGA Robot Admin"
     git push origin v1.0.0-poc
     ```
4. **Pembangunan Bundle Produksi (Production Build)**:
   ```bash
   pnpm build
   ```
5. **Eksekusi Migrasi Database Staging/Production**:
   ```bash
   pnpm db:migrate:deploy
   ```
6. **Deploy / Restart Service**:
   - Terapkan container baru atau restart proses aplikasi di balik reverse proxy Nginx.

## 4. Verifikasi (Verification)
1. Jalankan smoke-test pada 8 skenario UAT utama:
   - Unggah 1 file invoice multi-line item dummy -> verifikasi status bergeser `QUEUED -> PROCESSING -> READY_FOR_REVIEW`.
   - Lakukan approval dan pastikan voucher terbit dalam <= 3 detik.
   - Uji penolakan SoD dengan mencoba menyetujui dokumen yang diunggah akun sendiri.
2. Periksa health check status HTTP 200 pada `/api/v1/health`.

## 5. Prosedur Rollback (Rollback)
Jika terjadi kegagalan fatal pasca-rilis:
1. Revert container/commit ke versi stabil sebelumnya:
   ```bash
   git checkout tags/v0.9.0-previous
   pnpm build && pm2 restart all
   ```
2. Jika migrasi database perlu di-rollback:
   - Jalankan script down migration terverifikasi atau restore snapshot database sebelum deployment.
3. Beritahukan Service Lead dan Reviewer untuk menunda approval hingga status dinyatakan stabil.
