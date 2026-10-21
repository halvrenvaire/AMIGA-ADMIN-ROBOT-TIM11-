# Tracking Tugas — Feedback Owner AMIGA

Sumber: **Ringkasan Pemahaman Feedback Owner AMIGA** (18 Okt 2026, 12 masukan owner), ditambah feedback owner setelahnya.
Dokumen acuan lain: [BRD v2.0](../readme/BRD_AMIGA_Robot_Admin_v2.0.pdf) · [PRD v3](../readme/PRD_AMIGA_Robot_Admin_v3.pdf) · [BPMN v2](../readme/AMIGA_Robot_Admin_Invoice_to_Voucher_v2.png)

**Cara pakai**

- `[x]` selesai · `[ ]` belum · 🔄 sedang dikerjakan · ❓ menunggu jawaban owner/tim
- Setiap tugas punya ID (mis. `T3.2`). Sebut ID-nya saat minta update, misalnya "T6.1 sudah selesai".
- Saat tugas selesai: centang, isi kolom commit, perbarui ringkasan progres, lalu commit dan push.
- Nomor `#1`–`#12` merujuk ke nomor masukan owner di dokumen ringkasan.

_Terakhir diperbarui: 21 Okt 2026_

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
| 8 | Dokumen & rilis (BRD, PRD, BPMN, buku panduan, deploy) | Sedang | 1/6 | ⏳ |
| 9 | Feedback owner 20 Okt (PPN per invoice, PPh per baris, navigasi cepat layar tinjau) | Besar | 8/8 | ✅ |
| 10 | Mengurangi ketergantungan AI: isi manual, subtotal otomatis, beberapa vendor per voucher, pintasan rekening vendor | Besar | 6/6 | ✅ |
| 11 | Format voucher mengikuti contoh owner (No. 1702 & 1944): kop data, kolom tabel, satu baris per invoice, kotak Diketahui oleh | Besar | 0/9 | ⏳ (4 perlu konfirmasi) |
| 12 | Berkas invoice banyak halaman (invoice + Faktur Pajak + timesheet) | Kecil | 2/2 | ✅ |

---

## Tahap 1 — Istilah & kategori (spesifikasi 2.A, 2.E, 2.F)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T1.1 | Menu "Unggah Dokumen" diganti "Pembuatan Voucher" | #1 | [x] | `2644eb8` |
| T1.2 | Judul PDF menjadi "Voucher Pengeluaran" | #10 | [x] | `2644eb8` |
| T1.3 | "Jenis permintaan" menjadi kategori (Vendor / Reimburse / Lainnya), divalidasi server, data lama dimigrasi | #10 | [x] | `2644eb8` |
| T1.4 | Daftar kategori **bisa ditambah admin** (sekarang masih tetap di kode: `REQUEST_CATEGORIES`) | #10 | [ ] | — |
| T1.5 | Kategori jadi filter di Dashboard Antrean, Voucher, dan Pengajuan Saya; tidak dicetak di PDF | #10 | [x] | `2644eb8` |
| T1.6 | Rekening tujuan tidak dicetak di voucher; cek rekening palsu tetap jalan di sistem | #6 | [x] | `2644eb8` |
| T1.7 | Nama "Diajukan oleh" diketik bebas (default nama PIC); spesimen PIC tidak dicetak bila nama lain | #8 | [x] | `2644eb8` |
| T1.8 | Telegram: pilihan perusahaan juga muncul saat kirim foto; kategori lewat tombol | #5 | [x] | `2644eb8` |

## Tahap 2 — Lampiran & reimburse (spesifikasi 2.B, 2.E)

| ID | Tugas | Masukan | Status | Commit |
| --- | --- | --- | --- | --- |
| T2.1 | Halaman 2 dst. voucher berisi lampiran semua bukti (vektor, berlabel) | #7 | [x] | `18cfe86` |
| T2.2 | Beberapa bon digabung satu halaman (reimburse 4 per halaman, lainnya 1 per halaman) | #7 | [x] | `18cfe86` |
| T2.3 | Reimburse sampai 20 bukti; kategori lain tetap maks. 10 | #11 | [x] | `18cfe86` |
| T2.4 | Reimburse: struk/nota sah, boleh banyak vendor (aturan satu vendor/rekening tidak berlaku) | #11 | [x] | `18cfe86` |
| T2.5 | Reimburse: wajib hanya tanggal dan total; rekening vendor tidak dicek (dibayar ke karyawan) | #11 | [x] | `18cfe86` |
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
| T8.3 | Perbarui PRD (v3.1): FR baru Tahap 1–6, 9, dan 10 (isi manual saat AI bermasalah, VENDOR_MISMATCH jadi peringatan, cek rekening per invoice); FR-5.2 (teks batas otorisasi) dicabut owner; batas 5 halaman per file dihapus (T12.1) | [ ] | |
| T8.4 | Perbarui SOP (`docs/sop.md`) untuk alur draf dan pajak (termasuk PPN dan PPh per baris, Tahap 9), isi manual saat AI bermasalah, dan konfirmasi beberapa vendor (Tahap 10), lalu jalankan `POST /reindex` | [ ] | Asisten AI menjawab dari SOP |
| T8.5 | Deploy ulang ke EC2 (`git pull` lalu skrip deploy) | [ ] | Skrip deploy disimpan lokal (diabaikan git) |
| T8.6 | Buku panduan pengguna PDF v3.0 (15 bab, 28 gambar dari aplikasi terbaru, mencakup Tahap 1–10 dan 12) | [x] | [`readme/Buku_Panduan_AMIGA_Robot_Admin_v3.0.pdf`](../readme/Buku_Panduan_AMIGA_Robot_Admin_v3.0.pdf); Bab 8 (voucher) perlu diperbarui setelah Tahap 11 |

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
| T10.4 | Rekening dicek per invoice: setiap rekening dicocokkan dengan vendornya masing-masing (`ACCOUNT_MISMATCH` tetap menghalangi). Reviewer melihat "Pembayaran per rekening" (vendor, rekening, nilai dibayarkan, status), dan konfirmasi rekening saat menyetujui mencakup semua rekening yang belum terverifikasi | [x] | `707aef1` |
| T10.5 | Pintasan rekening vendor dari layar dokumen: PIC "Daftarkan rekening vendor" / "Perbarui rekening vendor" (diisi dari invoice; hanya pencatatan, pengajuan tetap berjalan), Finance Reviewer "Verifikasi rekening vendor ini" (SoD tetap berlaku). Formulir vendor dipindah ke `components/VendorForm.tsx`; `GET /vendors/{id}` ditambahkan | [x] | `707aef1` |
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
| T11.4 | Satu baris per invoice (keterangan ringkas yang bisa diedit PIC, nilai = total invoice termasuk PPN), bukan per barang | ❓ | — |
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
