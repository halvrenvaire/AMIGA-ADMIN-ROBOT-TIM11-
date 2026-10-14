"""Data referensi vendor, penanda tangan voucher, daftar voucher, dan metrik dashboard."""
import io
import re
from datetime import date, timedelta
from decimal import Decimal

from pypdf import PdfReader

from tests.test_documents import api, client_id, detail, extractor, invoice, tx, upload  # noqa: F401
from tests.test_review import NAMES

ALPHA = "PT Klien Alpha"


def add_vendor(email="pic.alpha@amiga.test", client=ALPHA, **kw):
    body = {"client_id": client_id(client), "name": "PT Vendor Jaya", "npwp": "01.234.567.8-901.000",
            "bank_name": "BCA", "account_no": "1234567890", **kw}
    return api(email).post("/vendors", json=body)


def add_signatory(kind, name, position, default=True, email="pic.alpha@amiga.test"):
    return api(email).post("/signatories", json={"client_id": client_id(ALPHA), "kind": kind, "full_name": name,
                                                  "position": position, "is_default": default}).json()


def approve(doc):
    return api(NAMES[doc["assigned_reviewer"]]).post(f"/documents/{doc['id']}/approve").json()


# --- Vendor ---

def test_pic_registers_vendor_and_duplicates_are_rejected(tx):
    r = add_vendor()
    assert r.status_code == 201
    assert r.json()["client"]["name"] == ALPHA
    dup = add_vendor(name="pt. VENDOR jaya")  # format berbeda, nama sama
    assert dup.status_code == 409
    assert "sudah terdaftar" in dup.json()["detail"]
    check = api("pic.alpha@amiga.test").get("/vendors/check", params={"client_id": client_id(ALPHA), "name": "PT  Vendor-Jaya"})
    assert check.json()["exists"] is True


def test_same_vendor_name_allowed_for_other_client(tx):
    assert add_vendor().status_code == 201
    assert add_vendor(email="pic.beta@amiga.test", client="PT Klien Beta").status_code == 201


def test_vendor_list_is_isolated_per_client(tx):
    add_vendor(name="Vendor Khusus Alpha")
    names = [v["name"] for v in api("pic.beta@amiga.test").get("/vendors").json()]
    assert "Vendor Khusus Alpha" not in names
    assert add_vendor(email="pic.beta@amiga.test", client=ALPHA).status_code == 403


def test_reviewer_can_read_but_not_create_vendor(tx):
    add_vendor()
    assert [v["name"] for v in api("reviewer1@amiga.test").get("/vendors").json()] == ["PT Vendor Jaya"]
    assert add_vendor(email="reviewer1@amiga.test").status_code == 403


def test_vendor_update_and_deactivate(tx):
    vid = add_vendor().json()["id"]
    pic = api("pic.alpha@amiga.test")
    r = pic.put(f"/vendors/{vid}", json={"name": "PT Vendor Jaya Abadi", "bank_name": "Mandiri"})
    assert r.json()["name"] == "PT Vendor Jaya Abadi" and r.json()["bank_name"] == "Mandiri"
    assert pic.patch(f"/vendors/{vid}/active", json={"is_active": False}).json()["is_active"] is False
    assert pic.get("/vendors").json() == []
    assert len(pic.get("/vendors", params={"include_inactive": True}).json()) == 1


def test_documents_are_linked_to_vendor_by_normalized_name(extractor):
    doc = upload().json()  # vendor hasil AI: "PT Vendor Jaya"
    assert detail(doc["id"])["vendor"] is None
    vendor = add_vendor(name="pt vendor jaya").json()  # vendor didaftarkan setelahnya
    assert detail(doc["id"])["vendor"]["id"] == vendor["id"]
    assert vendor["documents"] == 1
    extractor.result = invoice(invoice_no="INV-777")
    assert detail(upload().json()["id"])["vendor"]["id"] == vendor["id"]  # dokumen baru langsung tertaut


# --- Penanda tangan ---

def test_only_one_default_pengaju(tx):
    first = add_signatory("PENGAJU", "Rina Kartika", "Staf Keuangan")
    add_signatory("PENGAJU", "Andi", "Manajer Keuangan")
    sigs = {s["full_name"]: s for s in api("pic.alpha@amiga.test").get("/signatories").json()}
    assert sigs["Andi"]["is_default"] is True and sigs["Rina Kartika"]["is_default"] is False
    assert first["kind"] == "PENGAJU"


def test_only_pic_manages_signatories(tx):
    r = api("intake@amiga.test").post("/signatories", json={"client_id": client_id(ALPHA), "kind": "PENYETUJU",
                                                             "full_name": "X", "position": "Direktur"})
    assert r.status_code == 403


