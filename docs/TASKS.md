# Tracking Tugas — Feedback Owner AMIGA

Sumber: **Ringkasan Pemahaman Feedback Owner AMIGA** (18 Okt 2026, 12 masukan owner), ditambah feedback owner setelahnya.
Dokumen acuan lain: [BRD v3.0](../readme/BRD_AMIGA_Robot_Admin_v3.0.pdf) · [PRD v3](../readme/PRD_AMIGA_Robot_Admin_v3.pdf) · [BPMN v2](../readme/AMIGA_Robot_Admin_Invoice_to_Voucher_v2.png)

**Cara pakai**

- `[x]` selesai · `[ ]` belum · 🔄 sedang dikerjakan · ❓ menunggu jawaban owner/tim
- Setiap tugas punya ID (mis. `T3.2`). Sebut ID-nya saat minta update, misalnya "T6.1 sudah selesai".
- Saat tugas selesai: centang, isi kolom commit, perbarui ringkasan progres, lalu commit dan push.
- Nomor `#1`–`#12` merujuk ke nomor masukan owner di dokumen ringkasan.

_Terakhir diperbarui: 27 Okt 2026_

---

## Ringkasan progres

| Tahap | Isi | Ukuran | Selesai | Status |
| --- | --- | --- | --- | --- |
| 1 | Istilah, judul PDF, kategori, rekening tidak dicetak, nama pengaju bebas, Telegram pilih perusahaan | Kecil | 7/8 | 🔄 sisa T1.4 |
| 2 | Lampiran bukti di PDF, batas 20 bukti reimburse | Sedang | 6/6 | ✅ |
| 3 | Alur draf: PIC edit per invoice, simulasi voucher, reviewer hanya menyetujui | Besar | 7/7 | ✅ |
| 4 | Pajak: tabel tarif, NPWP, saran AI, potongan di voucher | Besar | 8/8 | ✅ |
| 5 | Konfirmasi tarif pajak | Kecil | 1/2 | ❓ PPh 26 |
| 6 | Feedback owner 19–20 Okt (kop voucher, PPN, tabel voucher) | Sedang | 4/4 | ✅ |
| 7 | Pertanyaan terbuka ke owner | — | 0/4 | ❓ |
| 8 | Dokumen & rilis (BRD, PRD, BPMN, buku panduan, deploy) | Sedang | 3/7 | ⏳ |
| 9 | Feedback owner 20 Okt (PPN per invoice, PPh per baris, navigasi cepat layar tinjau) | Besar | 8/8 | ✅ |
| 10 | Mengurangi ketergantungan AI: isi manual, subtotal otomatis, beberapa vendor per voucher, pintasan rekening vendor | Besar | 6/6 | ✅ |
| 11 | Format voucher mengikuti contoh owner (No. 1702 & 1944): kop data, kolom tabel, satu baris per invoice, kotak Diketahui oleh | Besar | 0/9 | ⏳ (4 perlu konfirmasi) |
| 12 | Berkas invoice banyak halaman (invoice + Faktur Pajak + timesheet) | Kecil | 2/2 | ✅ |
| 13 | Feedback uji coba 21–22 Okt: rekening opsional, alur simpan jelas, tampilan HP, full fit layar lebar & hide sidebar desktop | Sedang | 6/6 | ✅ |
| 14 | Mode AI total saja/rincian, rekening jadi fitur tambahan, pajak otomatis/manual, profil & tanda tangan pengaju, pratinjau voucher, estimasi biaya AI | Besar | 10/10 | ✅ |
| 15 | Toggle "Diajukan oleh" (profil PIC terkunci / isi manual), banyak invoice dalam satu PDF (pindai per 5 halaman, satu bukti per invoice, rentang halaman bisa diubah), tanda tangan di mode gelap, PPN "harga belum termasuk PPN" | Besar | 9/9 | ✅ |
| 16 | Pemisahan invoice gabungan on-demand (tombol AI) & saran PPh 23 imbalan jasa (merging branch `feat/pisah-invoice-gabungan` ke `main`) | Sedang | 8/8 | ✅ |
| 17 | Perbaikan Multi-Invoice DSS, Deteksi Total Gambar, & Otomatisasi Pajak | Sedang | 7/7 | ✅ |
| 18 | Sorting Tabel Riwayat & Akurasi Deteksi Pajak AI (Kontrak Jasa DSS & Eliminasi Kode Driver) | Sedang | 7/7 | ✅ |
| 19 | Feedback tim 24 Okt: saran PPN + PPh otomatis masuk voucher, langkah pajak di bot Telegram, tutorial di dalam aplikasi, dokumentasi | Besar | 5/5 | ✅ |

