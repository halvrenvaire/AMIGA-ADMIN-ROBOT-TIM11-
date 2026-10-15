"""Klasifikasi dokumen AI (invoice / struk / tidak relevan / meragukan) dan verifikasi rekening vendor."""
from decimal import Decimal

import pytest

from app.services.extraction_service import ExtractedLine, parse_response
from tests.test_documents import api, codes, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_reference import add_vendor
from tests.test_review import NAMES, audit

PIC = "pic.alpha@amiga.test"


def receipt(**kw):
    """Struk kasir: ada barang, harga, total; tanpa nomor invoice resmi dan tanpa rekening."""
    base = dict(doc_class="RECEIPT", document_type="Struk kasir", not_invoice_reason="Struk belanja yang sudah dibayar.",
                vendor_name="PT Vendor Jaya", invoice_no=None, bank_name=None, account_no=None, account_name=None,
                line_items=[ExtractedLine("Gula pasir", Decimal(2), Decimal(15900), Decimal(31800))], total=Decimal(31800))
    return invoice(**{**base, **kw})


def reviewer(doc):
    return api(NAMES[doc["assigned_reviewer"]])


def verified_vendor(account_no="1234567890"):
    """Vendor didaftarkan PIC, lalu diverifikasi Finance Reviewer (bukan pendaftarnya)."""
    vendor = add_vendor(account_no=account_no, account_name="PT Vendor Jaya").json()
    r = api("reviewer1@amiga.test").post(f"/vendors/{vendor['id']}/verify")
    assert r.status_code == 200, r.text
    return r.json()


# --- Klasifikasi oleh parser (pengaman aturan atas jawaban AI) ---

@pytest.mark.parametrize("answer, expected", [
    ('{"document_class": "invoice", "vendor_name": "PT A", "total": "10.000"}', "INVOICE"),
    ('{"document_class": "receipt", "document_type": "Struk", "total": "70.300", '
     '"line_items": [{"kind": "item", "description": "Gula", "subtotal": "70.300"}]}', "RECEIPT"),
    ('{"document_class": "irrelevant", "document_type": "Surat lamaran"}', "IRRELEVANT"),
    ('{"document_class": "uncertain", "vendor_name": "PT A"}', "UNCERTAIN"),
    # Struk tanpa data transaksi tidak bisa disusun sebagai draft → diperiksa manual
    ('{"document_class": "receipt", "document_type": "Struk"}', "UNCERTAIN"),
    # Invoice yang datanya kosong sama sekali → diperiksa manual
    ('{"document_class": "invoice", "document_type": "Invoice"}', "UNCERTAIN"),
    # Jawaban lama tanpa document_class
    ('{"is_invoice": false, "document_type": "Purchase order"}', "IRRELEVANT"),
])
def test_parser_classifies_documents(answer, expected):
    assert parse_response(answer).doc_class == expected


def test_irrelevant_document_keeps_no_data():
    inv = parse_response('{"document_class": "irrelevant", "document_type": "CV", "vendor_name": "Budi", '
                         '"account_no": "123", "total": "5.000"}')
    assert (inv.vendor_name, inv.account_no, inv.total, inv.line_items) == (None, None, None, [])


def test_receipt_does_not_invent_missing_data():
    inv = parse_response('{"document_class": "receipt", "document_type": "Struk", "vendor_name": "Toko A", '
                         '"total": "31.800", "line_items": [{"kind": "item", "description": "Gula", "subtotal": "31.800"}]}')
    assert inv.account_no is None and inv.invoice_no is None and inv.total == Decimal(31800)


# --- Alur dokumen ---

def test_valid_invoice_flow_is_unchanged(extractor):
    doc = detail(upload().json()["id"])
    assert doc["status"] == "READY_FOR_REVIEW" and doc["issues"] == []
    assert doc["classification"]["doc_class"] == "INVOICE"


