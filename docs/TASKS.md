# Tracking Tugas — Feedback Owner AMIGA

Sumber: **Ringkasan Pemahaman Feedback Owner AMIGA** (18 Okt 2026, 12 masukan owner), ditambah feedback owner setelahnya.
Dokumen acuan lain: [BRD v2.0](../readme/BRD_AMIGA_Robot_Admin_v2.0.pdf) · [PRD v3](../readme/PRD_AMIGA_Robot_Admin_v3.pdf) · [BPMN v2](../readme/AMIGA_Robot_Admin_Invoice_to_Voucher_v2.png)

**Cara pakai**

- `[x]` selesai · `[ ]` belum · 🔄 sedang dikerjakan · ❓ menunggu jawaban owner/tim
- Setiap tugas punya ID (mis. `T3.2`). Sebut ID-nya saat minta update, misalnya "T6.1 sudah selesai".
- Saat tugas selesai: centang, isi kolom commit, perbarui ringkasan progres, lalu commit dan push.
- Nomor `#1`–`#12` merujuk ke nomor masukan owner di dokumen ringkasan.

_Terakhir diperbarui: 24 Okt 2026_

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
| 8 | Dokumen & rilis (BRD, PRD, BPMN, buku panduan, deploy) | Sedang | 2/7 | ⏳ |
| 9 | Feedback owner 20 Okt (PPN per invoice, PPh per baris, navigasi cepat layar tinjau) | Besar | 8/8 | ✅ |
| 10 | Mengurangi ketergantungan AI: isi manual, subtotal otomatis, beberapa vendor per voucher, pintasan rekening vendor | Besar | 6/6 | ✅ |
| 11 | Format voucher mengikuti contoh owner (No. 1702 & 1944): kop data, kolom tabel, satu baris per invoice, kotak Diketahui oleh | Besar | 0/9 | ⏳ (4 perlu konfirmasi) |
| 12 | Berkas invoice banyak halaman (invoice + Faktur Pajak + timesheet) | Kecil | 2/2 | ✅ |
| 13 | Feedback uji coba 21–22 Okt: rekening opsional, alur simpan jelas, tampilan HP, full fit layar lebar & hide sidebar desktop | Sedang | 6/6 | ✅ |
| 14 | Mode AI total saja/rincian, rekening jadi fitur tambahan, pajak otomatis/manual, profil & tanda tangan pengaju, pratinjau voucher, estimasi biaya AI | Besar | 10/10 | ✅ |
| 15 | Toggle "Diajukan oleh" (profil PIC terkunci / isi manual), banyak invoice dalam satu PDF (pindai per 5 halaman, satu bukti per invoice, rentang halaman bisa diubah), tanda tangan di mode gelap, PPN "harga belum termasuk PPN" | Besar | 9/9 | ✅ |
| 16 | Pemisahan invoice gabungan on-demand (tombol AI) & saran PPh 23 imbalan jasa (merging branch `feat/pisah-invoice-gabungan` ke `main`) | Sedang | 8/8 | ✅ |
| 17 | Perbaikan multi-invoice DSS, deteksi total gambar, pajak otomatis | Sedang | 7/7 | ✅ |
| 18 | DPP PPh 23 kasus DSS: imbalan jasa (bagian kena PPN), bukan total invoice; halaman awal invoice diperiksa per halaman | Sedang | 5/5 | ✅ |

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
| T8.2 | Perbarui BRD (v2.1): status `DRAFT`, kategori, reimburse, pajak, isi PDF voucher (termasuk PPN dilebur, T6.3–T6.4, dan pengaturan PPN/PPh per baris T9.1–T9.6); satu voucher boleh beberapa vendor/rekening setelah dikonfirmasi PIC (T10.3); format voucher Tahap 11 | [ ] | |
| T8.3 | Perbarui PRD (v3.1): FR baru Tahap 1–6, 9, dan 10 (isi manual saat AI bermasalah, VENDOR_MISMATCH jadi peringatan, cek rekening per invoice); FR-5.2 (teks batas otorisasi) dicabut owner; batas 5 halaman per file dihapus (T12.1); rekening tidak wajib (T13.1) | [ ] | |
| T8.4 | Perbarui SOP (`docs/sop.md`) untuk alur draf dan pajak (termasuk PPN dan PPh per baris, Tahap 9), isi manual saat AI bermasalah, dan konfirmasi beberapa vendor (Tahap 10), lalu jalankan `POST /reindex` | [ ] | Asisten AI menjawab dari SOP |
| T8.5 | Deploy ulang ke EC2 (`git pull` lalu skrip deploy) | [ ] | Skrip deploy disimpan lokal (diabaikan git) |
| T8.6 | Buku panduan pengguna PDF v3.0 (15 bab, 28 gambar dari aplikasi terbaru, mencakup Tahap 1–10 dan 12) | [x] | [`readme/Buku_Panduan_AMIGA_Robot_Admin_v3.0.pdf`](../readme/Buku_Panduan_AMIGA_Robot_Admin_v3.0.pdf); Bab 8 (voucher) perlu diperbarui setelah Tahap 11 |
| T8.7 | Deploy publik: database Neon (aws-us-east-1), backend FastAPI Cloud (`https://amiga-robot-admin.fastapicloud.dev`, file di S3), frontend Vercel (`https://amiga-admin-robot-tim-11.vercel.app`) | [x] | Akun demo memakai password baru (lihat `backend/production.env`, tidak di-commit); `CORS_ORIGINS` dan `FRONTEND_URL` = alamat Vercel; bot Telegram tetap di komputer demo |

