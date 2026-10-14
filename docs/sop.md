# SOP — Pemrosesan Invoice Vendor menjadi Voucher Pembayaran

**Sistem:** AMIGA Robot Admin (Intelligent Vendor Invoice-to-Voucher Processing)
**Nomor SOP:** SOP-AMIGA-FIN-001
**Versi:** 1.0 (Draft PoC — MAIN Hackathon 2026)
**Tanggal berlaku:** [diisi saat disahkan]
**Pemilik proses:** Tim AMIGA Intelligent Back Office
**Disusun oleh:** TEAM 11 MAIN
**Disetujui oleh:** [Nama & jabatan pengesah]

---

## 1. Tujuan

SOP ini mengatur cara mengubah invoice vendor (PDF) menjadi voucher pembayaran resmi di AMIGA Robot Admin. Tujuannya:

1. Data invoice tidak diketik ulang secara manual.
2. Kesalahan nominal, nomor rekening, hitungan total, dan tagihan ganda tertangkap sebelum voucher terbit.
3. Setiap dokumen ditinjau oleh Tim Keuangan AMIGA, dan setiap tindakan tercatat untuk audit.

## 2. Ruang Lingkup

**Termasuk:**

- Pengunggahan invoice PDF, ekstraksi data oleh AI, validasi otomatis, peninjauan, pembuatan voucher PDF, dan serah terima voucher ke klien.

**Tidak termasuk** (dilakukan di luar sistem):

- Persetujuan dan pelaksanaan pembayaran oleh Client Approver.
- Integrasi ke ERP, akuntansi, atau internet banking.
- Validasi Faktur Pajak ke sistem DJP.

## 3. Referensi

- BRD AMIGA Robot Admin v1.0 (Kelompok 11)
- PRD AMIGA Robot Admin
- BPMN `AMIGA_Robot_Admin_Invoice_to_Voucher.bpmn`
- UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)

## 4. Definisi

| Istilah | Arti |
| --- | --- |
| Request ID | Nomor unik yang diterbitkan sistem untuk setiap pengajuan invoice |
| QUEUED | Invoice sudah diunggah dan menunggu dibaca AI |
| PROCESSING | AI sedang membaca invoice |
| READY_FOR_REVIEW | Invoice lolos pengecekan otomatis dan siap ditinjau |
| EXCEPTION | Ditemukan kendala yang harus diselesaikan dulu |
| AMIGA_REVIEWED | Disetujui Finance Reviewer; voucher sudah dibuat |
| SENT_TO_CLIENT | Voucher sudah diunduh PIC Klien |
| MISSING_EVIDENCE | Kendala: data wajib tidak ada, misalnya nomor rekening |
| CALCULATION_DISCREPANCY | Kendala: jumlah rincian barang tidak sama dengan total invoice |
| POSSIBLE_DUPLICATE | Kendala: ada invoice lain dengan nomor dan vendor yang sama |
| Segregation of Duties (SoD) | Aturan bahwa pengunggah dokumen tidak boleh menyetujui dokumen yang sama |

## 5. Peran dan Tanggung Jawab

| Peran | Tanggung jawab | Tidak boleh |
| --- | --- | --- |
| PIC Klien | Mengunggah invoice, melengkapi data bila ada kendala, mengunduh voucher | Meninjau atau menyetujui dokumen yang ia unggah |
| Intake Support / Backup | Mengunggah dan menindaklanjuti dokumen atas delegasi resmi PIC Klien | Mengakses klien yang tidak ditugaskan |
| Robot Admin (AI) | Membaca invoice dan mengisi draf data | Menyetujui voucher |
| Finance Reviewer | Memeriksa, mengoreksi, menyetujui, atau mengembalikan dokumen | Menyetujui dokumen yang ia unggah sendiri |
| Service Lead | Memantau antrean dan tenggat, mengalihkan dokumen ke reviewer lain | Mengotorisasi pembayaran klien |
| System Admin | Mengelola akun, peran, dan penugasan klien | Menyetujui transaksi atau mengubah jejak audit |
| Client Approver (eksternal) | Menyetujui dan membayar berdasarkan voucher | — (di luar sistem) |

## 6. Ketentuan Umum

