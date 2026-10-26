"""Dasar potongan PPh 23 untuk invoice jasa yang memisahkan imbalan jasa dari penggantian biaya (berkas DSS).

Contoh owner (voucher 1702): PPh 23 2% dipotong dari "Management Fee & Development" (bagian yang dikenai PPN), bukan
dari total invoice; Basic Fee, BPJS, dan Overtime driver adalah penggantian biaya. Angka baris di test ini disalin dari
pembacaan Nova Lite yang sebenarnya pada berkas samples/dss_sintetis/invoice_dss_sintetis.pdf, termasuk salah bacanya.
"""
import copy
import io
from decimal import Decimal

from pypdf import PdfReader

from app.services.extraction_service import ExtractedInvoice, _positive, fee_from_amounts, parse_response
from app.services.invoice_splitter import PageInfo
from tests.test_documents import api, detail, tx  # noqa: F401
from tests.test_invoice_split import ScanningExtractor, inv, numbered_pdf, use
from tests.test_total_only import PIC, upload


def rows(*pairs):
    return [{"label": label, "amount": amount} for label, amount in pairs]


BASIC, OVERTIME, FEE = "Total Basic Fee", "Total Overtime", "Total Management Fee & Development"
AMOUNT, NOT_VAT, VAT_SUB = "Total Amount", "Sub total (NOT subjected to VAT)", "Sub total (subjected to VAT)"
VAT, STAMP, TOTAL = "VAT / PPN", "Stamp Duty / Biaya Meterai", "Total Invoice / Total Tagihan"

# Invoice 005-PI-2604-00322 (halaman 1), terbaca benar
CLEAN = rows((BASIC, "6,375,633.00"), (OVERTIME, "0.00"), (FEE, "2,304,696.00"), (AMOUNT, "8,680,329.00"),
             (NOT_VAT, "6,567,691.00"), (VAT_SUB, "2,112,638.00"), (VAT, "253,517.00"), (STAMP, "0.00"),
             (TOTAL, "8,933,846.00"))


def test_fee_from_clean_summary_matches_vat():
    r = fee_from_amounts(CLEAN)
    assert (r.split, r.fee, r.vat, r.unverified) == (True, Decimal("2304696"), Decimal("253517"), None)


def test_fee_found_when_ai_shifts_amounts_one_row():
    # Halaman 5: angka bergeser satu baris dan Management Fee hilang; imbalan didapat dari DPP nilai lain x 12/11
    shifted = rows((BASIC, "6,375,633.00"), (OVERTIME, "0.00"), (FEE, "0.00"), (AMOUNT, "8,680,696.00"),
                   (NOT_VAT, "8,680,329.00"), (VAT_SUB, "6,567,691.00"), (VAT, "2,112,638.00"),
                   (STAMP, "253,517.00"), (TOTAL, "8,933,846.00"))
    r = fee_from_amounts(shifted)
    assert r.fee == Decimal("2304696") and r.vat == Decimal("253517")


def test_fee_found_when_ai_drops_a_row():
    # Halaman 26: baris "Sub total terkena PPN" terlewat sehingga PPN tertulis di baris materai
    dropped = rows((BASIC, "0.00"), (OVERTIME, "2,625,493.00"), (FEE, "393,824.00"), (AMOUNT, "3,019,317.00"),
                   (NOT_VAT, "2,658,312.00"), (VAT, "361,005.00"), (STAMP, "43,321.00"), (TOTAL, "3,062,638.00"))
    assert fee_from_amounts(dropped).fee == Decimal("393824")


def test_fee_confirmed_by_vat_subtotal_when_vat_is_misread():
    # Halaman 13: PPN terbaca 908.685 (seharusnya 108.685), tetapi "Sub total terkena PPN" 905.710 = 988.047 x 11/12
    misread = rows((BASIC, "0.00"), (OVERTIME, "6,586,980.00"), (FEE, "988,047.00"), (AMOUNT, "7,575,027.00"),
                   (NOT_VAT, "6,669,317.00"), (VAT_SUB, "905,710.00"), (VAT, "908,685.00"), (TOTAL, "7,683,712.00"))
    assert fee_from_amounts(misread).fee == Decimal("988047")


