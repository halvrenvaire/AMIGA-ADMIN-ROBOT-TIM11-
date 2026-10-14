"""Unggah, ekstraksi, verifikasi, dan perbaikan PIC (F1–F3; UAT 2, 3, 4, 6, 8).

Setiap test berjalan di dalam satu transaksi database yang di-rollback di akhir, karena
jejak audit append-only membuat dokumen test tidak bisa dihapus setelah di-commit.
"""
import copy
import io
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.config import settings
from app.main import app
from app.models import AuditLog, Client
from app.routers import documents as documents_router
from app.services import document_processing
from app.services.extraction_service import ExtractedInvoice, ExtractedLine, ExtractionError
from tests.auth_helpers import auth_header


# Finance Reviewer yang ditugaskan untuk PT Klien Alpha (seed.py)
ALPHA_REVIEWERS = {"Dewi (Finance Reviewer)", "Agus (Finance Reviewer)", "Yoga (Intake + Reviewer)"}


def make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def invoice(**kw) -> ExtractedInvoice:
    """Invoice 3 baris yang lolos semua verifikasi; kw mengganti field tertentu."""
    base = ExtractedInvoice(
        vendor_name="PT Vendor Jaya", invoice_no="INV-001", invoice_date=date(2026, 10, 1),
        line_items=[ExtractedLine("Kertas A4", Decimal(10), Decimal(50000), Decimal(500000)),
                    ExtractedLine("Tinta printer", Decimal(2), Decimal(150000), Decimal(300000)),
                    ExtractedLine("Map plastik", Decimal(20), Decimal(5000), Decimal(100000))],
        total=Decimal(900000), bank_name="BCA", account_no="1234567890", account_name="PT Vendor Jaya",
    )
    for key, value in kw.items():
        setattr(base, key, value)
    return base


class FakeExtractor:
    def __init__(self):
        self.result: ExtractedInvoice | Exception = invoice()
        self.calls = 0

    def extract(self, pdf_bytes):
        assert pdf_bytes.startswith(b"%PDF-")
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return copy.deepcopy(self.result)


# Proses background yang menunggu dijalankan (lihat fixture tx)
_pending: list[tuple] = []


class DrainingClient(TestClient):
    """Menjalankan proses background setelah request selesai dan sesi request ditutup."""

    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        while _pending:
            document_processing.process_document(*_pending.pop(0))
        return response


