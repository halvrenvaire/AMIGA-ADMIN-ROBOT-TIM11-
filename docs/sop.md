# SOP — Pemrosesan Invoice Vendor menjadi Voucher Pembayaran

**Sistem:** AMIGA Robot Admin (Intelligent Vendor Invoice-to-Voucher Processing)
**Nomor SOP:** SOP-AMIGA-FIN-001
**Versi:** 1.2 (Draft PoC — MAIN Hackathon 2026, selaras dengan BRD v1.1 dan PRD v2)
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

- Pengunggahan invoice PDF, ekstraksi data oleh AI, verifikasi otomatis oleh sistem, perbaikan data oleh PIC Klien, peninjauan, pembuatan voucher PDF, dan serah terima voucher ke klien.

**Tidak termasuk** (dilakukan di luar sistem):

- Persetujuan dan pelaksanaan pembayaran oleh Client Approver.
- Integrasi ke ERP, akuntansi, atau internet banking.
- Validasi Faktur Pajak ke sistem DJP.

## 3. Referensi

- BRD AMIGA Robot Admin v1.1 (Kelompok 11)
- PRD AMIGA Robot Admin v2 (versi PRD 1.1)
- BPMN `AMIGA_Robot_Admin_Invoice_to_Voucher.bpmn` (revisi 13/10/2026)
- UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)

## 4. Definisi

| Istilah | Arti |
| --- | --- |
| Request ID | Nomor unik yang diterbitkan sistem untuk setiap pengajuan invoice |
| QUEUED | Invoice sudah diunggah dan menunggu dibaca AI |
| PROCESSING | AI sedang membaca invoice |
| READY_FOR_REVIEW | Invoice lolos verifikasi sistem dan siap ditinjau Finance Reviewer |
| EXCEPTION | Sistem menemukan kendala, atau reviewer mengembalikan dokumen; PIC Klien perlu memperbaikinya |
| AMIGA_REVIEWED | Disetujui Finance Reviewer; voucher sudah dibuat |
| SENT_TO_CLIENT | Voucher sudah diunduh PIC Klien |
| MISSING_EVIDENCE | Kendala: data wajib tidak ada, misalnya nomor rekening |
| CALCULATION_DISCREPANCY | Kendala: jumlah rincian barang tidak sama dengan total invoice |
| POSSIBLE_DUPLICATE | Kendala: ada invoice lain dengan nomor dan vendor yang sama |
| RETURNED_BY_REVIEWER | Kendala: Finance Reviewer mengembalikan dokumen ke PIC Klien disertai alasan |
| NOT_AN_INVOICE | Kendala: dokumen tidak relevan (bukan dokumen tagihan, mis. CV, surat, purchase order) dan ditolak |
| RECEIPT_NOT_INVOICE | Kendala: dokumen adalah struk/bon/nota pembelian. Datanya disusun sebagai draft, tetapi bukan invoice resmi vendor |
| NEEDS_MANUAL_REVIEW | Kendala: jenis dokumen meragukan atau datanya terlalu sedikit; Finance Reviewer memeriksa secara manual |
| ACCOUNT_MISMATCH | Kendala: nomor rekening berbeda dengan rekening vendor yang sudah diverifikasi Finance Reviewer |
| Vendor terverifikasi | Vendor di Data Referensi yang rekeningnya sudah dicek Finance Reviewer ke sumber tepercaya. Menjadi acuan pemeriksaan rekening |
| Saluran | Asal pengajuan invoice, misalnya Email atau WhatsApp. Hanya dicatat sebagai keterangan. Bernilai **Telegram** bila invoice diunggah lewat bot resmi |
| Bot Telegram resmi | Bot @amiga_ro_bot yang terhubung ke akun AMIGA lewat kode sekali pakai dari Pengaturan akun. Pintu masuk resmi kedua selain dashboard |
| Segregation of Duties (SoD) | Aturan bahwa pengunggah dokumen tidak boleh menyetujui dokumen yang sama |

## 5. Peran dan Tanggung Jawab

| Peran | Tanggung jawab | Tidak boleh |
| --- | --- | --- |
| PIC Klien | Mengunggah invoice, melengkapi data bila ada kendala, mengunduh voucher | Meninjau atau menyetujui dokumen yang ia unggah |
| Intake Support / Backup | Mengunggah dan menindaklanjuti dokumen atas delegasi resmi PIC Klien | Mengakses klien yang tidak ditugaskan |
| AI Engine | Membaca invoice dan mengisi draf data | Memverifikasi atau menyetujui dokumen |
| Sistem AMIGA Robot Admin | Menerbitkan Request ID, memverifikasi angka, kelengkapan, dan duplikasi, menandai EXCEPTION, mengecek Segregation of Duties (termasuk mengalihkan otomatis ke reviewer lain), dan membuat voucher | Menyetujui voucher |
| Finance Reviewer | Memeriksa, mengoreksi, menyetujui, atau mengembalikan dokumen ke PIC Klien | Menyetujui dokumen yang ia unggah sendiri |
| Service Lead | Memantau antrean, tenggat, dan beban reviewer; mengalihkan dokumen bila beban seorang reviewer terlalu banyak | Mengotorisasi pembayaran klien |
| System Admin | Mengelola akun, peran, dan penugasan klien | Menyetujui transaksi atau mengubah jejak audit |
| Client Approver (eksternal) | Menyetujui dan membayar berdasarkan voucher | — (di luar sistem) |

