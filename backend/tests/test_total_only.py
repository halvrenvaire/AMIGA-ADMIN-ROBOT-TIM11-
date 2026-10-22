"""Tahap 14: mode baca AI "total saja" (bawaan), rekening opsional, profil "Diajukan oleh", dan estimasi biaya AI."""
import base64
import io
import re
from decimal import Decimal

from PIL import Image
from pypdf import PdfReader

from tests.test_documents import api, client_id, detail, extractor, invoice, make_pdf, tx  # noqa: F401
from tests.test_review import edit_file

PIC = "pic.alpha@amiga.test"


def upload(*pdfs, files_extra=None, **form):
    """Unggah seperti layar Pembuatan Voucher yang baru: tanpa mode = TOTAL_ONLY, tanpa rekening, tanpa kanal."""
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor",
            "submitted_date": "2026-10-22", **form}
    files = [("files", (f"inv{i}.pdf", pdf, "application/pdf")) for i, pdf in enumerate(pdfs or [make_pdf()], start=1)]
    return api(PIC).post("/documents", data=data, files=files + (files_extra or []))


def signature_png(fmt="PNG") -> bytes:
    img = Image.new("RGB", (300, 100), "white")
    for x in range(30, 270):
        for y in range(30 + x % 20, 45 + x % 20):  # goresan miring setebal 15 px
            img.putpixel((x, y), (10, 10, 60))
    out = io.BytesIO()
    img.save(out, format=fmt)
    return out.getvalue()


def text_of(pdf: bytes) -> str:
    return re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))


def set_tax(doc_id, position=1, **body):
    return api(PIC).put(f"/documents/{doc_id}/files/{position}/tax", json={"code": "NONE", **body})


def test_default_mode_reads_total_only_and_needs_no_line_items(extractor):
    r = upload()
    assert r.status_code == 201 and r.json()["extraction_mode"] == "TOTAL_ONLY" and r.json()["include_account"] is False
    doc = detail(r.json()["id"])
    assert extractor.modes == ["TOTAL_ONLY"]
    data = doc["files"][0]["data"]
    # Rincian tidak disimpan; uraian awal dari nomor invoice dan vendor
    assert data["line_items"] == [] and data["description"] == "Invoice INV-001 - PT Vendor Jaya"
    assert doc["status"] == "DRAFT" and doc["issues"] == [] and doc["channel"] is None
    assert doc["account_check"]["state"] == "OFF" and doc["payees"] == []


def test_total_only_voucher_prints_one_row_per_invoice(extractor):
    extractor.result = [invoice(), invoice(invoice_no="INV-002", total=Decimal(250000))]
    doc = detail(upload(make_pdf(), make_pdf()).json()["id"])
    edit_file(doc["id"], position=2, description="Sewa proyektor Oktober", invoice_no="INV-002",
              vendor_name="PT Vendor Jaya", invoice_date="2026-10-01", total="250000", line_items=[])
    pdf = api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content
    text = text_of(pdf)
    assert "Invoice INV-001 - PT Vendor Jaya" in text and "Sewa proyektor Oktober" in text
    assert "Kertas A4" not in text  # rincian barang tidak dicetak
    assert "TOTAL DIBAYARKAN" in text and "Rp 1.150.000" in text


def test_submit_needs_description_and_tax(extractor):
    doc = detail(upload().json()["id"])
    edit_file(doc["id"], position=1, description="", invoice_no="INV-001", vendor_name="PT Vendor Jaya",
              invoice_date="2026-10-01", total="900000", line_items=[])
    set_tax(doc["id"])
    r = api(PIC).post(f"/documents/{doc['id']}/submit")
    assert r.status_code == 409 and "uraian transaksi" in r.json()["detail"]
    edit_file(doc["id"], position=1, description="Pembelian ATK Oktober", invoice_no="INV-001",
              vendor_name="PT Vendor Jaya", invoice_date="2026-10-01", total="900000", line_items=[])
    r = api(PIC).post(f"/documents/{doc['id']}/submit")
    assert r.status_code == 200 and r.json()["status"] == "READY_FOR_REVIEW"


