"""Peninjauan, SoD, voucher, dan jejak audit (F4, F5, F8; UAT 1, 5, 7)."""
import io
import re
import time
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app import db as db_module
from app.models import AuditLog
from tests.test_documents import ALPHA_REVIEWERS, api, detail, extractor, invoice, tx, upload  # noqa: F401

NAMES = {"Dewi (Finance Reviewer)": "reviewer1@amiga.test", "Agus (Finance Reviewer)": "reviewer2@amiga.test",
         "Yoga (Intake + Reviewer)": "multi@amiga.test"}


def ready_doc(email="pic.alpha@amiga.test"):
    doc = detail(upload(email=email).json()["id"], email=email)
    assert doc["status"] == "READY_FOR_REVIEW"
    return doc


def reviewer_of(doc):
    return api(NAMES[doc["assigned_reviewer"]])


def audit(doc_id, action=None):
    with db_module.SessionLocal() as db:
        query = select(AuditLog).where(AuditLog.document_id == doc_id).order_by(AuditLog.id)
        if action:
            query = query.where(AuditLog.action == action)
        return db.scalars(query).all()


def pdf_text(data: bytes) -> str:
    text = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    return re.sub(r"\s+", " ", text)


# --- UAT 1: alur normal sampai SENT_TO_CLIENT ---

def test_uat1_normal_flow_ends_sent_to_client(extractor):
    doc = ready_doc()
    started = time.monotonic()
    r = reviewer_of(doc).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    assert r.status_code == 200
    assert time.monotonic() - started <= 3  # FR-5.1
    body = r.json()
    assert body["status"] == "AMIGA_REVIEWED"
    assert re.fullmatch(r"VCH/\d{4}/\d{2}/\d{4}", body["voucher"]["voucher_no"])

    pic = api("pic.alpha@amiga.test")
    preview = pic.get(f"/documents/{doc['id']}/voucher")
    assert preview.status_code == 200
    assert detail(doc["id"])["status"] == "AMIGA_REVIEWED"  # pratinjau tidak mengubah status

    text = pdf_text(preview.content)
    assert body["voucher"]["voucher_no"] in text
    assert "BATAS OTORISASI" in text and "BUKAN persetujuan pembayaran" in text
    assert "1234567890" in text and "Rp 900.000" in text

    download = pic.get(f"/documents/{doc['id']}/voucher", params={"download": True})
    assert download.headers["content-disposition"].startswith("attachment")
    assert detail(doc["id"])["status"] == "SENT_TO_CLIENT"
    assert [a.action for a in audit(doc["id"])][-4:] == [
        "APPROVED", "VOUCHER_CREATED", "VOUCHER_DOWNLOADED", "STATUS_CHANGED"]


@pytest.mark.parametrize("email", ["reviewer2@amiga.test", "multi@amiga.test"])
def test_reviewer_download_does_not_hand_over(extractor, email):
    # multi@ juga Intake Support, tetapi bukan pengunggah dokumen ini
    doc = ready_doc()
    reviewer_of(doc).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    api(email).get(f"/documents/{doc['id']}/voucher", params={"download": True})
    assert detail(doc["id"])["status"] == "AMIGA_REVIEWED"


def test_intake_uploader_download_hands_over(extractor):
    doc = ready_doc(email="intake@amiga.test")
    reviewer_of(doc).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    api("intake@amiga.test").get(f"/documents/{doc['id']}/voucher", params={"download": True})
    assert detail(doc["id"])["status"] == "SENT_TO_CLIENT"


def test_service_lead_cannot_open_voucher(extractor):
    doc = ready_doc()
    reviewer_of(doc).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    assert api("lead@amiga.test").get(f"/documents/{doc['id']}/voucher").status_code == 403


def test_voucher_numbers_are_sequential(extractor):
    numbers = []
    for n in range(2):
        extractor.result = invoice(invoice_no=f"INV-50{n}")
        doc = ready_doc()
        numbers.append(reviewer_of(doc).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).json()["voucher"]["voucher_no"])
    first, second = (int(n.rsplit("/", 1)[1]) for n in numbers)
    assert second == first + 1


@pytest.mark.parametrize("email", ["admin@amiga.test", "lead@amiga.test", "pic.alpha@amiga.test"])
def test_only_finance_reviewer_can_approve(extractor, email):
    doc = ready_doc()
    assert api(email).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).status_code == 403
    assert detail(doc["id"])["status"] == "READY_FOR_REVIEW"


def test_cannot_approve_exception_document(extractor):
    extractor.result = invoice(account_no=None)
    doc_id = upload().json()["id"]
    assert api("reviewer1@amiga.test").post(f"/documents/{doc_id}/approve", json={"account_confirmed": True}).status_code == 409


# --- UAT 5: Segregation of Duties ---

def test_sod_is_checked_before_account_confirmation(extractor):
    """Pihak pengaju langsung ditolak SoD (403), tidak diminta mengonfirmasi rekening dulu (422)."""
    doc = ready_doc(email="multi@amiga.test")
    assert detail(doc["id"])["account_check"]["state"] == "UNVERIFIED"
    r = api("multi@amiga.test").post(f"/documents/{doc['id']}/approve")  # tanpa konfirmasi rekening
    assert r.status_code == 403 and "Segregation of Duties" in r.json()["detail"]


def test_uat5_uploader_cannot_approve_and_document_is_reassigned(extractor):
    doc = ready_doc(email="multi@amiga.test")  # Intake Support + Finance Reviewer
    r = api("multi@amiga.test").post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True})
    assert r.status_code == 403
    assert "Segregation of Duties" in r.json()["detail"]

    after = detail(doc["id"])
    assert after["status"] == "READY_FOR_REVIEW"
    assert after["assigned_reviewer"] in ALPHA_REVIEWERS - {"Yoga (Intake + Reviewer)"}
    assert after["assigned_reviewer"] in r.json()["detail"]
    assert [a.action for a in audit(doc["id"])][-2:] == ["SOD_REJECTED", "REVIEWER_REASSIGNED"]

    assert reviewer_of(after).post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).json()["status"] == "AMIGA_REVIEWED"


