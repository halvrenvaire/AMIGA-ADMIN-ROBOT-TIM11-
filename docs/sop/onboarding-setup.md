# SOP — Onboarding & Lingkungan Pengembangan Lokal

**Nomor SOP:** SOP-AMIGA-DEV-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0 (PoC Baseline)  
**Dokumen Acuan:** `03-SRD.md` Bagian 2

---

## 1. Peran Penanggung Jawab (Owner Role)
**Full-Stack Engineer / Technical Lead**

## 2. Pemicu (Trigger)
Perekrutan engineer baru ke dalam tim, setup ulang mesin kerja lokal, atau inisialisasi lingkungan staging dari awal.

## 3. Langkah-Langkah Prosedur (Steps)
1. **Pemeriksaan Prasyarat Sistem**:
   - Pastikan terpasang: Node.js 20 LTS, pnpm v9+, Docker Desktop v24+, dan Git.
2. **Kloning Repositori & Instalasi Dependensi**:
   ```bash
   git clone <repo-url> apps-2
   cd apps-2
   pnpm install
   ```
3. **Konfigurasi Lingkungan (.env)**:
   - Salin template konfigurasi:
     ```bash
     cp .env.example .env
     ```
   - Pastikan variabel `DATABASE_URL`, `REDIS_HOST`, dan `STORAGE_ENDPOINT` terisi sesuai service lokal.
4. **Menjalankan Infrastruktur Pendukung (Docker Compose)**:
   ```bash
   docker compose up -d postgres redis minio
   ```
5. **Inisialisasi Database & Seeding Data**:
   ```bash
   pnpm db:migrate
   pnpm db:seed
   ```
   *(Menyediakan akun uji bawaan: reviewer1, reviewer2, pic_client, intake_support, service_lead, sysadmin).*
6. **Menjalankan Aplikasi (Development Server)**:
   ```bash
   pnpm dev
   ```
   - Frontend Next.js berjalan di `http://localhost:3000`
   - Backend Fastify API berjalan di `http://localhost:4000/api/v1`

## 4. Verifikasi (Verification)
1. Buka browser ke `http://localhost:3000` dan login dengan `reviewer1@amiga.co.id` / `Password123!`.
2. Pastikan Layar 01 Dashboard Antrean termuat dengan 0 console error dalam tempo <= 2 detik.
3. Akses `http://localhost:4000/api/v1/health` dan pastikan respon status `{ "status": "ok", "db": true, "redis": true }`.

## 5. Prosedur Rollback (Rollback)
Jika inisialisasi lingkungan gagal atau korup:
1. Hentikan seluruh container dan bersihkan volume:
   ```bash
   docker compose down -v
   ```
2. Bersihkan dependensi dan build cache:
   ```bash
   rm -rf node_modules frontend/node_modules backend/node_modules .turbo
   ```
3. Ulangi langkah dari nomor 2.
