"""Tahap 4 feedback owner: pajak per invoice, tarif sesuai NPWP, saran AI, voucher membayar nilai bersih."""
import io
import re
from decimal import Decimal

from pypdf import PdfReader
from sqlalchemy import select

from app import db as db_module
from app.models import AuditLog, User, Vendor
from app.services import tax_service
from app.services.extraction_service import ExtractedLine
from app.services.verification import normalize
from tests.test_documents import api, client_id, detail, extractor, invoice, send, tx, upload  # noqa: F401
from tests.test_reference import approve
from tests.test_review import edit_file

PIC = "pic.alpha@amiga.test"
JASA = [ExtractedLine("Jasa konsultan pajak Oktober", Decimal(1), Decimal(900000), Decimal(900000))]


def pdf_text(content: bytes) -> str:
    return re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages))


def draft(**kw):
    return detail(upload(submit=False, **kw).json()["id"])


def set_tax(doc_id, position=1, email=PIC, **body):
    return api(email).put(f"/documents/{doc_id}/files/{position}/tax", json=body)


def add_vendor(name, npwp):
    with db_module.SessionLocal() as db:
        creator = db.scalar(select(User.id).where(User.email == PIC))
        db.add(Vendor(client_id=client_id("PT Klien Alpha"), name=name, name_norm=normalize(name), npwp=npwp,
                      created_by=creator))
        db.commit()


def test_ai_only_suggests_and_pic_must_choose_before_sending(extractor):
    doc = draft()
    data = doc["files"][0]["data"]
    assert "tax" not in data and data["tax_suggestion"]["code"] == "NONE" and data["tax_suggestion"]["source"] == "aturan"
    assert doc["tax_summary"]["tax_total"] == "0" and doc["tax_summary"]["net"] == doc["tax_summary"]["gross"]
    r = api(PIC).post(f"/documents/{doc['id']}/submit")
    assert r.status_code == 409 and "Pilih pajak dulu untuk bukti 1" in r.json()["detail"]
    assert set_tax(doc["id"], code="NONE").status_code == 200
    assert api(PIC).post(f"/documents/{doc['id']}/submit").json()["status"] == "READY_FOR_REVIEW"


def test_service_invoice_is_suggested_pph23_and_net_is_paid(extractor):
    extractor.result = invoice(line_items=JASA)
    doc = draft()
    assert doc["files"][0]["data"]["tax_suggestion"]["code"] == "PPH23"
    doc = set_tax(doc["id"], code="PPH23").json()
    tax = doc["files"][0]["data"]["tax"]
    assert (tax["code"], tax["rate"], tax["base"], tax["amount"], tax["npwp"]) == ("PPH23", "2", "900000", "18000", True)
    assert Decimal(doc["tax_summary"]["net"]) == Decimal(882000)


def test_rate_follows_vendor_npwp_from_reference_data(extractor):
    add_vendor("PT Vendor Jaya", npwp=None)
    extractor.result = invoice(line_items=JASA)
    doc = draft()
    assert doc["files"][0]["data"]["npwp_known"] is False
    # Layar PIC memilih "Tidak punya NPWP" sesuai data referensi; tarif tanpa NPWP dipakai
    tax = set_tax(doc["id"], code="PPH23", npwp=False).json()["files"][0]["data"]["tax"]
    assert tax["rate"] == "4" and tax["amount"] == "36000"


def test_pic_chooses_tax_and_change_is_audited(extractor):
    doc = draft()
    r = set_tax(doc["id"], code="PPH4_2", npwp=True, base="500000")
    assert r.status_code == 200
    tax = r.json()["files"][0]["data"]["tax"]
    assert (tax["code"], tax["amount"], tax["base_auto"], tax["source"]) == ("PPH4_2", "50000", False, "pic")
    assert Decimal(r.json()["tax_summary"]["net"]) == Decimal(850000)
    with db_module.SessionLocal() as db:
        log = db.scalars(select(AuditLog).where(AuditLog.document_id == doc["id"], AuditLog.field.like("%.pajak"))).all()
    assert len(log) == 1 and log[0].old_value is None and "PPh 4 ayat 2" in log[0].new_value
    # Tanpa NPWP memakai tarif tanpa NPWP
    tax = set_tax(doc["id"], code="PPH23", npwp=False).json()["files"][0]["data"]["tax"]
    assert (tax["rate"], tax["amount"]) == ("4", "36000")


def test_editing_invoice_data_keeps_tax_and_recomputes_it(extractor):
    extractor.result = invoice(line_items=JASA)
    doc = set_tax(draft()["id"], code="PPH23").json()
    lines = doc["files"][0]["data"]["line_items"]
    lines[0]["subtotal"] = "1000000"
    r = edit_file(doc["id"], line_items=lines, total="1000000")
    tax = r.json()["files"][0]["data"]["tax"]
    assert tax["code"] == "PPH23" and tax["amount"] == "20000"
    assert r.json()["files"][0]["data"]["tax_suggestion"]["code"] == "PPH23"


