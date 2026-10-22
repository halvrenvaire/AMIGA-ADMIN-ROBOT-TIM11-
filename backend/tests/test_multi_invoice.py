"""Satu voucher dari beberapa invoice PDF (1–10 file per pengajuan)."""
from decimal import Decimal

from app.config import settings
from tests.test_documents import (  # noqa: F401
    submit_draft, api, client_id, codes, detail, extractor, invoice, make_pdf, send, tx, upload,
)
from app.services.extraction_service import ExtractedLine, ExtractionError
from tests.test_classification import verified_vendor
from tests.test_reference import add_vendor
from tests.test_review import NAMES, audit, edit_file

PIC = "pic.alpha@amiga.test"


def upload_many(pdfs, submit=True, **form):
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor", "channel": "Email",
            "submitted_date": "2026-10-15", "extraction_mode": "ITEMIZED", "include_account": "true", **form}
    files = [("files", (f"inv{i}.pdf", pdf, "application/pdf")) for i, pdf in enumerate(pdfs, start=1)]
    r = api(PIC).post("/documents", data=data, files=files)
    if submit:
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
    r = upload_many([make_pdf(), b"%PDF-1.4 rusak"])
    assert r.status_code == 422
    assert r.json()["detail"].startswith("inv2.pdf: ") and "rusak" in r.json()["detail"]


def test_different_vendor_is_a_soft_warning(extractor):
    extractor.result = [invoice(), second_invoice(vendor_name="CV Lain Sendiri", account_no="999")]
    doc = detail(upload_many([make_pdf(), make_pdf()], submit=False).json()["id"])
    # Tahap 14: hanya pengingat; tetap Draf dan konfirmasi PIC tidak wajib (tetap bisa dicatat beserta alasan)
    assert doc["status"] == "DRAFT"
    assert ("VENDOR_MISMATCH", "vendor_name") in codes(doc)

    ack = lambda reason, code="VENDOR_MISMATCH", email=PIC: api(email).post(  # noqa: E731
        f"/documents/{doc['id']}/acknowledge", json={"code": code, "reason": reason})
    assert ack("ok").status_code == 422  # alasan wajib
    assert ack("Dua vendor satu proyek", code="CALCULATION_DISCREPANCY").status_code == 422
    assert ack("Dua vendor satu proyek", email="reviewer1@amiga.test").status_code == 403
    r = ack("Dua vendor dalam satu proyek renovasi")
    assert r.status_code == 200
    assert "VENDOR_MISMATCH" not in {c for c, _ in codes(r.json())}
    assert r.json()["acknowledgements"]["VENDOR_MISMATCH"]["reason"] == "Dua vendor dalam satu proyek renovasi"

    # Reviewer melihat pembayaran per rekening
    payees = r.json()["payees"]
    assert [(p["vendor_name"], p["account_no"], p["invoices"], Decimal(p["net"])) for p in payees] == [
        ("PT Vendor Jaya", "1234567890", [1], Decimal(900000)), ("CV Lain Sendiri", "999", [2], Decimal(100000))]
    assert {p["state"] for p in payees} == {"UNVERIFIED"}
    sent = send(doc["id"])
    assert sent.status_code == 200 and sent.json()["status"] == "READY_FOR_REVIEW"
    reviewer = api(NAMES[sent.json()["assigned_reviewer"]])
    assert reviewer.post(f"/documents/{doc['id']}/approve", json={}).status_code == 422
    assert reviewer.post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).status_code == 200
    log = audit(doc["id"], "ACCOUNT_CONFIRMED_BY_REVIEWER")[-1]
    assert log.new_value == "1234567890, 999"
    assert audit(doc["id"], "WARNING_ACKNOWLEDGED")[-1].note == "Dua vendor dalam satu proyek renovasi"