def test_fee_not_used_when_nothing_matches():
    wrong = rows((BASIC, "0.00"), (OVERTIME, "6,586,980.00"), (FEE, "988,047.00"), (VAT_SUB, "6,659,710.00"),
                 (VAT, "908,685.00"), (TOTAL, "7,683,712.00"))
    r = fee_from_amounts(wrong)
    assert (r.split, r.fee, r.unverified) == (True, None, Decimal("988047"))


def test_invoice_without_reimbursed_costs_is_not_a_fee_split():
    # Invoice jasa biasa: PPh 23 dari seluruh DPP seperti sebelumnya, tidak ada imbalan jasa terpisah
    normal = rows(("Service Fee", "1.000.000"), ("PPN 11%", "110.000"), ("Total", "1.110.000"))
    assert fee_from_amounts(normal).split is False
    assert fee_from_amounts(None).split is False


def test_label_copied_instead_of_amount_is_rejected():
    # Pemindaian nyata: AI menyalin label; angka "05592" dari kode driver tidak boleh terbaca sebagai imbalan jasa
    assert _positive("Management Fee & Development Driver Service DD00003 / DRIVER C") is None
    assert _positive("VAT / PPN") is None
    assert _positive("Rp. 2.304.696,-") == Decimal("2304696")
    assert _positive("2,304,696.00") == Decimal("2304696.00")
    part = parse_response('{"document_class": "invoice", "vendor_name": "PT Demo Solusi Sejati", '
                          '"invoice_no": "005-PI-2604-00325", "total": "7,683,712.00", '
                          '"service_fee": "Management Fee & Development Driver Service DD00003 / DRIVER C", '
                          '"vat_amount": "VAT / PPN"}')
    assert part.service_fee is None and part.vat_printed is None


# Enam invoice berkas DSS: (nomor, halaman depan, total, imbalan jasa, PPN)
DSS = [("005-PI-2604-00322", 1, "8933846", "2304696", "253517"), ("005-PI-2604-00323", 5, "8933846", "2304696", "253517"),
       ("005-PI-2604-00324", 9, "8933846", "2304696", "253517"), ("005-PI-2604-00325", 13, "7683712", "988047", "108685"),
       ("005-PI-2604-00326", 20, "4348350", "559153", "61507"), ("005-PI-2604-00327", 26, "3062638", "393824", "43321")]


