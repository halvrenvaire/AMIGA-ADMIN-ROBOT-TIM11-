"""Berkas gabungan (beberapa invoice dalam satu PDF) dipecah per invoice, dan saran PPh 23 atas imbalan jasa.

Kasus acuan: tagihan bulanan jasa pengemudi (DSS), 6 invoice dalam satu PDF 32 halaman. Tiap invoice memisahkan
penggantian biaya (Basic Fee / Overtime) dari imbalan jasa (Management Fee). PPh 23 hanya atas imbalan jasa.
"""
from datetime import date
from decimal import Decimal

from app.services import document_processing, tax_service
from app.services.extraction_service import ExtractedInvoice, parse_response
from app.services.invoice_splitter import PageInfo, Segment, find_segments, slice_pdf
from tests.test_documents import FakeExtractor, api, client_id, detail, extractor, make_pdf, tx  # noqa: F401
from tests.test_total_only import PIC, set_tax, text_of
from pypdf import PdfReader
import io
import pytest
import uuid

VENDOR = "PT Dayakarya Solusi Sejati"

# (nomor invoice, penggantian biaya, imbalan jasa, PPN, total tagihan, PPh 23 yang diharapkan), 6 invoice acuan
DSS = [
    ("005-PI-2604-00322", 6375633, 2304696, 253517, 8933846, 46094),
    ("005-PI-2604-00323", 6375633, 2304696, 253517, 8933846, 46094),
    ("005-PI-2604-00324", 6375633, 2304696, 253517, 8933846, 46094),
    ("005-PI-2604-00325", 6586980, 988047, 108685, 7683712, 19761),
    ("005-PI-2604-00326", 3727690, 559153, 61507, 4348350, 11183),
    ("005-PI-2604-00327", 2625493, 393824, 43321, 3062638, 7876),
]
# Halaman pertama tiap invoice di PDF 32 halaman, dan jumlah halamannya
DSS_PAGES = [4, 4, 4, 7, 6, 7]


def dss_invoice(row) -> ExtractedInvoice:
    number, passthrough, fee, vat, total, _ = row
    assert passthrough + fee + vat == total
    return ExtractedInvoice(vendor_name=VENDOR, invoice_no=number, invoice_date=date(2026, 4, 9), total=Decimal(total),
                            service_fee=Decimal(fee), vat_printed=Decimal(vat))


def dss_page_infos() -> list[PageInfo]:
    infos, start = [], 0
    for (number, *_), pages in zip(DSS, DSS_PAGES):
        infos += [PageInfo(True, number)] + [PageInfo(False, None)] * (pages - 1)
        start += pages
    return infos


class SplittingExtractor(FakeExtractor):
    """Pemeriksa halaman tiruan: mengembalikan bagian invoice yang sudah ditentukan test."""

    def __init__(self, segments):
        super().__init__()
        self.segments = segments
        self.located = 0

    def locate_invoices(self, pdf_bytes):
        self.located += 1
        return list(self.segments), {"input_tokens": 100, "output_tokens": 10}


@pytest.fixture
def auto_split(monkeypatch):
    """Pemecahan otomatis saat unggah (bawaan mati; PIC memakai tombol)."""
    from app.config import settings
    monkeypatch.setattr(settings, "ai_split_auto", True)


def use(extractor_obj):
    from app.main import app
    app.state.extractor = extractor_obj
    return extractor_obj


def upload_combined(pdf, **form):
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor",
            "submitted_date": "2026-10-22", **form}
    return api(PIC).post("/documents", data=data, files=[("files", ("test_invoice dss.pdf", pdf, "application/pdf"))])


# --- Aturan pemecahan (tanpa AI) ---

def test_find_segments_splits_the_dss_file_into_six_invoices():
    segments = find_segments(dss_page_infos())
    assert [(s.start, s.end, s.invoice_no) for s in segments] == [
        (0, 4, "005-PI-2604-00322"), (4, 8, "005-PI-2604-00323"), (8, 12, "005-PI-2604-00324"),
        (12, 19, "005-PI-2604-00325"), (19, 25, "005-PI-2604-00326"), (25, 32, "005-PI-2604-00327")]


