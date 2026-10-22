"""Tahap 15: satu PDF berisi beberapa invoice/struk dipecah menjadi satu bukti per invoice."""
import copy
import io
from decimal import Decimal

from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.services.extraction_service import ExtractedInvoice, ScanResult
from tests.test_documents import FakeExtractor, api, detail, invoice, tx  # noqa: F401
from tests.test_documents import app
from tests.test_total_only import PIC, upload


def numbered_pdf(pages: int) -> bytes:
    """Halaman ke-n selebar 100 + n pt, supaya potongan halaman bisa dikenali."""
    writer = PdfWriter()
    for n in range(1, pages + 1):
        writer.add_blank_page(width=100 + n, height=200)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def page_numbers(pdf: bytes) -> list[int]:
    return [int(float(p.mediabox.width)) - 100 for p in PdfReader(io.BytesIO(pdf)).pages]


class ScanningExtractor(FakeExtractor):
    """AI palsu yang memindai: `starts` = {halaman awal: [invoice, ...]}."""

    def __init__(self, starts: dict[int, list[ExtractedInvoice]], general: ExtractedInvoice | None = None):
        super().__init__()
        self.starts, self.general = starts, general or invoice(doc_class="IRRELEVANT", is_invoice=False)
        self.chunks: list[tuple[int, int, int]] = []  # (awal, akhir, jumlah halaman PDF yang dikirim)
        self.focus: list[str | None] = []

    def scan_chunk(self, pdf_bytes, first, last, include_account=True):
        self.chunks.append((first, last, len(PdfReader(io.BytesIO(pdf_bytes)).pages)))
        found = []
        for page in range(first, last + 1):
            for inv in self.starts.get(page, []):
                inv = copy.deepcopy(inv)
                inv.page, inv.line_items = page, []
                found.append(inv)
        return ScanResult(invoices=found, document=copy.deepcopy(self.general) if not found else ExtractedInvoice(),
                          usage={"input_tokens": 100, "output_tokens": 20})

    def extract(self, pdf_bytes, mode="ITEMIZED", include_account=True, focus=None):
        self.focus.append(focus)
        return super().extract(pdf_bytes, mode, include_account)


def use(fake):
    app.state.extractor = fake
    return fake


def inv(no, total, vendor="PT DSS Indonesia"):
    return invoice(invoice_no=no, total=Decimal(total), vendor_name=vendor, line_items=[])


def bukti_pages(doc_id, position):
    return page_numbers(api(PIC).get(f"/documents/{doc_id}/files/{position}").content)


def test_many_invoices_over_many_pages_become_one_bukti_each(tx):
    # Seperti berkas DSS: tiap invoice = halaman invoice + rincian + 2 halaman Faktur Pajak
    fake = use(ScanningExtractor({1: [inv("DSS-01", 1000000)], 5: [inv("DSS-02", 2000000)],
                                  9: [inv("DSS-03", 3000000)]}))
    r = upload(numbered_pdf(12))
    assert r.status_code == 201
    doc = detail(r.json()["id"])
    # Dipindai per 5 halaman; mode total memakai hasil pindai tanpa membaca ulang
    assert fake.chunks == [(1, 5, 5), (6, 10, 5), (11, 12, 2)] and fake.calls == 0
    files = doc["files"]
    assert [(f["page_from"], f["page_to"], f["upload_pages"]) for f in files] == [(1, 4, 12), (5, 8, 12), (9, 12, 12)]
    assert [f["original_filename"] for f in files] == [
        "inv1.pdf (invoice 1, hal. 1–4)", "inv1.pdf (invoice 2, hal. 5–8)", "inv1.pdf (invoice 3, hal. 9–12)"]
    assert {f["upload_name"] for f in files} == {"inv1.pdf"}
    assert [f["data"]["invoice_no"] for f in files] == ["DSS-01", "DSS-02", "DSS-03"]
    assert files[1]["data"]["description"] == "Invoice DSS-02 - PT DSS Indonesia"
    assert bukti_pages(doc["id"], 2) == [5, 6, 7, 8]
    assert Decimal(doc["extraction"]["total"]) == Decimal(6000000)
    assert doc["status"] == "DRAFT" and doc["invoice_limit"] is None
    # Lampiran voucher: PDF unggahan dilampirkan sekali, utuh (12 halaman), bukan per bukti
    pdf = api(PIC).get(f"/documents/{doc['id']}/voucher-preview").content
    plain = api(PIC).get(f"/documents/{doc['id']}/voucher-preview", params={"attachments": False}).content
    assert len(PdfReader(io.BytesIO(pdf)).pages) - len(PdfReader(io.BytesIO(plain)).pages) == 12


