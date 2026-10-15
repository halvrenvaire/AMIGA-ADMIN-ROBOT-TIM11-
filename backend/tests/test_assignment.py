"""Pembagian kasus ke Finance Reviewer dan Segregation of Duties untuk pengguna peran ganda."""
from collections import Counter

from tests.test_documents import api, client_id, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_review import NAMES as EMAIL_OF

NAMES = {email: name for name, email in EMAIL_OF.items()}

REVIEWERS = {"reviewer1@amiga.test", "reviewer2@amiga.test", "multi@amiga.test"}


def test_cases_are_split_evenly_across_all_reviewers(extractor):
    # 20 pengajuan dari dua perusahaan, 3 reviewer → 7, 7, 6
    for i in range(20):
        extractor.result = invoice(invoice_no=f"INV-RATA-{i}")
        upload(client="PT Klien Alpha" if i % 2 else "PT Klien Beta",
               email="pic.alpha@amiga.test" if i % 2 else "pic.beta@amiga.test")
    lead = api("lead@amiga.test")
    docs = lead.get("/documents", params={"status": "READY_FOR_REVIEW"}).json()
    counts = Counter(d["assigned_reviewer"] for d in docs)
    assert len(docs) == 20 and sorted(counts.values()) == [6, 7, 7]
    assert set(counts) == {NAMES[e] for e in REVIEWERS}


def test_dual_role_user_who_fixed_the_data_cannot_review_it(extractor):
    """Yoga (Intake Support + Finance Reviewer) memperbaiki data invoice PIC, lalu tidak boleh
    menjadi reviewer, menandai bukan duplikat, ataupun menyetujuinya."""
    extractor.result = invoice(account_no=None)
    doc = upload().json()  # diunggah PIC Alpha → MISSING_EVIDENCE
    yoga = api("multi@amiga.test")
    r = yoga.post(f"/documents/{doc['id']}/fix", json={"fields": {"account_no": "1234567890"}})
    assert r.status_code == 200
    extractor.result = invoice()
    d = detail(doc["id"])
    assert d["status"] == "READY_FOR_REVIEW"
    assert d["assigned_reviewer"] != NAMES["multi@amiga.test"]

    r = yoga.post(f"/documents/{doc['id']}/approve")
    assert r.status_code == 403 and "pihak pengaju" in r.json()["detail"]
    assert detail(doc["id"])["status"] == "READY_FOR_REVIEW"


def test_dual_role_user_who_fixed_cannot_dismiss_duplicate(extractor):
    upload()
    extractor.result = invoice(account_no=None)  # nomor invoice sama → duplikat + data kurang
    doc = upload().json()
    yoga = api("multi@amiga.test")
    extractor.result = invoice()
    assert yoga.post(f"/documents/{doc['id']}/fix", json={"fields": {"account_no": "1234567890"}}).status_code == 200
    assert [i["code"] for i in detail(doc["id"])["issues"]] == ["POSSIBLE_DUPLICATE"]
    r = yoga.post(f"/documents/{doc['id']}/dismiss-duplicate", json={"reason": "nomor sudah diganti"})
    assert r.status_code == 403
    # Reviewer lain boleh
    r = api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/dismiss-duplicate", json={"reason": "beda tagihan"})
    assert r.status_code == 200 and r.json()["assigned_reviewer"] != NAMES["multi@amiga.test"]


def test_reviewer_role_does_not_allow_submitting_for_unassigned_company(extractor):
    # multi@ ditugaskan ke Alpha untuk mengajukan; sebagai reviewer ia melihat Beta tetapi tidak boleh mengajukan
    assert upload(email="multi@amiga.test", client="PT Klien Beta").status_code == 403
    me = api("multi@amiga.test").get("/auth/me").json()
    assert {c["name"] for c in me["upload_clients"]} == {"PT Klien Alpha"}
    assert {"PT Klien Alpha", "PT Klien Beta"} <= {c["name"] for c in me["clients"]}


def test_intake_upload_is_signed_by_delegating_pic(extractor):
    doc = upload(email="intake@amiga.test").json()
    signers = detail(doc["id"])["signers"]
    assert signers[0]["kind"] == "PENGAJU" and signers[0]["name"] == "Rina (PIC Alpha)"