def test_find_segments_ignores_repeated_numbers_and_pages_without_number():
    infos = dss_page_infos()
    infos[2] = PageInfo(True, "005-PI-2604-00322")  # Faktur Pajak salah ditandai, nomornya sama dengan invoice di depannya
    infos[1] = PageInfo(True, None)  # ditandai halaman depan tetapi tanpa nomor
    assert len(find_segments(infos)) == 6


def test_find_segments_leaves_single_invoice_and_suspicious_files_alone():
    one = [PageInfo(True, "INV-1")] + [PageInfo(False, None)] * 6
    assert find_segments(one) == []
    assert find_segments([PageInfo(False, None)] * 5) == []
    many = [PageInfo(True, f"INV-{i}") for i in range(5)]
    assert len(find_segments(many, max_invoices=5)) == 5 and find_segments(many, max_invoices=4) == []


def test_pages_before_first_cover_belong_to_first_invoice():
    infos = [PageInfo(False, None), PageInfo(True, "A-1"), PageInfo(False, None), PageInfo(True, "A-2")]
    assert [(s.start, s.end) for s in find_segments(infos)] == [(0, 3), (3, 4)]


def test_slice_pdf_keeps_page_range():
    assert len(PdfReader(io.BytesIO(slice_pdf(make_pdf(10), 3, 7))).pages) == 4


# --- Salinan angka pajak dari invoice ---

def test_parse_response_copies_service_fee_and_printed_vat():
    inv = parse_response('{"document_class":"invoice","vendor_name":"PT Dayakarya Solusi Sejati",'
                         '"invoice_no":"005-PI-2604-00322","total":"8,933,846.00",'
                         '"service_fee":"2,304,696.00","vat_amount":"253,517.00"}')
    assert (inv.total, inv.service_fee, inv.vat_printed) == (Decimal(8933846), Decimal(2304696), Decimal(253517))
    none = parse_response('{"document_class":"invoice","vendor_name":"X","total":"1000","service_fee":null,"vat_amount":"0"}')
    assert none.service_fee is None and none.vat_printed is None


def test_pph23_suggestion_uses_service_fee_as_base():
    data = {"vendor_name": VENDOR, "service_fee": "2304696", "line_items": []}
    sug = tax_service.suggest(None, [data], False, {"NONE", "PPH23"})[0]
    assert sug.code == "PPH23" and sug.base == Decimal(2304696) and "imbalan jasa" in sug.reason
    plain = tax_service.suggest(None, [{"vendor_name": VENDOR, "line_items": []}], False, {"NONE", "PPH23"})[0]
    assert plain.base is None


def test_line_suggestions_tax_only_the_service_fee_line():
    data = {"vendor_name": VENDOR, "service_fee": "2304696", "line_items": [
        {"description": "Total Basic Fee (Fixed) & BPJS - Driver Service", "subtotal": "6375633"},
        {"description": "Total Management Fee & Development - Driver Service", "subtotal": "2304696"},
        {"description": "VAT / PPN", "subtotal": "253517"}]}
    got = tax_service.suggest_lines_by_rules(data, False)
    assert [g and g["code"] for g in got] == ["NONE", "PPH23", None]


# --- Alur lengkap: satu berkas gabungan menjadi satu voucher ---

