"""Ekstraksi sungguhan dengan Amazon Nova (butuh kredensial AWS di .env).

Jalankan:  .venv/bin/python -m pytest -m integration tests/test_extraction_integration.py
"""
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.bedrock_client import BedrockClient
from app.services.extraction_service import InvoiceExtractor
from app.services.verification import normalize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_dummy_invoices import INVOICES, render  # noqa: E402

pytestmark = pytest.mark.integration

SAMPLES = {inv.filename: inv for inv in INVOICES}


@pytest.fixture(scope="module")
def extractor():
    return InvoiceExtractor(BedrockClient())


def test_normal_invoice_is_read_completely_within_15_seconds(extractor):
    inv = SAMPLES["01_normal_3_baris.pdf"]
    started = time.monotonic()
    result = extractor.extract(render(inv))
    assert time.monotonic() - started <= 15
    assert result.invoice_no == inv.invoice_no
    assert result.account_no == inv.account_no
    assert [line.subtotal for line in result.line_items] == [Decimal(q * p) for _, q, p in inv.lines]
    assert result.total == sum(Decimal(q * p) for _, q, p in inv.lines)


def test_missing_account_number_is_not_invented(extractor):
    result = extractor.extract(render(SAMPLES["02_tanpa_rekening.pdf"]))
    assert result.account_no is None


def test_duplicate_variant_normalizes_to_same_keys(extractor):
    a = extractor.extract(render(SAMPLES["01_normal_3_baris.pdf"]))
    b = extractor.extract(render(SAMPLES["03_duplikat_dari_01.pdf"]))
    assert normalize(a.invoice_no) == normalize(b.invoice_no)
    assert normalize(a.vendor_name) == normalize(b.vendor_name)


def _text_pdf(title: str, body: str) -> bytes:
    from fpdf import FPDF
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, body)
    return bytes(pdf.output())


NOT_INVOICES = {
    "surat lamaran": _text_pdf("Surat Lamaran Kerja", (
        "Kepada Yth. HRD PT Maju Jaya\nDengan hormat, saya Andi Pratama bermaksud melamar posisi Staf Keuangan. "
        "Saya lulusan S1 Akuntansi dengan pengalaman 3 tahun. Terlampir CV dan ijazah.\nHormat saya, Andi Pratama")),
    "purchase order": _text_pdf("PURCHASE ORDER No. PO-2026-118", (
        "Dari: PT Klien Alpha\nKepada: CV Sumber Kertas\nTanggal: 01-10-2026\n"
        "Mohon dikirimkan barang berikut:\n1. Kertas A4 80gsm - 20 rim\n2. Tinta printer hitam - 5 buah\n"
        "Pembayaran akan dilakukan setelah invoice diterima.\nDisetujui, Manajer Pengadaan")),
    "notulen rapat": _text_pdf("Notulen Rapat Bulanan", (
        "Tanggal: 3 Oktober 2026. Peserta: Tim Keuangan. Agenda: evaluasi anggaran Q3, rencana audit internal, "
        "dan jadwal tutup buku. Keputusan: audit internal dimulai 20 Oktober.")),
}


@pytest.mark.parametrize("kind", NOT_INVOICES)
def test_documents_that_are_not_invoices_are_rejected(extractor, kind):
    result = extractor.extract(NOT_INVOICES[kind])
    assert result.is_invoice is False, result.raw
    assert result.not_invoice_reason


@pytest.mark.parametrize("filename", SAMPLES)
def test_all_sample_invoices_are_recognised_as_invoices(extractor, filename):
    assert extractor.extract(render(SAMPLES[filename])).is_invoice is True


def test_subtotal_row_is_not_counted_twice(extractor):
    """Invoice tiket: baris "Subtotal Tiket" di bagian Ringkasan Biaya tidak boleh jadi item."""
    from fpdf import FPDF
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for text in ("No. Invoice: INV/2025/05/0187", "Tanggal: 18 Mei 2025", "", "Penjual",
                 "tiket.com (PT Global Tiket Network)", "Jl. Jend. Sudirman Kav. 52-53, Jakarta", "",
                 "Rincian Penerbangan", "Rute                         Maskapai     Harga (IDR)",
                 "Jakarta (CGK) - Bali (DPS)   Garuda       1.200.000",
                 "Bali (DPS) - Jakarta (CGK)   Garuda       1.200.000", "", "Ringkasan Biaya",
                 "Subtotal Tiket               2.400.000", "Biaya Layanan tiket.com      50.000",
                 "Tax (PPN 10%)                245.000", "Total Bayar                  2.695.000", "",
                 "Metode Pembayaran: Transfer Bank BCA", "No. Rekening: 123-456-7890",
                 "a.n. PT Global Tiket Network"):
        pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    result = extractor.extract(bytes(pdf.output()))
    assert result.total == Decimal(2695000)
    assert sum(line.subtotal for line in result.line_items) == Decimal(2695000)
    assert len(result.line_items) == 4
    assert "tiket.com" in (result.vendor_name or "").lower()


@pytest.mark.parametrize("kind,title,body", [
    ("struk kasir", "INDOGROSIR PADALARANG", "Struk belanja\nGULA PASIR 1KG   2 x 15.900   31.800\nMINYAK GORENG 2L   1 x 38.500   38.500\n"
     "TOTAL 70.300\nTUNAI 100.000\nKEMBALI 29.700\nKasir: 0123  Terima kasih telah berbelanja"),
    ("voucher", "AMIGA Robot Admin - Voucher Pembayaran Vendor", "VOUCHER VCH/2026/10/0001\nKlien: PT Klien Alpha\n"
     "Vendor: PT Sumber Kertas\nTOTAL DIBAYARKAN Rp 2.020.000\nDiajukan oleh / Disetujui oleh: Tanda tangan\n"
     "BATAS OTORISASI: Voucher ini bukan persetujuan pembayaran."),
])
def test_receipts_and_vouchers_are_not_invoices(extractor, kind, title, body):
    result = extractor.extract(_text_pdf(title, body))
    assert result.is_invoice is False, (kind, result.raw)