## Tahap 9 — Pajak per baris & navigasi cepat (feedback owner 20 Okt 2026)

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T9.1 | Pengaturan PPN per invoice: terpisah / harga sudah termasuk PPN / tidak ada; tarif bisa dipilih (bawaan 11%); baris bisa ditandai tidak kena PPN atau sebagai baris PPN | [x] | `707aef1` |
| T9.2 | PPN invoice dibandingkan dengan hitungan sistem: selisih hanya peringatan, voucher tetap memakai total invoice | [x] | `707aef1` |
| T9.3 | Pilihan "Tampilkan rincian PPN pada voucher" (bawaan tidak dicentang: PPN dilebur ke nilai barang, seperti T6.4) | [x] | `707aef1` |
| T9.4 | Penerapan PPh: satu jenis untuk seluruh invoice (bawaan) atau berbeda per baris; PIC memilih beberapa baris sekaligus (multi-select) untuk satu jenis PPh | [x] | `707aef1` |
| T9.5 | Saran PPh per baris dari aturan kata kunci (tanpa AI) sebagai isian awal; tombol "Minta rekomendasi AI untuk PPh per baris"; bila AI tidak tersedia muncul pesan dan saran aturan tetap dipakai | [x] | `707aef1` |
| T9.6 | Voucher: potongan PPh per jenis dicetak tepat di bawah barang terakhir yang dipotong jenis itu; ringkasan pajak di layar menampilkan PPN dan baris yang dipotong | [x] | `707aef1` |
| T9.7 | Navigasi cepat panel kanan layar tinjau: daftar bagian berwarna status (oranye = perlu diisi/diperbaiki, merah = menghalangi kirim), lompat ke kolom kosong, tombol "Perbaikan berikutnya", pemeriksaan di kartu hasil AI bisa diklik | [x] | `707aef1` |
| T9.8 | Sample invoice pajak (`samples/pajak/`, 8 kasus) dan test (`backend/tests/test_tax_per_line.py`) | [x] | `707aef1` |

## Tahap 10 — Mengurangi ketergantungan AI (setelah kunci AWS dicabut, 20 Okt 2026)

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T10.1 | Mode isi manual: `AI_EXTRACTION_ENABLED=false` di `.env`, atau AI gagal membaca (mis. kredensial), membuat bukti menjadi draf kosong dengan pesan "Isi data invoice secara manual", bukan dokumen "Ada kendala". Bukti lain yang terbaca AI tetap dipakai; saran pajak dari aturan tetap ada; tombol "Coba baca ulang dengan AI" hanya membaca ulang bukti yang gagal. File yang hilang di penyimpanan tetap `EXTRACTION_FAILED` | [x] | `707aef1` |
| T10.2 | Subtotal otomatis = qty × harga satuan (2 desimal, tanda "otomatis") bila keduanya terisi; selain itu subtotal diisi manual (borongan). Juga dihitung ulang di backend saat disimpan. Tombol "Samakan total dengan jumlah rincian" | [x] | `707aef1` |
| T10.3 | Beberapa vendor/rekening dalam satu voucher (`VENDOR_MISMATCH`) menjadi peringatan: dokumen tetap Draf, PIC mengonfirmasi dengan alasan (`POST /documents/{id}/acknowledge`, tercatat di riwayat, tidak dicetak di voucher). Konfirmasi gugur bila daftar vendor/rekening berubah | [x] | `707aef1` |
| T10.4 | Rekening dicek per invoice: setiap rekening dicocokkan dengan vendornya masing-masing (`ACCOUNT_MISMATCH` tetap menghalangi; **diganti oleh T14.3**: kini hanya pengingat). Reviewer melihat "Pembayaran per rekening" (vendor, rekening, nilai dibayarkan, status), dan konfirmasi rekening saat menyetujui mencakup semua rekening yang belum terverifikasi | [x] | `707aef1` |
| T10.5 | (**Diganti oleh T14.3**: pintasan hanya tampil bila fitur rekening aktif) Pintasan rekening vendor dari layar dokumen: PIC "Daftarkan rekening vendor" / "Perbarui rekening vendor" (diisi dari invoice; hanya pencatatan, pengajuan tetap berjalan), Finance Reviewer "Verifikasi rekening vendor ini" (SoD tetap berlaku). Formulir vendor dipindah ke `components/VendorForm.tsx`; `GET /vendors/{id}` ditambahkan | [x] | `707aef1` |
| T10.6 | Test: `test_documents.py` (isi manual, AI dimatikan, error tak terduga, file hilang), `test_multi_invoice.py` (konfirmasi PIC, konfirmasi gugur, rekening per invoice, daftar & verifikasi vendor), `test_review.py` (subtotal otomatis) | [x] | `707aef1` |

