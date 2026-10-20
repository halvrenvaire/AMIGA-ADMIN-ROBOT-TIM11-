"""Pajak tahap 9 (feedback owner 20 Okt 2026): pengaturan PPN dan PPh per baris.

Contoh utama: AC Split 2 x 1.000.000 + jasa pemasangan 500.000 + PPN 11% 275.000 = 2.775.000.
PPh 23 hanya dipotong dari jasa: 2% x 500.000 = 10.000 (bukan 50.000 dari seluruh invoice).
"""
import re
from decimal import Decimal

import pytest

from app.main import app
from app.services import tax_service
from app.services.bedrock_client import BedrockError
from app.services.extraction_service import ExtractedLine
from tests.test_documents import api, detail, extractor, invoice, send, tx, upload  # noqa: F401
from tests.test_reference import approve
from tests.test_review import edit_file
from tests.test_tax import PIC, pdf_text, set_tax

AC = ExtractedLine("AC Split 1 PK", Decimal(2), Decimal(1000000), Decimal(2000000))
PASANG = ExtractedLine("Jasa pemasangan AC", Decimal(1), Decimal(500000), Decimal(500000))
PPN = ExtractedLine("PPN 11%", None, None, Decimal(275000))


def ac_invoice(**kw):
    return invoice(vendor_name="PT Sejuk Selalu", invoice_no="INV-AC-01", line_items=[AC, PASANG, PPN],
                   total=Decimal(2775000), **kw)


def draft_id(extractor, result=None):
    extractor.result = result or ac_invoice()
    return upload(submit=False).json()["id"]


def per_line(doc_id, assign, npwp=True, vat=None, extra=None):
    lines = [{"index": i, "pph": code} for i, code in assign.items()] + (extra or [])
    body = {"mode": "line", "npwp": npwp, "lines": lines}
    if vat:
        body["vat"] = vat
    return set_tax(doc_id, **body)


def voucher_text(doc_id):
    send(doc_id)
    approve(detail(doc_id))
    return pdf_text(api(PIC).get(f"/documents/{doc_id}/voucher").content)


# --- Saran per baris ---

def test_rules_suggest_pph_per_line_without_ai(extractor):
    doc = detail(draft_id(extractor))
    sugg = doc["files"][0]["data"]["line_suggestions"]
    assert [s and (s["code"], s["source"]) for s in sugg] == [("NONE", "aturan"), ("PPH23", "aturan"), None]


def test_ai_recommendation_is_saved_as_suggestion_only(extractor, monkeypatch):
    doc_id = draft_id(extractor)

    class FakeBedrock:
        def generate(self, *a, **kw):
            return '{"lines": [{"no": 1, "code": "NONE", "reason": "Pembelian barang"}, ' \
                   '{"no": 2, "code": "PPH21", "reason": "Jasa pemasangan"}]}'

    monkeypatch.setattr(app.state, "bedrock", FakeBedrock(), raising=False)
    r = api(PIC).post(f"/documents/{doc_id}/files/1/tax/ai-suggest")
    assert r.status_code == 200
    data = r.json()["files"][0]["data"]
    # PPh 21 untuk PT dikoreksi ke PPh 23; saran tidak langsung diterapkan
    assert [s and (s["code"], s["source"]) for s in data["line_suggestions"]] == [
        ("NONE", "ai"), ("PPH23", "ai"), None]
    assert "tax" not in data
    # Rincian berubah: saran AI lama tidak berlaku lagi, kembali ke aturan
    lines = data["line_items"]
    lines[1]["description"] = "Jasa servis AC"
    data = edit_file(doc_id, line_items=lines).json()["files"][0]["data"]
    assert data["line_suggestions"][1]["source"] == "aturan"


def test_ai_unavailable_returns_clear_message(extractor, monkeypatch):
    doc_id = draft_id(extractor)

    class Down:
        def generate(self, *a, **kw):
            raise BedrockError("kredensial ditolak")

    monkeypatch.setattr(app.state, "bedrock", Down(), raising=False)
    r = api(PIC).post(f"/documents/{doc_id}/files/1/tax/ai-suggest")
    assert r.status_code == 503 and "Saran berbasis aturan tetap dapat Anda gunakan" in r.json()["detail"]
    assert detail(doc_id)["files"][0]["data"]["line_suggestions"][1]["code"] == "PPH23"


# --- PPh per baris ---

def test_pph_only_on_selected_lines(extractor):
    doc_id = draft_id(extractor)
    r = per_line(doc_id, {0: None, 1: "PPH23"})
    assert r.status_code == 200
    tax = r.json()["files"][0]["data"]["tax"]
    assert (tax["mode"], tax["amount"]) == ("line", "10000")
    assert [(g["code"], g["base"], g["amount"], g["lines"]) for g in tax["groups"]] == [("PPH23", "500000", "10000", [1])]
    summary = r.json()["tax_summary"]
    assert Decimal(summary["net"]) == Decimal(2765000)
    assert summary["lines"][0]["detail"] == "Jasa pemasangan AC"
    # Satu jenis untuk seluruh invoice: 2% x 2.500.000 = 50.000 (pembanding)
    assert set_tax(doc_id, code="PPH23").json()["files"][0]["data"]["tax"]["amount"] == "50000"