## 6. Ketentuan Umum

1. Invoice wajib berformat **PDF digital, maksimal 5 halaman**.
2. Setiap invoice **wajib ditinjau** Finance Reviewer sebelum voucher terbit. Hasil AI tidak boleh dipakai tanpa peninjauan.
3. Pengiriman invoice lewat WhatsApp atau Email **tidak diproses**. PIC diarahkan untuk mengunggah ke sistem, dan asal pengajuan dicatat di kolom **Saluran**.
4. Invoice boleh diunggah lewat **dashboard** atau lewat **bot Telegram resmi** (@amiga_ro_bot) dari **chat pribadi** akun yang sudah terhubung. Keduanya masuk ke sistem yang sama dengan aturan yang sama. Mengirim invoice ke nomor/akun lain, atau ke grup chat, tetap tidak diproses.
5. Pengguna hanya mengakses data klien yang ditugaskan kepadanya.
6. Jejak audit tidak boleh diubah atau dihapus oleh siapa pun, termasuk System Admin.
7. Selama PoC, gunakan **data dummy atau data yang sudah dianonimkan**.

## 7. Prosedur

### 7.1 Pengunggahan invoice — PIC Klien / Intake Support

1. Masuk ke AMIGA Robot Admin dan buka menu **Unggah invoice**.
2. Isi semua kolom wajib: **nama klien**, **jenis permintaan**, **saluran** (asal invoice, misalnya Email atau WhatsApp), dan **tanggal pengajuan**.
3. Pilih file invoice PDF, lalu klik **Kirim ke antrean**.
4. Pastikan sistem menampilkan **Request ID** dan status **QUEUED**. Catat Request ID untuk pelacakan.
5. Jika file ditolak (bukan PDF atau lebih dari 5 halaman), sistem mengembalikan Anda ke formulir unggah. Perbaiki file lalu ulangi dari langkah 3.
6. Intake Support yang mengunggah atas nama klien hanya boleh melakukannya untuk klien yang didelegasikan. Sistem mencatat nama pengunggah sebenarnya.

**Lewat bot Telegram (alternatif):**

1. Hubungkan akun sekali saja: dashboard → **Pengaturan akun** → **Hubungkan Telegram**, lalu kirim kode ke @amiga_ro_bot. **Jangan pernah mengirim password di chat.**
2. Kirim file invoice **PDF** (bukan foto) ke chat pribadi bot. Beberapa PDF untuk satu voucher boleh dikirim sekaligus.
3. Pilih **perusahaan** dan **jenis permintaan** lewat tombol. Saluran terisi **Telegram** dan tanggal pengajuan terisi hari ini secara otomatis.
4. Periksa ringkasan, lalu tekan **Kirim ke AMIGA**. Bot menampilkan **Request ID** dan status **QUEUED**, lalu mengabari hasil proses AI.
5. Bila ada kendala, perbaiki datanya lewat dashboard (lihat 7.3).

### 7.2 Ekstraksi dan verifikasi otomatis — AI Engine dan Sistem

Langkah ini berjalan otomatis. Tidak ada tindakan pengguna.

1. Status berubah menjadi **PROCESSING** saat AI mulai membaca invoice.
2. AI **mengklasifikasikan** setiap file lebih dulu:
   - **Invoice vendor** → lanjut ke ekstraksi dan verifikasi seperti biasa.
   - **Struk, bon, atau nota pembelian** yang memuat data transaksi (barang, harga, kuantitas, total) → datanya diekstrak sebagai **Preview Draft** dengan kode **RECEIPT_NOT_INVOICE**. Struk/nota **tidak otomatis menjadi invoice resmi** dan voucher tidak terbit.
   - **Dokumen tidak relevan** → langsung ditolak dengan kode **NOT_AN_INVOICE** beserta alasannya.
   - **Dokumen meragukan atau tidak lengkap** → ditandai **NEEDS_MANUAL_REVIEW** untuk diperiksa Finance Reviewer.