## Tahap 11 — Format voucher sesuai contoh owner (20 Okt 2026)

Sumber: contoh voucher owner `samples/test_case_amiga/1702_…DSS Management Fee…pdf` (6 invoice, PPh 23) dan
`1944_…Fee Pembicara…pdf` (PPh 21). Isi halaman 1 contoh 1702:

- Kop data: **Nomor** 1702-04-2026 · **Nama** (pengaju) · **Peruntukan** · **Tanggal/Periode** · **Nominal** (= total bersih)
- Tabel **NO · TANGGAL · KETERANGAN · JUMLAH · HARGA**; satu baris per invoice senilai total invoice (termasuk PPN),
  lalu baris potongan di bawahnya: `Potongan PPh 23 ( Rp 2,304,696 x 2% ) Syaiful Rindang` = `-Rp46,094`
- PPh 23 hanya dari baris jasa (Management Fee), bukan Basic Fee/Overtime → sudah didukung PPh per baris (T9.4)
- Kotak tanda tangan: **Diajukan Oleh · Diketahui Oleh · Disetujui Oleh** (nama + jabatan)

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T11.1 | Kop data voucher: Nomor, Nama (pengaju), **Peruntukan** (kolom baru diisi PIC, mis. "Pembayaran DSS Management Fee … Maret 2026"), Tanggal/Periode, Nominal (total dibayarkan) | [ ] | — |
| T11.2 | Format nomor voucher `{urut}-{MM}-{YYYY}` (mis. 1702-04-2026); nomor urut tidak reset per bulan (1702 di April, 1944 di Oktober) | ❓ | — |
| T11.3 | Kolom tabel NO · TANGGAL · KETERANGAN · JUMLAH · HARGA; tanggal = tanggal voucher | [ ] | — |
| T11.4 | Satu baris per invoice (keterangan ringkas yang bisa diedit PIC, nilai = total invoice termasuk PPN), bukan per barang — **diganti oleh T14.1/T14.5** (mode "Total saja") | [x] | `e01d698` |
| T11.5 | Teks potongan `Potongan PPh 23 ( Rp DPP x 2% ) <keterangan>`, nilai negatif `-Rp…`; baris akhir `TOTAL` | [ ] | — |
| T11.6 | Kotak tanda tangan ketiga **Diketahui oleh** (nama + jabatan, didaftarkan PIC seperti penanda tangan lain) | [ ] | — |
| T11.7 | Gross-up PPh 21: contoh 1944 fee Rp 3.076.923 dipotong 2,5% agar bersih tepat Rp 3.000.000 | ❓ | — |
| T11.8 | Format angka: contoh owner `Rp8,933,846` (koma); aplikasi sekarang `Rp 8.933.846` | ❓ | — |
| T11.9 | Test dengan dua contoh owner: total 1702 = Rp 41.719.136, total 1944 = Rp 3.000.000 | [ ] | — |

Pertanyaan ke owner untuk T11.2, T11.4, T11.7, T11.8:
1. Nomor voucher: nomor urut per klien yang melanjutkan nomor terakhir mereka (1944 → 1945), atau mulai dari 1?
2. Rincian per barang tetap boleh dicetak, atau selalu satu baris per invoice?
3. Perlu hitung otomatis gross-up (PIC mengisi nilai bersih, sistem menghitung bruto)?
4. Angka di voucher ikut format contoh (koma) atau format Indonesia (titik)?

## Tahap 12 — Berkas invoice banyak halaman (feedback owner 20 Okt 2026)

Sumber: contoh owner `1702_…DSS Management Fee…pdf` (33 halaman): tiap invoice dikirim sebagai satu berkas berisi
invoice, rincian, Faktur Pajak, dan timesheet (4–8 halaman lebih), sehingga batas 5 halaman per file menolaknya.

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T12.1 | Batas halaman per file dihapus (dashboard, API, Telegram); batas 10 MB per file tetap. AI hanya membaca 5 halaman pertama (`AI_MAX_PAGES`), semua halaman tetap dilampirkan di voucher. Diuji dengan berkas invoice pertama contoh 1702 (8 halaman): total Rp 8.933.846 terbaca tepat | [x] | `1210ba3` |
| T12.2 | Baris PPN berlabel "Jumlah PPN …", "Total PPN", "Nilai PPN" (format Faktur DSS) dikenali sebagai baris PPN, tidak jadi barang atau dasar PPh | [x] | `1210ba3` |

## Tahap 13 — Feedback uji coba 21 Okt 2026

