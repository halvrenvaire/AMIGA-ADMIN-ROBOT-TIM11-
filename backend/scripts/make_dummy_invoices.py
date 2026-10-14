"""Membuat invoice PDF dummy untuk skenario UAT (PRD bagian 8).

Jalankan dari folder backend/:  .venv/bin/python scripts/make_dummy_invoices.py
Hasil: ../samples/invoices/*.pdf. Semua data fiktif.
"""
from dataclasses import dataclass, field
from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(__file__).resolve().parents[2] / "samples" / "invoices"


@dataclass
class Invoice:
    filename: str
    vendor: str
    invoice_no: str
    date: str
    lines: list[tuple[str, int, int]]  # deskripsi, jumlah, harga satuan
    bank: str | None = "Bank Central Asia (BCA)"
    account_no: str | None = "1234567890"
    account_name: str | None = None
    # Total yang dicetak; None = jumlah semua subtotal
    printed_total: int | None = None
    notes: list[str] = field(default_factory=list)


def rupiah(n: int) -> str:
    return "Rp " + f"{n:,}".replace(",", ".")


def render(inv: Invoice) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, inv.vendor, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Jl. Gatot Subroto No. 12, Jakarta Selatan  |  (021) 555-0101", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in [("No. Invoice", inv.invoice_no), ("Tanggal", inv.date),
                         ("Kepada", "PT Klien Alpha")]:
        pdf.cell(35, 6, label)
        pdf.cell(0, 6, f": {value}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = (10, 80, 20, 40, 40)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 236, 245)
    for w, h in zip(widths, ("No", "Deskripsi", "Qty", "Harga Satuan", "Subtotal")):
        pdf.cell(w, 8, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    total = 0
    for i, (desc, qty, price) in enumerate(inv.lines, start=1):
        subtotal = qty * price
        total += subtotal
        for w, text, align in zip(widths, (str(i), desc, str(qty), rupiah(price), rupiah(subtotal)),
                                  ("C", "L", "C", "R", "R")):
            pdf.cell(w, 8, text, border=1, align=align)
        pdf.ln()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(sum(widths[:4]), 8, "TOTAL", border=1, align="R")
    pdf.cell(widths[4], 8, rupiah(inv.printed_total if inv.printed_total is not None else total),
             border=1, align="R")
    pdf.ln(14)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Pembayaran ditransfer ke:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in [("Bank", inv.bank), ("No. Rekening", inv.account_no),
                         ("Atas Nama", inv.account_name or inv.vendor)]:
        if value:
            pdf.cell(35, 6, label)
            pdf.cell(0, 6, f": {value}", new_x="LMARGIN", new_y="NEXT")
    for note in inv.notes:
        pdf.ln(2)
        pdf.multi_cell(0, 5, note)
    pdf.ln(12)
    pdf.cell(0, 6, "Hormat kami,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(14)
    pdf.cell(0, 6, f"Bagian Keuangan {inv.vendor}")
    return bytes(pdf.output())


INVOICES = [
    # UAT 1 & 2: lolos verifikasi, 3 baris barang
    Invoice("01_normal_3_baris.pdf", "PT Sumber Kertas Nusantara", "INV-SKN/2026/10/001", "01 Oktober 2026",
            [("Kertas HVS A4 80gsm (rim)", 20, 52_000), ("Tinta printer hitam", 4, 185_000),
             ("Map plastik bening (lusin)", 10, 24_000)]),
    # UAT 3: tanpa nomor rekening
    Invoice("02_tanpa_rekening.pdf", "CV Kreasi Media Digital", "KMD-0921", "03 Oktober 2026",
            [("Desain banner promosi", 1, 1_500_000), ("Cetak banner 3x1 m", 4, 275_000)],
            account_no=None),
    # UAT 4: nomor & vendor sama dengan 01, ditulis dengan format berbeda
    Invoice("03_duplikat_dari_01.pdf", "PT. SUMBER KERTAS NUSANTARA", "inv skn 2026 10 001", "01 Oktober 2026",
            [("Kertas HVS A4 80gsm (rim)", 20, 52_000), ("Tinta printer hitam", 4, 185_000),
             ("Map plastik bening (lusin)", 10, 24_000)]),
    # Aturan angka (test otomatis, bukan skenario UAT tersendiri): total tercetak salah
    Invoice("04_selisih_total.pdf", "PT Teknologi Jaringan Prima", "TJP/INV/2026/0477", "05 Oktober 2026",
            [("Switch 24 port", 2, 3_250_000), ("Kabel UTP Cat6 (box)", 3, 1_150_000),
             ("Jasa instalasi", 1, 2_000_000), ("Patch panel 24 port", 2, 650_000)],
            printed_total=13_500_000),
    # UAT 5 / UAT 7: invoice normal lain untuk alur persetujuan
    Invoice("05_normal_jasa.pdf", "PT Bersih Sejahtera Abadi", "BSA-2026-1088", "07 Oktober 2026",
            [("Jasa kebersihan kantor Oktober", 1, 8_500_000), ("Pembersihan karpet", 120, 15_000),
             ("Bahan pembersih", 1, 750_000)],
            bank="Bank Mandiri", account_no="1370012345678"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for inv in INVOICES:
        (OUT_DIR / inv.filename).write_bytes(render(inv))
        print(f"  {inv.filename}")
    print(f"Selesai: {len(INVOICES)} invoice di {OUT_DIR}")


if __name__ == "__main__":
    main()