# --- UAT 7: koreksi tercatat di jejak audit; field gagal verifikasi ditandai ---

def test_uat7_reviewer_correction_is_audited_and_reverified(extractor):
    doc = ready_doc()
    reviewer = reviewer_of(doc)
    r = reviewer.put(f"/documents/{doc['id']}/extraction", json={"fields": {"total": "950000"}})
    assert r.status_code == 200
    assert [i["code"] for i in r.json()["issues"]] == ["CALCULATION_DISCREPANCY"]
    assert r.json()["status"] == "READY_FOR_REVIEW"
    assert reviewer.post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).status_code == 409

    log = audit(doc["id"], "CORRECTED_BY_REVIEWER")[-1]
    assert (log.field, Decimal(log.old_value), log.new_value) == ("total", Decimal(900000), "950000")
    assert doc["assigned_reviewer"] in log.actor_label
    assert log.created_at is not None

    lines = [{"description": li["description"], "qty": li["qty"], "unit_price": li["unit_price"],
              "subtotal": li["subtotal"]} for li in doc["extraction"]["line_items"]]
    lines[2]["subtotal"] = "150000"
    r = reviewer.put(f"/documents/{doc['id']}/extraction", json={"line_items": lines})
    assert r.json()["issues"] == []
    assert audit(doc["id"], "CORRECTED_BY_REVIEWER")[-1].field == "line_items[3].subtotal"
    assert reviewer.post(f"/documents/{doc['id']}/approve", json={"account_confirmed": True}).status_code == 200


def test_correction_rejects_invalid_values(extractor):
    doc = ready_doc()
    reviewer = reviewer_of(doc)
    assert reviewer.put(f"/documents/{doc['id']}/extraction",
                        json={"fields": {"total": "9.500.000"}}).status_code == 422
    assert reviewer.put(f"/documents/{doc['id']}/extraction",
                        json={"fields": {"status": "x"}}).status_code == 422


def test_clearing_account_number_flags_missing_evidence(extractor):
    doc = ready_doc()
    r = reviewer_of(doc).put(f"/documents/{doc['id']}/extraction", json={"fields": {"account_no": None}})
    assert [(i["code"], i["field"]) for i in r.json()["issues"]] == [("MISSING_EVIDENCE", "account_no")]


# --- Kembalikan ke PIC ---

def test_return_to_pic_requires_reason_then_pic_resubmits(extractor):
    doc = ready_doc()
    reviewer = reviewer_of(doc)
    assert reviewer.post(f"/documents/{doc['id']}/return", json={"reason": ""}).status_code == 422

    r = reviewer.post(f"/documents/{doc['id']}/return", json={"reason": "Lampirkan invoice revisi bertanda tangan."})
    assert r.json()["status"] == "EXCEPTION"
    issue = r.json()["issues"][0]
    assert issue["code"] == "RETURNED_BY_REVIEWER"
    assert "Lampirkan invoice revisi" in issue["message"]

    again = api("pic.alpha@amiga.test").post(f"/documents/{doc['id']}/fix",
                                             json={"note": "Invoice revisi sudah diunggah vendor."})
    assert again.status_code == 200
    final = detail(doc["id"])
    assert final["status"] == "READY_FOR_REVIEW"
    assert final["request_id"] == doc["request_id"]


# --- Duplikat yang ternyata bukan duplikat ---

def test_reviewer_can_dismiss_false_duplicate_with_reason(extractor):
    upload()
    dup = detail(upload().json()["id"])
    assert dup["status"] == "EXCEPTION"
    assert api("pic.alpha@amiga.test").post(f"/documents/{dup['id']}/dismiss-duplicate",
                                            json={"reason": "Tagihan bulan berbeda"}).status_code == 403

    r = api("reviewer1@amiga.test").post(f"/documents/{dup['id']}/dismiss-duplicate",
                                         json={"reason": "Tagihan bulan berbeda, sudah dicek ke vendor"})
    assert r.status_code == 200
    assert r.json()["status"] == "READY_FOR_REVIEW"
    assert audit(dup["id"], "DUPLICATE_DISMISSED")[-1].note.startswith("Tagihan bulan berbeda")


def test_uploader_cannot_dismiss_own_duplicate(extractor):
    upload(email="multi@amiga.test")
    dup = upload(email="multi@amiga.test").json()["id"]
    r = api("multi@amiga.test").post(f"/documents/{dup}/dismiss-duplicate", json={"reason": "Bukan duplikat"})
    assert r.status_code == 403


def test_dismiss_only_when_duplicate_is_the_only_issue(extractor):
    extractor.result = invoice(account_no=None)
    doc_id = upload().json()["id"]
    r = api("reviewer1@amiga.test").post(f"/documents/{doc_id}/dismiss-duplicate", json={"reason": "Bukan duplikat"})
    assert r.status_code == 409


# --- Riwayat (Layar 05) ---

def test_history_visible_to_assigned_users_and_admin_only(extractor):
    doc = ready_doc()
    actions = [a["action"] for a in api("pic.alpha@amiga.test").get(f"/documents/{doc['id']}/history").json()]
    assert actions[0] == "DOCUMENT_UPLOADED"
    assert api("admin@amiga.test").get(f"/documents/{doc['id']}/history").status_code == 200
    assert api("pic.beta@amiga.test").get(f"/documents/{doc['id']}/history").status_code == 403