Sumber: uji coba tim di dashboard online. Mengisi rekening mengganggu karena sering tidak ada di invoice, sementara owner
sebelumnya menyatakan rekening tidak perlu (tidak ada proses transfer di sistem). Setelah mengisi data juga tidak jelas
harus menekan apa.

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T13.1 | Rekening tujuan (bank, nomor, nama penerima) **tidak wajib**: tidak lagi `MISSING_EVIDENCE`, navigasi menandainya "opsional". Bila diisi, tetap dicocokkan dengan rekening vendor terverifikasi (`ACCOUNT_MISMATCH` tetap berlaku; **diganti oleh T14.3**: rekening jadi fitur tambahan, perbedaan hanya pengingat) | [x] | `d89897d` |
| T13.2 | Tombol **Simpan bukti** menjadi tombol utama dan muncul "Ada perubahan yang belum disimpan" setiap ada isian yang belum disimpan | [x] | `d89897d` |
| T13.3 | Tampilan HP (≤ 860 px): menu samping jadi laci (tombol ☰), topbar ringkas, tombol Asisten bulat, tabel bisa digeser ke samping, rincian barang tetap terbaca, tombol keputusan dua kolom, simulasi voucher layar penuh | [x] | `0353ad4` |
| T13.4 | Di HP, kotak **pencarian** (Request ID / vendor) ada di dalam laci menu ☰; laci tertutup otomatis setelah mencari | [x] | `27043ad` |
| T13.5 | Dashboard & semua layar **full fit**: batas `max-width: 1440px` pada kontainer `.content` dicabut sehingga seluruh kartu metrik, grafik tren harian, tabel data, form, dan split-screen memanfaatkan 100% lebar layar kanan tanpa sisa space kosong | [x] | — |
| T13.6 | Sidebar desktop bisa di-**minimize** (bukan menutup total): mengecil ke mode ikon (68 px) dengan animasi halus (cubic-bezier), teks keterangan menu muncul sebagai floating tooltip berpanah saat di-hover; tombol toggle panah (`ChevronLeft` / `ChevronRight`) terletak di kanan atas header sidebar (sejajar logo); preferensi tersimpan di `localStorage` (`amiga_side_collapsed`); drawer HP tetap terjaga | [x] | — |

## Tahap 14 — Mode AI, rekening opsional, profil pengaju (feedback owner 22 Okt 2026)

Sumber: permintaan owner 22 Okt 2026 beserta jawaban open question (rekening sebagai fitur tambahan, vendor berbeda hanya
pengingat, pajak boleh dihitung manual, profil pengaju diingat per PIC). Data lama tetap aman: pengajuan lama otomatis
mode "Rincian" tanpa fitur rekening, data rekeningnya tetap tersimpan, dan salinan penanda tangan lama tetap tercetak.

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T14.1 | Dua mode baca AI per pengajuan (`extraction_mode`): **Total saja** (bawaan; prompt ringkas: jenis dokumen, vendor, nomor, tanggal, total; 1 baris voucher per invoice) dan **Rincian barang/jasa** (1 baris per item). Pilihan di halaman Pembuatan Voucher; migrasi `a6e3c9d2f415` | [x] | `89d5d6a` |
| T14.2 | Mode bisa diganti di halaman detail: Total → Rincian membaca ulang rincian dengan AI (data utama, uraian, pajak tetap); Rincian → Total menyembunyikan rincian, total tetap | [x] | `89d5d6a` |
| T14.3 | Rekening tujuan jadi **fitur tambahan** (toggle "Perlu input rekening tujuan ke voucher", bawaan mati): bila aktif, rekening dibaca AI, diisi, dicek ke data vendor, dan dicetak di voucher. `VENDOR_MISMATCH` dan `ACCOUNT_MISMATCH` jadi **pengingat** yang tidak menahan pengajuan maupun persetujuan; rekening berbeda/belum terverifikasi tetap perlu konfirmasi reviewer saat menyetujui | [x] | `89d5d6a` |
| T14.4 | Pajak mode Total saja: DPP otomatis dari total sesuai perlakuan PPN (terpisah/termasuk/tanpa + tarif), tetap bisa diubah; PPh di level dokumen. Opsi **"Hitung pajak otomatis"** (bawaan aktif); bila dimatikan, DPP, PPN, dan potongan PPh diisi manual | [x] | `89d5d6a` |
| T14.5 | Uraian per invoice (bawaan "Invoice {nomor} - {vendor}", bisa diedit) dicetak sebagai satu baris voucher; wajib terisi sebelum diajukan | [x] | `89d5d6a` |
| T14.6 | Profil **Diajukan oleh** (**diganti oleh T15.1–T15.2**: profil tidak lagi diingat dari isian pengajuan): nama, jabatan, perusahaan/unit, tanda tangan (PNG/JPG/WEBP, maks. 2 MB). Disimpan per pengajuan dan diingat sebagai isian awal PIC; bisa diubah di halaman detail; dicetak di simulasi dan voucher final. Unggahan Telegram memakai mode Total saja dan profil tersimpan | [x] | `89d5d6a` |
| T14.7 | Halaman 1 disusun ulang: Klien → Kategori → Tanggal → Diajukan oleh → Disetujui oleh → Mode AI → Fitur tambahan (saluran & tenggat, rekening) → File bukti, lalu **Simpan draf & lanjutkan** langsung ke halaman detail. Saluran & tenggat jadi opsional | [x] | `89d5d6a` |
| T14.8 | Halaman 2: mode Total saja menampilkan formulir ringkas (data utama, uraian, total, pajak dokumen) tanpa tabel rincian; **pratinjau voucher** langsung di halaman (di HP lewat tombol buka di tab baru); tombol "Kirim ke reviewer" menjadi **Ajukan untuk Direview** (aktif setelah uraian dan pajak terisi) | [x] | `89d5d6a` |
| T14.9 | **Estimasi biaya AI** per mode (token tercatat per pengajuan × harga di pengaturan) di Dashboard Service Lead dan halaman Pengguna System Admin; `GET /dashboard/ai-usage` | [x] | `89d5d6a` |
| T14.10 | Cek ulang tampilan HP (390 px) untuk halaman unggah, detail, pajak, dan kartu biaya AI: tidak ada geser ke samping; test backend `tests/test_total_only.py` + test lama disesuaikan; Cypress disesuaikan dengan alur baru (belum dijalankan ulang) | [x] | `89d5d6a` |

