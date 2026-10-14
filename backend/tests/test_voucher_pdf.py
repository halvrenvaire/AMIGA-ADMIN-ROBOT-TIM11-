"""Tata letak voucher PDF: uraian panjang dibungkus, tidak dipotong dan tidak meluber ke kolom lain."""
import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as N

from pypdf import PdfReader

from app.services.voucher_service import render_voucher

LONG = ("Brownies Besar Uk. 20x20 Pengiriman tanggal 25 September 2025 ke kantor pusat "
        "Jl. Gatot Subroto No. 12, lantai 3 (bagian keuangan)")


def _render(lines):
    ex = N(vendor_name="Blue 'n Bake", invoice_no="INV/2026/0030", invoice_date=date(2026, 10, 1),
           total=sum((li.subtotal for li in lines), Decimal(0)), bank_name="BCA", account_no="7770857591",
           account_name="Feranny", line_items=lines)
    doc = N(extraction=ex, client=N(name="PT Klien Alpha"), request_id="REQ-20261014-E321B5")
    return PdfReader(io.BytesIO(render_voucher(doc, "VCH/2026/10/0002", N(full_name="Dewi"), datetime.now(timezone.utc))))


def _line(n, desc="Barang"):
    return N(position=n, description=desc, qty=Decimal(2), unit_price=Decimal(95000), subtotal=Decimal(190000))


def test_long_description_is_wrapped_not_truncated():
    reader = _render([_line(1, LONG), _line(2, "Ongkir")])
    text = re.sub(r"\s+", " ", reader.pages[0].extract_text())
    # Seluruh uraian ada (dulu dipotong 60 karakter, dan sisanya menimpa kolom Qty)
    assert "lantai 3 (bagian keuangan)" in text
    assert "Rp 380.000" in text


def test_many_lines_continue_on_next_page_with_total():
    reader = _render([_line(n, LONG) for n in range(1, 31)])
    assert len(reader.pages) >= 2
    last = reader.pages[-1].extract_text()
    assert "TOTAL DIBAYARKAN" in last and "BATAS OTORISASI" in last
    assert "Uraian" in last  # header tabel diulang di halaman lanjutan


def test_signature_blocks_for_amiga_and_optional_client():
    reader = _render([_line(1, "Ongkir")])
    text = re.sub(r"\s+", " ", reader.pages[0].extract_text())
    assert "Disetujui oleh AMIGA" in text and "Finance Reviewer AMIGA" in text and "Dewi" in text
    assert "Persetujuan Klien (opsional)" in text and "Jabatan: Client Approver" in text


def test_signature_blocks_stay_together_on_last_page():
    reader = _render([_line(n, LONG) for n in range(1, 31)])
    last = re.sub(r"\s+", " ", reader.pages[-1].extract_text())
    assert "Disetujui oleh AMIGA" in last and "Persetujuan Klien (opsional)" in last
    assert "Tanggal:" in last
