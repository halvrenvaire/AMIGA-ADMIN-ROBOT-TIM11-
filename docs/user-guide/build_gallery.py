"""Dokumentasi visual AMIGA Robot Admin: folder gambar per kategori + PDF galeri.

Jalankan dari folder induk repo:
    backend/.venv/bin/python docs/user-guide/build_gallery.py

Hasil:
- readme/Galeri_Dokumentasi_AMIGA_Robot_Admin.pdf (di-commit)
- readme/Dokumentasi_Visual_AMIGA_Robot_Admin/ (folder siap unggah ke Google Drive; tidak di-commit karena isinya
  salinan docs/user-guide/img/)
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_user_guide import IMG, LOGO, MUTED, DARK, PRIMARY, LIGHT, ROOT, Guide  # noqa: E402
from fpdf.enums import XPos, YPos  # noqa: E402

OUT_PDF = ROOT / "readme" / "Galeri_Dokumentasi_AMIGA_Robot_Admin.pdf"
OUT_DIR = ROOT / "readme" / "Dokumentasi_Visual_AMIGA_Robot_Admin"

# (folder, judul bagian, [(file sumber, nama file hasil, keterangan)])
GALLERY = [
    ("01_Alur_Kerja", "Alur kerja sistem", [
        ("00-alur-kerja.jpg", "01_alur_kerja_invoice_ke_voucher.jpg",
         "Alur kerja: PIC Klien mengunggah, AI membaca, sistem memverifikasi dan menyarankan pajak, PIC memeriksa draf, "
         "Finance Reviewer menyetujui, voucher resmi terbit."),
    ]),
    ("02_Antarmuka_Utama", "Antarmuka utama", [
        ("01-login.jpg", "01_login.jpg", "Halaman login."),
        ("02-dashboard-pic.jpg", "02_dashboard_pic_klien.jpg", "Dashboard PIC Klien: dokumen per status, invoice masuk, voucher terbit, nilai pembayaran."),
        ("03-unggah-atas.jpg", "03_pembuatan_voucher.jpg", "Pembuatan voucher: klien, kategori, tanggal, Diajukan oleh."),
        ("04-unggah-mode.jpg", "04_mode_baca_ai.jpg", "Pilihan mode baca AI (Total saja / Rincian) dan fitur tambahan."),
        ("06-tutorial.jpg", "05_tutorial_tombol_tanya.jpg", "Tutorial di dalam aplikasi (tombol ?): bagian yang dijelaskan disorot langkah demi langkah."),
        ("07-draf-atas.jpg", "06_halaman_draf.jpg", "Halaman draf: bukti asli di kiri, data hasil AI dan navigasi cepat di kanan."),
        ("13-pengajuan.jpg", "07_pengajuan_saya.jpg", "Pengajuan Saya: semua pengajuan beserta statusnya."),
        ("40-peninjauan.jpg", "08_peninjauan_reviewer.jpg", "Peninjauan Saya (Finance Reviewer)."),
        ("20-antrean.jpg", "09_dashboard_antrean.jpg", "Dashboard Antrean (Service Lead): semua dokumen dan beban reviewer."),
        ("21-dashboard-lead.jpg", "10_dashboard_service_lead.jpg", "Dashboard Service Lead: kinerja dan estimasi biaya AI."),
        ("17-vendor.jpg", "11_data_vendor.jpg", "Data referensi vendor (NPWP dan rekening terverifikasi)."),
        ("14-tarif.jpg", "12_tarif_pajak.jpg", "Tabel tarif pajak PPh dengan dan tanpa NPWP."),
        ("15-akun.jpg", "13_pengaturan_akun.jpg", "Pengaturan akun: profil, tanda tangan, hubungkan Telegram."),
        ("23-admin-pengguna.jpg", "14_admin_pengguna.jpg", "System Admin: pengguna dan peran."),
    ]),
    ("03_Proses_AI", "Proses interaksi AI", [
        ("a1-unggah-file-dipilih.jpg", "01_unggah_invoice.jpg", "PIC memilih file invoice lalu menyimpan draf."),
        ("a2-ai-sedang-membaca.jpg", "02_ai_sedang_membaca.jpg", "AMIGA AI Engine (Amazon Nova Lite) sedang membaca invoice: diterima, dibaca AI, verifikasi."),
        ("a3-ai-hasil-baca.jpg", "03_hasil_baca_ai.jpg", "Hasil baca AI: lolos semua pemeriksaan, waktu baca, vendor terdaftar."),
        ("a4-ai-saran-pajak.jpg", "04_saran_pajak_ai.jpg", "Saran pajak AI: PPh 23 untuk jasa oleh badan usaha, tarif menyesuaikan NPWP vendor."),
        ("08-draf-bukti.jpg", "05_ai_memisah_banyak_invoice.jpg", "AI memisahkan satu PDF DSS 32 halaman menjadi 6 bukti invoice (invoice + Faktur Pajak + timesheet)."),
        ("09-draf-pajak.jpg", "06_ppn_tercetak_dss.jpg", "PPN tercetak di invoice DSS dipakai apa adanya (harga sudah termasuk PPN)."),
        ("10-draf-pajak-saran.jpg", "07_dpp_pph23_imbalan_jasa.jpg", "DPP PPh 23 = imbalan jasa (Management Fee Rp 2.304.696), bukan total invoice; dicocokkan dengan PPN."),
        ("c1-deteksi-duplikat.jpg", "08_deteksi_duplikat.jpg", "Sistem mendeteksi invoice yang pernah diajukan (POSSIBLE_DUPLICATE)."),
        ("b1-asisten-sop.jpg", "09_asisten_ai_jawab_sop.jpg", "Asisten AI (RAG) menjawab pertanyaan SOP tentang DPP PPh 23, dengan kutipan SOP."),
        ("b2-asisten-data.jpg", "10_asisten_ai_jawab_data.jpg", "Asisten AI menjawab pertanyaan data: daftar pengajuan milik pengguna."),
    ]),
    ("04_Hasil_Keluaran", "Hasil keluaran", [
        ("a5-pratinjau-voucher.jpg", "01_pratinjau_voucher.jpg", "Pratinjau voucher di halaman draf, diperbarui setiap data atau pajak disimpan."),
        ("50-simulasi.jpg", "02_simulasi_voucher_dss.jpg", "Simulasi voucher berkas DSS: 6 invoice, baris potongan PPh 23, total dibayarkan Rp 41.719.136."),
        ("42-review-keputusan.jpg", "03_ringkasan_potongan_reviewer.jpg", "Ringkasan potongan pajak dan tombol keputusan Finance Reviewer."),
        ("d1-disetujui.jpg", "04_dokumen_disetujui.jpg", "Dokumen disetujui Finance Reviewer; voucher resmi terbit."),
        ("51-voucher-resmi.jpg", "05_voucher_resmi_VCH-2026-10-0006.jpg", "Voucher Pengeluaran resmi VCH/2026/10/0006, sama dengan voucher bayar owner (Rp 41.719.136)."),
        ("d3-daftar-voucher.jpg", "06_daftar_voucher.jpg", "Daftar voucher yang sudah terbit."),
        ("22-rekap.jpg", "07_rekap_voucher.jpg", "Rekap voucher per periode (laporan PDF)."),
        ("d4-jejak-audit.jpg", "08_jejak_audit_dokumen.jpg", "Jejak audit satu dokumen: unggah, baca AI, perubahan, pengajuan, keputusan."),
    ]),
    ("05_Tampilan_HP", "Tampilan HP", [
        ("30-hp-daftar.jpg", "01_hp_pengajuan.jpg", "Pengajuan Saya di HP."),
        ("31-hp-laci.jpg", "02_hp_menu_laci.jpg", "Menu laci dan pencarian di HP."),
    ]),
]


def build():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    pdf = Guide()
    pdf.set_title("Galeri Dokumentasi AMIGA Robot Admin")
    pdf.header_text = "AMIGA Robot Admin · Galeri Dokumentasi Visual"
    # Sampul
    pdf.add_page()
    pdf.set_fill_color(*LIGHT)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, pdf.w, 8, style="F")
    if LOGO.exists():
        pdf.image(str(LOGO), x=pdf.l_margin, y=36, h=18)
    pdf.set_y(70)
    pdf.set_font("body", "B", 12)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 8, "DOKUMENTASI VISUAL PROYEK AKHIR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("body", "B", 30)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(0, 14, "AMIGA Robot Admin")
    pdf.set_font("body", "", 13)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 7, "Galeri antarmuka, alur kerja, proses AI, dan hasil keluaran\nMAIN Hackathon 2026 · Kelompok 11")
    pdf.ln(8)
    pdf.set_font("body", "", 10.5)
    pdf.set_text_color(*DARK)
    for folder, title, items in GALLERY:
        pdf.cell(0, 7, f"{folder.replace('_', ' ')}  ·  {len(items)} gambar", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("body", "I", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, "Login: http://13.212.201.121/login · Bot Telegram: @amiga_online_ro_bot\n"
                         "Screenshot diambil dari aplikasi yang berjalan dengan AI sungguhan (Amazon Bedrock). "
                         "Contoh DSS memakai berkas sintetis (nama, NPWP, dan rekening fiktif) dengan angka yang sama.")
    for folder, title, items in GALLERY:
        target = OUT_DIR / folder
        target.mkdir(parents=True, exist_ok=True)
        pdf.chapter(title)
        for src, name, caption in items:
            shutil.copy(IMG / src, target / name)
            pdf.figure(src, f"{caption} ({folder}/{name})")
    pdf.output(str(OUT_PDF))
    shutil.copy(OUT_PDF, OUT_DIR / OUT_PDF.name)
    count = sum(len(items) for _, _, items in GALLERY)
    print(f"Selesai: {OUT_PDF.relative_to(ROOT)} ({pdf.pages_count} halaman) dan {OUT_DIR.relative_to(ROOT)}/ ({count} gambar)")


if __name__ == "__main__":
    build()