## Tahap 15 — Toggle pengaju & banyak invoice dalam satu PDF (feedback owner 22 Okt 2026)

Sumber: masukan owner 22 Okt 2026 dengan contoh `samples/test_case_amiga/test_voucher bayar dss.pdf` (32 halaman: tiap
invoice = halaman invoice + rincian + 2 halaman Faktur Pajak) beserta jawaban open question. Data lama tetap aman: bukti
lama tetap 1 file = 1 bukti (kolom halaman kosong), salinan penanda tangan lama tetap tercetak.

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T15.1 | **Diajukan oleh** punya pilihan **Diisi PIC Klien** (bawaan; nama, jabatan, perusahaan/unit, dan tanda tangan dikunci ke profil akun PIC) atau **Diisi manual** (nama wajib, jabatan, perusahaan, tanda tangan opsional; kosong = tanda tangan basah). Isian manual tidak diingat. Intake Support: mode PIC memakai profil PIC yang mendelegasikan, tetap bisa pilih manual. Field `submitter_source` di unggah dan `PUT /documents/{id}/signers` | [x] | `07b8c19` |
| T15.2 | Halaman **Akun**: kartu Profil "Diajukan oleh" (jabatan, perusahaan/unit, tanda tangan elektronik); nama mengikuti nama tampilan. Tanda tangan di halaman detail hanya bisa diganti untuk isian manual | [x] | `07b8c19` |
| T15.3 | Kotak tanda tangan tidak lagi putih terang di **mode gelap**: latar mengikuti tema dan goresan tinta dibalik menjadi terang | [x] | `07b8c19` |
| T15.4 | **Banyak invoice dalam satu PDF**: AI memindai semua halaman per 5 halaman (`AI_MAX_PAGES`) sampai `AI_MAX_SCAN_PAGES` (bawaan 40) dan mendaftar tiap invoice/struk (nomor, tanggal, vendor, total, halaman awal). Faktur Pajak, rincian, timesheet tidak dihitung sebagai invoice. Bila potongan pertama tidak memuat tagihan, pemindaian berhenti (hemat token). Mode Total saja memakai hasil pindai tanpa membaca ulang | [x] | `07b8c19` |
| T15.5 | Setiap invoice jadi satu **bukti** (tab, uraian, pajak, satu baris voucher): invoice di halaman berbeda dipotong per rentang halaman (invoice + lampirannya sampai sebelum invoice berikutnya); beberapa struk dalam satu halaman = beberapa bukti di halaman yang sama (mode Rincian membaca ulang tiap struk dengan petunjuk struk mana). Lampiran voucher tetap memuat PDF unggahan utuh, sekali. Migrasi `b8d2e4f6a713` (`upload_key`, `page_from`, `page_to`, `upload_pages`) | [x] | `07b8c19` |
| T15.6 | PIC bisa **mengubah rentang halaman**, **menambah bukti** dari halaman yang terlewat AI (dibaca AI atau diisi manual), dan **menghapus bukti** (minimal 1); semua tercatat di jejak audit. Endpoint `PUT /documents/{id}/files/{n}/pages`, `POST /documents/{id}/files`, `DELETE /documents/{id}/files/{n}` | [x] | `07b8c19` |
| T15.7 | Batas **invoice per voucher** dihitung per invoice yang terdeteksi: `MAX_INVOICES_PER_VOUCHER` (bawaan 30); kelebihannya ikut bukti terakhir dan muncul peringatan. `backend/.env.example` diperbarui | [x] | `07b8c19` |
| T15.8 | Test backend `tests/test_invoice_split.py` (berkas mirip DSS, struk satu halaman, batas, ubah/tambah/hapus bukti, prompt pindai) dan `tests/test_total_only.py` (toggle PIC/manual, tidak diingat, Intake); cek browser desktop dan HP 390 px (mode gelap) tanpa geser ke samping | [x] | `07b8c19` |
| T15.9 | Pilihan PPN "PPN terpisah" diganti **Harga belum termasuk PPN (ditambahkan PPN)**: harga = DPP dan PPN ditambahkan (mis. 200.000 dengan PPN 11% = 222.000 di baris voucher; PPh dihitung dari 200.000). Mode rincian: PPN dihitung sistem (tarif x DPP baris yang kena PPN); baris PPN di invoice hanya pembanding, selisih lebih dari Rp 100 dari total invoice menjadi pengingat. Data lama "PPN terpisah" ikut dihitung cara baru (keputusan owner: masih uji coba) | [x] | `07b8c19` |