class DssExtractor(ScanningExtractor):
    """Pemindaian seperti Nova Lite: halaman awal disebut halaman pertama potongan dan imbalan jasa berupa label;
    pemeriksaan per halaman menemukan halaman depan yang benar beserta blok ringkasannya."""

    def __init__(self, fronts: dict[int, PageInfo]):
        starts: dict[int, list[ExtractedInvoice]] = {}
        for no, page, total, _, _ in DSS:
            wrong_page = ((page - 1) // 5) * 5 + 1
            scanned = inv(no, total, vendor="PT Demo Solusi Sejati")
            scanned.raw = {"service_fee": "Management Fee & Development Driver Service"}
            starts.setdefault(wrong_page, []).append(scanned)
        super().__init__(starts)
        self.fronts, self.checked = fronts, []

    def read_front_page(self, page_pdf, usage):
        page = int(float(PdfReader(io.BytesIO(page_pdf)).pages[0].mediabox.width)) - 100
        self.checked.append(page)
        usage["input_tokens"] = usage.get("input_tokens", 0) + 10
        return copy.deepcopy(self.fronts.get(page, PageInfo()))


def dss_fronts() -> dict[int, PageInfo]:
    fronts = {}
    for no, page, total, fee, vat in DSS:
        fronts[page] = PageInfo(True, no, rows((BASIC, "0.00"), (OVERTIME, "1,000.00"), (FEE, f"{int(fee):,}.00"),
                                                (VAT, f"{int(vat):,}.00"), (TOTAL, f"{int(total):,}.00")))
    return fronts


def test_dss_file_pages_and_pph23_base_follow_the_owner_voucher(tx):
    fake = use(DssExtractor(dss_fronts()))
    r = upload(numbered_pdf(32), auto_tax="true")  # layar unggah mengirim pajak otomatis aktif
    assert r.status_code == 201
    doc = detail(r.json()["id"])
    files = doc["files"]
    # Halaman awal dari pemeriksaan per halaman, bukan dari pemindaian (yang menyebut 1, 1, 6, 11, 16, 26)
    assert [f["page_from"] for f in files] == [1, 5, 9, 13, 20, 26]
    assert [f["page_to"] for f in files] == [4, 8, 12, 19, 25, 32]
    assert 27 not in fake.checked or 26 in fake.checked  # hanya potongan yang memuat invoice yang diperiksa
    for f, (no, _, _, fee, vat) in zip(files, DSS):
        data = f["data"]
        assert data["invoice_no"] == no
        assert Decimal(data["service_fee"]) == Decimal(fee) and Decimal(data["vat_printed"]) == Decimal(vat)
        tax = data["tax"]  # pajak otomatis: PPh 23 2% dari imbalan jasa
        assert tax["code"] == "PPH23" and Decimal(tax["base"]) == Decimal(fee)
        assert Decimal(tax["amount"]) == (Decimal(fee) * 2 / 100).quantize(Decimal(1))
        # Saran PPN otomatis: PPN tercetak berarti total sudah termasuk PPN; nilainya angka tercetak, bukan 11% x total
        assert tax["vat"]["mode"] == "included"
        assert data["tax_suggestion"]["vat"]["amount"] == vat and "tercetak" in data["tax_suggestion"]["vat"]["reason"]
    summary = doc["tax_summary"]
    assert [Decimal(v["amount"]) for v in summary["vat"]] == [Decimal(v) for *_, v in DSS]
    text = " ".join(PdfReader(io.BytesIO(api(PIC).get(f"/documents/{doc['id']}/voucher-preview",
                                                       params={"attachments": False}).content)).pages[0]
                    .extract_text().split())
    assert "Potongan PPh 23 (Rp 2.304.696 x 2%) 005-PI-2604-00322 (Rp 46.094)" in text
    assert "(termasuk PPN) Rp 8.933.846" in text
    # Voucher 1702 owner: total invoice 41.896.238, potongan PPh 23 177.102, dibayar 41.719.136
    assert Decimal(summary["gross"]) == Decimal("41896238")
    assert Decimal(summary["tax_total"]) == Decimal("177102")
    assert Decimal(summary["net"]) == Decimal("41719136")


def test_fee_left_for_pic_when_front_page_numbers_do_not_match(tx):
    fronts = dss_fronts()
    fronts[13].amounts = rows((OVERTIME, "6,586,980.00"), (FEE, "988,047.00"), (VAT, "908,685.00"))
    fake = use(DssExtractor(fronts))
    doc = detail(upload(numbered_pdf(32)).json()["id"])
    data = doc["files"][3]["data"]
    assert data.get("service_fee") is None and Decimal(data["service_fee_unverified"]) == Decimal("988047")
    assert fake.checked.count(13) == 2  # dibaca ulang sekali


def test_service_fee_is_never_guessed_from_total_or_vat_ratio():
    from app.services import tax_service
    # Total sama persis dengan invoice DSS, tetapi tanpa imbalan jasa yang terbaca: tidak ada tabel angka hafalan
    assert tax_service.service_fee({"vendor_name": "PT Demo Solusi Sejati (DSS)", "total": "8933846"}) is None
    # Invoice PT yang hanya sebagian barangnya kena PPN (PPN < 8% dari total) bukan invoice imbalan jasa
    assert tax_service.service_fee({"vendor_name": "PT Sumber Makmur", "total": "10000000", "vat_printed": "330000"}) is None
    assert tax_service.suggest_by_rules({"vendor_name": "PT Sumber Makmur", "total": "10000000",
                                         "vat_printed": "330000"}, False).code == "NONE"
    # Imbalan jasa yang sudah dicocokkan dengan PPN tetap dipakai
    assert tax_service.service_fee({"service_fee": "2304696"}) == Decimal("2304696")


def test_invoice_missed_by_scan_is_added_from_page_check(tx):
    # Pembacaan nyata 26 Okt 2026: pemindaian per 5 halaman tidak mendaftar invoice 00323 (halaman 5), padahal
    # pemeriksaan per halaman menemukan halaman depannya
    fake = DssExtractor(dss_fronts())
    fake.starts[1] = [i for i in fake.starts[1] if i.invoice_no != "005-PI-2604-00323"]
    # Bukti yang terlewat dibaca ulang AI (mode total saja) untuk data kepalanya
    fake.result = inv("005-PI-2604-00323", "8933846", vendor="PT Demo Solusi Sejati")
    use(fake)
    doc = detail(upload(numbered_pdf(32), auto_tax="true").json()["id"])
    files = doc["files"]
    assert [f["page_from"] for f in files] == [1, 5, 9, 13, 20, 26]
    assert [f["data"]["invoice_no"] for f in files] == [no for no, *_ in DSS]
    assert fake.calls == 1  # hanya bukti yang terlewat yang dibaca ulang
    added = files[1]["data"]
    assert Decimal(added["service_fee"]) == Decimal("2304696") and added["vendor_name"] == "PT Demo Solusi Sejati"
    assert Decimal(added["tax"]["base"]) == Decimal("2304696")
    assert Decimal(doc["tax_summary"]["net"]) == Decimal("41719136")


def test_scanned_detail_page_is_dropped_and_unsure_fee_is_not_auto_taxed(tx):
    # Pembacaan nyata 26 Okt 2026: lampiran rincian di halaman 6 terdaftar sebagai invoice "005-DO2311-000001";
    # imbalan jasa invoice 00325 tidak cocok dengan PPN
    fronts = dss_fronts()
    fronts[13].amounts = rows((OVERTIME, "6,586,980.00"), (FEE, "988,047.00"), (VAT, "908,685.00"))
    fake = DssExtractor(fronts)
    detail_page = inv("005-DO2311-000001", "6375633", vendor="PT Demo Solusi Sejati")
    fake.starts[6].insert(0, detail_page)
    use(fake)
    doc = detail(upload(numbered_pdf(32), auto_tax="true").json()["id"])
    files = doc["files"]
    assert [f["data"]["invoice_no"] for f in files] == [no for no, *_ in DSS]
    unsure = files[3]["data"]
    # Pajak tidak dipasang otomatis dengan DPP seluruh tagihan; PIC mengisi DPP (peringatan di panel pajak)
    assert unsure.get("tax") is None and Decimal(unsure["service_fee_unverified"]) == Decimal("988047")
    r = api(PIC).post(f"/documents/{doc['id']}/tax/apply-all")
    assert r.json()["files"][3]["data"].get("tax") is None


def test_misread_number_is_matched_only_when_close():
    from app.services.invoice_split import _same_invoice
    front = PageInfo(True, "005-PI-2604-00324", rows((TOTAL, "8,933,846.00")))
    assert _same_invoice(inv("005-PI-2604-0O324", "1"), front)  # salah baca satu karakter
    assert _same_invoice(inv(None, "8933846"), front)  # nomor tidak terbaca, total sama
    assert not _same_invoice(inv("005-DO2311-000001", "6375633"), front)  # lampiran rincian


def test_fee_confirmed_by_total_minus_amount_when_vat_and_subtotal_are_misread():
    # Halaman 13, pembacaan nyata 26 Okt 2026: PPN 908.685 dan "Sub total terkena PPN" 7.575.027 salah terbaca, tetapi
    # Total Invoice - Total Amount = 7.683.712 - 7.575.027 = 108.685 = 988.047 x 11%
    misread = rows((BASIC, "0.00"), (OVERTIME, "6,586,980.00"), (FEE, "988,047.00"), (AMOUNT, "7,575,027.00"),
                   (NOT_VAT, "6,669,317.00"), (VAT_SUB, "7,575,027.00"), (VAT, "908,685.00"), (STAMP, "0.00"),
                   (TOTAL, "7,683,712.00"))
    r = fee_from_amounts(misread)
    assert r.fee == Decimal("988047") and r.vat == Decimal("108685")
    # Baris "Sub total (NOT subjected to VAT)" bukan baris PPN
    assert fee_from_amounts(rows((BASIC, "1"), (FEE, "100"), (NOT_VAT, "5"), (VAT, "11"))).vat == Decimal("11")

