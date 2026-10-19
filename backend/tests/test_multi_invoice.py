"""Satu voucher dari beberapa invoice PDF (1–10 file per pengajuan)."""
from decimal import Decimal

from app.config import settings
from tests.test_documents import (  # noqa: F401
    submit_draft, api, client_id, codes, detail, extractor, invoice, make_pdf, tx,
)
from app.services.extraction_service import ExtractedLine, ExtractionError

PIC = "pic.alpha@amiga.test"


def upload_many(pdfs, **form):
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor", "channel": "Email",
            "submitted_date": "2026-10-15", **form}
    files = [("files", (f"inv{i}.pdf", pdf, "application/pdf")) for i, pdf in enumerate(pdfs, start=1)]
    r = api(PIC).post("/documents", data=data, files=files)
    submit_draft(r)
    return r


def second_invoice(**kw):
    return invoice(invoice_no="INV-002", line_items=[ExtractedLine("Amplop", Decimal(10), Decimal(10000), Decimal(100000))],
                   total=Decimal(100000), **kw)


def test_three_invoices_become_one_document(extractor):
    extractor.result = [invoice(), second_invoice(), invoice(invoice_no="INV-003")]
    r = upload_many([make_pdf(1), make_pdf(2), make_pdf(1)])
    assert r.status_code == 201
    doc = detail(r.json()["id"])
    assert extractor.calls == 3
    assert [(f["position"], f["original_filename"], f["page_count"]) for f in doc["files"]] == [
        (1, "inv1.pdf", 1), (2, "inv2.pdf", 2), (3, "inv3.pdf", 1)]
    assert doc["page_count"] == 4
    assert doc["status"] == "READY_FOR_REVIEW", doc["issues"]
    ex = doc["extraction"]
    assert ex["invoice_no"] == "INV-001, INV-002, INV-003"
    assert Decimal(ex["total"]) == Decimal(1900000)
    assert len(ex["line_items"]) == 7
    assert ex["line_items"][3]["description"] == "[INV-002] Amplop"
    # PDF gabungan untuk layar peninjauan
    pdf = api(PIC).get(f"/documents/{doc['id']}/file")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")


def test_file_count_limits(extractor):
    assert upload_many([]).status_code == 422
    r = upload_many([make_pdf()] * (settings.max_upload_files + 1))
    assert r.status_code == 422 and "maksimal 10" in r.json()["detail"]


def test_bad_file_in_batch_is_named(extractor):
    r = upload_many([make_pdf(), make_pdf(6)])
    assert r.status_code == 422
    assert r.json()["detail"].startswith("inv2.pdf: ") and "6 halaman" in r.json()["detail"]


def test_different_vendor_in_one_voucher_is_an_exception(extractor):
    extractor.result = [invoice(), second_invoice(vendor_name="CV Lain Sendiri", account_no="999")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert doc["status"] == "EXCEPTION"
    assert ("VENDOR_MISMATCH", "vendor_name") in codes(doc)


def test_same_invoice_twice_in_batch_is_flagged(extractor):
    extractor.result = [invoice(), invoice()]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert ("POSSIBLE_DUPLICATE", "invoice_no") in codes(doc)


def test_invoice_reused_from_earlier_batch_is_a_duplicate(extractor):
    extractor.result = [invoice(), second_invoice()]
    first = upload_many([make_pdf(), make_pdf()]).json()
    extractor.result = [second_invoice()]
    doc = detail(upload_many([make_pdf()]).json()["id"])
    assert ("POSSIBLE_DUPLICATE", "invoice_no") in codes(doc)
    assert any(first["request_id"] in i["message"] for i in doc["issues"])


def test_one_unreadable_invoice_fails_the_batch_with_its_name(extractor):
    extractor.result = [invoice(), ExtractionError("timeout")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert codes(doc) == [("EXTRACTION_FAILED", None)]
    # Progres per file untuk layar detail: file pertama sempat terbaca, file kedua tidak
    assert [bool(f["read_at"]) for f in doc["files"]] == [True, False]


def test_every_file_is_marked_read_after_processing(extractor):
    extractor.result = [invoice(), second_invoice()]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert all(f["read_at"] for f in doc["files"])


def not_invoice():
    return invoice(is_invoice=False, document_type="Surat lamaran", not_invoice_reason="Berisi lamaran kerja",
                   vendor_name=None, invoice_no=None, total=None, line_items=[])


def test_pdf_that_is_not_an_invoice_is_an_exception(extractor):
    extractor.result = not_invoice()
    doc = detail(upload_many([make_pdf()]).json()["id"])
    assert doc["status"] == "EXCEPTION"
    # Hanya kendala "bukan invoice", tanpa daftar data yang hilang
    assert codes(doc) == [("NOT_AN_INVOICE", None)]
    assert "inv1.pdf ditolak karena bukan dokumen tagihan (terbaca sebagai: Surat lamaran). Berisi lamaran kerja." \
        in doc["issues"][0]["message"]


def test_non_invoice_file_in_batch_is_named(extractor):
    extractor.result = [invoice(), not_invoice()]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert codes(doc) == [("NOT_AN_INVOICE", None)]
    assert "inv2.pdf" in doc["issues"][0]["message"] and "inv1.pdf" not in doc["issues"][0]["message"]
