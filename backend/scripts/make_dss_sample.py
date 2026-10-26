"""Membuat berkas tiruan kasus DSS: satu PDF berisi 6 invoice jasa driver (32 halaman).

Jalankan dari folder backend/:  .venv/bin/python scripts/make_dss_sample.py
Hasil: ../samples/dss_sintetis/invoice_dss_sintetis.pdf.

Struktur dan angka meniru berkas uji coba owner (invoice + rincian + Faktur Pajak + catatan e-Faktur, sebagian
dengan timesheet), tetapi SEMUA nama perusahaan, orang, kode driver, NPWP, dan rekening fiktif. Hasil yang diharapkan:
6 bukti di halaman 1, 5, 9, 13, 20, 26; PPh 23 2% dari imbalan jasa (Management Fee & Development); total dibayarkan
Rp 41.719.136.
"""
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parents[2] / "samples" / "dss_sintetis" / "invoice_dss_sintetis.pdf"

VENDOR = "PT Demo Solusi Sejati"
CUSTOMER = "PT Klien Alpha"

# (nomor invoice, driver, kode, jenis, jumlah halaman timesheet, ringkasan)
# ringkasan: basic, overtime, management fee, total amount, tidak kena PPN, kena PPN (DPP nilai lain), PPN, total
INVOICES = [
    ("005-PI-2604-00322", "Driver A", "DD00001", "Basic Fee (Fixed) and BPJS", 0,
     (6375633, 0, 2304696, 8680329, 6567691, 2112638, 253517, 8933846)),
    ("005-PI-2604-00323", "Driver B", "DD00002", "Basic Fee (Fixed) and BPJS", 0,
     (6375633, 0, 2304696, 8680329, 6567691, 2112638, 253517, 8933846)),
    ("005-PI-2604-00324", "Driver C", "DD00003", "Basic Fee (Fixed) and BPJS", 0,
     (6375633, 0, 2304696, 8680329, 6567691, 2112638, 253517, 8933846)),
    ("005-PI-2604-00325", "Driver A", "DD00001", "Overtime (Variable)", 3,
     (0, 6586980, 988047, 7575027, 6669317, 905710, 108685, 7683712)),
    ("005-PI-2604-00326", "Driver B", "DD00002", "Overtime (Variable)", 2,
     (0, 3727690, 559153, 4286843, 3774286, 512557, 61507, 4348350)),
    ("005-PI-2604-00327", "Driver C", "DD00003", "Overtime (Variable)", 3,
     (0, 2625493, 393824, 3019317, 2658312, 361005, 43321, 3062638)),
]


def num(value: int) -> str:
    return f"{value:,.2f}"  # format invoice asli: 8,933,846.00