---

## Tahap 1 — Istilah & kategori (spesifikasi 2.A, 2.E, 2.F)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T1.1 | Menu "Unggah Dokumen" diganti "Pembuatan Voucher" | #1 | [x] | `2644eb8` |
| T1.2 | Judul PDF menjadi "Voucher Pengeluaran" | #10 | [x] | `2644eb8` |
| T1.3 | "Jenis permintaan" menjadi kategori (Vendor / Reimburse / Lainnya), divalidasi server, data lama dimigrasi | #10 | [x] | `2644eb8` |
| T1.4 | Daftar kategori **bisa ditambah admin** (sekarang masih tetap di kode: `REQUEST_CATEGORIES`) | #10 | [ ] | — |
| T1.5 | Kategori jadi filter di Dashboard Antrean, Voucher, dan Pengajuan Saya; tidak dicetak di PDF | #10 | [x] | `2644eb8` |
| T1.6 | Rekening tujuan tidak dicetak di voucher; cek rekening palsu tetap jalan di sistem (bagian rekening **diganti oleh T14.3**: rekening dicetak bila fitur rekening diaktifkan) | #6 | [x] | `2644eb8` |
| T1.7 | Nama "Diajukan oleh" diketik bebas (default nama PIC); spesimen PIC tidak dicetak bila nama lain | #8 | [x] | `2644eb8` |
| T1.8 | Telegram: pilihan perusahaan juga muncul saat kirim foto; kategori lewat tombol | #5 | [x] | `2644eb8` |

## Tahap 2 — Lampiran & reimburse (spesifikasi 2.B, 2.E)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T2.1 | Halaman 2 dst. voucher berisi lampiran semua bukti (vektor, berlabel) | #7 | [x] | `18cfe86` |
| T2.2 | Beberapa bon digabung satu halaman (reimburse 4 per halaman, lainnya 1 per halaman) | #7 | [x] | `18cfe86` |
| T2.3 | Reimburse sampai 20 bukti; kategori lain tetap maks. 10 | #11 | [x] | `18cfe86` |
| T2.4 | Reimburse: struk/nota sah, boleh banyak vendor (aturan satu vendor/rekening tidak berlaku) | #11 | [x] | `18cfe86` |
| T2.5 | Reimburse: wajib hanya tanggal dan total; rekening vendor tidak dicek (dibayar ke karyawan) (bagian rekening **diganti oleh T14.3**: rekening hanya diisi bila fitur rekening aktif) | #11 | [x] | `18cfe86` |
| T2.6 | Test reimburse (lampiran, batas, aturan) | — | [x] | `18cfe86` |

## Tahap 3 — Alur draf (spesifikasi 2.C)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T3.1 | Status baru `DRAFT`: hasil AI berhenti di draf (atau EXCEPTION bila ada kendala wajib) | #2 | [x] | `e456f7a` |
| T3.2 | Data disimpan dan diedit **per invoice** oleh PIC; voucher disusun dan diverifikasi ulang setiap simpan | #3 | [x] | `e456f7a` |
| T3.3 | Simulasi Voucher Pengeluaran (bertanda SIMULASI, lengkap dengan lampiran) | #4 | [x] | `e456f7a` |
| T3.4 | Simulasi bisa dilihat layar penuh, tab baru, dan diunduh | #4 | [x] | `0ed9289` |
| T3.5 | PIC mengirim draf ke Finance Reviewer; ditolak bila masih ada kendala wajib | #2 | [x] | `e456f7a` |
| T3.6 | Finance Reviewer **tidak bisa mengedit**: hanya Setujui atau Kembalikan ke PIC; pengirim draf dihitung pihak pengaju (SoD) | #2 | [x] | `e456f7a` |
| T3.7 | Telegram: tombol "Kirim ke reviewer" untuk draf, pesan data belum lengkap diringkas | #2 | [x] | `e456f7a`, `1e2ea1a` |