def test_combined_file_becomes_one_invoice_per_part_with_pph_rows(extractor, auto_split):
    pdf = make_pdf(32)
    segments, start = [], 0
    for (number, *_), pages in zip(DSS, DSS_PAGES):
        segments.append(Segment(start, start + pages, number))
        start += pages
    fake = use(SplittingExtractor(segments))
    fake.result = [dss_invoice(row) for row in DSS]

    r = upload_combined(pdf)
    assert r.status_code == 201
    doc = detail(r.json()["id"])

    assert fake.located == 1 and fake.calls == 6
    assert [(f["position"], f["page_count"]) for f in doc["files"]] == list(enumerate(DSS_PAGES, start=1))
    assert doc["page_count"] == 32 and doc["status"] == "DRAFT", doc["issues"]
    assert [f["data"]["invoice_no"] for f in doc["files"]] == [row[0] for row in DSS]
    assert doc["files"][0]["original_filename"].endswith("invoice 1 (005-PI-2604-00322)")
    # Saran pajak: PPh 23 atas imbalan jasa saja
    for f, row in zip(doc["files"], DSS):
        sug = f["data"]["tax_suggestion"]
        assert sug["code"] == "PPH23" and Decimal(sug["base"]) == row[2]
        assert Decimal(f["data"]["vat_printed"]) == row[3]

    # PIC menerapkan saran (dasar = imbalan jasa), lalu voucher: 6 baris invoice + 6 potongan + total bersih
    for f, row in zip(doc["files"], DSS):
        res = set_tax(doc["id"], f["position"], code="PPH23", base=str(row[2]))
        assert res.status_code == 200, res.text
        assert res.json()["files"][f["position"] - 1]["data"]["tax"]["amount"] == str(row[5])
    pdf_out = api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content
    text = text_of(pdf_out)
    compact = text.replace(" ", "")  # nomor invoice panjang bisa terpotong di akhir baris
    for number, _, _, _, total, cut in DSS:
        assert number in compact
        assert f"{total:,}".replace(",", ".") in text and f"{cut:,}".replace(",", ".") in text
    assert compact.count("PotonganPPh23") == 6
    gross, cuts = sum(r[4] for r in DSS), sum(r[5] for r in DSS)
    assert (gross, cuts, gross - cuts) == (41896238, 177102, 41719136)
    assert "41.719.136" in text and "TOTAL DIBAYARKAN" in text

    history = api(PIC).get(f"/documents/{doc['id']}/history").json()
    assert any(h["action"] == "INVOICES_SPLIT" for h in history)


def test_single_invoice_file_is_not_split(extractor, auto_split):
    fake = use(SplittingExtractor([]))
    r = upload_combined(make_pdf(5))
    doc = detail(r.json()["id"])
    assert fake.located == 1 and fake.calls == 1 and len(doc["files"]) == 1


def test_split_failure_never_blocks_the_document(extractor, auto_split):
    class Broken(SplittingExtractor):
        def locate_invoices(self, pdf_bytes):
            raise RuntimeError("AI mati")

    fake = use(Broken([]))
    doc = detail(upload_combined(make_pdf(5)).json()["id"])
    assert fake.calls == 1 and len(doc["files"]) == 1 and doc["status"] in ("DRAFT", "EXCEPTION")


def test_already_read_files_are_not_split_again(extractor, auto_split):
    fake = use(SplittingExtractor([Segment(0, 2, "A-1"), Segment(2, 4, "A-2")]))
    fake.result = [dss_invoice(DSS[0]), dss_invoice(DSS[1])]
    doc = detail(upload_combined(make_pdf(4)).json()["id"])
    assert len(doc["files"]) == 2 and fake.located == 1
    fake.result = [dss_invoice(DSS[0]), dss_invoice(DSS[1])]
    document_processing.process_document(uuid.UUID(doc["id"]), fake)  # pemrosesan ulang seluruh bukti
    assert fake.located == 1  # bagian yang sudah terbaca tidak diperiksa lagi
    assert len(detail(doc["id"])["files"]) == 2 and fake.calls == 4


# --- Data hasil AI nyata yang sudah terekam (pembacaan PDF DSS 32 halaman). Tanpa memanggil AI. ---

# Halaman yang ditandai AI sebagai halaman depan invoice (nomor halaman mulai 1). Selain 6 yang benar (1, 5, 9, 13, 20, 26),
# AI juga menandai 6 halaman Faktur Pajak dan membaca nomor seri faktur (16-17 digit) sebagai nomor invoice.
REAL_AI_STARTS = {
    1: "005-PI-2604-00322", 3: "04002600121202282", 5: "005-PI-2604-00323", 7: "04002600121201910",
    9: "005-PI-2604-00324", 11: "04002600121201982", 13: "005-PI-2604-00325", 15: "04002600121201790",
    20: "005-PI-2604-00326", 22: "0400260012122029", 26: "005-PI-2604-00327", 28: "04002600121201664",
}


def test_real_ai_output_with_tax_invoice_pages_still_splits_into_six_invoices():
    infos = [PageInfo(page in REAL_AI_STARTS, REAL_AI_STARTS.get(page)) for page in range(1, 33)]
    segments = find_segments(infos)
    assert [(s.start + 1, s.end, s.invoice_no) for s in segments] == [
        (1, 4, "005-PI-2604-00322"), (5, 8, "005-PI-2604-00323"), (9, 12, "005-PI-2604-00324"),
        (13, 19, "005-PI-2604-00325"), (20, 25, "005-PI-2604-00326"), (26, 32, "005-PI-2604-00327")]


