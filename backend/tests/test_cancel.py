"""Pembatalan pengajuan oleh PIC Klien / Intake Support."""
from tests.test_documents import api, codes, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_reference import approve

PIC = "pic.alpha@amiga.test"
REASON = {"reason": "Salah unggah, ini struk belanja."}


def test_pic_cancels_problem_document(extractor):
    extractor.result = invoice(invoice_date=None)
    doc = upload().json()
    r = api(PIC).post(f"/documents/{doc['id']}/cancel", json=REASON)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "CANCELLED" and body["issues"] == []
    assert body["cancellation"]["reason"] == REASON["reason"] and "Rina" in body["cancellation"]["by"]
    history = api(PIC).get(f"/documents/{doc['id']}/history").json()
    assert any(h["action"] == "DOCUMENT_CANCELLED" and h["note"] == REASON["reason"] for h in history)
    # Tidak bisa diperbaiki, disetujui, atau dibatalkan lagi
    assert api(PIC).post(f"/documents/{doc['id']}/fix", json={"note": "coba"}).status_code == 409
    assert api(PIC).post(f"/documents/{doc['id']}/cancel", json=REASON).status_code == 409


def test_ready_document_can_be_cancelled_but_not_after_voucher(extractor):
    ready = detail(upload().json()["id"])
    assert ready["status"] == "READY_FOR_REVIEW"
    assert api(PIC).post(f"/documents/{ready['id']}/cancel", json=REASON).status_code == 200
    reviewer_cannot = api("reviewer1@amiga.test").post(f"/documents/{ready['id']}/approve", json={"account_confirmed": True})
    assert reviewer_cannot.status_code == 409

    extractor.result = invoice(invoice_no="INV-VOUCHER")
    done = detail(upload().json()["id"])
    approve(done)
    assert api(PIC).post(f"/documents/{done['id']}/cancel", json=REASON).status_code == 409


def test_cancelled_invoice_can_be_resubmitted_without_duplicate_flag(extractor):
    first = upload().json()
    assert api(PIC).post(f"/documents/{first['id']}/cancel", json=REASON).status_code == 200
    again = detail(upload().json()["id"])
    assert ("POSSIBLE_DUPLICATE", "invoice_no") not in codes(again)
    assert again["status"] == "READY_FOR_REVIEW"


def test_cancel_rules(extractor):
    doc = upload().json()
    assert api(PIC).post(f"/documents/{doc['id']}/cancel", json={"reason": "x"}).status_code == 422  # alasan wajib
    assert api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/cancel", json=REASON).status_code == 403
    assert api("pic.beta@amiga.test").post(f"/documents/{doc['id']}/cancel", json=REASON).status_code == 403
    # Intake Support yang ditugaskan ke perusahaan itu boleh
    assert api("intake@amiga.test").post(f"/documents/{doc['id']}/cancel", json=REASON).status_code == 200