## Tahap 16 — Pemisahan invoice gabungan on-demand (tombol AI) & saran PPh 23 imbalan jasa (24 Okt 2026)

Sumber: Penggabungan branch `feat/pisah-invoice-gabungan` (commit `4552d26`) ke `main` (commit `07b8c19`).
Menambahkan tombol on-demand AI split untuk efisiensi token, filter proteksi nomor faktur pajak,
rekomendasi PPh 23 atas imbalan jasa yang diverifikasi dengan PPN tercetak, pratinjau file lokal sebelum simpan,
dan kompatibilitas migrasi di OS Windows.

| ID | Tugas | Status | Commit / Modul |
| --- | --- | --- | --- |
| T16.1 | **Tombol "Pisahkan otomatis (AI)"** (`<Scissors />`) pada tiap bukti multi-halaman di editor draf: AI memeriksa halaman, memotong PDF per invoice (tab, baris voucher, dan pajak tersendiri). Dialog konfirmasi menampilkan estimasi token dan biaya sebelum eksekusi | [x] | `frontend/src/pages/DocumentPage.tsx`, `backend/app/routers/documents.py` |
| T16.2 | **Konfigurasi AI Split**: `AI_SPLIT_ENABLED` (bawaan true), `AI_SPLIT_AUTO` (bawaan false untuk menghemat token pada unggahan biasa; pemisahan dijalankan via tombol), `AI_SPLIT_MIN_PAGES` (2), `AI_SPLIT_MAX_PAGES` (40), `AI_SPLIT_MAX_INVOICES` (30), dan `AI_SPLIT_WORKERS` (4) | [x] | `backend/app/config.py` |
| T16.3 | **Filter Proteksi Faktur Pajak**: Fungsi `_is_tax_serial` mendeteksi nomor 15+ digit angka (nomor seri Faktur Pajak) sehingga tidak dianggap sebagai nomor invoice dan mencegah berkas terpecah salah sasaran | [x] | `backend/app/services/invoice_splitter.py` |
| T16.4 | **Saran PPh 23 Imbalan Jasa & Verifikasi PPN**: AI membaca komponen imbalan jasa (`service_fee`) dan mencocokkannya dengan PPN tercetak (11% atau 12%). Jika cocok, saran PPh 23 otomatis memakai imbalan jasa sebagai dasar potongan (DPP). Jika tidak cocok, muncul peringatan `service_fee_unverified` di formulir pajak agar PIC mengisi DPP secara manual | [x] | `backend/app/services/extraction_service.py`, `tax_service.py`, `TaxPanel.tsx` |
| T16.5 | **Pratinjau Berkas Lokal Sebelum Unggah**: Tombol `<Eye />` pada daftar file unggahan membuka modal pratinjau browser (`FilePreviewModal`) langsung dari memori tanpa mengirim ke server | [x] | `frontend/src/pages/Upload.tsx` |
| T16.6 | **Jejak Audit Pemisahan Invoice**: Pencatatan aktivitas audit log untuk `INVOICES_SPLIT`, `SPLIT_REQUESTED`, dan `INVOICES_SPLIT_CHECKED` | [x] | `backend/app/services/document_processing.py`, `frontend/src/pages/HistoryPage.tsx` |
| T16.7 | **Perbaikan Alembic di Windows**: Menyesuaikan pemanggilan alembic di test runner `conftest.py` menggunakan `sys.executable -m alembic` | [x] | `backend/tests/conftest.py` |
| T16.8 | **Pengujian & Validasi Komprehensif**: 23 unit test AI split (`backend/tests/test_split_invoices.py`), lulus bersama 7 test `test_invoice_split.py` dan 22 test `test_tax_per_line.py` (total 52 test lulus 100%); build bundle frontend (`tsc --noEmit && vite build`) sukses tanpa error | [x] | `backend/tests/test_split_invoices.py` |

## Tahap 17 — Perbaikan Multi-Invoice DSS, Deteksi Total Gambar, & Otomatisasi Pajak (24 Okt 2026)