## Tahap 4 — Pajak (spesifikasi 2.D)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T4.1 | Tabel tarif pajak (PPh 21 non final, PPh 23, PPh 4 ayat 2, PPh 26, Tanpa potongan), bisa diubah Service Lead / System Admin | #9, #12 | [x] | `4047cf6` |
| T4.2 | Tarif mengikuti NPWP vendor dari Data Referensi; bisa diubah PIC per invoice | #9 | [x] | `4047cf6` |
| T4.3 | DPP otomatis dari rincian tanpa baris PPN | #9 | [x] | `4047cf6` |
| T4.4 | AI menyarankan jenis pajak (cadangan aturan kata kunci); PPh 21 untuk PT/CV dikoreksi ke PPh 23; reimburse Tanpa potongan | #12 | [x] | `4047cf6` |
| T4.5 | PIC **wajib memilih** pajak tiap bukti sebelum kirim; saran AI tidak berlaku otomatis | #12 | [x] | `7b8e445` |
| T4.6 | Voucher mencetak jumlah tagihan, potongan per invoice, dan total dibayarkan (bersih) | #9 | [x] | `4047cf6` |
| T4.7 | Tabel voucher, CSV, rekap, dan Telegram memakai nilai bersih | #9 | [x] | `4047cf6` |
| T4.8 | Perubahan pajak tercatat di jejak audit | — | [x] | `4047cf6` |

## Tahap 5 — Konfirmasi tarif

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T5.1 | Tarif PPh 21, PPh 23, PPh 4 ayat 2, dan Tanpa potongan dikonfirmasi tim (label "perlu dikonfirmasi" dicabut) | [x] | `4809b51` |
| T5.2 | PPh 26: owner menulis "Ppn 26 (luar negeri)". Maksudnya PPh 26 atau PPN luar negeri? | ❓ | — |

## Tahap 6 — Feedback owner 19–20 Okt 2026

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T6.1 | Kop voucher memakai **logo klien** (diunggah PIC Klien atau System Admin) | [x] | `82be79e` |
| T6.2 | Klien, Request ID, vendor, No./Tgl. invoice, rekening, catatan e-sign, dan teks batas otorisasi **tidak dicetak** di voucher | [x] | `82be79e` |
| T6.3 | PPN tidak diperhitungkan lagi: baris PPN tidak dicetak, voucher memakai total invoice termasuk PPN, PPh dihitung dari nilai sebelum PPN | [x] | `5305fec` |
| T6.4 | Tabel voucher jadi No · Uraian · Jumlah: PPN dilebur ke nilai barang, potongan PPh jadi baris bernomor tepat di bawah barangnya | [x] | `ecfdf59` |

## Tahap 7 — Pertanyaan terbuka ke owner

| ID | Pertanyaan | Status | Jawaban |
| --- | --- | --- | --- |
| T7.1 | Kategori apa saja selain Pembayaran vendor dan Reimburse (kas kecil, uang muka, perjalanan dinas)? | ❓ | — |
| T7.2 | Jenis pajak yang paling sering dipakai klien AMIGA; apakah ada daftar tarif resmi dari konsultan pajak? | ❓ | — |
| T7.3 | Benarkah reimburse karyawan (bon tol, parkir) tidak dipotong PPh? (sementara: saran Tanpa potongan, PIC tetap boleh memilih) | ❓ | — |
| T7.4 | PPh 26 atau PPN luar negeri? (lihat T5.2) | ❓ | — |

## Tahap 8 — Dokumen & rilis

