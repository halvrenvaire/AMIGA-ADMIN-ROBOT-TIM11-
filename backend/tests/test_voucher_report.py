"""Rekap voucher PDF untuk Service Lead (1, 7, 30 hari, dan periode kustom)."""
import io
import re
from datetime import date, timedelta

from pypdf import PdfReader

from app.routers.vouchers import report_range
from tests.test_documents import api, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_reference import approve

TODAY = date(2026, 10, 16)


def text_of(pdf: bytes) -> str:
    return re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))


def test_period_ranges():
    assert report_range("1", None, None, TODAY) == (TODAY, TODAY)
    assert report_range("7", None, None, TODAY) == (TODAY - timedelta(days=6), TODAY)
    assert report_range("30", None, None, TODAY) == (TODAY - timedelta(days=29), TODAY)
    assert report_range("custom", date(2026, 10, 1), date(2026, 10, 5), TODAY) == (date(2026, 10, 1), date(2026, 10, 5))


def test_report_lists_vouchers_with_summary(extractor):
    for i, (email, client) in enumerate([("pic.alpha@amiga.test", "PT Klien Alpha"),
                                          ("pic.beta@amiga.test", "PT Klien Beta")]):
        extractor.result = invoice(invoice_no=f"INV-REKAP-{i}")
        approve(detail(upload(email=email, client=client).json()["id"], email=email))
    r = api("lead@amiga.test").get("/vouchers/report", params={"period": "1"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('attachment; filename="rekap-voucher_')
    text = text_of(r.content)
    for expected in ("REKAP VOUCHER HARI INI", "Jumlah voucher", "Rekap per perusahaan", "PT Klien Alpha",
                     "PT Klien Beta", "Rekap per Finance Reviewer", "Daftar voucher", "INV-REKAP-0",
                     "INV-REKAP-1", "Rp 1.800.000", "PIC: Rina (PIC Alpha)", "PIC: Budi (PIC Beta)"):
        assert expected in text, expected


def test_custom_period_outside_vouchers_is_empty(extractor):
    approve(detail(upload().json()["id"]))
    r = api("lead@amiga.test").get("/vouchers/report",
                                   params={"period": "custom", "date_from": "2020-01-01", "date_to": "2020-01-31"})
    assert r.status_code == 200
    assert "Tidak ada voucher" in text_of(r.content)


def test_custom_period_validation_and_role(tx):
    lead = api("lead@amiga.test")
    assert lead.get("/vouchers/report", params={"period": "custom"}).status_code == 422
    assert lead.get("/vouchers/report", params={"period": "custom", "date_from": "2026-10-05",
                                                "date_to": "2026-10-01"}).status_code == 422
    assert lead.get("/vouchers/report", params={"period": "custom", "date_from": "2024-01-01",
                                                "date_to": "2026-01-01"}).status_code == 422
    for email in ("reviewer1@amiga.test", "pic.alpha@amiga.test", "admin@amiga.test"):
        assert api(email).get("/vouchers/report").status_code == 403


def test_intake_upload_lists_delegating_pic(extractor):
    approve(detail(upload(email="intake@amiga.test").json()["id"]))
    rows = api("lead@amiga.test").get("/vouchers").json()
    assert rows[0]["pic_name"] == "Rina (PIC Alpha)"