def test_irrelevant_document_is_rejected_with_reason(extractor):
    extractor.result = invoice(doc_class="IRRELEVANT", document_type="Surat lamaran", not_invoice_reason="Berisi lamaran kerja")
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION" and codes(doc) == [("NOT_AN_INVOICE", None)]
    assert "ditolak" in doc["issues"][0]["message"] and "Berisi lamaran kerja" in doc["issues"][0]["message"]


def test_receipt_becomes_draft_with_missing_data_and_no_voucher(extractor):
    extractor.result = receipt()
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION"
    found = {c for c, _ in codes(doc)}
    assert "RECEIPT_NOT_INVOICE" in found and "MISSING_EVIDENCE" in found
    missing = {f for c, f in codes(doc) if c == "MISSING_EVIDENCE"}
    assert {"invoice_no", "account_no", "bank_name"} <= missing
    # Data transaksi tetap tersimpan sebagai draft untuk Preview
    assert doc["extraction"]["total"] is not None and doc["extraction"]["line_items"][0]["description"] == "Gula pasir"
    assert doc["classification"]["doc_class"] == "RECEIPT"
    # Voucher tidak bisa terbit dari status ini
    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    assert r.status_code == 409 and doc["voucher"] is None


def test_receipt_cannot_be_turned_into_invoice_or_accepted_while_incomplete(extractor):
    extractor.result = receipt()
    doc = detail(upload().json()["id"])
    rev = api("reviewer1@amiga.test")
    url = f"/documents/{doc['id']}/classification"
    assert rev.post(url, json={"decision": "INVOICE", "reason": "Kelihatan seperti invoice"}).status_code == 422
    r = rev.post(url, json={"decision": "RECEIPT_ACCEPTED", "reason": "Struk sah untuk reimbursement"})
    assert r.status_code == 409 and "MISSING_EVIDENCE" in r.json()["detail"]


def test_receipt_accepted_only_with_complete_data_and_verified_account(extractor):
    verified_vendor()
    extractor.result = receipt(invoice_no="STRUK-0091", bank_name="BCA", account_no="1234567890",
                               account_name="PT Vendor Jaya")
    doc = detail(upload().json()["id"])
    assert codes(doc) == [("RECEIPT_NOT_INVOICE", None)]
    assert doc["account_check"]["state"] == "VERIFIED"

    # Pengunggah tidak boleh memutuskan (SoD); PIC bukan Finance Reviewer sama sekali
    assert api(PIC).post(f"/documents/{doc['id']}/classification",
                         json={"decision": "RECEIPT_ACCEPTED", "reason": "Struk sah"}).status_code == 403
    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/classification",
                                         json={"decision": "RECEIPT_ACCEPTED", "reason": "Reimbursement sesuai kebijakan klien"})
    assert r.status_code == 200, r.text
    after = r.json()
    # Diterima ≠ disetujui: tetap masuk antrean Finance Reviewer, voucher belum terbit
    assert after["status"] == "READY_FOR_REVIEW" and after["voucher"] is None
    assert after["classification"]["decision"]["decision"] == "RECEIPT_ACCEPTED"
    assert audit(doc["id"], "CLASSIFICATION_DECIDED")[0].note == "Reimbursement sesuai kebijakan klien"
    assert reviewer(after).post(f"/documents/{doc['id']}/approve").json()["status"] == "AMIGA_REVIEWED"


def test_uncertain_document_needs_manual_review(extractor):
    extractor.result = invoice(doc_class="UNCERTAIN", document_type="Tidak jelas", not_invoice_reason="Hasil pindai buram")
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION" and ("NEEDS_MANUAL_REVIEW", None) in codes(doc)

    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/classification",
                                         json={"decision": "INVOICE", "reason": "Dicek manual: invoice resmi vendor"})
    assert r.json()["status"] == "READY_FOR_REVIEW" and r.json()["issues"] == []


