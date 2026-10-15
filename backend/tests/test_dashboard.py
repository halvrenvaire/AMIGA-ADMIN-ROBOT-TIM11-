"""Dashboard antrean, filter, pengalihan Service Lead, dan Asisten dengan data antrean (F6)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import db as db_module
from app.config import settings
from app.main import app
from app.models import AuditLog, User
from tests.test_ask import FakeBedrock, FakeIndexing, _store
from tests.test_documents import api, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_review import NAMES


def user_id(email):
    with db_module.SessionLocal() as db:
        return str(db.scalar(select(User.id).where(User.email == email)))


@pytest.fixture
def docs(extractor):
    """Alpha: 1 READY (tenggat besok), 1 EXCEPTION (lewat tenggat). Beta: 1 READY."""
    tomorrow, yesterday = date.today() + timedelta(days=1), date.today() - timedelta(days=1)
    extractor.result = invoice(invoice_no="INV-A1", vendor_name="PT Alfa Makmur")
    a_ready = upload(due_date=tomorrow.isoformat()).json()
    extractor.result = invoice(invoice_no="INV-A2", account_no=None)
    a_problem = upload(due_date=yesterday.isoformat()).json()
    extractor.result = invoice(invoice_no="INV-B1")
    b_ready = upload(email="pic.beta@amiga.test", client="PT Klien Beta").json()
    return a_ready, a_problem, b_ready


# --- Ringkasan (FR-6.1) ---

def test_summary_counts_due_and_reviewer_load(docs):
    body = api("lead@amiga.test").get("/dashboard/summary").json()
    assert body["counts"]["READY_FOR_REVIEW"] == 2
    assert body["counts"]["EXCEPTION"] == body["problem"] == 1
    assert body["due_soon"] == 1 and body["overdue"] == 1
    assert sum(r["pending"] for r in body["reviewers"]) == 2


def test_reviewer_sees_every_company(docs):
    # multi@ hanya ditugaskan ke Alpha (untuk mengajukan), tetapi sebagai reviewer menangani semua perusahaan
    a_ready, _, b_ready = docs
    ids = {d["id"] for d in api("multi@amiga.test").get("/documents", params={"status": "READY_FOR_REVIEW"}).json()}
    assert {a_ready["id"], b_ready["id"]} <= ids


def test_overloaded_reviewer_is_flagged(docs, monkeypatch):
    monkeypatch.setattr(settings, "reviewer_overload_threshold", 0)
    reviewers = api("lead@amiga.test").get("/dashboard/summary").json()["reviewers"]
    assert {r["overloaded"] for r in reviewers if r["pending"] > 0} == {True}
    assert {r["overloaded"] for r in reviewers if r["pending"] == 0} <= {False}


@pytest.mark.parametrize("email", ["pic.alpha@amiga.test", "intake@amiga.test", "admin@amiga.test"])
def test_summary_is_for_lead_and_reviewer(tx, email):
    assert api(email).get("/dashboard/summary").status_code == 403


# --- Filter (FR-6.2) ---

def test_list_filters(docs):
    a_ready, a_problem, b_ready = docs
    lead = api("lead@amiga.test")
    ids = lambda **p: [d["id"] for d in lead.get("/documents", params=p).json()]  # noqa: E731
    assert ids(problem=True) == [a_problem["id"]]
    assert set(ids(due_within_days=2)) == {a_ready["id"], a_problem["id"]}
    assert ids(sort="tenggat")[:2] == [a_problem["id"], a_ready["id"]]
    assert ids(q="alfa makmur") == [a_ready["id"]]
    assert ids(q=b_ready["request_id"][-6:]) == [b_ready["id"]]
    reviewer = detail(a_ready["id"])["assigned_reviewer"]
    assert a_ready["id"] in ids(reviewer_id=user_id(NAMES[reviewer]))


# --- Pengalihan oleh Service Lead (FR-6.3) ---

def test_lead_reassigns_without_changing_status(docs):
    doc = detail(docs[0]["id"])
    current = NAMES[doc["assigned_reviewer"]]
    target = next(e for e in ("reviewer1@amiga.test", "reviewer2@amiga.test") if e != current)
    r = api("lead@amiga.test").post(f"/documents/{doc['id']}/reassign",
                                    json={"reviewer_id": user_id(target), "reason": "Dewi cuti"})
    assert r.status_code == 200
    assert r.json()["status"] == "READY_FOR_REVIEW"
    assert NAMES[r.json()["assigned_reviewer"]] == target
    with db_module.SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.document_id == doc["id"],
                                               AuditLog.action == "REVIEWER_REASSIGNED"))
    assert (log.old_value, log.new_value, log.note) == (doc["assigned_reviewer"], r.json()["assigned_reviewer"], "Dewi cuti")
    assert "lead@amiga.test" in log.actor_label


def test_reassign_rules(extractor):
    doc = upload(email="multi@amiga.test").json()  # pengunggah = multi@ (juga reviewer Alpha)
    lead = api("lead@amiga.test")
    url = f"/documents/{doc['id']}/reassign"
    assert lead.post(url, json={"reviewer_id": user_id("multi@amiga.test")}).status_code == 422  # SoD
    assert lead.post(url, json={"reviewer_id": user_id("lead@amiga.test")}).status_code == 422   # bukan reviewer
    current = NAMES[detail(doc["id"])["assigned_reviewer"]]
    assert lead.post(url, json={"reviewer_id": user_id(current)}).status_code == 409
    assert api("reviewer1@amiga.test").post(url, json={"reviewer_id": user_id(current)}).status_code == 403


def test_cannot_reassign_exception_document(docs):
    r = api("lead@amiga.test").post(f"/documents/{docs[1]['id']}/reassign",
                                    json={"reviewer_id": user_id("reviewer1@amiga.test")})
    assert r.status_code == 409


# --- Asisten dengan data antrean ---

@pytest.fixture
def assistant(tx):
    fake = FakeBedrock()
    app.state.bedrock = fake
    app.state.indexing = FakeIndexing(_store())
    return fake


def ask(email, question):
    return api(email).post("/ask-agent", json={"question": question, "session_id": f"t-{email}"}).json()


def test_assistant_answers_queue_questions_within_access(docs, assistant):
    a_ready, _, b_ready = docs
    body = ask("multi@amiga.test", "Dokumen apa yang tenggatnya dekat?")
    assert body["used_queue_data"] is True
    assert body["answer_id"] is None  # data antrean tidak disimpan ke memori
    # Reviewer menangani semua perusahaan
    assert a_ready["request_id"] in assistant.last_system and b_ready["request_id"] in assistant.last_system


def test_lead_sees_reviewer_load_in_assistant(docs, assistant):
    ask("lead@amiga.test", "Beban reviewer siapa yang paling banyak?")
    assert "Beban reviewer" in assistant.last_system


def test_admin_assistant_uses_sop_only(docs, assistant):
    body = ask("admin@amiga.test", "Berapa dokumen yang bermasalah?")
    assert body["used_queue_data"] is False
    assert "DATA ANTREAN" not in assistant.last_system


def test_procedure_question_does_not_use_queue_data(docs, assistant):
    body = ask("reviewer1@amiga.test", "Apa itu QUEUED?")
    assert body["used_queue_data"] is False
    assert body["answer_id"] is not None


def test_reviewer_options_exclude_uploader_and_current_reviewer(extractor):
    doc = upload(email="multi@amiga.test").json()  # pengunggah = multi@ (juga reviewer Alpha)
    current = detail(doc["id"])["assigned_reviewer"]
    names = {r["name"] for r in api("lead@amiga.test").get(f"/documents/{doc['id']}/reviewer-options").json()}
    assert "Yoga (Intake + Reviewer)" not in names
    assert current not in names
    assert names == set(NAMES) - {"Yoga (Intake + Reviewer)", current}
    assert api("reviewer1@amiga.test").get(f"/documents/{doc['id']}/reviewer-options").status_code == 403