def test_vat_line_is_not_part_of_the_tax_base(extractor):
    extractor.result = invoice(line_items=JASA + [ExtractedLine("PPN 11%", None, None, Decimal(99000))],
                               total=Decimal(999000))
    tax = set_tax(draft()["id"], code="PPH23").json()["files"][0]["data"]["tax"]
    assert tax["base"] == "900000" and tax["amount"] == "18000"


def test_reimburse_is_not_deducted(extractor):
    extractor.result = invoice(line_items=JASA)
    suggestion = draft(request_type="Voucher Pengeluaran Reimburse")["files"][0]["data"]["tax_suggestion"]
    assert suggestion["code"] == "NONE"


def test_voucher_shows_deduction_and_pays_net(extractor):
    extractor.result = invoice(line_items=JASA)
    doc_id = upload(submit=False).json()["id"]
    set_tax(doc_id, code="PPH23")
    send(doc_id)
    doc = detail(doc_id)
    approve(doc)
    text = pdf_text(api(PIC).get(f"/documents/{doc['id']}/voucher").content)
    assert "JUMLAH TAGIHAN" in text and "Potongan PPh 23 2% x DPP" in text
    assert re.search(r"TOTAL DIBAYARKAN Rp ?882\.000", text)
    row = next(r for r in api(PIC).get("/vouchers").json() if r["document_id"] == doc["id"])
    assert (Decimal(row["total"]), Decimal(row["gross"]), Decimal(row["tax_total"])) == (882000, 900000, 18000)


def test_tax_only_editable_in_draft_and_unknown_code_rejected(extractor):
    doc = draft()
    assert set_tax(doc["id"], code="PPN99").status_code == 422
    send(doc["id"])
    r = set_tax(doc["id"], code="PPH23")
    assert r.status_code == 409


def test_tax_rate_table_is_editable_by_service_lead_only(extractor):
    rates = api(PIC).get("/tax-rates").json()
    assert [r["code"] for r in rates] == ["NONE", "PPH23", "PPH21", "PPH4_2", "PPH26"]
    assert all("needs_confirmation" in r for r in rates)  # isi awal: true (database test bisa berisi sisa E2E)
    assert api(PIC).put("/tax-rates/PPH23", json={"rate_npwp": "3"}).status_code == 403
    extractor.result = invoice(line_items=JASA)
    doc = draft()
    set_tax(doc["id"], code="PPH23")
    r = api("lead@amiga.test").put("/tax-rates/PPH23", json={"rate_npwp": "3", "needs_confirmation": False})
    assert r.status_code == 200 and Decimal(r.json()["rate_npwp"]) == 3 and not r.json()["needs_confirmation"]
    # Draf lama tetap memakai tarif saat dipilih
    assert detail(doc["id"])["files"][0]["data"]["tax"]["rate"] == "2"
    assert api("lead@amiga.test").put("/tax-rates/NONE", json={"rate_npwp": "1"}).status_code == 422


class FakeBedrock:
    def __init__(self, answer):
        self.answer = answer

    def generate(self, *a, **kw):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_ai_suggestion_is_used_when_valid_and_falls_back_to_rules():
    items = [{"vendor_name": "PT Gedung Megah", "line_items": [{"description": "Sewa ruang kantor"}]},
             {"vendor_name": "PT Toko", "line_items": [{"description": "Kertas"}]}]
    valid = {"NONE", "PPH23", "PPH21", "PPH4_2", "PPH26"}
    ai = tax_service.suggest(FakeBedrock('{"invoices": [{"code": "PPH4_2", "reason": "Sewa ruang kantor"}, '
                                         '{"code": "PPN99"}]}'), items, False, valid)
    assert [(s.code, s.source) for s in ai] == [("PPH4_2", "ai"), ("NONE", "aturan")]
    from app.services.bedrock_client import BedrockError
    rules = tax_service.suggest(FakeBedrock(BedrockError("mati")), items, False, valid)
    assert [(s.code, s.source) for s in rules] == [("PPH4_2", "aturan"), ("NONE", "aturan")]


def test_ai_pph21_for_a_company_is_corrected_to_pph23():
    valid = {"NONE", "PPH23", "PPH21", "PPH4_2", "PPH26"}
    items = [{"vendor_name": "PT Konsultan Prima", "line_items": [{"description": "Jasa konsultasi pajak"}]},
             {"vendor_name": "Budi Santoso", "line_items": [{"description": "Honor narasumber"}]}]
    out = tax_service.suggest(FakeBedrock('{"invoices": [{"code": "PPH21", "reason": "Jasa konsultasi"}, '
                                          '{"code": "PPH21", "reason": "Honor orang pribadi"}]}'), items, False, valid)
    assert [s.code for s in out] == ["PPH23", "PPH21"]


def test_only_pph26_still_needs_confirmation(tx):
    # Tahap 5 (20 Okt 2026): tarif PPh 21, 23, dan 4 ayat 2 dikonfirmasi tim; arti "Ppn 26" dari owner belum jelas
    rates = {r["code"]: r for r in api(PIC).get("/tax-rates").json()}
    assert {code for code, r in rates.items() if r["needs_confirmation"]} == {"PPH26"}
    assert "Ppn 26" in rates["PPH26"]["description"]
