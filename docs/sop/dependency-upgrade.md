# SOP — Pembaruan & Manajemen Ketergantungan (Dependency Upgrade)

**Nomor SOP:** SOP-AMIGA-SEC-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0  
**Dokumen Acuan:** `01-tech-stack.md`, `03-coding-standards.md`

---

## 1. Peran Penanggung Jawab (Owner Role)
**Senior Software Engineer / Security Lead**

## 2. Pemicu (Trigger)
Peringatan kerentanan keamanan otomatis (`pnpm audit`), rilis patch keamanan kritis (CVE), atau siklus pemeliharaan bulanan versi dependensi.

## 3. Langkah-Langkah Prosedur (Steps)
1. **Audit Kerentanan Awal**:
   ```bash
   pnpm audit
   ```
2. **Pemeriksaan Batasan Stack Resmi**:
   - Buka `.agents/rules/01-tech-stack.md`.
   - **PERINGATAN:** DILARANG mengupgrade Next.js ke versi yang merusak React 19, dilarang downgrade ke Tailwind v3, dan dilarang menginstal pustaka terlarang (misal Moment.js atau Axios).
3. **Pembuatan Branch Kerja Terisolasi**:
   ```bash
   git checkout -b chore/deps-upgrade-$(date +%Y%m%d)
   ```
4. **Eksekusi Pembaruan Parsial (Bukan Blanket Upgrade)**:
   - Perbarui paket target secara eksplisit:
     ```bash
     pnpm update <nama-paket>@latest
     ```
5. **Verifikasi Kompilasi & Pengujian Otomatis**:
   ```bash
   pnpm typecheck
   pnpm test
   pnpm test:e2e
   ```
6. **Verifikasi Visual Antarmuka Kritis**:
   - Jalankan `pnpm dev` dan uji manual rendering Layar 03 Split-Screen (pastikan PDF.js canvas tidak mengalami regresi rendering).
7. **Pembaruan Lockfile & Git Commit**:
   ```bash
   git add package.json pnpm-lock.yaml
   git commit -m "chore(deps): upgrade <nama-paket> to <version>"
   ```

## 4. Verifikasi (Verification)
1. Perintah `pnpm audit` menghasilkan 0 kerentanan tingkat HIGH atau CRITICAL.
2. Perintah `pnpm typecheck` menghasilkan 0 error tipe TypeScript.
3. Seluruh 8 skenario UAT lulus pengujian otomatis Playwright/Vitest.

## 5. Prosedur Rollback (Rollback)
Jika pembaruan dependensi menimbulkan breaking change atau instabilitas:
1. Batalkan perubahan pada manifest dan lockfile:
   ```bash
   git checkout -- package.json pnpm-lock.yaml
   ```
2. Pulihkan instalasi dependensi bersih:
   ```bash
   pnpm install --frozen-lockfile
   ```
3. Hapus branch kerja upgrade dan dokumentasikan alasan pembatalan jika terjadi konflik dependensi.
