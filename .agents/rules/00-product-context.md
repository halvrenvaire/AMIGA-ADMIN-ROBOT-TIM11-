---
trigger: always_on
description: "Konteks produk AMIGA Robot Admin: visi bisnis, pengguna, batasan scope, non-goals, dan link glosarium."
---

# 00 — Product Context: AMIGA Robot Admin

Dokumen aturan ini menetapkan batas pemahaman produk bagi seluruh AI agent dan engineer. Seluruh pekerjaan implementasi MUST selaras dengan konteks di bawah ini.

## 1. Visi & Masalah yang Diselesaikan [BR-001, PR-001]
AMIGA beroperasi sebagai *Back Office Operating Partner* multi-industri. AMIGA Robot Admin mengotomatisasi transformasi invoice vendor (berkas PDF digital maks. 5 halaman) menjadi voucher pembayaran resmi terverifikasi dalam hitungan detik.

Masalah operasional manual yang dihapus tuntas:
1. **Pengetikan Ulang Manual**: Menghapus waktu input 5–10 menit per invoice dan penyusunan voucher 5–15 menit.
2. **Risiko Kesalahan Finansial**: Mencegah salah ketik nominal/rekening bank, salah hitung subtotal/total, dan pembayaran ganda (*duplicate payment*).
3. **Ketiadaan Jejak Audit**: Membangun pencatatan riwayat perubahan data dan alur persetujuan yang transparan dan dapat diaudit secara permanen.

## 2. Pengguna & Pembagian Peran [BR-002, BR-006, PR-004, PR-024]
Sistem memiliki 6 peran manusia dan 2 entitas otomatis:
- **PIC Klien**: Mengunggah invoice PDF, melengkapi metadata, memperbaiki dokumen berstatus `EXCEPTION`, dan mengunduh voucher PDF resmi (`SENT_TO_CLIENT`).
- **Intake Support / Backup**: Membantu unggah dan tindak lanjut atas delegasi resmi untuk klien yang ditugaskan.
- **Finance Reviewer AMIGA**: Memeriksa dokumen pada layar *split-screen*, mengoreksi data ekstraksi, menyetujui (`AMIGA_REVIEWED`), atau mengembalikan dokumen ke PIC (`EXCEPTION`).
- **Service Lead**: Memantau antrean dan menyeimbangkan alokasi beban kerja antar-reviewer. DILARANG mengotorisasi pembayaran.
- **System Admin**: Mengelola akun, peran, dan penugasan delegasi klien. DILARANG menyetujui transaksi dokumen.
- **Client Approver (Eksternal)**: Menyetujui dan mengeksekusi transfer dana di luar sistem AMIGA.
- **AI Engine (Otomatis)**: Mengekstrak isi teks PDF ke draf voucher (`PROCESSING`). DILARANG memverifikasi logika dan dilarang menyetujui voucher.
- **Sistem AMIGA (Otomatis)**: Menerbitkan Request ID, memverifikasi aturan bisnis, menandai `EXCEPTION`, mengecek Segregation of Duties (SoD), dan mengompilasi berkas voucher PDF resmi.

## 3. Batasan Cakupan Rilis PoC (In-Scope vs Non-Goals) [BR-005, BR-012, PR-001..025]

### In-Scope (Wajib Diimplementasikan P0/P1)
- Formulir unggah PDF (maks. 5 halaman, maks. 10MB) beserta metadata awal (klien, tipe, saluran, tanggal) -> Request ID unik -> `QUEUED`.
- Ekstraksi AI asinkron (header vendor, line items, nominal, data rekening transfer) -> `PROCESSING` (SLA <= 15s).
- Verifikasi sistem otomatis: kelengkapan rekening (`MISSING_EVIDENCE`), duplikasi (`POSSIBLE_DUPLICATE`), hitungan angka (`CALCULATION_DISCREPANCY`).
- Hasil verifikasi sistem: `READY_FOR_REVIEW` jika bersih; `EXCEPTION` jika ada kejanggalan.
- Layar peninjauan split-screen bagi Finance Reviewer (PDF asli berdampingan dengan form data yang dapat diedit, SLA muat <= 2s).
- Penegakan Segregation of Duties (SoD): sistem menolak persetujuan jika Reviewer == Uploader, lalu otomatis mengalihkan penugasan ke reviewer lain dengan antrean paling sedikit (*least-loaded active reviewer*).
- Kompilasi voucher PDF resmi dengan teks batas otorisasi legal permanen (SLA <= 3s) -> `AMIGA_REVIEWED`.
- Unduh voucher oleh PIC Klien -> status `SENT_TO_CLIENT`.
- Jejak audit permanen (*immutable ledger*) yang mencatat setiap mutasi status dan nilai awal vs nilai baru.
- Dashboard antrean kerja multi-klien dan rebalance beban oleh Service Lead.

### Non-Goals (Out-of-Scope — DILARANG DIBUAT)
- Sistem persetujuan transfer internal klien atau eksekusi pembayaran internet banking / payment gateway.
- Portal akun khusus untuk Client Approver eksternal.
- Integrasi otomatis penarikan invoice dari Email/WhatsApp API (saluran hanya dicatat sebagai metadata teks).
- Pemrosesan format berkas non-PDF (misal Word, Excel, JPG gambar foto mentah) atau PDF melebihi 5 halaman.
- Validasi faktur pajak ke sistem Direktorat Jenderal Pajak (DJP).

## 4. Siklus Hidup Dokumen (6 Status Pasti) [PR-006, PR-012, PR-019, PR-022, PF-004..016]
Dokumen invoice HANYA boleh memiliki satu dari 6 status resmi berikut:
1. `QUEUED`: Berkas berhasil diunggah dan masuk antrean ekstraksi.
2. `PROCESSING`: AI Engine sedang membaca dokumen.
3. `READY_FOR_REVIEW`: Lolos seluruh verifikasi sistem; siap diperiksa Reviewer.
4. `EXCEPTION`: Ditemukan kendala otomatis sistem atau dikembalikan oleh Reviewer. Perbaikan oleh PIC Klien MUST mempertahankan Request ID yang sama.
5. `AMIGA_REVIEWED`: Disetujui oleh Reviewer dan voucher PDF resmi telah terbit.
6. `SENT_TO_CLIENT`: Berkas voucher PDF resmi telah diunduh oleh PIC Klien.

## 5. Tiga Aturan Verifikasi Sistem [BR-008, PR-011, SR-013]
1. **Kelengkapan Rekening (`MISSING_EVIDENCE`)**: Jika nomor rekening atau bank tujuan transfer tidak ditemukan.
2. **Duplikasi Tagihan (`POSSIBLE_DUPLICATE`)**: Jika nomor invoice dan nama vendor identik dengan dokumen sebelumnya pada klien yang sama (setelah normalisasi lowercase & pembersihan spasi/tanda baca).
3. **Discrepansi Perhitungan (`CALCULATION_DISCREPANCY`)**: Jika total invoice tidak sama dengan penjumlahan subtotal rincian line item ditambah pajak.

## 6. Glosarium Domain & Referensi Lanjutan
Definisi istilah teknis dan domain formal didefinisikan secara lengkap pada dokumen referensi utama:  
Lihat [Glosarium Domain Analisis](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/apps-2/docs/specs/00-analysis.md#4-glosarium-domain-domain-glossary).