def test_total_only_tax_derives_dpp_from_total(extractor):
    extractor.result = invoice(total=Decimal(1110000))
    doc = detail(upload().json()["id"])
    r = set_tax(doc["id"], code="PPH23", vat={"mode": "included", "rate": "11", "show": True})
    tax = r.json()["files"][0]["data"]["tax"]
    # Total 1.110.000 sudah termasuk PPN 11%: DPP 1.000.000, PPN 110.000, PPh 23 2% dari DPP
    assert (tax["base"], tax["amount"]) == ("1000000", "20000")
    summary = r.json()["tax_summary"]
    assert Decimal(summary["vat"][0]["amount"]) == 110000 and Decimal(summary["net"]) == 1090000
    text = text_of(api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content)
    # Rincian PPN dicetak: baris DPP + baris PPN + potongan PPh
    assert "Rp 1.000.000" in text and "PPN 11%" in text and "Rp 110.000" in text and "(Rp 20.000)" in text


def test_tax_can_be_entered_manually_without_calculation(extractor):
    doc = detail(upload().json()["id"])
    r = set_tax(doc["id"], code="PPH23", calc=False, base="800000", vat_amount="88000", amount="15000",
                vat={"mode": "separate", "rate": "11", "show": False})
    tax = r.json()["files"][0]["data"]["tax"]
    assert tax["calc"] is False and (tax["base"], tax["amount"], tax["vat"]["amount"]) == ("800000", "15000", "88000")
    # Harga belum termasuk PPN: 900.000 + PPN manual 88.000 - PPh 15.000
    assert Decimal(r.json()["tax_summary"]["net"]) == 973000
    # Data invoice diedit: angka manual tidak dihitung ulang
    r = edit_file(doc["id"], position=1, description="ATK", invoice_no="INV-001", vendor_name="PT Vendor Jaya",
                  invoice_date="2026-10-01", total="950000", line_items=[])
    assert r.json()["files"][0]["data"]["tax"]["amount"] == "15000"
    assert set_tax(doc["id"], code="PPH23", calc=False, mode="line").status_code == 422


def test_switch_to_itemized_rereads_lines_and_keeps_pic_data(extractor):
    doc = detail(upload().json()["id"])
    edit_file(doc["id"], position=1, description="ATK kantor", invoice_no="INV-001", vendor_name="PT Vendor Jaya Abadi",
              invoice_date="2026-10-01", total="900000", line_items=[])
    set_tax(doc["id"], code="PPH23")
    r = api(PIC).put(f"/documents/{doc['id']}/options", json={"extraction_mode": "ITEMIZED"})
    assert r.status_code == 200 and r.json()["status"] == "PROCESSING"
    after = detail(doc["id"])
    data = after["files"][0]["data"]
    assert extractor.modes == ["TOTAL_ONLY", "ITEMIZED"]
    assert [li["description"] for li in data["line_items"]] == ["Kertas A4", "Tinta printer", "Map plastik"]
    # Isian PIC dan pajak tetap; DPP pajak kini dari rincian
    assert data["vendor_name"] == "PT Vendor Jaya Abadi" and data["description"] == "ATK kantor"
    assert data["tax"]["code"] == "PPH23" and data["tax"]["base"] == "900000"
    assert after["extraction_mode"] == "ITEMIZED" and after["status"] == "DRAFT"

    # Kembali ke total saja: rincian disembunyikan, total tetap
    r = api(PIC).put(f"/documents/{doc['id']}/options", json={"extraction_mode": "TOTAL_ONLY"})
    assert r.json()["files"][0]["data"]["line_items"] == [] and Decimal(r.json()["total"]) == 900000


def test_account_feature_is_an_optional_add_on(extractor):
    doc = detail(upload().json()["id"])
    assert doc["account_check"]["state"] == "OFF"
    r = api(PIC).put(f"/documents/{doc['id']}/options", json={"include_account": True})
    assert r.json()["include_account"] is True and r.json()["account_check"]["state"] == "UNVERIFIED"
    assert [p["account_no"] for p in r.json()["payees"]] == ["1234567890"]
    text = text_of(api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content)
    assert "Rekening tujuan" in text and "BCA 1234567890 a.n. PT Vendor Jaya" in text
    r = api(PIC).put(f"/documents/{doc['id']}/options", json={"include_account": False})
    text = text_of(api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content)
    assert "Rekening tujuan" not in text and "1234567890" not in text


