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