3. AI **hanya mengekstrak** data yang tertulis: vendor, nomor dan tanggal invoice, rincian barang, total, bank, nomor rekening, dan nama penerima. Data yang tidak ada dibiarkan kosong, **tidak ditebak**. Target waktunya **≤ 15 detik** per dokumen. AI tidak memverifikasi dan tidak menyetujui.
4. **Sistem** (bukan AI) menjalankan verifikasi:
   - data wajib ada, termasuk nomor rekening → bila tidak, **MISSING_EVIDENCE**;
   - jumlah rincian sama dengan total → bila tidak, **CALCULATION_DISCREPANCY**;
   - tidak ada invoice lain dengan nomor dan vendor yang sama → bila ada, **POSSIBLE_DUPLICATE**;
   - nomor rekening dicocokkan dengan rekening **vendor terverifikasi** di Data Referensi → bila berbeda, **ACCOUNT_MISMATCH**. Rekening dari invoice maupun isian PIC tidak dianggap benar dengan sendirinya.
5. Jika semua lolos, status menjadi **READY_FOR_REVIEW**. Jika ada kendala, status menjadi **EXCEPTION** dan sistem menampilkan kode kendala beserta alasannya.
6. Jika AI gagal membaca, dokumen tetap tersimpan. Finance Reviewer dapat memproses ulang atau mengisi data secara manual.

### 7.3 Penanganan kendala (EXCEPTION) — PIC Klien / Intake Support

1. Buka dokumen dari **Pengajuan saya** atau **Dashboard antrean**.
2. Baca kode dan alasan kendala di bagian atas layar.
3. Lengkapi atau perbaiki data sesuai kodenya:

   | Kode | Tindakan PIC Klien |
   | --- | --- |
   | MISSING_EVIDENCE | Isi data yang kosong, misalnya nomor rekening vendor, lalu klik **Kirim perbaikan** |
   | CALCULATION_DISCREPANCY | Konfirmasi ke vendor apakah total atau rinciannya yang benar. Bila perlu, minta invoice revisi lalu unggah ulang |
   | POSSIBLE_DUPLICATE | Periksa apakah tagihan ini memang sudah pernah diajukan. Jika ya, beri tahu Finance Reviewer agar dokumen tidak diproses |
   | RETURNED_BY_REVIEWER | Ikuti alasan yang ditulis Finance Reviewer, lalu klik **Kirim perbaikan** |
   | NOT_AN_INVOICE | Batalkan pengajuan, lalu unggah ulang hanya dengan file invoice/tagihan dari vendor |
   | RECEIPT_NOT_INVOICE | Minta invoice resmi ke vendor lalu ajukan ulang. Bila vendor memang hanya memberi struk/nota, lengkapi data wajib dan tunggu keputusan Finance Reviewer |
   | ACCOUNT_MISMATCH | Jangan ubah rekening sendiri. Konfirmasi ke vendor lewat kontak resmi; bila rekening vendor memang berganti, perbarui Data Referensi agar diverifikasi ulang Finance Reviewer |

4. Setelah perbaikan dikirim, dokumen **kembali ke tahap ekstraksi** (PROCESSING) dengan **Request ID yang sama**, lalu diverifikasi ulang oleh sistem. Sistem tidak menerbitkan Request ID baru.
5. Data yang Anda isi atau perbaiki **tidak ditimpa** oleh hasil ekstraksi ulang AI.

### 7.4 Peninjauan dan persetujuan — Finance Reviewer

1. Buka **Dashboard antrean**, lalu saring status **READY_FOR_REVIEW**. Dahulukan dokumen dengan tenggat terdekat.
2. Klik **Buka** untuk masuk ke layar **Peninjauan & verifikasi**.
3. Bandingkan PDF asli (kiri) dengan data hasil AI (kanan), terutama:
   - nama vendor dan nomor invoice;
   - setiap baris barang: uraian, qty, dan harga;
   - total invoice;
   - bank, nomor rekening, dan nama penerima. **Nomor rekening dicek digit per digit.**
4. Jika ada yang salah, koreksi kolomnya lalu klik **Simpan & verifikasi ulang**. Setiap perubahan tercatat otomatis (nilai awal → nilai baru, nama, waktu).
5. Ambil keputusan:
   - **Setujui** — hanya bila status **READY_FOR_REVIEW** dan semua data sudah sesuai dengan PDF.
   - **Kembalikan ke PIC** — **wajib** menulis alasan yang jelas, misalnya "Lampirkan invoice revisi dengan total yang benar." Status menjadi **EXCEPTION** dengan kode **RETURNED_BY_REVIEWER**.
