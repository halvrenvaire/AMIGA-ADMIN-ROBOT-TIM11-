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
    extractor.result = invoice(invoice_no="INV-A2", invoice_date=None)
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


# --- Asisten text-to-query ---

class PlannerBedrock(FakeBedrock):
    """Model palsu: panggilan perencana mengembalikan rencana query JSON yang sudah ditentukan."""

    def __init__(self, plan: str):
        super().__init__()
        self.plan = plan

    def generate(self, system_prompt, messages, **kw):
        if system_prompt.startswith("Kamu menerjemahkan"):
            self.planner_messages = messages
            self.planner_system = system_prompt
            return self.plan
        return super().generate(system_prompt, messages, **kw)


def ask_with_plan(email, question, plan):
    app.state.bedrock = PlannerBedrock(plan)
    app.state.indexing = FakeIndexing(_store())
    return ask(email, question)


def test_query_reviewer_progress(docs):
    body = ask_with_plan("lead@amiga.test", "progres reviewer gimana?",
                         '{"query": "progres_pengguna", "peran": "FINANCE_REVIEWER"}')
    assert body["used_queue_data"] is True and body["answer_id"] is None
    assert body["query_label"].startswith("Progres per Finance Reviewer")
    [table] = body["data_tables"]
    assert table["columns"][:2] == ["Nama", "Menunggu review"]
    assert sum(int(r[1].split()[0]) for r in table["rows"]) == 2  # dua dokumen READY
    assert "HASIL QUERY DATA" in app.state.bedrock.last_system


def test_query_submitter_progress_counts_by_status(docs):
    body = ask_with_plan("lead@amiga.test", "progres PIC?", 'Rencana: {"query": "progres_pengguna", "peran": "PIC_KLIEN"}')
    rows = {r[0]: r for r in body["data_tables"][0]["rows"]}
    cols = body["data_tables"][0]["columns"]
    alpha = rows["Rina (PIC Alpha)"]
    assert alpha[cols.index("Total")] == "2" and alpha[cols.index("Ada kendala")] == "1"
    assert rows["Budi (PIC Beta)"][cols.index("Siap ditinjau")] == "1"


def test_query_document_list_filters_and_respects_scope(docs, make_user):
    a_ready, a_problem, b_ready = docs
    body = ask_with_plan("lead@amiga.test", "invoice yang lewat tenggat",
                         '{"query": "daftar_dokumen", "tenggat": "lewat"}')
    assert [r[0] for r in body["data_tables"][0]["rows"]] == [a_problem["request_id"]]

    body = ask_with_plan("lead@amiga.test", "dokumen Beta", '{"query": "daftar_dokumen", "klien": "Beta"}')
    assert [r[0] for r in body["data_tables"][0]["rows"]] == [b_ready["request_id"]]


def test_query_summary_by_status(docs):
    body = ask_with_plan("reviewer1@amiga.test", "sekarang progresnya gimana?", '{"query": "ringkasan"}')
    rows = {r[0]: r[1] for r in body["data_tables"][0]["rows"]}
    assert rows["Siap ditinjau"] == "2" and rows["Ada kendala"] == "1"


def test_sop_plan_or_unreadable_plan_falls_back(docs):
    body = ask_with_plan("reviewer1@amiga.test", "Apa itu QUEUED?", '{"query": "sop"}')
    assert body["data_tables"] == [] and body["used_queue_data"] is False
    body = ask_with_plan("reviewer1@amiga.test", "Dokumen apa yang tenggatnya dekat?", "maaf, tidak paham")
    assert body["data_tables"] == [] and body["used_queue_data"] is True  # ringkasan antrean lama
    body = ask_with_plan("reviewer1@amiga.test", "progres?", '{"query": "DROP TABLE users"}')
    assert body["data_tables"] == []


@pytest.mark.parametrize("plan", ['{"query": "progres_pengguna"}', '{"query": "dokumen_terakhir"}',
                                  '{"query": "daftar_dokumen"}'])
def test_admin_never_gets_document_data(docs, plan):
    body = ask_with_plan("admin@amiga.test", "progres PIC?", plan)
    assert body["data_tables"] == [] and body["cards"] == []
    assert "tidak tersedia untuk peran penanya" in app.state.bedrock.last_system


def test_admin_gets_user_and_client_overview(docs):
    body = ask_with_plan("admin@amiga.test", "ada berapa user di sistem?", '{"query": "pengguna"}')
    [recap] = body["data_tables"]
    rows = {r[0]: r for r in recap["rows"]}
    assert int(rows["Finance Reviewer"][1]) >= 3 and recap["links"][0]["href"] == "/admin/pengguna"

    body = ask_with_plan("admin@amiga.test", "PIC Alpha?", '{"query": "pengguna", "peran": "PIC_KLIEN", "klien": "Alpha"}')
    names = [r[0] for r in body["data_tables"][1]["rows"]]
    assert "Rina (PIC Alpha)" in names and "Budi (PIC Beta)" not in names
    body = ask_with_plan("admin@amiga.test", "klien tanpa PIC", '{"query": "data_klien", "tanpa_pic": true}')
    assert all(r[1] == "Belum ada PIC" for r in body["data_tables"][0]["rows"])