1. Invoice wajib berformat **PDF digital, maksimal 5 halaman**.
2. Setiap invoice **wajib ditinjau** Finance Reviewer sebelum voucher terbit. Hasil AI tidak boleh dipakai tanpa peninjauan.
3. Pengiriman invoice lewat WhatsApp atau Email **tidak diproses**. PIC diarahkan untuk mengunggah ke sistem.
4. Pengguna hanya mengakses data klien yang ditugaskan kepadanya.
5. Jejak audit tidak boleh diubah atau dihapus oleh siapa pun, termasuk System Admin.
6. Selama PoC, gunakan **data dummy atau data yang sudah dianonimkan**.

## 7. Prosedur

### 7.1 Pengunggahan invoice — PIC Klien / Intake Support

1. Masuk ke AMIGA Robot Admin dan buka menu **Unggah invoice**.
2. Pilih **nama klien** (wajib), **jenis permintaan**, dan **tanggal pengajuan**.
3. Pilih file invoice PDF, lalu klik **Kirim ke antrean**.
4. Pastikan sistem menampilkan **Request ID** dan status **QUEUED**. Catat Request ID untuk pelacakan.
5. Jika file ditolak (bukan PDF atau lebih dari 5 halaman), perbaiki file lalu ulangi dari langkah 3.
6. Intake Support yang mengunggah atas nama klien hanya boleh melakukannya untuk klien yang didelegasikan. Sistem mencatat nama pengunggah sebenarnya.

### 7.2 Ekstraksi dan validasi otomatis — Sistem dan AI

Langkah ini berjalan otomatis. Tidak ada tindakan pengguna.

1. Status berubah menjadi **PROCESSING** saat AI mulai membaca invoice.
2. AI mengisi data: vendor, nomor dan tanggal invoice, rincian barang, total, bank, nomor rekening, dan nama penerima. Target waktunya **≤ 15 detik** per dokumen.
3. Sistem menjalankan tiga pengecekan:
   - nomor rekening ada → bila tidak, **MISSING_EVIDENCE**;
   - jumlah rincian sama dengan total → bila tidak, **CALCULATION_DISCREPANCY**;
   - tidak ada invoice lain dengan nomor dan vendor yang sama → bila ada, **POSSIBLE_DUPLICATE**.
4. Jika semua lolos, status menjadi **READY_FOR_REVIEW**. Jika ada kendala, status menjadi **EXCEPTION**.
5. Jika AI gagal membaca, dokumen tetap tersimpan. Finance Reviewer dapat memproses ulang atau mengisi data secara manual.

### 7.3 Penanganan kendala (EXCEPTION) — PIC Klien

1. Buka dokumen dari **Pengajuan saya** atau **Dashboard antrean**.
2. Baca kode dan penjelasan kendala di bagian atas layar.
3. Tindak lanjuti sesuai kodenya:

   | Kode | Tindakan PIC Klien |
   | --- | --- |
   | MISSING_EVIDENCE | Isi nomor rekening vendor, lalu klik **Kirim perbaikan** |
   | CALCULATION_DISCREPANCY | Konfirmasi ke vendor apakah total atau rinciannya yang benar. Bila perlu, minta invoice revisi lalu unggah ulang |
   | POSSIBLE_DUPLICATE | Periksa apakah tagihan ini memang sudah pernah diajukan. Jika ya, beri tahu Finance Reviewer agar dokumen tidak diproses |

4. Setelah perbaikan, sistem otomatis memvalidasi ulang dokumen.

### 7.4 Peninjauan dan persetujuan — Finance Reviewer

1. Buka **Dashboard antrean**, lalu saring status **READY_FOR_REVIEW** atau **EXCEPTION**. Dahulukan dokumen dengan tenggat terdekat.
2. Klik **Buka** untuk masuk ke layar **Peninjauan & verifikasi**.
3. Bandingkan PDF asli (kiri) dengan data hasil AI (kanan), terutama:
   - nama vendor dan nomor invoice;
   - setiap baris barang: uraian, qty, dan harga;
   - total invoice;
   - bank, nomor rekening, dan nama penerima. **Nomor rekening dicek digit per digit.**
4. Jika ada yang salah, koreksi kolomnya lalu klik **Simpan & validasi ulang**. Setiap perubahan tercatat otomatis (nilai awal → nilai baru, nama, waktu).
5. Ambil keputusan:
   - **Setujui** — hanya bila status **READY_FOR_REVIEW** dan semua data sudah sesuai dengan PDF.
   - **Kembalikan ke PIC** — tulis alasan yang jelas, misalnya "Lampirkan invoice revisi dengan total yang benar."