| ID | Tugas | Status | Referensi / Berkas |
| --- | --- | --- | --- |
| T17.1 | **Penyaringan Halaman Faktur Pajak**: Menggunakan `_is_tax_serial` dan filter tipe dokumen pada `parse_scan()` agar halaman Faktur Pajak (seperti nomor seri 16 digit pada berkas DSS) tidak dijadikan invoice mandiri | [x] | `backend/app/services/extraction_service.py`, `invoice_splitter.py` |
| T17.2 | **Perbaikan Parsing Nilai Desimal Indonesia**: Menghapus akhiran rupiah non-standar (`,-`, `,--`, `.-`, `-`) pada `to_decimal` sehingga foto/gambar tagihan (seperti `12.425.000,-`) terdeteksi totalnya dengan akurat | [x] | `backend/app/services/extraction_service.py` |
| T17.3 | **Format Uraian Baris Transaksi Sesuai Standar**: Mengadaptasi format `"Invoice {nomor} - {vendor} - {uraian spesifik singkat terkait invoice}"` dari pembacaan AI `service_description` | [x] | `backend/app/services/document_processing.py`, `frontend/src/pages/DocumentPage.tsx` |
| T17.4 | **Toggle "Atur pajak secara otomatis" di Halaman Upload**: Toggle bawaan ON (`useState(true)`), mengirimkan `auto_tax=true` saat pengajuan baru agar rekomendasi PPh & PPN langsung diterapkan | [x] | `frontend/src/pages/Upload.tsx` |
| T17.5 | **Toggle & Tombol Aksi Cepat di Editor Draf**: Toggle pengaturan `auto_tax` di panel "Mode AI & fitur", serta tombol cepat `<Wand2 /> Atur pajak otomatis semua bukti` di tab Pajak | [x] | `frontend/src/pages/DocumentPage.tsx` |
| T17.6 | **Skema DB, Migrasi & Endpoint Backend**: Penambahan kolom `auto_tax` (default True) via Alembic revision `c9e4a8b2d1f7`, endpoint `POST /{id}/tax/apply-all`, dan update `PUT /{id}/options` | [x] | `backend/alembic/versions/c9e4a8b2d1f7_auto_tax_option.py`, `models.py`, `routers/documents.py`, `schemas/schemas.py` |
| T17.7 | **Pengujian Komprehensif**: Test suite baru `tests/test_dss_and_tax_improvements.py` (5/5 passed), 52/52 test split & tax backend passed, dan frontend build sukses tanpa error | [x] | `backend/tests/test_dss_and_tax_improvements.py` |


## Tahap 18 — DPP PPh 23 untuk invoice jasa yang memisahkan imbalan jasa (temuan voucher DSS 1702, 24 Okt 2026)

Temuan: di voucher bayar DSS, PPh 23 2% dipotong dari **Management Fee & Development** (mis. Rp 2.304.696), bukan dari
total invoice (Rp 8.933.846). Istilah "jasa" membingungkan karena driver juga jasa. **Batasan yang dipakai sistem:**
DPP PPh 23 = imbalan jasa milik vendor, yaitu bagian tagihan yang **dikenai PPN**. Penggantian biaya yang diteruskan
(Basic Fee/gaji, BPJS, Overtime driver) tidak dikenai PPN dan tidak dipotong PPh 23. Imbalan jasa hanya dipakai bila
cocok dengan angka PPN tercetak (imbalan x 11% = PPN, atau Sub total terkena PPN = imbalan x 11/12); bila tidak cocok,
PIC mengisi DPP sendiri. Invoice yang tidak memisahkan penggantian biaya tetap memakai DPP penuh seperti sebelumnya.

| ID | Tugas | Status | Commit |
| --- | --- | --- | --- |
| T18.1 | Halaman awal tiap invoice di berkas gabungan **diperiksa per halaman** (paralel) pada potongan yang memuat invoice, dicocokkan dari nomor invoice. Pembacaan nyata berkas DSS: pemindaian per 5 halaman menyebut 1, 3, 6, 11, 16, 26 (seharusnya 1, 5, 9, 13, 20, 26) sehingga rentang halaman bukti salah | [x] | `e01d698` |
| T18.2 | Halaman depan sekaligus menyalin **blok ringkasan jumlah** (label + angka). Imbalan jasa ditentukan kode (`fee_from_amounts`) dengan cek silang semua angka di blok itu, sehingga angka yang bergeser satu baris atau baris yang terlewat tetap ditemukan; bila tetap tidak cocok, halaman dibaca ulang sekali | [x] | `e01d698` |
| T18.3 | Label yang tersalin sebagai angka ditolak (mis. "Management Fee ... DD05592" sebelumnya terbaca imbalan jasa Rp 5.592) | [x] | `e01d698` |
| T18.4 | Panel pajak menjelaskan batasan DPP PPh 23 (imbalan jasa vendor, bukan penggantian gaji/BPJS/lembur) dan peringatan bila imbalan jasa tidak cocok dengan PPN | [x] | `e01d698` |
| T18.5 | Test `tests/test_dss_pph23.py` memakai angka pembacaan Nova Lite yang sebenarnya (termasuk salah bacanya); berkas DSS 6 invoice menghasilkan potongan 177.102 dan dibayar Rp 41.719.136, sama dengan voucher 1702 owner. Uji nyata dengan AI: 6/6 halaman awal dan 6/6 DPP benar (±123 ribu token per berkas 32 halaman) | [x] | `e01d698` |
---