def test_several_receipts_on_one_page_point_to_the_same_page(tx):
    fake = use(ScanningExtractor({1: [inv("S-1", 10000, "Toko A"), inv("S-2", 20000, "Toko B"),
                                      inv("S-3", 30000, "Toko C")]}))
    fake.result = [invoice(invoice_no=f"S-{i}", vendor_name=v, total=Decimal(t), line_items=[])
                   for i, v, t in ((1, "Toko A", 10000), (2, "Toko B", 20000), (3, "Toko C", 30000))]
    doc = detail(upload(numbered_pdf(1), extraction_mode="ITEMIZED").json()["id"])
    files = doc["files"]
    assert [(f["page_from"], f["page_to"]) for f in files] == [(1, 1)] * 3
    # Mode rincian: tiap struk dibaca ulang dengan petunjuk struk mana yang dibaca
    assert fake.calls == 3 and all(fake.focus) and "S-2" in fake.focus[1] and "Toko B" in fake.focus[1]
    assert [f["data"]["invoice_no"] for f in files] == ["S-1", "S-2", "S-3"]
    assert [f["original_filename"] for f in files][2] == "inv1.pdf (invoice 3, hal. 1)"


def test_invoice_limit_from_settings(tx, monkeypatch):
    monkeypatch.setattr(settings, "max_invoices_per_voucher", 2)
    use(ScanningExtractor({1: [inv("A", 1)], 3: [inv("B", 2)], 5: [inv("C", 3)]}))
    doc = detail(upload(numbered_pdf(6)).json()["id"])
    # Invoice yang tidak dipisah ikut bukti terakhir, jadi tidak ada halaman yang hilang
    assert [(f["page_from"], f["page_to"]) for f in doc["files"]] == [(1, 2), (3, 6)]
    assert doc["invoice_limit"] == {"limit": 2, "files": [{"file": "inv1.pdf", "skipped": 1}]}
    assert api(PIC).post(f"/documents/{doc['id']}/files",
                         json={"source_position": 1, "page_from": 1, "page_to": 1}).status_code == 422


def test_scan_stops_at_page_limit_and_when_first_chunk_has_no_invoice(tx, monkeypatch):
    monkeypatch.setattr(settings, "ai_max_scan_pages", 8)
    fake = use(ScanningExtractor({1: [inv("A", 1)], 7: [inv("B", 2)], 10: [inv("C", 3)]}))
    doc = detail(upload(numbered_pdf(12)).json()["id"])
    assert fake.chunks == [(1, 5, 5), (6, 8, 3)]
    assert [(f["page_from"], f["page_to"]) for f in doc["files"]] == [(1, 6), (7, 12)]

    fake = use(ScanningExtractor({8: [inv("Z", 1)]}))
    doc = detail(upload(numbered_pdf(12)).json()["id"])
    assert fake.chunks == [(1, 5, 5)] and len(doc["files"]) == 1
    assert doc["files"][0]["original_filename"] == "inv1.pdf" and doc["classification"]["doc_class"] == "IRRELEVANT"