| ID | Tugas | Status | Catatan |
| --- | --- | --- | --- |
| T8.1 | Perbarui BPMN: alur draf (PIC edit → simulasi → kirim), reviewer tanpa edit | [ ] | BPMN v2 masih alur lama (reviewer mengoreksi) |
| T8.2 | BRD v3.0 (as-built 27 Okt 2026): 18 perubahan D1–D18 terhadap v2.0 (alur draf, kategori, reimburse, banyak invoice per PDF, mode baca AI, pajak dan PPN, DPP PPh 23 imbalan jasa, format voucher, rekening opsional, isi manual, profil pengaju, bot @amiga_online_ro_bot, kemudahan pakai, biaya AI, lokasi server, status DRAFT), epic dan UAT diperbarui, pertanyaan terbuka dan lembar persetujuan. Sisa format voucher Tahap 11 dicatat sebagai backlog | [x] | `df19cf6` |
| T8.3 | Perbarui PRD (v3.1): FR baru Tahap 1–6, 9, dan 10 (isi manual saat AI bermasalah, VENDOR_MISMATCH jadi peringatan, cek rekening per invoice); FR-5.2 (teks batas otorisasi) dicabut owner; batas 5 halaman per file dihapus (T12.1); rekening tidak wajib (T13.1) | [ ] | |
| T8.4 | Perbarui SOP (`docs/sop.md`) untuk alur draf dan pajak (termasuk PPN dan PPh per baris, Tahap 9), isi manual saat AI bermasalah, dan konfirmasi beberapa vendor (Tahap 10), lalu jalankan `POST /reindex` | [ ] | Asisten AI menjawab dari SOP |
| T8.5 | Deploy ulang ke EC2 (`git pull` lalu skrip deploy) | [ ] | Skrip deploy disimpan lokal (diabaikan git) |

---

## Riwayat pembaruan