def test_non_admin_cannot_query_admin_data(docs):
    body = ask_with_plan("lead@amiga.test", "ada berapa user?", '{"query": "pengguna"}')
    assert body["data_tables"] == []
    assert "tidak tersedia untuk peran penanya" in app.state.bedrock.last_system


def test_query_document_detail(docs):
    _, a_problem, _ = docs
    body = ask_with_plan("lead@amiga.test", f"detail {a_problem['request_id']}",
                         f'{{"query": "detail_dokumen", "request_ids": ["{a_problem['request_id'].lower()}"]}}')
    [card] = body["cards"]
    assert card["request_id"] == a_problem["request_id"] and card["href"] == f"/dokumen/{a_problem['id']}"
    fields = dict(card["fields"])
    assert card["status_label"] == "Ada kendala" and "MISSING_EVIDENCE" in fields["Kendala aktif"]
    assert fields["Pengaju"] == "Rina (PIC Alpha)"
    assert [s["state"] for s in card["steps"]][:3] == ["done", "done", "bad"]
    assert card["history"][0]["action"] and "@" not in " ".join(h["actor"] for h in card["history"])
    # Service Lead tidak membuka voucher; tombolnya ke Dashboard Antrean
    assert {l["href"] for l in card["links"]} >= {card["href"], f"{card['href']}/riwayat", "/antrean"}


def test_follow_up_sees_previous_plan_and_data(docs):
    _, a_problem, _ = docs
    sid = "t-lanjutan-lead"
    lead = api("lead@amiga.test")
    app.state.indexing = FakeIndexing(_store())
    app.state.bedrock = PlannerBedrock('{"query": "daftar_dokumen", "tenggat": "lewat"}')
    lead.post("/ask-agent", json={"question": "dokumen lewat tenggat?", "session_id": sid})
    app.state.bedrock = PlannerBedrock('{"query": "detail_dokumen", "tenggat": "lewat"}')
    body = lead.post("/ask-agent", json={"question": "tampilkan detail dokumen tersebut", "session_id": sid}).json()

    previous = app.state.bedrock.planner_messages[-2]["content"]
    assert '"tenggat": "lewat"' in previous and a_problem["request_id"] in previous
    assert body["cards"][0]["request_id"] == a_problem["request_id"]


def test_sessions_are_listed_per_user_with_tables(docs):
    sid = "t-riwayat-lead"
    ask_with_plan("lead@amiga.test", "progres PIC?", '{"query": "progres_pengguna", "peran": "PIC_KLIEN"}')
    lead = api("lead@amiga.test")
    lead.post("/ask-agent", json={"question": "ringkasan status", "session_id": sid})

    listed = {s["session_id"]: s for s in lead.get("/ask-agent/sessions").json()}
    assert listed[sid]["title"] == "ringkasan status" and listed[sid]["messages"] == 2
    messages = lead.get(f"/ask-agent/sessions/t-lead@amiga.test").json()
    assert messages[1]["query_label"].startswith("Progres per PIC Klien") and messages[1]["data_tables"]

    other = api("reviewer1@amiga.test")
    assert sid not in {s["session_id"] for s in other.get("/ask-agent/sessions").json()}
    assert other.get(f"/ask-agent/sessions/{sid}").status_code == 404
    assert other.delete(f"/ask-agent/sessions/{sid}").status_code == 404
    assert lead.delete(f"/ask-agent/sessions/{sid}").status_code == 204
    assert lead.get(f"/ask-agent/sessions/{sid}").status_code == 404


def test_parse_plan_tolerates_model_mistakes():
    from app.services.data_query_service import parse_plan
    plan = parse_plan('```json\n{"query": "ringkasan", "status": ["disetujui", "Siap ditinjau", "ngawur"]}\n```')
    assert [s.value for s in plan.status] == ["AMIGA_REVIEWED", "READY_FOR_REVIEW"]
    plan = parse_plan('{"query": "daftar_dokumen", "tenggat": "kemarin", "periode_hari": 9999, "klien": "Alpha"}')
    assert plan.query == "daftar_dokumen" and plan.klien == "Alpha" and plan.tenggat is None and plan.periode_hari is None
    assert parse_plan('{"query": "hapus_semua"}') is None
    assert parse_plan("[1, 2]") is None


# --- Asisten untuk semua peran: data dibatasi klien penanya ---