def test_reviewer_can_reject_uncertain_document_as_irrelevant(extractor):
    extractor.result = invoice(doc_class="UNCERTAIN")
    doc = detail(upload().json()["id"])
    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/classification",
                                         json={"decision": "IRRELEVANT", "reason": "Ini surat penawaran, bukan tagihan"})
    assert r.json()["status"] == "EXCEPTION" and codes(r.json()) == [("NOT_AN_INVOICE", None)]


def test_classification_decision_only_for_receipt_or_uncertain(extractor):
    extractor.result = invoice(account_no=None)
    doc = detail(upload().json()["id"])
    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/classification",
                                         json={"decision": "INVOICE", "reason": "alasan apa saja"})
    assert r.status_code == 409


# --- Verifikasi rekening terhadap data referensi tepercaya ---

def test_unverified_account_needs_explicit_reviewer_confirmation(extractor):
    doc = detail(upload().json()["id"])
    assert doc["account_check"]["state"] == "UNVERIFIED"
    rev = reviewer(doc)
    r = rev.post(f"/documents/{doc['id']}/approve")
    assert r.status_code == 422 and "Rekening belum terverifikasi" in r.json()["detail"]
    assert detail(doc["id"])["status"] == "READY_FOR_REVIEW"
    ok = rev.post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True, "account_note": "Telepon vendor"})
    assert ok.json()["status"] == "AMIGA_REVIEWED"
    assert audit(doc["id"], "ACCOUNT_CONFIRMED_BY_REVIEWER")[0].note == "Telepon vendor"


def test_account_entered_by_pic_is_not_trusted(extractor):
    extractor.result = invoice(account_no=None)
    doc = detail(upload().json()["id"])
    fixed = api(PIC).post(f"/documents/{doc['id']}/fix", json={"fields": {"account_no": "1234567890"}})
    assert fixed.status_code == 200, fixed.text
    after = detail(doc["id"])
    assert after["account_check"]["source"] == "PIC" and after["account_check"]["state"] == "UNVERIFIED"
    assert "diisi PIC" in after["account_check"]["message"]


def test_verified_vendor_matches_and_skips_confirmation(extractor):
    verified_vendor()
    doc = detail(upload().json()["id"])
    assert doc["account_check"]["state"] == "VERIFIED"
    assert reviewer(doc).post(f"/documents/{doc['id']}/approve").json()["status"] == "AMIGA_REVIEWED"


def test_account_different_from_verified_vendor_is_blocked(extractor):
    verified_vendor(account_no="9999999999")
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION" and ("ACCOUNT_MISMATCH", "account_no") in codes(doc)
    assert doc["account_check"]["state"] == "MISMATCH"


def test_vendor_verification_rules(tx):
    vendor = add_vendor(account_name="PT Vendor Jaya").json()
    # Hanya Finance Reviewer; bukan pendaftar / pengubah terakhir data bank (SoD)
    assert api(PIC).post(f"/vendors/{vendor['id']}/verify").status_code == 403
    yoga_vendor = add_vendor(email="multi@amiga.test", name="PT Yoga Supplier", account_name="PT Yoga").json()
    assert api("multi@amiga.test").post(f"/vendors/{yoga_vendor['id']}/verify").status_code == 403
    incomplete = add_vendor(name="PT Tanpa Nama Rekening").json()
    assert api("reviewer1@amiga.test").post(f"/vendors/{incomplete['id']}/verify").status_code == 422

    verified = api("reviewer1@amiga.test").post(f"/vendors/{vendor['id']}/verify").json()
    assert verified["verified_at"] and verified["verified_by"] == "Dewi (Finance Reviewer)"
    # Data bank berubah → verifikasi batal
    body = {k: verified[k] for k in ("name", "npwp", "bank_name", "account_name")} | {"account_no": "1112223334"}
    changed = api(PIC).put(f"/vendors/{vendor['id']}", json=body).json()
    assert changed["verified_at"] is None