def test_upload_uses_default_signers_and_voucher_prints_them(extractor):
    add_signatory("PENGAJU", "Rina Kartika", "Staf Keuangan")
    add_signatory("PENYETUJU", "Budi Santoso", "Direktur")
    add_signatory("PENYETUJU", "Sari Dewi", "Bendahara")
    add_signatory("PENYETUJU", "Tidak Dipakai", "Komisaris", default=False)
    doc = detail(upload().json()["id"])
    assert [(s["kind"], s["name"]) for s in doc["signers"]] == [
        ("PENGAJU", "Rina Kartika"), ("PENYETUJU", "Budi Santoso"), ("PENYETUJU", "Sari Dewi")]

    approve(doc)
    pdf = api("pic.alpha@amiga.test").get(f"/documents/{doc['id']}/voucher").content
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))
    for expected in ("Diajukan oleh", "Rina Kartika", "Staf Keuangan", "Diverifikasi oleh AMIGA",
                     "Budi Santoso", "Direktur", "Sari Dewi", "Bendahara"):
        assert expected in text
    assert "Tidak Dipakai" not in text


def test_pic_can_change_signers_until_voucher_issued(extractor):
    andi = add_signatory("PENYETUJU", "Andi", "Direktur", default=False)
    doc = detail(upload().json()["id"])
    pic = api("pic.alpha@amiga.test")
    r = pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": [andi["id"]]})
    assert [s["name"] for s in r.json()["signers"]] == ["Andi"]
    approve(doc)
    assert pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": []}).status_code == 409


def test_signer_limits_and_ownership(extractor):
    ids = [add_signatory("PENYETUJU", f"P{i}", "Direktur", default=False)["id"] for i in range(4)]
    doc = upload().json()
    pic = api("pic.alpha@amiga.test")
    assert pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": ids}).status_code == 422
    beta_sig = api("pic.beta@amiga.test").post("/signatories", json={
        "client_id": client_id("PT Klien Beta"), "kind": "PENYETUJU", "full_name": "Beta", "position": "Direktur"}).json()
    assert pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": [beta_sig["id"]]}).status_code == 422


def test_upload_with_explicit_empty_signers(extractor):
    add_signatory("PENGAJU", "Rina Kartika", "Staf Keuangan")
    doc = detail(upload(signatory_ids="").json()["id"])
    assert doc["signers"] == []


# --- Daftar voucher ---

def test_voucher_list_filters(extractor):
    a = detail(upload().json()["id"])
    approve(a)
    extractor.result = invoice(invoice_no="INV-B1", vendor_name="CV Lain")
    b = detail(upload(email="pic.beta@amiga.test", client="PT Klien Beta").json()["id"], email="pic.beta@amiga.test")
    approve(b)
    api("pic.alpha@amiga.test").get(f"/documents/{a['id']}/voucher", params={"download": True})

    lead = api("lead@amiga.test")
    rows = lead.get("/vouchers").json()
    assert {r["request_id"] for r in rows} == {a["request_id"], b["request_id"]}
    assert [r["request_id"] for r in lead.get("/vouchers", params={"status": "SENT_TO_CLIENT"}).json()] == [a["request_id"]]
    assert [r["vendor_name"] for r in lead.get("/vouchers", params={"vendor": "cv lain"}).json()] == ["CV Lain"]
    assert [r["client"]["name"] for r in lead.get("/vouchers", params={"client_id": client_id(ALPHA)}).json()] == [ALPHA]
    assert len(api("pic.alpha@amiga.test").get("/vouchers").json()) == 1  # isolasi klien


# --- Metrik dashboard ---

def test_metrics_cover_status_trend_speed_quality_and_value(extractor):
    a = detail(upload(due_date=(date.today() + timedelta(days=3)).isoformat()).json()["id"])
    approve(a)
    extractor.result = invoice(invoice_no="INV-M2", account_no=None)
    upload()
    m = api("lead@amiga.test").get("/dashboard/metrics", params={"days": 7}).json()
    assert m["received"] == 2 and m["approved"] == 1
    assert m["status_counts"]["AMIGA_REVIEWED"] == 1 and m["status_counts"]["EXCEPTION"] == 1
    assert len(m["trend"]) == 7 and m["trend"][-1]["received"] == 2 and m["trend"][-1]["approved"] == 1
    assert m["trend"][-1]["exception"] == 1
    assert m["avg_hours_to_voucher"] is not None and m["sla_on_time"] == 1 and m["sla_total"] == 1
    assert (m["first_pass"], m["first_pass_total"]) == (1, 2)
    assert m["top_issues"][0]["code"] == "MISSING_EVIDENCE"
    assert Decimal(m["total_value"]) == Decimal(900000)
    assert m["top_vendors"][0]["vendor"] == "PT Vendor Jaya"


def test_metrics_are_isolated(extractor):
    approve(detail(upload().json()["id"]))
    m = api("pic.beta@amiga.test").get("/dashboard/metrics").json()
    assert m["approved"] == 0 and Decimal(m["total_value"]) == 0
    assert api("admin@amiga.test").get("/dashboard/metrics").status_code == 403