def test_manual_submitter_is_printed_but_not_remembered(extractor):
    r = upload(submitter_source="MANUAL", submitter_name="Rina Kusuma", submitter_position="Manajer Keuangan",
               submitter_company="Divisi Umum",
               files_extra=[("submitter_signature", ("ttd.png", signature_png(), "image/png"))])
    doc = detail(r.json()["id"])
    pengaju = doc["signers"][0]
    assert (pengaju["name"], pengaju["position"], pengaju["company"], pengaju["signature"], pengaju["source"]) == (
        "Rina Kusuma", "Manajer Keuangan", "Divisi Umum", True, "MANUAL")
    assert doc["submitter_signature"] is True
    sim = api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content
    text = text_of(sim)
    assert "Rina Kusuma" in text and "Manajer Keuangan" in text and "Divisi Umum" in text
    assert "Tanda tangan elektronik" in text and "Tanggal: 22-10-2026" in text
    assert len(PdfReader(io.BytesIO(sim)).pages[0].images) >= 1

    # Isian manual tidak diingat: pengajuan berikutnya kembali ke profil PIC (mode bawaan)
    me = api(PIC).get("/auth/me").json()
    assert me["signature_updated_at"] is None and not me["submitter_profile"].get("name")
    again = detail(upload().json()["id"])["signers"][0]
    assert (again["name"], again["position"], again["company"], again["signature"], again["source"]) == (
        "Rina (PIC Alpha)", "PIC Klien", "PT Klien Alpha", False, "PIC")
    # Mode manual wajib nama
    assert upload(submitter_source="MANUAL").status_code == 422


def test_pic_submitter_is_locked_to_account_profile(extractor):
    pic = api(PIC)
    me = pic.patch("/auth/me", json={"submitter_position": "Manajer Keuangan", "submitter_company": "Divisi Umum"})
    assert me.status_code == 200 and me.json()["submitter_profile"]["position"] == "Manajer Keuangan"
    image = "data:image/png;base64," + base64.b64encode(signature_png()).decode()
    assert pic.put("/auth/me/signature", json={"image": image}).status_code == 200
    # Isian manual diabaikan bila mode PIC dipilih
    doc = detail(upload(submitter_source="PIC", submitter_name="Orang Lain").json()["id"])
    pengaju = doc["signers"][0]
    assert (pengaju["name"], pengaju["position"], pengaju["company"], pengaju["signature"], pengaju["source"]) == (
        "Rina (PIC Alpha)", "Manajer Keuangan", "Divisi Umum", True, "PIC")
    # Tanda tangan mode PIC hanya lewat halaman Akun
    assert pic.delete(f"/documents/{doc['id']}/submitter-signature").status_code == 409
    # Ganti ke manual di halaman detail: tanda tangan PIC dilepas
    r = pic.put(f"/documents/{doc['id']}/signers", json={
        "signatory_ids": [], "submitter_source": "MANUAL", "submitter_name": "Andi Wijaya",
        "submitter_position": "Staf Umum"})
    pengaju = r.json()["signers"][0]
    assert (pengaju["name"], pengaju["position"], pengaju["company"], pengaju["signature"], pengaju["source"]) == (
        "Andi Wijaya", "Staf Umum", "PT Klien Alpha", False, "MANUAL")
    # Kembali ke PIC: profil dan tanda tangan akun disalin lagi
    r = pic.put(f"/documents/{doc['id']}/signers", json={"signatory_ids": [], "submitter_source": "PIC"})
    assert r.json()["signers"][0]["name"] == "Rina (PIC Alpha)" and r.json()["submitter_signature"] is True