def test_multi_select_lines_and_several_pph_types(extractor):
    lines = [AC, PASANG, ExtractedLine("Jasa servis berkala", Decimal(1), Decimal(300000), Decimal(300000)),
             ExtractedLine("Sewa ruang gudang", Decimal(1), Decimal(1000000), Decimal(1000000))]
    doc_id = draft_id(extractor, invoice(vendor_name="PT Sejuk Selalu", line_items=lines, total=Decimal(3800000)))
    tax = per_line(doc_id, {1: "PPH23", 2: "PPH23", 3: "PPH4_2"}).json()["files"][0]["data"]["tax"]
    assert [(g["code"], g["base"], g["amount"]) for g in tax["groups"]] == [
        ("PPH23", "800000", "16000"), ("PPH4_2", "1000000", "100000")]
    text = voucher_text(doc_id)
    # Potongan per jenis tepat di bawah barang terakhir yang dipotong jenis itu
    assert re.search(r"3 Jasa servis berkala .*? 4 Potongan PPh 23 2% x DPP Rp ?800\.000 "
                     r"\(Jasa pemasangan AC, Jasa servis berkala\) \(Rp ?16\.000\) 5 Sewa ruang gudang", text)
    assert re.search(r"6 Potongan PPh 4 ayat 2 \(final\) 10% x DPP Rp ?1\.000\.000 \(Sewa ruang gudang\)", text)
    assert re.search(r"TOTAL DIBAYARKAN Rp ?3\.684\.000", text)


def test_no_npwp_doubles_pph23_per_line(extractor):
    tax = per_line(draft_id(extractor), {1: "PPH23"}, npwp=False).json()["files"][0]["data"]["tax"]
    assert tax["groups"][0]["rate"] == "4" and tax["amount"] == "20000"


def test_line_choice_survives_data_edit_and_is_recomputed(extractor):
    doc_id = draft_id(extractor)
    data = per_line(doc_id, {1: "PPH23"}).json()["files"][0]["data"]
    lines = data["line_items"]
    assert lines[1]["pph"] == "PPH23"
    lines[1]["subtotal"] = "600000"
    lines[1]["unit_price"] = "600000"
    lines[2]["subtotal"] = "286000"
    tax = edit_file(doc_id, line_items=lines, total="2886000").json()["files"][0]["data"]["tax"]
    assert (tax["groups"][0]["base"], tax["amount"]) == ("600000", "12000")


def test_invalid_line_choice_is_rejected(extractor):
    doc_id = draft_id(extractor)
    assert per_line(doc_id, {1: "PPN99"}).status_code == 422
    assert per_line(doc_id, {9: "PPH23"}).status_code == 422


def test_line_mode_with_nothing_selected_means_no_deduction(extractor):
    doc_id = draft_id(extractor)
    r = per_line(doc_id, {})
    assert r.json()["files"][0]["data"]["tax"]["amount"] == "0"
    assert send(doc_id).json()["status"] == "READY_FOR_REVIEW"


# --- PPN ---

def test_default_voucher_merges_ppn_into_items(extractor):
    doc_id = draft_id(extractor)
    per_line(doc_id, {1: "PPH23"})
    text = voucher_text(doc_id)
    assert re.search(r"1 AC Split 1 PK \(2 x Rp ?1\.000\.000, termasuk PPN\) Rp ?2\.220\.000", text)
    assert re.search(r"2 Jasa pemasangan AC \(1 x Rp ?500\.000, termasuk PPN\) Rp ?555\.000 "
                     r"3 Potongan PPh 23 2% x DPP Rp ?500\.000 \(Jasa pemasangan AC\) \(Rp ?10\.000\)", text)
    assert "275.000" not in text
    assert re.search(r"TOTAL DIBAYARKAN Rp ?2\.765\.000", text)


def test_show_ppn_detail_on_voucher(extractor):
    doc_id = draft_id(extractor)
    r = per_line(doc_id, {1: "PPH23"}, vat={"mode": "separate", "rate": "11", "show": True})
    assert r.json()["files"][0]["data"]["tax"]["vat"] == {"mode": "separate", "rate": "11", "show": True}
    text = voucher_text(doc_id)
    assert re.search(r"1 AC Split 1 PK \(2 x Rp ?1\.000\.000\) Rp ?2\.000\.000", text)
    assert re.search(r"3 Potongan PPh 23 .*?\(Rp ?10\.000\) 4 PPN 11% Rp ?275\.000", text)
    assert re.search(r"TOTAL DIBAYARKAN Rp ?2\.765\.000", text)


