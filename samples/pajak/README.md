# Sample invoice pajak (PPN & PPh per baris)

Invoice fiktif untuk menguji pengaturan pajak Tahap 9 (`docs/TASKS.md`). Dibuat ulang dengan:

```bash
cd backend && .venv/bin/python scripts/make_tax_invoices.py
```

Unggah satu file per pengajuan (kategori *Pembayaran vendor*), buka draf, lalu atur bagian **Pajak**.
Angka di bawah menganggap vendor punya NPWP, kecuali disebut lain.

| File | Kasus | Yang dilakukan PIC | Hasil yang diharapkan |
| --- | --- | --- | --- |
| `06_barang_jasa_ppn.pdf` | Barang + jasa, PPN terpisah | PPh **Berbeda per baris**: "Jasa pemasangan AC" → PPh 23 (saran sistem sudah terisi) | PPN Rp 275.000 tidak jadi dasar PPh. Potongan PPh 23 2% × 500.000 = **Rp 10.000**, dibayarkan **Rp 2.765.000**. Pembanding: mode satu jenis PPh 23 = Rp 50.000 (salah, barang ikut dipotong). |
| `07_multi_jenis_pph.pdf` | Tiga perlakuan dalam satu invoice | Mode per baris. Pilih baris 2 dan 3 (multi-select) → PPh 23, baris 4 → PPh 4 ayat 2. Coba juga **Minta rekomendasi AI untuk PPh per baris** | PPh 23 2% × 800.000 = Rp 16.000; PPh 4 ayat 2 10% × 2.000.000 = Rp 200.000. Dibayarkan **Rp 4.002.000**. Di voucher, tiap potongan tepat di bawah barang terakhir jenis itu. |
| `08_struk_harga_termasuk_ppn.pdf` | Struk, harga sudah termasuk PPN | Perlakuan PPN **Harga sudah termasuk PPN**; mode per baris, "Jasa cuci karpet" → PPh 23 | DPP jasa 555.000 × 100/111 = 500.000 → PPh 23 **Rp 10.000**. PPN tercakup Rp 66.000. Dibayarkan **Rp 656.000**. |
| `09_ppn_12_persen.pdf` | PPN 12% | Biarkan tarif 11% dulu, lalu ganti **Tarif PPN** ke 12% | Dengan 11% muncul peringatan selisih (invoice 1.800.000, sistem 1.650.000). Dengan 12% peringatan hilang. Dibayarkan Rp 16.800.000. |
| `10_ppn_tidak_sesuai.pdf` | PPN tertulis salah (300.000, seharusnya 275.000) | Tidak perlu apa-apa | Peringatan "PPN pada invoice berbeda dengan hitungan sistem". Tidak memblokir; voucher tetap memakai total invoice Rp 2.800.000. |
| `11_sebagian_tidak_kena_ppn.pdf` | Ongkos kirim tidak kena PPN | Buka **Atur PPN per baris**, hilangkan centang PPN di "Ongkos kirim" | Sebelum: peringatan (sistem menghitung 231.000). Sesudah: cocok 220.000. Voucher melebur PPN hanya ke kursi. |
| `12_baris_pajak_tidak_dikenali.pdf` | Baris "Pajak 11%" tidak dikenali sebagai PPN | Klik **Tandai sebagai baris PPN** di baris itu | Baris pajak keluar dari DPP: DPP 1.500.000, PPN 165.000. |
| `13_jasa_vendor_tanpa_npwp.pdf` | Vendor tanpa NPWP | Mode satu jenis: PPh 23, NPWP **Tidak punya NPWP** | Tarif 4%: potongan **Rp 36.000**, dibayarkan **Rp 864.000**. |

Centang **Tampilkan rincian PPN pada voucher** (bawaan: tidak dicentang) untuk mencetak barang senilai DPP
dan PPN sebagai baris sendiri. Tanpa centang, PPN sudah termasuk dalam nilai tiap barang dan total.