def test_intake_uses_delegating_pic_profile_or_manual(extractor):
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor",
            "submitted_date": "2026-10-22"}
    files = [("files", ("inv.pdf", make_pdf(), "application/pdf"))]
    intake = api("intake@amiga.test")
    pic_mode = detail(intake.post("/documents", data=data, files=files).json()["id"])["signers"][0]
    assert (pic_mode["name"], pic_mode["source"]) == ("Rina (PIC Alpha)", "PIC")
    manual = intake.post("/documents", data={**data, "submitter_source": "MANUAL", "submitter_name": "Sari"},
                         files=files).json()
    assert detail(manual["id"])["signers"][0]["name"] == "Sari"


def test_signature_can_be_webp_and_changed_on_detail_page(extractor):
    r = upload(submitter_name="Rina Kusuma",
               files_extra=[("submitter_signature", ("ttd.webp", signature_png("WEBP"), "image/webp"))])
    assert r.status_code == 201
    doc_id = r.json()["id"]
    assert detail(doc_id)["submitter_signature"] is True
    assert api(PIC).get(f"/documents/{doc_id}/submitter-signature").headers["content-type"] == "image/png"
    r = api(PIC).delete(f"/documents/{doc_id}/submitter-signature")
    assert r.json()["submitter_signature"] is False and r.json()["signers"][0]["signature"] is False
    image = "data:image/png;base64," + base64.b64encode(signature_png()).decode()
    r = api(PIC).put(f"/documents/{doc_id}/submitter-signature", json={"image": image})
    assert r.json()["signers"][0]["signature"] is True
    bad = upload(files_extra=[("submitter_signature", ("ttd.gif", b"GIF89a....", "image/gif"))])
    assert bad.status_code == 422


def test_ai_usage_estimate_is_for_admin_and_service_lead_only(extractor):
    extractor.result = invoice()
    extractor.result.usage = {"input_tokens": 2000, "output_tokens": 300}
    upload()
    usage = api("lead@amiga.test").get("/dashboard/ai-usage").json()
    total_only = usage["modes"]["TOTAL_ONLY"]
    assert total_only["input_tokens"] >= 2000 and total_only["output_tokens"] >= 300 and usage["total_idr"] >= 0
    assert api("admin@amiga.test").get("/dashboard/ai-usage").status_code == 200
    assert api(PIC).get("/dashboard/ai-usage").status_code == 403
    assert api("reviewer1@amiga.test").get("/dashboard/ai-usage").status_code == 403


def test_old_documents_stay_itemized(tx):
    """Dokumen lama (sebelum Tahap 14) tetap mode rincian dan tanpa rekening di voucher (default kolom database)."""
    from sqlalchemy import text
    from app import db as db_module
    with db_module.SessionLocal() as db:
        defaults = db.execute(text(
            "SELECT column_default FROM information_schema.columns WHERE table_name = 'documents' "
            "AND column_name IN ('extraction_mode', 'include_account') ORDER BY column_name")).scalars().all()
    assert "ITEMIZED" in defaults[0] and "false" in defaults[1]


def test_price_excluding_ppn_adds_ppn_to_the_total(extractor):
    """Tahap 15: "Harga belum termasuk PPN (ditambahkan PPN)": 200.000 dengan PPN 11% = 222.000 di baris voucher."""
    extractor.result = invoice(total=Decimal(200000))
    doc = detail(upload().json()["id"])
    r = set_tax(doc["id"], code="PPH23", vat={"mode": "excluded", "rate": "11", "show": False})
    tax = r.json()["files"][0]["data"]["tax"]
    assert (tax["base"], tax["amount"]) == ("200000", "4000")  # PPh 23 2% dari harga sebelum PPN
    summary = r.json()["tax_summary"]
    assert Decimal(summary["vat"][0]["amount"]) == 22000 and summary["vat"][0]["warning"] is None
    assert (Decimal(summary["gross"]), Decimal(summary["net"])) == (222000, 218000)
    text = text_of(api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content)
    assert "Rp 222.000" in text and "(termasuk PPN)" in text and "(Rp 4.000)" in text
    # Rincian PPN dicetak: harga dan PPN jadi dua baris
    set_tax(doc["id"], code="NONE", vat={"mode": "excluded", "rate": "12", "show": True})
    text = text_of(api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content)
    assert "Rp 200.000" in text and "PPN 12%" in text and "Rp 24.000" in text and "Rp 224.000" in text
