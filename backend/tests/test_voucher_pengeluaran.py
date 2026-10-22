"""Tahap 1 feedback owner: kategori, Voucher Pengeluaran, nama "Diajukan oleh" bebas, rekening tidak dicetak."""
import io
import re

from pypdf import PdfReader

from tests.test_documents import api, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_reference import approve

PIC = "pic.alpha@amiga.test"


def pdf_text(content: bytes) -> str:
    return re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages))


def test_unknown_category_is_rejected(extractor):
    r = upload(request_type="Pembayaran vendor")
    assert r.status_code == 422 and "Voucher Pengeluaran Vendor" in r.json()["detail"]


def test_category_filters_documents_and_vouchers(extractor):
    vendor = upload().json()
    extractor.result = invoice(invoice_no="INV-REIMB")
    reimb = upload(request_type="Voucher Pengeluaran Reimburse").json()
    pic = api(PIC)
    ids = {d["id"] for d in pic.get("/documents", params={"request_type": "Voucher Pengeluaran Reimburse"}).json()}
    assert reimb["id"] in ids and vendor["id"] not in ids
    approve(detail(reimb["id"]))
    rows = pic.get("/vouchers", params={"request_type": "Voucher Pengeluaran Reimburse"}).json()
    assert [r["document_id"] for r in rows] == [reimb["id"]] and rows[0]["request_type"] == "Voucher Pengeluaran Reimburse"
    assert pic.get("/vouchers", params={"request_type": "Lainnya"}).json() == []


def test_submitter_name_can_be_another_employee(extractor):
    doc = detail(upload(submitter_name="Andi Wijaya", include_account="false").json()["id"])
    pengaju = doc["signers"][0]
    assert pengaju["kind"] == "PENGAJU" and pengaju["name"] == "Andi Wijaya"
    assert (pengaju["position"], pengaju["company"], pengaju["signature"]) == ("", "PT Klien Alpha", False)
    approve(doc)
    text = pdf_text(api(PIC).get(f"/documents/{doc['id']}/voucher").content)
    assert "Andi Wijaya" in text and "Rina (PIC Alpha)" not in text
    assert "VOUCHER PENGELUARAN" in text and "Rekening tujuan" not in text and "1234567890" not in text


def test_submitter_name_defaults_to_pic_and_can_be_changed_before_voucher(extractor):
    doc = detail(upload().json()["id"])
    assert doc["signers"][0]["name"] == "Rina (PIC Alpha)"
    pic = api(PIC)
    r = pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": [], "submitter_name": "Sinta Dewi"})
    assert r.status_code == 200 and r.json()["signers"][0]["name"] == "Sinta Dewi"
    # Kosong = kembali ke PIC pengaju
    r = pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": [], "submitter_name": ""})
    assert r.json()["signers"][0]["name"] == "Rina (PIC Alpha)"
