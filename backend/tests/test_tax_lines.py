"""PPN, biaya, dan potongan di bawah tabel barang (contoh nyata: faktur PT Sukanda Djaya).

Rincian 855.000 + PPN 94.050 = total 949.050. Tanpa baris PPN, sistem keliru melaporkan
CALCULATION_DISCREPANCY.
"""
import json
from decimal import Decimal

from app.models import IssueCode
from app.services.bedrock_client import BedrockError
from app.services.extraction_service import InvoiceExtractor, complete_with_charges, parse_response, ExtractedLine
from app.services.verification import InvoiceData, verify

ITEM = {"kind": "item", "description": "COFFEE PRECIOUS CARGO 1 KG", "qty": 3, "unit_price": "285.000",
        "subtotal": "855.000"}


def answer(*line_items, total="949.050") -> str:
    return json.dumps({"document_class": "invoice", "document_type": "Faktur penjualan",
                       "vendor_name": "PT SUKANDA DJAYA", "invoice_no": "4081411791", "invoice_date": "2026-10-09",
                       "line_items": list(line_items), "total": total,
                       "bank_name": None, "account_no": None, "account_name": None})


def subtotals(result) -> list[Decimal]:
    return [line.subtotal for line in result.line_items]


# --- Pembacaan pertama ---

def test_tax_line_read_by_ai_is_kept():
    result = parse_response(answer(ITEM, {"kind": "tax", "description": "PPN", "subtotal": "94.050"}))
    assert sum(subtotals(result)) == result.total == Decimal("949050")


def test_tax_mislabelled_as_summary_is_recovered():
    result = parse_response(answer(
        ITEM,
        {"kind": "summary", "description": "JUMLAH HARGA JUAL", "subtotal": "855.000"},
        {"kind": "summary", "description": "PPN", "subtotal": "94.050"},
        {"kind": "summary", "description": "NILAI YANG HARUS DIBAYAR", "subtotal": "949.050"},
    ))
    assert subtotals(result) == [Decimal("855000"), Decimal("94050")]
    assert result.raw["charges_recovered_from_summary"] == ["PPN"]
    assert "PPN" not in result.raw["summary_lines_skipped"]


def test_summary_charge_is_not_added_when_it_does_not_fix_the_total():
    # PPN tertulis 90.000 (salah baca): tidak ditambahkan, selisih tetap dilaporkan sistem
    result = parse_response(answer(ITEM, {"kind": "summary", "description": "PPN", "subtotal": "90.000"}))
    assert subtotals(result) == [Decimal("855000")]


def test_discount_in_summary_area_is_negative():
    lines = [ExtractedLine(description="Barang", subtotal=Decimal(1000))]
    found = complete_with_charges(lines, [ExtractedLine(description="Diskon", subtotal=Decimal(-100))], Decimal(900))
    assert [line.subtotal for line in found] == [Decimal(-100)]


# --- Pembacaan ulang terarah ---

class FakeBedrock:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.instructions = []

    def read_pdf(self, system_prompt, pdf_bytes, instruction, max_tokens):
        self.instructions.append(instruction)
        result = self.answers.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_followup_finds_missed_ppn():
    bedrock = FakeBedrock(answer(ITEM),
                          json.dumps({"missing_lines": [{"kind": "tax", "description": "PPN", "subtotal": "94.050"}]}))
    result = InvoiceExtractor(bedrock).extract(b"%PDF-")
    assert subtotals(result) == [Decimal("855000"), Decimal("94050")]
    assert result.raw["charges_recovered_by_followup"] == ["PPN"]
    assert "855000" in bedrock.instructions[1] and "949050" in bedrock.instructions[1]


def test_followup_is_ignored_when_it_does_not_fix_the_total():
    bedrock = FakeBedrock(answer(ITEM),
                          json.dumps({"missing_lines": [{"kind": "fee", "description": "Ongkir", "subtotal": "10.000"}]}))
    result = InvoiceExtractor(bedrock).extract(b"%PDF-")
    assert subtotals(result) == [Decimal("855000")]


def test_no_followup_when_totals_already_match():
    bedrock = FakeBedrock(answer(ITEM, total="855.000"))
    InvoiceExtractor(bedrock).extract(b"%PDF-")
    assert len(bedrock.instructions) == 1


def test_followup_failure_keeps_first_reading():
    bedrock = FakeBedrock(answer(ITEM), BedrockError("timeout"))
    result = InvoiceExtractor(bedrock).extract(b"%PDF-")
    assert subtotals(result) == [Decimal("855000")] and result.total == Decimal("949050")


# --- Verifikasi sistem ---

def _data(subs, total):
    return InvoiceData(vendor_name="V", invoice_no="1", invoice_date=None, total=Decimal(total), bank_name="BCA",
                       account_no="1", account_name="V", subtotals=[Decimal(s) for s in subs])


def test_matching_totals_with_ppn_line_have_no_discrepancy():
    issues = verify(_data(["855000", "94050"], "949050"))
    assert IssueCode.CALCULATION_DISCREPANCY not in [i.code for i in issues]


def test_discrepancy_message_hints_at_missing_ppn():
    [issue] = [i for i in verify(_data(["855000"], "949050")) if i.code == IssueCode.CALCULATION_DISCREPANCY]
    assert "11% dari jumlah rincian" in issue.message and "PPN" in issue.message


def test_other_discrepancies_have_no_ppn_hint():
    [issue] = [i for i in verify(_data(["855000"], "900000")) if i.code == IssueCode.CALCULATION_DISCREPANCY]
    assert "PPN" not in issue.message


def test_followup_that_resends_full_data_still_yields_tax_line():
    full = json.dumps({"document_class": "invoice", "invoice_data": {"line_items": [
        ITEM, {"kind": "tax", "description": "PPN", "subtotal": "94.050"}]}})
    result = InvoiceExtractor(FakeBedrock(answer(ITEM), full)).extract(b"%PDF-")
    assert subtotals(result) == [Decimal("855000"), Decimal("94050")]
