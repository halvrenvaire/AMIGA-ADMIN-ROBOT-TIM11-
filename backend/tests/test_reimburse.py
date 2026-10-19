"""Tahap 2 feedback owner: lampiran bukti di voucher dan Voucher Pengeluaran Reimburse."""
import io
from datetime import date
from decimal import Decimal

from pypdf import PdfReader

from app.services.extraction_service import RECEIPT, ExtractedLine
from tests.test_documents import api, codes, detail, extractor, invoice, make_pdf, tx  # noqa: F401
from tests.test_multi_invoice import upload_many
from tests.test_reference import approve

PIC = "pic.alpha@amiga.test"
REIMBURSE = "Voucher Pengeluaran Reimburse"


def bon_tol(i: int, **kw):
    """Bon tol: tanpa nomor invoice dan rekening, vendor berbeda-beda, berupa struk."""
    data = dict(vendor_name=f"Tol Ruas {i}", invoice_no=None, invoice_date=date(2026, 10, i), bank_name=None,
                account_no=None, account_name=None, doc_class=RECEIPT, document_type="Struk tol",
                line_items=[ExtractedLine("Tarif tol Gol I", Decimal(1), Decimal(27000), Decimal(27000))],
                total=Decimal(27000))
    data.update(kw)
    return invoice(**data)


def voucher_pdf(doc_id: str) -> PdfReader:
    return PdfReader(io.BytesIO(api(PIC).get(f"/documents/{doc_id}/voucher").content))


def pages_text(reader: PdfReader) -> str:
    return " ".join(p.extract_text() for p in reader.pages)


def test_reimburse_accepts_many_receipts_from_different_vendors(extractor):
    extractor.result = [bon_tol(i) for i in range(1, 7)]
    doc = detail(upload_many([make_pdf() for _ in range(6)], request_type=REIMBURSE).json()["id"])
    # Struk, beda vendor, tanpa nomor invoice dan rekening: semuanya sah untuk reimburse
    assert doc["status"] == "READY_FOR_REVIEW", codes(doc)
    assert doc["account_check"]["state"] == "NOT_APPLICABLE"
    approve(doc)  # tanpa konfirmasi rekening
    reader = voucher_pdf(doc["id"])
    text = pages_text(reader)
    # 6 bukti, 4 per halaman → 2 lembar lampiran setelah halaman voucher
    assert text.count("LAMPIRAN BUKTI") == 2 and "Lampiran 6: inv6.pdf" in text
    assert len(reader.pages) == 3


def test_reimburse_still_needs_date_and_total(extractor):
    extractor.result = [bon_tol(1, total=None, line_items=[]), bon_tol(2)]
    doc = detail(upload_many([make_pdf(), make_pdf()], request_type=REIMBURSE).json()["id"])
    assert doc["status"] == "EXCEPTION"
    assert ("MISSING_EVIDENCE", "total") in codes(doc)
    assert all(field not in ("invoice_no", "account_no", "bank_name") for _, field in codes(doc))


def test_vendor_voucher_keeps_vendor_rules(extractor):
    extractor.result = [invoice(), invoice(invoice_no="INV-002", vendor_name="CV Lain", account_no="999")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert ("VENDOR_MISMATCH", "vendor_name") in codes(doc)


def test_file_limits_per_category(extractor):
    assert upload_many([make_pdf()] * 11).status_code == 422
    r = upload_many([make_pdf()] * 21, request_type=REIMBURSE)
    assert r.status_code == 422 and "maksimal 20" in r.json()["detail"]
    extractor.result = [bon_tol(i % 28 + 1) for i in range(20)]
    assert upload_many([make_pdf()] * 20, request_type=REIMBURSE).status_code == 201


def test_vendor_voucher_attaches_each_invoice_on_its_own_page(extractor):
    extractor.result = [invoice(), invoice(invoice_no="INV-002")]
    doc = detail(upload_many([make_pdf(), make_pdf(2)]).json()["id"])
    approve(doc)
    reader = voucher_pdf(doc["id"])
    text = pages_text(reader)
    # 1 + 2 halaman bukti, masing-masing satu lembar
    assert text.count("LAMPIRAN BUKTI") == 3
    assert "Lampiran 1: inv1.pdf" in text and "Lampiran 2: inv2.pdf (hal. 2/2)" in text