def test_pic_edits_page_range_deletes_and_adds_bukti(tx):
    fake = use(ScanningExtractor({1: [inv("A", 100)], 3: [inv("B", 200)]}))
    doc = detail(upload(numbered_pdf(6)).json()["id"])
    pic = api(PIC)
    # Rentang halaman diubah: potongan PDF bukti ikut berubah, data invoice tetap
    r = pic.put(f"/documents/{doc['id']}/files/1/pages", json={"page_from": 1, "page_to": 3})
    assert r.status_code == 200 and r.json()["files"][0]["original_filename"] == "inv1.pdf (invoice 1, hal. 1–3)"
    assert bukti_pages(doc["id"], 1) == [1, 2, 3] and r.json()["files"][0]["data"]["invoice_no"] == "A"
    assert pic.put(f"/documents/{doc['id']}/files/1/pages", json={"page_from": 4, "page_to": 9}).status_code == 422

    # Tambah bukti dari halaman yang terlewat AI, diisi manual
    r = pic.post(f"/documents/{doc['id']}/files",
                 json={"source_position": 1, "page_from": 5, "page_to": 6, "read_ai": False})
    assert r.status_code == 201
    files = r.json()["files"]
    assert len(files) == 3 and (files[2]["page_from"], files[2]["page_to"]) == (5, 6)
    assert files[2]["data"]["invoice_no"] is None and bukti_pages(doc["id"], 3) == [5, 6]

    # Tambah bukti yang dibaca AI: hanya bukti baru yang dibaca
    fake.result = inv("C", 300)
    calls = fake.calls
    r = pic.post(f"/documents/{doc['id']}/files", json={"source_position": 2, "page_from": 6, "page_to": 6})
    after = detail(doc["id"])
    assert fake.calls == calls + 1 and [f["data"]["invoice_no"] for f in after["files"]] == ["A", "B", None, "C"]

    # Hapus bukti: nomor urut dan nama diatur ulang
    r = pic.delete(f"/documents/{doc['id']}/files/3")
    files = r.json()["files"]
    assert [f["position"] for f in files] == [1, 2, 3] and [f["data"]["invoice_no"] for f in files] == ["A", "B", "C"]
    assert files[2]["original_filename"] == "inv1.pdf (invoice 3, hal. 6)"
    assert Decimal(r.json()["extraction"]["total"]) == Decimal(600)
    # Minimal 1 bukti tersisa
    for _ in range(2):
        pic.delete(f"/documents/{doc['id']}/files/1")
    assert pic.delete(f"/documents/{doc['id']}/files/1").status_code == 422
    assert detail(doc["id"])["files"][0]["original_filename"] == "inv1.pdf"


def test_old_extractor_without_scan_reads_one_invoice_per_file(tx):
    """Extractor tanpa pemindaian (mis. versi lama) tetap 1 file = 1 bukti; data lama tidak berubah."""
    fake = use(FakeExtractor())
    fake.result = inv("X", 500)
    doc = detail(upload(numbered_pdf(7)).json()["id"])
    assert len(doc["files"]) == 1 and doc["files"][0]["page_from"] is None and fake.pages == [5]


def test_real_extractor_scan_prompt_and_parsing():
    """InvoiceExtractor.scan_chunk: halaman relatif diubah ke halaman berkas asli; tagihan kosong dilewati."""
    from app.services.extraction_service import InvoiceExtractor

    class Bedrock:
        def read_pdf_usage(self, system, pdf, instruction, max_tokens):
            self.instruction = instruction
            return ('{"document_class": "invoice", "invoices": ['
                    '{"page": 2, "document_class": "invoice", "vendor_name": "PT A", "invoice_no": "A-1", '
                    '"invoice_date": "2026-10-01", "total": "Rp 1.500.000"},'
                    '{"page": 9, "document_class": "receipt", "document_type": "Struk", "vendor_name": "Toko B", '
                    '"invoice_no": null, "total": "25.000"},'
                    '{"page": 7, "document_class": "invoice", "vendor_name": null, "invoice_no": null, "total": null}'
                    ']}', {"input_tokens": 500, "output_tokens": 80})

    bedrock = Bedrock()
    result = InvoiceExtractor(bedrock).scan_chunk(b"%PDF-", 6, 10, include_account=False)
    assert "halaman 6 sampai 10" in bedrock.instruction and "account_no" not in bedrock.instruction
    assert [(i.invoice_no, i.page, i.total, i.doc_class) for i in result.invoices] == [
        ("A-1", 7, Decimal(1500000), "INVOICE"), (None, 9, Decimal(25000), "RECEIPT")]
    assert result.usage == {"input_tokens": 500, "output_tokens": 80}
