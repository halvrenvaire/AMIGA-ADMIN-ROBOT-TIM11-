"""Membuat invoice PDF dummy untuk menguji pengaturan PPN dan PPh per baris (Tahap 9).

Jalankan dari folder backend/:  .venv/bin/python scripts/make_tax_invoices.py
Hasil: ../samples/pajak/*.pdf. Semua data fiktif. Hasil yang diharapkan per file ada di
samples/pajak/README.md.
"""
from dataclasses import dataclass, field
from pathlib import Path

from fpdf import FPDF

from make_dummy_invoices import rupiah

OUT_DIR = Path(__file__).resolve().parents[2] / "samples" / "pajak"


@dataclass
class Invoice:
    filename: str
    vendor: str
    invoice_no: str
    date: str
    lines: list[tuple[str, int, int]]  # deskripsi, jumlah, harga satuan
    # Baris di bawah tabel (label, nilai), mis. ("PPN 11%", 275_000). Total = subtotal barang + baris ini.
    charges: list[tuple[str, int]] = field(default_factory=list)
    receipt: bool = False  # tampilan struk kasir (harga sudah termasuk PPN)
    bank: str | None = "Bank Central Asia (BCA)"
    account_no: str | None = "5550123456"
    notes: list[str] = field(default_factory=list)


def render(inv: Invoice) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, inv.vendor, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Jl. Raya Bekasi Km 18, Jakarta Timur  |  (021) 555-0199", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "STRUK PEMBELIAN" if inv.receipt else "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in [("No. Invoice" if not inv.receipt else "No. Struk", inv.invoice_no), ("Tanggal", inv.date),
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
    label_w = sum(widths[:4])
    if inv.charges:
        pdf.cell(label_w, 8, "SUBTOTAL", border=1, align="R")
        pdf.cell(widths[4], 8, rupiah(total), border=1, align="R")
        pdf.ln()
    for label, value in inv.charges:
        total += value
        pdf.cell(label_w, 8, label, border=1, align="R")
        pdf.cell(widths[4], 8, rupiah(value), border=1, align="R")
        pdf.ln()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(label_w, 8, "TOTAL", border=1, align="R")
    pdf.cell(widths[4], 8, rupiah(total), border=1, align="R")
    pdf.ln(14)

    pdf.set_font("Helvetica", "B", 10)
    if inv.bank:
        pdf.cell(0, 6, "Pembayaran ditransfer ke:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for label, value in [("Bank", inv.bank), ("No. Rekening", inv.account_no), ("Atas Nama", inv.vendor)]:
            if value:
                pdf.cell(35, 6, label)
                pdf.cell(0, 6, f": {value}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for note in inv.notes:
        pdf.ln(2)
        pdf.multi_cell(0, 5, note)
    pdf.ln(12)
    pdf.cell(0, 6, "Hormat kami,", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(14)
    pdf.cell(0, 6, f"Bagian Keuangan {inv.vendor}")
    return bytes(pdf.output())


INVOICES = [
    # Kasus utama: barang + jasa, PPN terpisah; PPh 23 hanya untuk jasa
    Invoice("06_barang_jasa_ppn.pdf", "PT Sejuk Selalu Teknik", "SST/INV/2026/10/118", "12 Oktober 2026",
            [("AC Split 1 PK", 2, 1_000_000), ("Jasa pemasangan AC", 1, 500_000)],
            charges=[("PPN 11%", 275_000)]),
    # Beberapa jenis PPh dalam satu invoice: PPh 23 (dua baris jasa), PPh 4 ayat 2 (sewa gudang), barang tanpa potongan
    Invoice("07_multi_jenis_pph.pdf", "PT Graha Logistik Mandiri", "GLM-INV-2026-0457", "13 Oktober 2026",
            [("Rak besi gudang", 4, 250_000), ("Jasa pemasangan rak", 1, 500_000),
             ("Jasa servis forklift", 1, 300_000), ("Sewa ruang gudang Oktober", 1, 2_000_000)],
            charges=[("PPN 11%", 418_000)]),
    # Struk ritel: harga sudah termasuk PPN, tidak ada baris PPN
    Invoice("08_struk_harga_termasuk_ppn.pdf", "CV Bersih Cemerlang", "STR-77120", "14 Oktober 2026",
            [("Jasa cuci karpet", 1, 555_000), ("Sabun karpet", 1, 111_000)], receipt=True, bank=None,
            notes=["Harga sudah termasuk PPN 11%."]),
    # Tarif PPN 12%: perlu memilih tarif 12% (dengan 11% muncul peringatan selisih)
    Invoice("09_ppn_12_persen.pdf", "PT Elektronik Prima Jaya", "EPJ/2026/X/0091", "15 Oktober 2026",
            [("Proyektor 4K", 1, 15_000_000)], charges=[("PPN 12%", 1_800_000)]),
    # PPN tertulis tidak sesuai tarif (seharusnya 275.000): peringatan, tidak memblokir
    Invoice("10_ppn_tidak_sesuai.pdf", "PT Sejuk Selalu Teknik", "SST/INV/2026/10/131", "16 Oktober 2026",
            [("AC Split 1 PK", 2, 1_000_000), ("Jasa pemasangan AC", 1, 500_000)],
            charges=[("PPN 11%", 300_000)]),
    # Sebagian baris tidak kena PPN (ongkos kirim): hilangkan centang "Kena PPN" pada baris itu
    Invoice("11_sebagian_tidak_kena_ppn.pdf", "PT Perabot Kantor Sentosa", "PKS-2026-1010", "17 Oktober 2026",
            [("Kursi kerja ergonomis", 4, 500_000), ("Ongkos kirim", 1, 100_000)],
            charges=[("PPN 11%", 220_000)]),
    # Baris pajak dengan nama yang tidak dikenali sistem: PIC menandainya sebagai "Baris PPN"
    Invoice("12_baris_pajak_tidak_dikenali.pdf", "PT Sinar Cetak Grafika", "SCG/1022/2026", "18 Oktober 2026",
            [("Cetak brosur A5 (1.000 lembar)", 2, 750_000)], charges=[("Pajak 11%", 165_000)]),
    # Vendor tanpa NPWP: tarif PPh 23 menjadi 4%
    Invoice("13_jasa_vendor_tanpa_npwp.pdf", "CV Solusi Pajak Mandiri", "SPM-2026-031", "19 Oktober 2026",
            [("Jasa konsultan pajak Oktober", 1, 900_000)], account_no="7770012345",
            notes=["Catatan: CV Solusi Pajak Mandiri belum memiliki NPWP."]),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for inv in INVOICES:
        (OUT_DIR / inv.filename).write_bytes(render(inv))
        print(f"  {inv.filename}")
    print(f"Selesai: {len(INVOICES)} invoice di {OUT_DIR}")


if __name__ == "__main__":
    main()
