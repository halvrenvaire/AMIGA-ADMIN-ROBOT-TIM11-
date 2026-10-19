"""Tahap 3 feedback owner: draf, PIC mengedit per invoice, simulasi voucher, reviewer hanya menyetujui."""
import io
import re
from decimal import Decimal

from pypdf import PdfReader

from tests.test_documents import api, detail, extractor, invoice, make_pdf, send, tx  # noqa: F401
from tests.test_multi_invoice import second_invoice
from tests.test_review import edit_file

PIC = "pic.alpha@amiga.test"


def upload_draft(pdfs, **form):
    from tests.test_documents import client_id
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor",
            "channel": "Email", "submitted_date": "2026-10-19", **form}
    files = [("files", (f"inv{i}.pdf", pdf, "application/pdf")) for i, pdf in enumerate(pdfs, start=1)]
    return detail(api(PIC).post("/documents", data=data, files=files).json()["id"])


def test_ai_result_stops_at_draft_with_data_per_invoice(extractor):
    extractor.result = [invoice(), second_invoice()]
    doc = upload_draft([make_pdf(), make_pdf()])
    assert doc["status"] == "DRAFT" and doc["assigned_reviewer"] is None
    assert [f["data"]["invoice_no"] for f in doc["files"]] == ["INV-001", "INV-002"]
    assert doc["files"][1]["data"]["line_items"][0]["description"] == "Amplop"
    # PDF per invoice untuk layar edit
    one = api(PIC).get(f"/documents/{doc['id']}/files/2")
    assert one.status_code == 200 and one.content.startswith(b"%PDF-")


def test_editing_one_invoice_rebuilds_the_voucher_data(extractor):
    extractor.result = [invoice(), second_invoice()]
    doc = upload_draft([make_pdf(), make_pdf()])
    lines = doc["files"][1]["data"]["line_items"]
    lines.append({"description": "Ongkos kirim", "qty": "1", "unit_price": "25000", "subtotal": "25000"})
    r = edit_file(doc["id"], 2, line_items=lines, total="125000")
    assert r.status_code == 200 and r.json()["status"] == "DRAFT"
    ex = r.json()["extraction"]
    assert Decimal(ex["total"]) == Decimal(1025000)  # 900.000 + 125.000
    assert ex["line_items"][-1]["description"] == "[INV-002] Ongkos kirim"
    assert r.json()["files"][0]["data"]["total"] == "900000"  # invoice 1 tidak berubah


def test_blocking_issue_moves_to_exception_and_back_to_draft(extractor):
    extractor.result = [invoice(account_no=None)]
    doc = upload_draft([make_pdf()])
    assert doc["status"] == "EXCEPTION"
    r = api(PIC).post(f"/documents/{doc['id']}/submit")
    assert r.status_code == 409 and "MISSING_EVIDENCE" in r.json()["detail"]
    r = edit_file(doc["id"], account_no="1234567890")
    assert r.json()["status"] == "DRAFT" and r.json()["issues"] == []
    assert send(doc["id"]).json()["status"] == "READY_FOR_REVIEW"


def test_simulation_voucher_is_marked_and_has_attachments(extractor):
    extractor.result = [invoice(), second_invoice()]
    doc = upload_draft([make_pdf(), make_pdf()])
    r = api(PIC).get(f"/documents/{doc['id']}/voucher-preview")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages))
    assert "SIMULASI" in text and "VCH/" not in text
    assert "Lampiran 2: inv2.pdf" in text and "Rp 1.000.000" in text
    assert detail(doc["id"])["voucher"] is None  # simulasi tidak menerbitkan voucher


def test_only_submitters_can_edit_or_submit(extractor):
    doc = upload_draft([make_pdf()])
    assert api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/submit").status_code == 403
    assert api("pic.beta@amiga.test").post(f"/documents/{doc['id']}/submit").status_code == 403


def test_submitting_a_draft_counts_as_submitter_for_sod(extractor):
    # Yoga (Intake + Reviewer) yang mengirim draf PIC lain tidak boleh menjadi reviewernya
    for n in range(4):
        extractor.result = [invoice(invoice_no=f"INV-SOD-{n}")]
        doc = upload_draft([make_pdf()])
        sent = send(doc["id"], "multi@amiga.test").json()
        assert sent["status"] == "READY_FOR_REVIEW"
        assert "Yoga" not in (sent["assigned_reviewer"] or "")