# (total, imbalan jasa yang dibaca AI, PPN yang dibaca AI) pada pembacaan nyata, dan apakah angkanya benar
REAL_AI_FEES = [
    ("8933846", "2304696", "253517", True),   # benar
    ("8933846", "5341665", "253517", False),  # AI memilih angka salah
    ("8933846", "4641666", "253517", False),
    ("7683712", "988047", "108685", True),    # benar
    ("4348350", "3727690", "61507", False),   # AI mengambil nilai Overtime
    ("3062638", "3993824", "361321", False),
]


def test_service_fee_must_match_printed_vat_else_it_is_not_used():
    for total, fee, vat, correct in REAL_AI_FEES:
        inv = parse_response(f'{{"document_class":"invoice","vendor_name":"{VENDOR}","invoice_no":"X-1",'
                             f'"total":"{total}","service_fee":"{fee}","vat_amount":"{vat}"}}')
        if correct:
            assert inv.service_fee == Decimal(fee) and inv.service_fee_unverified is None
        else:
            assert inv.service_fee is None and inv.service_fee_unverified == Decimal(fee)
            assert inv.raw["service_fee_rejected"] == fee
    # Tanpa PPN tercetak, angkanya tidak bisa diperiksa dan tetap dipakai (PIC yang memeriksa)
    inv = parse_response(f'{{"document_class":"invoice","vendor_name":"{VENDOR}","total":"1000000","service_fee":"300000"}}')
    assert inv.service_fee == Decimal(300000)


def test_rejected_fee_gives_no_base_in_pph_suggestion():
    inv = parse_response(f'{{"document_class":"invoice","vendor_name":"{VENDOR}","total":"8933846",'
                         f'"service_fee":"5341665","vat_amount":"253517"}}')
    data = document_processing.part_to_data(inv)
    assert "service_fee" not in data and data["service_fee_unverified"] == "5341665"
    assert tax_service.suggest(None, [data], False, {"NONE", "PPH23"})[0].base is None