@pytest.fixture
def tx(monkeypatch, tmp_path):
    """Semua sesi database (request dan background) memakai satu transaksi yang di-rollback.

    Di dalam satu koneksi, sesi request yang baru ditutup setelah background task akan
    me-rollback savepoint-nya beserta hasil background. Karena itu proses background
    ditunda sampai request selesai (DrainingClient), seperti urutan di server sungguhan.
    """
    connection = db_module.engine.connect()
    transaction = connection.begin()
    monkeypatch.setattr(db_module, "SessionLocal", sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", autoflush=False, expire_on_commit=False))
    _pending.clear()
    monkeypatch.setattr(documents_router, "process_document", lambda *a: _pending.append(a))
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    yield
    transaction.rollback()
    connection.close()


@pytest.fixture
def extractor(tx):
    fake = FakeExtractor()
    app.state.extractor = fake
    return fake


def api(email):
    return DrainingClient(app, headers=auth_header(email))


def client_id(name):
    with db_module.SessionLocal() as db:
        return str(db.scalar(select(Client.id).where(Client.name == name)))


def upload(email="pic.alpha@amiga.test", client="PT Klien Alpha", pdf=None, filename="invoice.pdf", **form):
    data = {"client_id": client_id(client), "request_type": "Pembayaran vendor", "channel": "Email",
            "submitted_date": "2026-10-14", **form}
    return api(email).post("/documents", data=data,
                           files={"file": (filename, pdf if pdf is not None else make_pdf(), "application/pdf")})


def detail(doc_id, email="pic.alpha@amiga.test"):
    return api(email).get(f"/documents/{doc_id}").json()


def codes(doc):
    return sorted((i["code"], i["field"]) for i in doc["issues"])


# --- F1: unggah ---

def test_upload_issues_request_id_queued_then_ready_for_review(extractor):
    r = upload()
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "QUEUED"
    assert re.fullmatch(r"REQ-\d{8}-[0-9A-F]{6}", body["request_id"])
    assert body["channel"] == "Email"

    doc = detail(body["id"])
    assert doc["status"] == "READY_FOR_REVIEW"
    assert doc["issues"] == []
    assert doc["assigned_reviewer"] in ALPHA_REVIEWERS


def test_uat2_multi_line_items_are_all_read_and_total_correct(extractor):
    doc = detail(upload().json()["id"])
    lines = doc["extraction"]["line_items"]
    assert [line["description"] for line in lines] == ["Kertas A4", "Tinta printer", "Map plastik"]
    assert sum(Decimal(line["subtotal"]) for line in lines) == Decimal(doc["extraction"]["total"])


@pytest.mark.parametrize("pdf, filename, message", [
    (b"bukan pdf", "invoice.docx", "format PDF"),
    (make_pdf(6), "invoice.pdf", "6 halaman"),
    (b"%PDF-1.4 rusak", "invoice.pdf", "rusak"),
])
def test_invalid_files_are_rejected_with_clear_message(extractor, pdf, filename, message):
    r = upload(pdf=pdf, filename=filename)
    assert r.status_code == 422
    assert message in r.json()["detail"]
    assert api("pic.alpha@amiga.test").get("/documents").json() == []


def test_five_pages_is_accepted(extractor):
    assert upload(pdf=make_pdf(5)).json()["page_count"] == 5


def test_channel_is_required_and_limited(extractor):
    assert upload(channel="Telepati").status_code == 422


@pytest.mark.parametrize("email", ["reviewer1@amiga.test", "lead@amiga.test", "admin@amiga.test"])
def test_only_pic_and_intake_can_upload(extractor, email):
    assert upload(email=email).status_code == 403


def test_pic_cannot_upload_for_other_client(extractor):
    assert upload(email="pic.alpha@amiga.test", client="PT Klien Beta").status_code == 403


def test_intake_uploads_on_behalf_of_delegating_pic(extractor):
    body = upload(email="intake@amiga.test").json()
    assert body["uploaded_by"] == "Sari (Intake Support)"
    assert body["on_behalf_of"] == "Rina (PIC Alpha)"


def test_reviewer_is_never_the_uploader(extractor):
    # multi@ = Intake Support + Finance Reviewer untuk Alpha
    doc = detail(upload(email="multi@amiga.test").json()["id"], email="multi@amiga.test")
    assert doc["status"] == "READY_FOR_REVIEW"
    assert doc["assigned_reviewer"] != "Yoga (Intake + Reviewer)"


def test_reviewer_with_fewest_pending_is_assigned(extractor):
    assigned = []
    for n in range(3):
        extractor.result = invoice(invoice_no=f"INV-10{n}")
        assigned.append(detail(upload().json()["id"])["assigned_reviewer"])
    # Tiga dokumen tersebar ke tiga reviewer Alpha, satu per orang
    assert set(assigned) == ALPHA_REVIEWERS


# --- F2/F3: ekstraksi dan verifikasi ---

def test_uat3_missing_account_number(extractor):
    extractor.result = invoice(account_no=None)
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION"
    assert codes(doc) == [("MISSING_EVIDENCE", "account_no")]
    assert "Nomor rekening" in doc["issues"][0]["message"]


def test_calculation_discrepancy(extractor):
    extractor.result = invoice(total=Decimal(950000))
    doc = detail(upload().json()["id"])
    assert codes(doc) == [("CALCULATION_DISCREPANCY", "total")]


def test_uat4_duplicate_with_formatting_variants(extractor):
    first = upload().json()
    extractor.result = invoice(invoice_no="inv 001", vendor_name="PT. VENDOR JAYA")
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION"
    assert codes(doc) == [("POSSIBLE_DUPLICATE", "invoice_no")]
    assert first["request_id"] in doc["issues"][0]["message"]


def test_same_invoice_at_other_client_is_not_a_duplicate(extractor):
    upload()
    doc = detail(upload(email="pic.beta@amiga.test", client="PT Klien Beta").json()["id"],
                 email="pic.beta@amiga.test")
    assert doc["status"] == "READY_FOR_REVIEW"


def test_extraction_failure_keeps_document_and_reviewer_can_reprocess(extractor):
    extractor.result = ExtractionError("Bedrock tidak tersedia")
    doc = detail(upload().json()["id"])
    assert doc["status"] == "EXCEPTION"
    assert codes(doc) == [("EXTRACTION_FAILED", None)]

    assert api("pic.alpha@amiga.test").post(f"/documents/{doc['id']}/reprocess").status_code == 403
    extractor.result = invoice()
    assert api("reviewer1@amiga.test").post(f"/documents/{doc['id']}/reprocess").status_code == 200
    again = detail(doc["id"])
    assert again["status"] == "READY_FOR_REVIEW"
    assert again["request_id"] == doc["request_id"]


def test_reprocess_only_for_failed_extraction(extractor):
    doc_id = upload().json()["id"]
    assert api("reviewer1@amiga.test").post(f"/documents/{doc_id}/reprocess").status_code == 409


# --- Perbaikan PIC (UAT 8) ---

def test_uat8_pic_fix_reextracts_with_same_request_id_and_keeps_pic_value(extractor):
    extractor.result = invoice(account_no=None)  # PDF memang tidak memuat nomor rekening
    first = detail(upload().json()["id"])
    assert first["status"] == "EXCEPTION"

    r = api("pic.alpha@amiga.test").post(f"/documents/{first['id']}/fix",
                                         json={"fields": {"account_no": "9876543210"}})
    assert r.status_code == 200
    assert r.json()["status"] == "PROCESSING"

    doc = detail(first["id"])
    assert doc["request_id"] == first["request_id"]
    assert doc["status"] == "READY_FOR_REVIEW"
    assert doc["extraction"]["account_no"] == "9876543210"  # tidak ditimpa hasil AI yang kosong
    assert doc["pic_overrides"] == {"account_no": "9876543210"}
    assert extractor.calls == 2

    with db_module.SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.action == "FIXED_BY_PIC")
                        .order_by(AuditLog.id.desc()).limit(1))
    assert (log.field, log.old_value, log.new_value) == ("account_no", None, "9876543210")