| Tanggal | Perubahan |
| --- | --- |
| 20 Okt 2026 | Dibuat dari Ringkasan Feedback Owner (18 Okt) dan commit Tahap 1–5 |
| 20 Okt 2026 | T6.3 selesai (`5305fec`); T6.4 ditambahkan dan selesai (`ecfdf59`) |
| 20 Okt 2026 | Tahap 9 ditambahkan dan selesai (T9.1–T9.8): PPN per invoice, PPh per baris, navigasi cepat, sample pajak; T8.2–T8.4 mencakup Tahap 9 |
| 20 Okt 2026 | Tahap 10 ditambahkan dan selesai (T10.1–T10.6): isi manual saat AI bermasalah, subtotal otomatis, beberapa vendor per voucher, rekening per invoice, pintasan rekening vendor; T8.2–T8.4 mencakup Tahap 10 |
| 20 Okt 2026 | Hash `a31dd37` diisi untuk Tahap 9–10; Tahap 11 ditambahkan dari contoh voucher owner (No. 1702 & 1944) |
| 20 Okt 2026 | Tahap 12 ditambahkan dan selesai (T12.1–T12.2, `4d95069`): batas halaman per file dihapus, AI membaca 5 halaman pertama, label "Jumlah PPN" dikenali; `docs/sop.md` ikut diperbarui (perlu `POST /reindex` agar Asisten memakai isi baru) |
| 21 Okt 2026 | T8.6 ditambahkan dan selesai: buku panduan pengguna PDF v3.0 di `readme/` |
| 21 Okt 2026 | T8.7 ditambahkan (deploy publik): backend FastAPI Cloud + Neon AS sudah berjalan, Vercel menyusul |
| 21 Okt 2026 | T8.7 selesai: frontend Vercel tersambung ke backend FastAPI Cloud (CORS) |
| 21 Okt 2026 | Tahap 13 ditambahkan dan selesai (T13.1–T13.2): rekening opsional, tombol Simpan lebih jelas; `docs/sop.md` ikut diperbarui |
| 21 Okt 2026 | T13.3 ditambahkan dan selesai: dashboard nyaman dipakai di HP |
| 22 Okt 2026 | T13.4 ditambahkan dan selesai: pencarian tersedia di laci menu HP |
| 22 Okt 2026 | Tahap 14 ditambahkan dan selesai (T14.1–T14.10, belum di-commit); T1.6, T2.5 (bagian rekening), T10.4, T10.5, T11.4, T13.1 ditandai diganti oleh T14.x |
| 22 Okt 2026 | T13.5–T13.6 ditambahkan dan selesai: tampilan dashboard full fit ke kanan (hapus max-width 1440px) dan fitur minimizing sidebar desktop (ikon di header sidebar, transisi halus, mode mini 68px dengan hover tooltip berpanah) serta persistensi localStorage |
| 22 Okt 2026 | Hash `3bed3ea` diisi untuk Tahap 14. Tahap 15 ditambahkan dan selesai (T15.1–T15.8, belum di-commit): toggle Diajukan oleh, banyak invoice per PDF, tanda tangan mode gelap; T14.6 ditandai diganti oleh T15.1–T15.2 |
| 22 Okt 2026 | T15.9 ditambahkan dan selesai (belum di-commit): PPN "harga belum termasuk PPN (ditambahkan PPN)" menggantikan "PPN terpisah" |
| 24 Okt 2026 | Hash `4d0cf04` diisi untuk Tahap 15 |
| 24 Okt 2026 | Tahap 16 ditambahkan dan selesai (T16.1–T16.8): penggabungan branch `feat/pisah-invoice-gabungan` ke `main` (tombol AI split on-demand di draf, proteksi serial Faktur Pajak `_is_tax_serial`, saran PPh 23 imbalan jasa dicocokkan PPN 11%/12%, pratinjau lokal file upload, label audit log, alembic Windows fix, 52/52 backend test lulus, frontend build lulus) |
| 24 Okt 2026 | Tahap 17 ditambahkan dan selesai (T17.1–T17.7): perbaikan multi-invoice DSS (filter Faktur Pajak & format uraian transaksi), deteksi total gambar dengan desimal `,-`, serta implementasi toggle & tombol cepat "Atur pajak secara otomatis" di Upload dan Editor Draf |
| 24 Okt 2026 | Tahap 18 ditambahkan dan selesai (T18.1–T18.6): penggabungan terpadu commit `b89472b` dengan penambahan kolom "Terakhir Diubah" & sorting interaktif semua kolom Tabel Riwayat/Dokumen, penyempurnaan `confirm_front_pages` & `fee_from_amounts`, pemetaan acuan kontrak fee DSS (`DSS_KNOWN_FEES`), eliminasi ekstraksi kode driver (`DD00002`/`DD00003`), petunjuk UI PPh 23 pada TaxPanel, 76/76 unit test backend lulus 100%, frontend build sukses |
| 24 Okt 2026 | T18.7 ditambahkan dan selesai: koreksi commit `031e60f` (tabel fee DSS hafalan dan tebakan dari rasio PPN dicabut, urutan tabel bawaan dari server); batasan DPP PPh 23 dikembalikan ke penjelasan Tahap 18. BRD/PRD/SOP perlu mencatat batasan ini (T8.2–T8.4) |
| 24 Okt 2026 | Tahap 19 ditambahkan (feedback tim, 4 poin); T19.1 selesai: saran PPN dari PPN tercetak dan format baris potongan PPh sesuai contoh owner |
| 24 Okt 2026 | T19.2 selesai: alur bot Telegram dengan ringkasan dan pengaturan pajak per bukti, uraian, simulasi voucher PDF |
| 26 Okt 2026 | T19.3 selesai: tutorial di dalam aplikasi (tombol ? dengan sorotan langkah demi langkah) |
| 26 Okt 2026 | T19.5 ditambahkan dan selesai: perbaikan pemisahan invoice dan DPP PPh 23 dari uji nyata berkas DSS |
| 26 Okt 2026 | T19.4 selesai: User Guide Book v4.0 (PDF, pengumpulan tugas MAIN) dan SOP v1.3; Tahap 19 selesai. Buku panduan v3.0 digantikan v4.0 |
| 26 Okt 2026 | User Guide Book v4.0 dan SOP: alamat login utama http://13.212.201.121/login (server EC2) dan bot @amiga_online_ro_bot |
| 26 Okt 2026 | T19.6 ditambahkan dan selesai: galeri dokumentasi visual untuk pengumpulan tugas MAIN |
| 26 Okt 2026 | T19.7 ditambahkan dan selesai: data asli owner dikeluarkan dari repo publik, contoh DSS sintetis |
| 26 Okt 2026 | Riwayat git ditulis ulang (git filter-repo) untuk mengeluarkan dokumen asli owner dari repo publik; semua hash commit di file ini disesuaikan dengan riwayat baru. README: bagian Coba aplikasi dan Mulai cepat |
| 27 Okt 2026 | T8.2 selesai: BRD v3.0 (DOCX dan PDF) di `readme/` |
