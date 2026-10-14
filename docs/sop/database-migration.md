# SOP — Migrasi Skema Database Relasional

**Nomor SOP:** SOP-AMIGA-DBA-001  
**Sistem:** AMIGA Robot Admin  
**Versi:** 1.0  
**Dokumen Acuan:** `03-SRD.md` Bagian 3, `04-architecture-guardrails.md`

---

## 1. Peran Penanggung Jawab (Owner Role)
**Database Administrator (DBA) / Backend Lead**

## 2. Pemicu (Trigger)
Kebutuhan penambahan tabel, kolom, indeks, atau constraint relasional baru yang telah disahkan pada dokumen arsitektur `system-design.md`.

## 3. Langkah-Langkah Prosedur (Steps)
1. **Pencadangan Database Pra-Migrasi (Mandatory Backup)**:
   ```bash
   pg_dump -U amiga_user -h localhost -d amiga_robot_admin -F c -b -v -f "backup_pre_migration_$(date +%Y%m%d_%H%M%S).dump"
   ```
2. **Modifikasi Skema Prisma (`backend/prisma/schema.prisma`)**:
   - Tambahkan model atau kolom baru.
   - Pastikan foreign key dilengkapi indeks dan constraint referensial (`ON DELETE RESTRICT` untuk vouchers/audit, `CASCADE` untuk line items/issues).
3. **Pembuatan Berkas Migrasi SQL (Development)**:
   ```bash
   pnpm --filter backend prisma migrate dev --name <nama_migrasi_deskriptif>
   ```
4. **Pemeriksaan Isi Berkas SQL Migrasi**:
   - Buka berkas SQL yang baru terbentuk di `backend/prisma/migrations/<timestamp>_<nama_migrasi>/migration.sql`.
   - Pastikan TIDAK ADA instruksi `DROP TABLE` atau `DROP COLUMN` yang tidak disengaja.
5. **Eksekusi Migrasi ke Lingkungan Target (Staging/Production)**:
   ```bash
   pnpm --filter backend prisma migrate deploy
   ```
6. **Regenerasi Type Client**:
   ```bash
   pnpm --filter backend prisma generate
   ```

## 4. Verifikasi (Verification)
1. Periksa struktur tabel dan indeks menggunakan Prisma Studio:
   ```bash
   pnpm --filter backend prisma studio
   ```
2. Jalankan integration test database untuk memvalidasi constraint SoD dan multi-tenant:
   ```bash
   pnpm test:integration
   ```
3. Pastikan service backend dapat booting dan melakukan query tanpa error koneksi.

## 5. Prosedur Rollback (Rollback)
Jika migrasi mengakibatkan error atau kegagalan aplikasi:
1. Hentikan service backend untuk mencegah inkonsistensi data:
   ```bash
   pm2 stop amiga-api
   ```
2. Pulihkan snapshot database dari berkas backup:
   ```bash
   pg_restore -U amiga_user -h localhost -d amiga_robot_admin --clean --if-exists backup_pre_migration_*.dump
   ```
3. Tandai status migrasi yang gagal sebagai rolled back di Prisma:
   ```bash
   pnpm --filter api prisma migrate resolve --rolled-back <migration_name>
   ```
4. Jalankan kembali service backend dan verifikasi status operasional.