def test_fix_only_when_exception(extractor):
    doc_id = upload().json()["id"]
    r = api("pic.alpha@amiga.test").post(f"/documents/{doc_id}/fix", json={"fields": {"account_no": "1"}})
    assert r.status_code == 409


@pytest.mark.parametrize("fields, message", [
    ({"status": "READY_FOR_REVIEW"}, "tidak bisa diperbaiki"),
    ({"total": "1.250.000"}, "angka"),
    ({"invoice_date": "14/10/2026"}, "YYYY-MM-DD"),
    ({}, "minimal satu"),
])
def test_invalid_fix_is_rejected(extractor, fields, message):
    extractor.result = invoice(account_no=None)
    doc_id = upload().json()["id"]
    r = api("pic.alpha@amiga.test").post(f"/documents/{doc_id}/fix", json={"fields": fields})
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_reviewer_cannot_send_pic_fix(extractor):
    extractor.result = invoice(account_no=None)
    doc_id = upload().json()["id"]
    r = api("reviewer1@amiga.test").post(f"/documents/{doc_id}/fix", json={"fields": {"account_no": "1"}})
    assert r.status_code == 403


# --- Isolasi klien di level dokumen (UAT 6) ---

def test_uat6_other_client_cannot_open_document_or_file(extractor):
    doc_id = upload().json()["id"]
    beta = api("pic.beta@amiga.test")
    assert beta.get(f"/documents/{doc_id}").status_code == 403
    assert beta.get(f"/documents/{doc_id}/file").status_code == 403
    assert beta.get("/documents").json() == []


def test_assigned_users_can_download_original_pdf(extractor):
    pdf = make_pdf(2)
    doc_id = upload(pdf=pdf).json()["id"]
    r = api("reviewer2@amiga.test").get(f"/documents/{doc_id}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == pdf


def test_list_filters_by_status(extractor):
    upload()
    extractor.result = invoice(invoice_no="INV-009", account_no=None)
    upload()
    pic = api("pic.alpha@amiga.test")
    assert [d["status"] for d in pic.get("/documents", params={"status": "EXCEPTION"}).json()] == ["EXCEPTION"]
    assert len(pic.get("/documents").json()) == 2


def test_status_changes_are_audited(extractor):
    doc_id = upload().json()["id"]
    with db_module.SessionLocal() as db:
        rows = db.execute(select(AuditLog.action, AuditLog.status_after)
                          .where(AuditLog.document_id == doc_id).order_by(AuditLog.id)).all()
    assert [tuple(r) for r in rows] == [
        ("DOCUMENT_UPLOADED", "QUEUED"), ("STATUS_CHANGED", "PROCESSING"),
        ("EXTRACTED", None), ("STATUS_CHANGED", "READY_FOR_REVIEW"),
    ]