def request_ids(body):
    return {r[0] for t in body["data_tables"] for r in t["rows"]} | {c["request_id"] for c in body["cards"]}


@pytest.mark.parametrize("email", ["pic.alpha@amiga.test", "intake@amiga.test"])
def test_submitter_roles_only_see_their_clients(docs, email):
    a_ready, a_problem, b_ready = docs
    body = ask_with_plan(email, "dokumen apa saja?", '{"query": "daftar_dokumen"}')
    ids = request_ids(body)
    assert {a_ready["request_id"], a_problem["request_id"]} <= ids and b_ready["request_id"] not in ids

    # Meminta klien lain secara eksplisit tetap tidak menghasilkan data
    body = ask_with_plan(email, "dokumen PT Klien Beta", '{"query": "daftar_dokumen", "klien": "Beta"}')
    assert body["data_tables"][0]["rows"] == []
    assert "tidak ditemukan di perusahaan yang bisa Anda akses" in body["data_tables"][0]["note"]
    body = ask_with_plan(email, "detail", f'{{"query": "detail_dokumen", "request_ids": ["{b_ready["request_id"]}"]}}')
    assert b_ready["request_id"] not in request_ids(body)

    body = ask_with_plan(email, "ringkasan per klien", '{"query": "ringkasan", "kelompok": "klien"}')
    assert [r[0] for r in body["data_tables"][0]["rows"]] == ["PT Klien Alpha"]


def test_reviewer_and_lead_see_every_client(docs):
    _, _, b_ready = docs
    for email in ("reviewer1@amiga.test", "lead@amiga.test"):
        body = ask_with_plan(email, "ringkasan per klien", '{"query": "ringkasan", "kelompok": "klien"}')
        assert {r[0] for r in body["data_tables"][0]["rows"]} == {"PT Klien Alpha", "PT Klien Beta"}


def test_pic_sees_only_reviewers_of_own_client(docs):
    _, _, b_ready = docs
    plan = '{"query": "progres_pengguna", "peran": "FINANCE_REVIEWER"}'
    beta_reviewer = detail(b_ready["id"], "pic.beta@amiga.test")["assigned_reviewer"]
    rows = ask_with_plan("pic.beta@amiga.test", "progres reviewer", plan)["data_tables"][0]["rows"]
    assert [r[0] for r in rows] == [beta_reviewer]
    all_rows = ask_with_plan("lead@amiga.test", "progres reviewer", plan)["data_tables"][0]["rows"]
    assert len(all_rows) > 1


def test_planner_knows_who_is_asking(docs):
    ask_with_plan("pic.alpha@amiga.test", "progres pengajuan saya", '{"query": "progres_pengguna", "orang": "Rina"}')
    assert "Penanya: Rina (PIC Alpha) (peran: PIC_KLIEN)" in app.state.bedrock.planner_system


def test_submitter_can_open_assistant_history(docs):
    ask_with_plan("intake@amiga.test", "progres?", '{"query": "ringkasan"}')
    assert api("intake@amiga.test").get("/ask-agent/sessions").status_code == 200



def test_last_touched_document_is_the_askers_own(docs):
    a_ready, a_problem, b_ready = docs
    # PIC Alpha terakhir mengunggah a_problem (a_ready lebih dulu); dokumen Beta bukan miliknya
    body = ask_with_plan("pic.alpha@amiga.test", "progres invoice yang terakhir saya update", '{"query": "dokumen_terakhir"}')
    [card] = body["cards"]
    assert card["request_id"] == a_problem["request_id"]
    assert card["hint"].startswith("Ada kendala yang perlu Anda perbaiki")
    assert {l["href"] for l in card["links"]} >= {f"/dokumen/{a_problem['id']}", "/pengajuan"}

    body = ask_with_plan("pic.beta@amiga.test", "invoice terakhir saya", '{"query": "dokumen_terakhir", "jumlah": 5}')
    assert [c["request_id"] for c in body["cards"]] == [b_ready["request_id"]]


def test_document_list_rows_link_to_detail(docs):
    a_ready, a_problem, _ = docs
    body = ask_with_plan("pic.alpha@amiga.test", "dokumen saya", '{"query": "daftar_dokumen"}')
    table = body["data_tables"][0]
    links = dict(zip((r[0] for r in table["rows"]), table["row_links"]))
    assert links[a_ready["request_id"]] == f"/dokumen/{a_ready['id']}"
    assert {"label": "Pengajuan Saya", "href": "/pengajuan"} in table["links"]


def test_cards_are_kept_in_history(docs):
    ask_with_plan("pic.alpha@amiga.test", "terakhir", '{"query": "dokumen_terakhir"}')
    messages = api("pic.alpha@amiga.test").get("/ask-agent/sessions/t-pic.alpha@amiga.test").json()
    assert messages[-1]["cards"][0]["steps"]
