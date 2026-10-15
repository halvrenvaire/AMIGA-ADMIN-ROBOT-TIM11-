"""Verifikasi sistem dan parser jawaban AI (tanpa database)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models import IssueCode
from app.services.extraction_service import ExtractionError, parse_response, to_decimal
from app.services.verification import InvoiceData, normalize, verify


def _data(**kw):
    base = dict(vendor_name="PT Vendor Jaya", invoice_no="INV-001", invoice_date=date(2026, 10, 1),
                total=Decimal("300000"), bank_name="BCA", account_no="1234567890",
                account_name="PT Vendor Jaya", subtotals=[Decimal("100000"), Decimal("200000")])
    return InvoiceData(**{**base, **kw})


def test_complete_and_correct_invoice_has_no_issue():
    assert verify(_data()) == []


def test_missing_account_number_is_missing_evidence():
    issues = verify(_data(account_no=None))
    assert [(i.code, i.field) for i in issues] == [(IssueCode.MISSING_EVIDENCE, "account_no")]
    assert "Nomor rekening" in issues[0].message


def test_line_sum_differs_from_total():
    issues = verify(_data(total=Decimal("310000")))
    assert [i.code for i in issues] == [IssueCode.CALCULATION_DISCREPANCY]
    assert "Rp 300.000" in issues[0].message and "Rp 310.000" in issues[0].message


def test_no_line_items_is_missing_evidence_not_calculation():
    issues = verify(_data(subtotals=[]))
    assert [(i.code, i.field) for i in issues] == [(IssueCode.MISSING_EVIDENCE, "line_items")]


def test_duplicate_mentions_earlier_request_id():
    issues = verify(_data(), duplicate_request_id="REQ-20261014-ABC123")
    assert [i.code for i in issues] == [IssueCode.POSSIBLE_DUPLICATE]
    assert "REQ-20261014-ABC123" in issues[0].message


@pytest.mark.parametrize("a, b", [("INV-001", "inv 001"), ("PT. Vendor Jaya", "pt vendor-jaya")])
def test_normalize_matches_formatting_variants(a, b):
    assert normalize(a) == normalize(b)


@pytest.mark.parametrize("raw, expected", [
    (1250000, "1250000"), (1250000.5, "1250000.5"), ("Rp 1.250.000", "1250000"),
    ("1.250.000,50", "1250000.50"), ("1,250,000.50", "1250000.50"), ("150.000", "150000"),
    ("12.5", "12.5"), ("3", "3"), (None, None), ("-", None),
])
def test_to_decimal(raw, expected):
    result = to_decimal(raw)
    assert (str(result) if result is not None else None) == expected


def test_parse_response_reads_json_inside_text():
    text = 'Berikut hasilnya:\n```json\n{"vendor_name": "PT A", "invoice_no": "X1", ' \
           '"invoice_date": "2026-10-01", "line_items": [{"description": "Kertas", "qty": 2, ' \
           '"unit_price": "Rp 50.000", "subtotal": 100000}], "total": 100000, "bank_name": null, ' \
           '"account_no": 123, "account_name": ""}\n```'
    inv = parse_response(text)
    assert inv.vendor_name == "PT A"
    assert inv.invoice_date == date(2026, 10, 1)
    assert inv.line_items[0].unit_price == Decimal("50000")
    assert inv.account_no == "123"
    assert inv.bank_name is None and inv.account_name is None


def test_parse_response_without_json_fails():
    with pytest.raises(ExtractionError):
        parse_response("Maaf, saya tidak bisa membaca dokumen ini.")


def test_parse_response_reads_document_check():
    inv = parse_response('{"is_invoice": false, "document_type": "Surat lamaran", '
                         '"not_invoice_reason": "Berisi lamaran kerja.", "line_items": []}')
    assert inv.is_invoice is False
    assert inv.document_type == "Surat lamaran" and inv.not_invoice_reason == "Berisi lamaran kerja."
    # Jawaban tanpa is_invoice tidak dianggap bukan invoice
    assert parse_response('{"vendor_name": "PT A"}').is_invoice is True


def test_summary_lines_are_not_line_items():
    inv = parse_response('{"total": 2695000, "line_items": ['
                         '{"kind": "item", "description": "Tiket CGK-DPS", "subtotal": 1200000},'
                         '{"kind": "item", "description": "Tiket DPS-CGK", "subtotal": 1200000},'
                         '{"kind": "summary", "description": "Subtotal Tiket", "subtotal": 2400000},'
                         '{"kind": "fee", "description": "Biaya Layanan", "subtotal": 50000},'
                         '{"kind": "tax", "description": "PPN 10%", "subtotal": 245000},'
                         '{"kind": "summary", "description": "Total Bayar", "subtotal": 2695000}]}')
    assert [line.description for line in inv.line_items] == ["Tiket CGK-DPS", "Tiket DPS-CGK", "Biaya Layanan", "PPN 10%"]
    assert sum(line.subtotal for line in inv.line_items) == inv.total
    assert inv.raw["summary_lines_skipped"] == ["Subtotal Tiket", "Total Bayar"]


def test_running_subtotal_marked_as_item_is_dropped_only_when_it_fixes_the_total():
    rows = ('{"description": "Tiket A", "subtotal": 1200000}, {"description": "Tiket B", "subtotal": 1200000},'
            '{"description": "Ringkasan Biaya", "subtotal": 2400000}, {"description": "PPN", "subtotal": 245000}')
    inv = parse_response('{"total": 2645000, "line_items": [' + rows + ']}')
    assert [line.description for line in inv.line_items] == ["Tiket A", "Tiket B", "PPN"]
    # Total tidak cocok setelah dibuang → rincian dibiarkan; selisih dilaporkan verifikasi sistem
    inv = parse_response('{"total": 9999, "line_items": [' + rows + ']}')
    assert len(inv.line_items) == 4


def test_item_equal_to_previous_item_is_kept_when_total_matches():
    inv = parse_response('{"total": 200, "line_items": ['
                         '{"description": "A", "subtotal": 100}, {"description": "B", "subtotal": 100}]}')
    assert len(inv.line_items) == 2


def test_total_read_with_thousand_dots_as_decimal_is_corrected():
    inv = parse_response('{"total": 2695, "line_items": [{"subtotal": 2400000}, {"subtotal": 295000}]}')
    assert inv.total == Decimal(2695000) and inv.raw["total_corrected_from"] == "2695"
    # Selisih lain tidak dikoreksi: tetap dilaporkan verifikasi sistem
    assert parse_response('{"total": 2600000, "line_items": [{"subtotal": 2695000}]}').total == Decimal(2600000)


def test_discount_is_always_negative():
    inv = parse_response('{"total": "Rp 720.000", "line_items": ['
                         '{"kind": "item", "description": "Kaos", "subtotal": "Rp 750.000"},'
                         '{"kind": "discount", "description": "DISKON", "subtotal": "Rp 100.000"},'
                         '{"kind": "tax", "description": "PAJAK", "subtotal": "Rp 70.000"}]}')
    assert [line.subtotal for line in inv.line_items] == [Decimal(750000), Decimal(-100000), Decimal(70000)]
    assert sum(line.subtotal for line in inv.line_items) == inv.total
    # Sudah negatif tetap negatif
    inv = parse_response('{"line_items": [{"kind": "discount", "subtotal": "-50.000"}]}')
    assert inv.line_items[0].subtotal == Decimal(-50000)


def test_document_type_overrides_inconsistent_is_invoice():
    inv = parse_response('{"is_invoice": true, "document_type": "Voucher Pembayaran Vendor", "line_items": []}')
    assert inv.is_invoice is False and "Voucher Pembayaran Vendor" in inv.not_invoice_reason
    assert parse_response('{"is_invoice": true, "document_type": "Struk kasir belanja"}').is_invoice is False
    # Jenis yang memang tagihan tidak terpengaruh
    assert parse_response('{"is_invoice": true, "document_type": "Faktur"}').is_invoice is True
    assert parse_response('{"is_invoice": true, "document_type": "Invoice pembayaran"}').is_invoice is True


def test_change_line_marks_cashier_receipt():
    inv = parse_response('{"is_invoice": true, "document_type": "Invoice", "total": "70.300", "line_items": ['
                         '{"kind": "item", "description": "GULA", "subtotal": "70.300"},'
                         '{"kind": "summary", "description": "KEMBALI", "subtotal": "29.700"}]}')
    assert inv.is_invoice is False and inv.document_type == "Struk kasir"


def test_discount_recognised_by_description_even_if_labelled_fee():
    inv = parse_response('{"line_items": [{"kind": "fee", "description": "DISKON", "subtotal": "Rp 100,000"},'
                         '{"kind": "fee", "description": "Potongan member", "subtotal": "5.000"},'
                         '{"kind": "fee", "description": "Biaya layanan", "subtotal": "2.000"}]}')
    assert [line.subtotal for line in inv.line_items] == [Decimal(-100000), Decimal(-5000), Decimal(2000)]