6. Jika sistem menolak persetujuan karena **Segregation of Duties** (Anda adalah pengunggah dokumen), jangan mencari jalan lain. Minta Service Lead mengalihkan dokumen ke reviewer lain.
7. Setelah disetujui, status menjadi **AMIGA_REVIEWED** dan voucher PDF terbentuk otomatis (target **≤ 3 detik**).

### 7.5 Pengalihan dokumen — Service Lead

1. Pantau **Dashboard antrean** setiap hari, terutama dokumen yang tenggatnya ≤ 2 hari lagi dan dokumen berstatus EXCEPTION.
2. Alihkan dokumen ke reviewer lain jika:
   - persetujuan ditolak karena Segregation of Duties;
   - reviewer berhalangan;
   - beban kerja reviewer tidak seimbang.
3. Pilih reviewer baru di kolom **Reviewer**. Sistem mencatat pengalihan di jejak audit.

### 7.6 Serah terima voucher — PIC Klien

1. Buka menu **Pratinjau voucher** dan pilih voucher yang sesuai.
2. Periksa nomor voucher, vendor, rekening tujuan, dan total. Pastikan teks **Batas Otorisasi** tercantum.
3. Klik **Unduh voucher PDF**. Status berubah menjadi **SENT_TO_CLIENT**.
4. Teruskan voucher ke **Client Approver** sesuai prosedur internal klien.
5. Voucher **bukan** persetujuan pembayaran. Keputusan bayar ada di Client Approver.

### 7.7 Pengelolaan akses — System Admin

1. Buat akun hanya berdasarkan permintaan tertulis dari atasan pengguna.
2. Berikan satu peran sesuai tugas, dan tugaskan hanya klien yang relevan.
3. Catat setiap delegasi Intake Support beserta klien dan masa berlakunya.
4. Nonaktifkan akun pada hari yang sama saat pengguna pindah tugas atau keluar.
5. Tinjau daftar akun dan peran setiap bulan.

## 8. Target Waktu Layanan

| Tahap | Target |
| --- | --- |
| Ekstraksi AI per invoice (≤ 5 halaman) | ≤ 15 detik |
| Pemuatan antrean dan layar review | ≤ 2 detik |
| Pembuatan voucher setelah disetujui | ≤ 3 detik |
| Peninjauan oleh Finance Reviewer | [diisi sesuai SLA klien, misalnya 1 hari kerja] |
| Tindak lanjut EXCEPTION oleh PIC Klien | [diisi sesuai SLA klien, misalnya 2 hari kerja] |

## 9. Kontrol dan Audit

1. **Peninjauan wajib:** voucher tidak bisa terbit tanpa persetujuan Finance Reviewer.
2. **Segregation of Duties:** sistem menolak persetujuan oleh pengunggah dokumen.
3. **Isolasi klien:** pengguna klien A tidak dapat membuka dokumen klien B. Setiap upaya akses ditolak dan dicatat.
4. **Jejak audit** mencatat:
   - setiap aktivitas: unggah, ekstraksi, validasi, koreksi, persetujuan, penolakan, pengalihan, dan unduh;
   - setiap perubahan data: nilai awal, nilai baru, nama pengguna, dan waktu.
5. **Pemeriksaan berkala:** Service Lead meninjau sampel jejak audit setiap minggu, terutama koreksi nominal dan nomor rekening.

## 10. Penanganan Masalah

| Masalah | Tindakan | Penanggung jawab |
| --- | --- | --- |
| Dokumen lebih dari 5 menit di status PROCESSING | Laporkan Request ID ke tim teknis. Reviewer dapat mengisi data secara manual | Finance Reviewer |
| Hasil AI banyak salah pada satu vendor | Catat nama vendor dan contoh invoice, lalu laporkan ke tim teknis untuk perbaikan | Finance Reviewer |
| Akses ke klien yang seharusnya bisa dibuka ditolak | Ajukan perbaikan penugasan klien ke System Admin | Pengguna |
| Dugaan penyalahgunaan akses | Laporkan ke Service Lead dan System Admin. Jangan menghapus data apa pun | Semua pengguna |

## 11. Riwayat Revisi

| Versi | Tanggal | Perubahan | Oleh |
| --- | --- | --- | --- |
| 1.0 | 13 Oktober 2026 | Draf awal untuk PoC MAIN Hackathon 2026 | TEAM 11 MAIN |