def header(pdf: FPDF):
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(60, 12, "DEMO", new_x="RIGHT")
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(0, 4, f"{VENDOR}\nJl. Contoh Raya No. 1, Tangerang Selatan 15000\nContact Center: 021-000-0000",
                   align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def invoice_page(pdf: FPDF, no: str, driver: str, code: str, kind: str, s: tuple):
    basic, overtime, fee, amount, not_vat, vat_base, vat, total = s
    pdf.add_page()
    header(pdf)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "INVOICE", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    y = pdf.get_y()
    pdf.multi_cell(90, 5, f"Customer Code : C00001\n{CUSTOMER}\nJl. Contoh Sudirman Kav. 1, Jakarta Selatan\n"
                          "PIC : Rina (PIC Alpha)", new_x="RIGHT", new_y="TOP")
    pdf.set_xy(110, y)
    pdf.multi_cell(0, 5, f"Invoice No (No. Tagihan) : {no}\nInvoice Date (Tanggal Tagihan) : 9/4/2026\n"
                         "Due Date (Tanggal Jatuh Tempo) : 9/5/2026", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 6, "Detail As Attached", border=1, new_x="LMARGIN", new_y="NEXT")
    rows = [("Total Basic Fee", basic), ("Total Overtime", overtime), ("Total Management Fee & Development", fee),
            ("Total Amount", amount), ("Sub total (NOT subjected to VAT) / Sub Total (TIDAK terkena PPN)", not_vat),
            ("Sub total (subjected to VAT) / Sub Total (terkena PPN)", vat_base), ("VAT / PPN", vat),
            ("Stamp Duty / Biaya Meterai", 0)]
    for label, value in rows:
        pdf.cell(140, 5.5, label, border="L")
        pdf.cell(0, 5.5, num(value), border="R", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(140, 6, "Total Invoice / Total Tagihan", border="LTB")
    pdf.cell(0, 6, num(total), border="RTB", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(4)
    pdf.multi_cell(0, 5, f"Keterangan: {kind} - Driver Service {code} / {driver} periode 01/03/2026 - 31/03/2026")
    pdf.ln(3)
    pdf.multi_cell(0, 5, "Please transfer to (Pembayaran dapat ditransfer ke rekening):\n"
                         "Bank Contoh - Virtual Account  |  Beneficiary: PT Klien Alpha  |  Account No: 0000000000")
    pdf.ln(10)
    pdf.cell(0, 5, f"Hormat kami, {VENDOR}", align="R")


def detail_page(pdf: FPDF, no: str, driver: str, code: str, s: tuple):
    pdf.add_page()
    header(pdf)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, f"Lampiran rincian invoice {no}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    for i, (label, value) in enumerate([("Basic Fee & BPJS", s[0]), ("Overtime", s[1]),
                                         ("Management Fee & Development", s[2])], start=1):
        pdf.cell(10, 5, str(i), border=1)
        pdf.cell(40, 5, "005-DO2311-00000" + str(i), border=1)
        pdf.cell(90, 5, f"{code} / {driver} - {label}", border=1)
        pdf.cell(0, 5, num(value), border=1, align="R", new_x="LMARGIN", new_y="NEXT")


def faktur_page(pdf: FPDF, no: str, driver: str, code: str, s: tuple):
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Faktur Pajak", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.multi_cell(0, 4.6, f"Kode dan Nomor Seri Faktur Pajak: 0400000000000{no[-3:]}\n"
                           f"Pengusaha Kena Pajak: {VENDOR}, NPWP 0000000000000000\n"
                           f"Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak: {CUSTOMER}, NPWP 0000000000000001")
    pdf.ln(2)
    for i, (label, value) in enumerate([("Basic/Overtime Driver Service", s[0] + s[1]),
                                         ("Management Fee and Development Driver Service", s[2])], start=1):
        pdf.cell(10, 5, str(i), border=1)
        pdf.cell(130, 5, f"{label} {code} / {driver}", border=1)
        pdf.cell(0, 5, num(value).replace(",", "#").replace(".", ",").replace("#", "."), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")
    for label, value in [("Harga Jual / Penggantian", s[3]), ("Dasar Pengenaan Pajak", s[5]),
                         ("Jumlah PPN (Pajak Pertambahan Nilai)", s[6])]:
        pdf.cell(140, 5, label, border=1)
        pdf.cell(0, 5, num(value).replace(",", "#").replace(".", ",").replace("#", "."), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")


def note_page(pdf: FPDF):
    pdf.add_page()
    pdf.set_font("Helvetica", "", 7)
    pdf.multi_cell(0, 3.5, "Faktur Pajak ini telah ditandatangani secara elektronik sehingga tidak diperlukan tanda "
                           "tangan basah. (Halaman catatan e-Faktur)")


def timesheet_page(pdf: FPDF, driver: str, code: str, part: int):
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, f"Timesheet Mobile Data Absen - {code} / {driver} (bagian {part})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7.5)
    for day in range(1, 23):
        pdf.cell(25, 4.5, f"{day:02d}/03/2026", border=1)
        pdf.cell(25, 4.5, "07:00", border=1)
        pdf.cell(25, 4.5, "19:00", border=1)
        pdf.cell(0, 4.5, "Approved", border=1, new_x="LMARGIN", new_y="NEXT")


def build() -> Path:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    for no, driver, code, kind, sheets, s in INVOICES:
        invoice_page(pdf, no, driver, code, kind, s)
        detail_page(pdf, no, driver, code, s)
        faktur_page(pdf, no, driver, code, s)
        note_page(pdf)
        for part in range(1, sheets + 1):
            timesheet_page(pdf, driver, code, part)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"Selesai: {out}")