6. Periksa status rekening di layar peninjauan. Bila **Rekening belum terverifikasi**, cocokkan rekening dengan sumber tepercaya (mis. konfirmasi langsung ke vendor lewat kontak resmi), lalu centang konfirmasi pengecekan rekening sebelum **Setujui**. Konfirmasi ini tercatat di jejak audit. Rekening yang **tidak cocok** dengan vendor terverifikasi tidak bisa disetujui.
7. Untuk dokumen **NEEDS_MANUAL_REVIEW** atau **RECEIPT_NOT_INVOICE**, Finance Reviewer yang bukan pihak pengaju memutuskan dengan alasan tertulis:
   - **Proses sebagai invoice** — hanya untuk dokumen meragukan yang ternyata invoice resmi;
   - **Terima struk sebagai dasar pembayaran** — hanya bila semua data wajib lengkap dan rekening cocok dengan vendor terverifikasi. Dokumen lalu masuk antrean dan **tetap harus disetujui** Finance Reviewer;
   - **Tolak: tidak relevan**.
8. Verifikasi rekening vendor dilakukan Finance Reviewer di **Data Referensi → Vendor**, setelah dicek ke sumber tepercaya. Pendaftar atau pengubah terakhir data bank vendor tidak boleh memverifikasinya sendiri. Mengubah data bank vendor membatalkan verifikasi.
9. Saat Anda klik **Setujui**, sistem mengecek **Segregation of Duties**. Jika Anda adalah pengunggah dokumen, sistem **menolak persetujuan dan otomatis mengalihkan** dokumen ke reviewer lain dengan antrean tertunda paling sedikit. Anda tidak perlu menghubungi Service Lead. Penolakan dan pengalihan tercatat di jejak audit.
10. Jika lolos cek SoD, status menjadi **AMIGA_REVIEWED** dan voucher PDF terbentuk otomatis (target **≤ 3 detik**).

### 7.5 Pengaturan beban reviewer — Service Lead

1. Pantau **Dashboard antrean** setiap hari: jumlah dokumen per status, **beban per reviewer**, dan dokumen yang tenggatnya ≤ 2 hari lagi.
2. Alihkan dokumen ke reviewer lain **hanya bila beban seorang reviewer terlalu banyak**, termasuk saat reviewer berhalangan.
3. Pilih reviewer baru di kolom **Reviewer**. Status dokumen tidak berubah, dan sistem mencatat pengalihan di jejak audit.
4. Pengalihan karena **Segregation of Duties** tidak dilakukan Service Lead, karena sudah dialihkan otomatis oleh sistem (lihat 7.4 langkah 6).

### 7.6 Serah terima voucher — PIC Klien

1. Buka menu **Pratinjau voucher** dan pilih voucher yang sesuai.
2. Periksa nomor voucher, vendor, rekening tujuan, dan total. Pastikan teks **Batas Otorisasi** tercantum.
3. Klik **Unduh voucher PDF**. Status berubah menjadi **SENT_TO_CLIENT**.
4. Teruskan voucher ke **Client Approver** sesuai prosedur internal klien.
5. Voucher **bukan** persetujuan pembayaran. Keputusan bayar ada di Client Approver.

### 7.7 Pengelolaan akses — System Admin

1. Buat akun hanya berdasarkan permintaan tertulis dari atasan pengguna.
2. Berikan peran sesuai tugas, dan tugaskan hanya klien yang relevan. Satu pengguna boleh memiliki lebih dari satu peran internal (misalnya Intake Support sekaligus Finance Reviewer), kecuali kombinasi **PIC Klien dengan peran internal** dan **System Admin dengan Finance Reviewer**. System Admin tidak boleh memberi peran kepada dirinya sendiri.
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
2. **Segregation of Duties:** sistem menolak persetujuan oleh pengunggah dokumen (termasuk dokumen yang diunggah atas namanya), lalu otomatis mengalihkan dokumen ke reviewer lain.
3. **Isolasi klien:** pengguna klien A tidak dapat membuka dokumen klien B. Setiap upaya akses ditolak dan dicatat.
4. **Jejak audit** mencatat:
   - setiap aktivitas: unggah, ekstraksi, verifikasi, perbaikan oleh PIC, koreksi, persetujuan, pengembalian ke PIC (beserta alasan), penolakan SoD, pengalihan reviewer (otomatis atau oleh Service Lead), dan unduh;
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
| 1.1 | 13 Oktober 2026 | Diselaraskan dengan BRD v1.1, PRD v2, dan BPMN revisi: field saluran, peran AI vs Sistem, perbaikan oleh PIC dengan ekstraksi ulang (Request ID sama), Kembalikan ke PIC, pengalihan otomatis saat penolakan SoD, Service Lead hanya mengatur beban, peran ganda | TEAM 11 MAIN |
| 1.2 | 16 Oktober 2026 | Unggah invoice lewat bot Telegram resmi @amiga_ro_bot (6.4, 7.1); saluran Telegram | TEAM 11 MAIN |