def test_unconfirmed_vendor_warning_does_not_block_submit_or_approve(extractor):
    extractor.result = [invoice(), second_invoice(vendor_name="CV Lain Sendiri", account_no="999")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert doc["status"] == "READY_FOR_REVIEW" and ("VENDOR_MISMATCH", "vendor_name") in codes(doc)
    reviewer = api(NAMES[doc["assigned_reviewer"]])
    r = reviewer.post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    assert r.status_code == 200 and r.json()["status"] == "AMIGA_REVIEWED"


def test_confirmation_is_void_when_vendors_change(extractor):
    extractor.result = [invoice(), second_invoice(vendor_name="CV Lain Sendiri", account_no="999")]
    doc_id = upload_many([make_pdf(), make_pdf()], submit=False).json()["id"]
    api(PIC).post(f"/documents/{doc_id}/acknowledge", json={"code": "VENDOR_MISMATCH", "reason": "Satu proyek"})
    r = edit_file(doc_id, position=2, vendor_name="CV Vendor Ketiga")
    assert ("VENDOR_MISMATCH", "vendor_name") in codes(r.json())
    assert r.json()["acknowledgements"] == {}


def test_account_is_checked_per_invoice(extractor):
    verified_vendor()  # PT Vendor Jaya, rekening 1234567890 terverifikasi
    extractor.result = [second_invoice(vendor_name="CV Lain Sendiri", account_no="999"),
                        invoice(invoice_no="INV-003", account_no="5555")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    # Rekening invoice kedua berbeda dengan rekening terverifikasi PT Vendor Jaya, walau invoice pertama vendor lain.
    # Tahap 14: peringatan untuk reviewer, bukan kendala yang menahan draf
    assert ("ACCOUNT_MISMATCH", "account_no") in codes(doc)
    assert doc["status"] == "READY_FOR_REVIEW"
    states = {p["vendor_name"]: p["state"] for p in doc["payees"]}
    assert states == {"CV Lain Sendiri": "UNVERIFIED", "PT Vendor Jaya": "MISMATCH"}


def test_same_vendor_invoices_share_one_payee_row(extractor):
    extractor.result = [invoice(), second_invoice()]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert [(p["invoices"], Decimal(p["gross"])) for p in doc["payees"]] == [([1, 2], Decimal(1000000))]


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


def test_one_unreadable_invoice_is_filled_manually_and_retried_alone(extractor):
    extractor.result = [invoice(), ExtractionError("timeout")]
    doc = detail(upload_many([make_pdf(), make_pdf()]).json()["id"])
    assert doc["status"] == "DRAFT"
    assert doc["ai_manual"]["files"] == ["inv2.pdf"] and "1 dari 2 invoice (inv2.pdf)" in doc["ai_manual"]["message"]
    assert doc["files"][0]["data"]["vendor_name"] == "PT Vendor Jaya"
    assert doc["files"][1]["data"]["vendor_name"] is None and doc["files"][1]["data"]["manual"] is True
    api(PIC).put(f"/documents/{doc['id']}/files/1/tax", json={"code": "NONE"})

    # Baca ulang hanya invoice yang gagal; data dan pilihan pajak invoice pertama tetap
    extractor.result = [second_invoice()]
    assert api(PIC).post(f"/documents/{doc['id']}/reprocess").status_code == 200
    again = detail(doc["id"])
    assert extractor.calls == 3
    assert again["ai_manual"] is None
    assert again["files"][0]["data"]["tax"]["code"] == "NONE"
    assert again["files"][1]["data"]["invoice_no"] == "INV-002"


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


def test_pic_registers_vendor_from_draft_and_reviewer_verifies_it(extractor):
    doc_id = upload(submit=False).json()["id"]
    assert detail(doc_id)["payees"][0]["vendor_id"] is None
    # Pendaftaran hanya pencatatan: draf tetap bisa dikirim walau rekening belum diverifikasi
    vendor = add_vendor(account_name="PT Vendor Jaya").json()
    payee = detail(doc_id)["payees"][0]
    assert payee["vendor_id"] == vendor["id"] and payee["state"] == "UNVERIFIED" and not payee["vendor_verified"]
    sent = send(doc_id)
    assert sent.status_code == 200
    reviewer = api(NAMES[sent.json()["assigned_reviewer"]])
    assert reviewer.post(f"/vendors/{vendor['id']}/verify").status_code == 200
    assert detail(doc_id)["payees"][0]["state"] == "VERIFIED"
    # Rekening sudah terverifikasi: persetujuan tidak lagi memerlukan konfirmasi manual
    assert reviewer.post(f"/documents/{doc_id}/approve", json={}).status_code == 200