def test_price_including_ppn_uses_dpp_for_pph(extractor):
    # Struk ritel: harga sudah termasuk PPN 11%, tanpa baris PPN
    lines = [ExtractedLine("Jasa cuci karpet", Decimal(1), Decimal(555000), Decimal(555000)),
             ExtractedLine("Sabun karpet", Decimal(1), Decimal(111000), Decimal(111000))]
    doc_id = draft_id(extractor, invoice(vendor_name="CV Bersih", line_items=lines, total=Decimal(666000)))
    r = per_line(doc_id, {0: "PPH23"}, vat={"mode": "included", "rate": "11", "show": True})
    tax = r.json()["files"][0]["data"]["tax"]
    assert (tax["groups"][0]["base"], tax["amount"]) == ("500000", "10000")
    [vat] = r.json()["tax_summary"]["vat"]
    assert (vat["mode"], Decimal(vat["amount"]), vat["warning"]) == ("included", Decimal(66000), None)
    text = voucher_text(doc_id)
    assert re.search(r"1 Jasa cuci karpet .*?Rp ?500\.000 2 Potongan PPh 23 .*?\(Rp ?10\.000\) "
                     r"3 Sabun karpet .*?Rp ?100\.000 4 PPN 11% Rp ?66\.000", text)
    assert re.search(r"TOTAL DIBAYARKAN Rp ?656\.000", text)


def test_ppn_rate_is_selectable_and_mismatch_only_warns(extractor):
    doc_id = draft_id(extractor)
    r = set_tax(doc_id, code="NONE", vat={"mode": "separate", "rate": "12"})
    [vat] = r.json()["tax_summary"]["vat"]
    assert vat["rate"] == "12" and "berbeda dengan hitungan sistem" in vat["warning"]
    assert "Rp 300.000" in vat["warning"]  # 12% x 2.500.000
    assert Decimal(r.json()["tax_summary"]["net"]) == Decimal(2775000)  # tetap total invoice
    [vat] = set_tax(doc_id, code="NONE", vat={"mode": "separate", "rate": "11"}).json()["tax_summary"]["vat"]
    assert vat["warning"] is None
    assert send(doc_id).json()["status"] == "READY_FOR_REVIEW"  # peringatan tidak memblokir


def test_line_not_subject_to_ppn_gets_no_ppn_share(extractor):
    lines = [AC, ExtractedLine("Ongkos kirim", None, None, Decimal(100000)), ExtractedLine("PPN", None, None, Decimal(220000))]
    doc_id = draft_id(extractor, invoice(line_items=lines, total=Decimal(2320000)))
    r = set_tax(doc_id, code="NONE", lines=[{"index": 1, "vat": False}])
    assert r.json()["tax_summary"]["vat"][0]["warning"] is None  # 11% x 2.000.000 = 220.000
    text = voucher_text(doc_id)
    assert re.search(r"1 AC Split 1 PK .*?Rp ?2\.220\.000 2 Ongkos kirim Rp ?100\.000", text)


def test_pic_can_mark_a_line_as_ppn(extractor):
    lines = [AC, ExtractedLine("Pajak 11%", None, None, Decimal(220000))]
    doc_id = draft_id(extractor, invoice(line_items=lines, total=Decimal(2220000)))
    assert detail(doc_id)["files"][0]["data"]["line_suggestions"][1] is not None  # dianggap barang
    tax = set_tax(doc_id, code="PPH23", lines=[{"index": 1, "kind": "vat"}]).json()["files"][0]["data"]["tax"]
    assert tax["base"] == "2000000" and tax["vat"]["mode"] == "separate"


@pytest.mark.parametrize("mode,show", [("separate", False), ("separate", True), ("included", False), ("included", True)])
def test_voucher_rows_always_sum_to_net(mode, show):
    from types import SimpleNamespace as N
    from app.services.voucher_service import voucher_rows
    data = {"invoice_no": "INV-9", "total": "1110000", "line_items": [
        {"description": "Kursi", "qty": "3", "unit_price": "222000", "subtotal": "666000", "pph": "PPH23"},
        {"description": "Meja", "qty": "1", "unit_price": "333000", "subtotal": "333000"},
        {"description": "Ongkir", "subtotal": "111000", "vat": False}]}
    if mode == "separate":
        data["line_items"][2] = {"description": "PPN 11%", "subtotal": "111000"}
        data["line_items"][0]["subtotal"], data["line_items"][1]["subtotal"] = "600000", "400000"
    data["tax"] = tax_service.build(None, True, None, True, data, mode="line", vat={"mode": mode, "rate": "11", "show": show},
                                    table={"PPH23": N(name="PPh 23", rate_npwp=Decimal(2), rate_no_npwp=Decimal(4))})
    rows, paid = voucher_rows(N(files=[N(data=data)], extraction=None))
    assert sum((a for _, a, cut in rows if not cut), Decimal(0)) == Decimal(1110000)
    assert paid == Decimal(1110000) - Decimal(data["tax"]["amount"])