## Riwayat pembaruan

| Tanggal | Perubahan |
| --- | --- |
| 20 Okt 2026 | Dibuat dari Ringkasan Feedback Owner (18 Okt) dan commit Tahap 1–5 |
| 20 Okt 2026 | T6.3 selesai (`5305fec`); T6.4 ditambahkan dan selesai (`ecfdf59`) |
| 20 Okt 2026 | Tahap 9 ditambahkan dan selesai (T9.1–T9.8): PPN per invoice, PPh per baris, navigasi cepat, sample pajak; T8.2–T8.4 mencakup Tahap 9 |
| 20 Okt 2026 | Tahap 10 ditambahkan dan selesai (T10.1–T10.6): isi manual saat AI bermasalah, subtotal otomatis, beberapa vendor per voucher, rekening per invoice, pintasan rekening vendor; T8.2–T8.4 mencakup Tahap 10 |
| 20 Okt 2026 | Hash `707aef1` diisi untuk Tahap 9–10; Tahap 11 ditambahkan dari contoh voucher owner (No. 1702 & 1944) |
| 20 Okt 2026 | Tahap 12 ditambahkan dan selesai (T12.1–T12.2, `1210ba3`): batas halaman per file dihapus, AI membaca 5 halaman pertama, label "Jumlah PPN" dikenali; `docs/sop.md` ikut diperbarui (perlu `POST /reindex` agar Asisten memakai isi baru) |
| 21 Okt 2026 | T8.6 ditambahkan dan selesai: buku panduan pengguna PDF v3.0 di `readme/` |
| 21 Okt 2026 | T8.7 ditambahkan (deploy publik): backend FastAPI Cloud + Neon AS sudah berjalan, Vercel menyusul |
| 21 Okt 2026 | T8.7 selesai: frontend Vercel tersambung ke backend FastAPI Cloud (CORS) |
| 21 Okt 2026 | Tahap 13 ditambahkan dan selesai (T13.1–T13.2): rekening opsional, tombol Simpan lebih jelas; `docs/sop.md` ikut diperbarui |
| 21 Okt 2026 | T13.3 ditambahkan dan selesai: dashboard nyaman dipakai di HP |
| 22 Okt 2026 | T13.4 ditambahkan dan selesai: pencarian tersedia di laci menu HP |
| 22 Okt 2026 | Tahap 14 ditambahkan dan selesai (T14.1–T14.10, belum di-commit); T1.6, T2.5 (bagian rekening), T10.4, T10.5, T11.4, T13.1 ditandai diganti oleh T14.x |
| 22 Okt 2026 | T13.5–T13.6 ditambahkan dan selesai: tampilan dashboard full fit ke kanan (hapus max-width 1440px) dan fitur minimizing sidebar desktop (ikon di header sidebar, transisi halus, mode mini 68px dengan hover tooltip berpanah) serta persistensi localStorage |
| 22 Okt 2026 | Hash `89d5d6a` diisi untuk Tahap 14. Tahap 15 ditambahkan dan selesai (T15.1–T15.8, belum di-commit): toggle Diajukan oleh, banyak invoice per PDF, tanda tangan mode gelap; T14.6 ditandai diganti oleh T15.1–T15.2 |
| 22 Okt 2026 | T15.9 ditambahkan dan selesai (belum di-commit): PPN "harga belum termasuk PPN (ditambahkan PPN)" menggantikan "PPN terpisah" |
| 24 Okt 2026 | Hash `07b8c19` diisi untuk Tahap 15 |
| 24 Okt 2026 | Tahap 16 ditambahkan dan selesai (T16.1–T16.8): penggabungan branch `feat/pisah-invoice-gabungan` ke `main` (tombol AI split on-demand di draf, proteksi serial Faktur Pajak `_is_tax_serial`, saran PPh 23 imbalan jasa dicocokkan PPN 11%/12%, pratinjau lokal file upload, label audit log, alembic Windows fix, 52/52 backend test lulus, frontend build lulus) |
| 24 Okt 2026 | Tahap 17 ditambahkan dan selesai (T17.1–T17.7): perbaikan multi-invoice DSS (filter Faktur Pajak & format uraian transaksi), deteksi total gambar dengan desimal `,-`, serta implementasi toggle & tombol cepat "Atur pajak secara otomatis" di Upload dan Editor Draf |
| 24 Okt 2026 | Tahap 18 ditambahkan dan selesai (T18.1–T18.5): DPP PPh 23 dari imbalan jasa yang dicocokkan dengan PPN, halaman awal invoice diperiksa per halaman. BRD/PRD/SOP perlu mencatat batasan DPP PPh 23 ini (T8.2–T8.4) |