def test_long_files_are_not_checked_to_protect_token_cost(extractor, auto_split, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ai_split_max_pages", 3)
    fake = use(SplittingExtractor([Segment(0, 2, "A-1"), Segment(2, 4, "A-2")]))
    doc = detail(upload_combined(make_pdf(4)).json()["id"])
    assert fake.located == 0 and len(doc["files"]) == 1


# --- Komponen biaya yang disalin AI (label dan angka persis seperti di invoice DSS); kode yang menentukan imbalan jasa ---

def read_components(components, vat, total="8933846"):
    import json
    return parse_response(json.dumps({"document_class": "invoice", "vendor_name": VENDOR, "invoice_no": "X-1", "total": total,
                                      "components": components, "vat_amount": vat}))


def test_service_fee_is_derived_from_copied_components():
    basic = read_components([{"label": "Total Basic Fee", "amount": "6,375,633.00"},
                             {"label": "Total Overtime", "amount": "0.00"},
                             {"label": "Total Management Fee & Development", "amount": "2,304,696.00"}], "253,517.00")
    assert basic.service_fee == Decimal(2304696) and basic.service_fee_unverified is None
    overtime = read_components([{"label": "Total Basic Fee", "amount": "0.00"},
                                {"label": "Total Overtime", "amount": "6,586,980.00"},
                                {"label": "Total Management Fee & Development", "amount": "988,047.00"}],
                               "108,685.00", total="7683712")
    assert overtime.service_fee == Decimal(988047)


def test_component_fee_still_checked_against_printed_vat():
    wrong = read_components([{"label": "Total Basic Fee", "amount": "6,375,633.00"},
                             {"label": "Total Management Fee & Development", "amount": "2,304,696.00"}], "999,999.00")
    assert wrong.service_fee is None and wrong.service_fee_unverified == Decimal(2304696)


def test_plain_service_fee_line_without_pass_through_is_not_a_pph_base():
    inv = read_components([{"label": "Service Fee", "amount": "500,000.00"}], "55,000.00", total="605000")
    assert inv.service_fee is None and inv.service_fee_unverified is None
    assert read_components([], None).service_fee is None


# --- Tombol "Pisahkan otomatis (AI)": token AI hanya terpakai bila diminta ---

def post_split(doc_id, position=1, email=PIC):
    return api(email).post(f"/documents/{doc_id}/files/{position}/split")


def two_files(combined_pages=4):
    data = {"client_id": client_id("PT Klien Alpha"), "request_type": "Voucher Pengeluaran Vendor",
            "submitted_date": "2026-10-22"}
    files = [("files", ("gabungan.pdf", make_pdf(combined_pages), "application/pdf")),
             ("files", ("satu.pdf", make_pdf(1), "application/pdf"))]
    return api(PIC).post("/documents", data=data, files=files)


def actions(doc_id):
    return [a["action"] for a in api(PIC).get(f"/documents/{doc_id}/history").json()]


def test_upload_does_not_spend_tokens_on_splitting_by_default(extractor):
    fake = use(SplittingExtractor([Segment(0, 2, "A-1"), Segment(2, 4, "A-2")]))
    doc = detail(upload_combined(make_pdf(4)).json()["id"])
    assert fake.located == 0 and fake.calls == 1 and len(doc["files"]) == 1


def test_split_button_splits_only_that_file_and_keeps_the_others(extractor):
    fake = use(SplittingExtractor([Segment(0, 2, "A-1"), Segment(2, 4, "A-2")]))
    fake.result = [dss_invoice(DSS[0]), dss_invoice(DSS[1])]
    doc = detail(two_files().json()["id"])
    assert len(doc["files"]) == 2 and fake.calls == 2 and fake.located == 0
    assert set_tax(doc["id"], 2, code="PPH23", base="1000000").status_code == 200  # pilihan PIC pada bukti lain

    fake.result = [dss_invoice(DSS[3]), dss_invoice(DSS[4])]
    r = post_split(doc["id"], 1)
    assert r.status_code == 200 and r.json()["status"] == "PROCESSING"
    after = detail(doc["id"])
    assert fake.located == 1 and fake.calls == 4  # hanya 2 bagian baru yang dibaca, bukti lain tidak dibaca ulang
    assert [(f["position"], f["page_count"]) for f in after["files"]] == [(1, 2), (2, 2), (3, 1)]
    assert [f["data"]["invoice_no"] for f in after["files"][:2]] == [DSS[3][0], DSS[4][0]]
    assert after["files"][2]["original_filename"] == "satu.pdf"
    assert after["files"][2]["data"]["tax"]["code"] == "PPH23"  # pajak PIC pada bukti lain tetap
    assert after["status"] == "DRAFT", after["issues"]
    assert {"SPLIT_REQUESTED", "INVOICES_SPLIT"} <= set(actions(doc["id"]))


def test_split_button_reports_when_there_is_only_one_invoice(extractor):
    fake = use(SplittingExtractor([]))
    doc = detail(two_files().json()["id"])
    calls = fake.calls
    assert post_split(doc["id"], 1).status_code == 200
    after = detail(doc["id"])
    assert len(after["files"]) == 2 and fake.located == 1 and fake.calls == calls and after["status"] == "DRAFT"
    assert "INVOICES_SPLIT_CHECKED" in actions(doc["id"])


def test_split_button_rejects_unfit_requests(extractor, monkeypatch):
    from app.config import settings
    use(SplittingExtractor([]))
    doc = detail(two_files().json()["id"])
    assert post_split(doc["id"], 2).status_code == 409  # satu halaman
    assert post_split(doc["id"], 9).status_code == 404
    assert post_split(doc["id"], 1, email="pic.beta@amiga.test").status_code in (403, 404)  # klien lain
    monkeypatch.setattr(settings, "ai_split_max_pages", 3)
    r = post_split(doc["id"], 1)
    assert r.status_code == 409 and "batas pemeriksaan 3 halaman" in r.json()["detail"]
    monkeypatch.setattr(settings, "ai_split_max_pages", 40)
    monkeypatch.setattr(settings, "ai_split_enabled", False)
    assert post_split(doc["id"], 1).status_code == 409
