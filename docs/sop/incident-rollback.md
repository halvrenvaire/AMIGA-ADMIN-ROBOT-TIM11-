# SOP — Penanganan Insiden & Prosedur Rollback Darurat

**Nomor SOP:** SOP-AMIGA-INC-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0  
**Dokumen Acuan:** `01-BRD.md` Bagian 6.3 (Matriks Risiko), `03-SRD.md` Bagian 5

---

## 1. Peran Penanggung Jawab (Owner Role)
**Incident Commander / Technical Lead**

## 2. Pemicu (Trigger)
Terjadi anomali kritis (P0/P1) di lingkungan produksi atau live demo, meliputi:
- Kegagalan API AI pihak ketiga (timeout/rate-limit).
- Antrean BullMQ macet (*stalled queue*) atau redis connection dropped.
- Terindikasi celah kebocoran data multi-tenant atau kegagalan penegakan SoD.
- Layanan aplikasi mengalami crash berulang (HTTP 500 error spike).

## 3. Langkah-Langkah Prosedur (Steps)
1. **Identifikasi & Triase Awal (Triage - < 2 Menit)**:
   - Identifikasi titik kegagalan: apakah pada layer API, Database, AI Worker, atau Storage S3.
2. **Penanganan Kegagalan Layanan Eksternal AI**:
   - Jika service AI pihak ketiga down:
     - Ubah environment variable `AI_PROVIDER=mock` di file `.env`.
     - Restart worker: `pm2 restart amiga-worker`.
     - Sistem otomatis beralih ke *High-Fidelity Deterministic Mock Extractor* tanpa menghentikan alur antrean invoice.
3. **Penanganan Kebocoran Keamanan atau Integritas Data**:
   - Jika terindikasi anomali hak akses, segera aktifkan maintenance window:
     - Aktifkan flag `MAINTENANCE_MODE=true` pada API Gateway.
     - Hentikan konsumsi antrean BullMQ sementara: `pnpm queue:pause`.
4. **Eksekusi Rollback Versi Aplikasi**:
   - Jika insiden dipicu oleh rilis kode baru, lakukan rollback instan ke Git commit/image stabil sebelumnya:
     ```bash
     git checkout tags/v1.0.0-stable
     pnpm build
     pm2 restart all
     ```
5. **Pembersihan Antrean Macet (Stalled Jobs Cleanup)**:
   - Jika Redis BullMQ mengalami dead-lock:
     ```bash
     pnpm queue:drain-failed
     ```

## 4. Verifikasi (Verification)
1. Periksa endpoint health check `/api/v1/health` menghasilkan status OK.
2. Jalankan uji pengunggahan invoice dummy dan pastikan status bergerak mulus ke `READY_FOR_REVIEW` atau `EXCEPTION`.
3. Verifikasi bahwa log audit mencatat seluruh peristiwa insiden dan pemulihan tanpa adanya data transaksi yang hilang.

## 5. Prosedur Rollback dari Rollback (Secondary Failover)
Jika langkah rollback gagal memulihkan sistem:
1. Alihkan DNS/Proxy ke node backup *cold-standby*.
2. Pulihkan database snapshot dari backup harian terakhir (Point-in-Time Recovery).
3. Informasikan kepada Service Lead dan PIC Klien mengenai estimasi waktu pemulihan.
