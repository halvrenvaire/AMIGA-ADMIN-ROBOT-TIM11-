import uuid
from decimal import Decimal
import pytest
from app.services.extraction_service import to_decimal, parse_scan
from app.services.document_processing import default_description, part_to_data
from app.services.invoice_splitter import _is_tax_serial
from tests.test_documents import api, client_id, detail, extractor, make_pdf, tx, upload  # noqa: F401
from tests.test_tax import PIC


def test_to_decimal_indonesian_shorthand():
    assert to_decimal("12.425.000,-") == Decimal("12425000")
    assert to_decimal("Rp 12.425.000,--") == Decimal("12425000")
    assert to_decimal("1.500.000.-") == Decimal("1500000")
    assert to_decimal("500.000-") == Decimal("500000")
    assert to_decimal("Rp. 2.304.696,-") == Decimal("2304696")


def test_is_tax_serial():
    assert _is_tax_serial("0400260012122029") is True
    assert _is_tax_serial("0100000000000000") is True
    assert _is_tax_serial("INV-2026-001") is False
    assert _is_tax_serial(None) is False
    assert _is_tax_serial("") is False


def test_parse_scan_filters_faktur_pajak():
    # Scan text where page 22 is a Faktur Pajak with 16 digit serial number
    scan_json = """{
        "document_class": "invoice",
        "invoices": [
            {
                "page": 1,
                "document_class": "invoice",
                "vendor_name": "PT DSS",
                "invoice_no": "INV/2026/01",
                "total": "10.000.000",
                "description": "Jasa Pengelolaan"
            },
            {
                "page": 22,
                "document_class": "invoice",
                "document_type": "Faktur Pajak",
                "vendor_name": "PT DSS",
                "invoice_no": "0400260012122029",
                "total": "1.100.000"
            }
        ]
    }"""
    result = parse_scan(scan_json, 1, 30)
    assert len(result.invoices) == 1
    assert result.invoices[0].invoice_no == "INV/2026/01"
    assert result.invoices[0].description == "Jasa Pengelolaan"


def test_default_description_formatting():
    data = {
        "invoice_no": "1702/04/2026",
        "vendor_name": "PT Daya Semesta Sejahtera",
        "service_description": "Jasa Kebersihan April 2026",
    }
    desc = default_description(data)
    assert desc == "Invoice 1702/04/2026 - PT Daya Semesta Sejahtera - Jasa Kebersihan April 2026"


def test_auto_tax_toggle_and_apply_all(extractor):
    # Upload with auto_tax=False
    data = {
        "client_id": client_id("PT Klien Alpha"),
        "request_type": "Voucher Pengeluaran Vendor",
        "channel": "Email",
        "submitted_date": "2026-10-14",
        "extraction_mode": "ITEMIZED",
        "include_account": "true",
        "auto_tax": "false",
    }
    r = api(PIC).post("/documents", data=data, files={"files": ("inv.pdf", make_pdf(), "application/pdf")})
    assert r.status_code == 201
    doc_id = r.json()["id"]

    # In draft, file should not have tax applied
    doc = detail(doc_id)
    assert doc["auto_tax"] is False
    assert doc["files"][0]["data"].get("tax") is None

    # Apply all taxes via endpoint
    r2 = api(PIC).post(f"/documents/{doc_id}/tax/apply-all")
    assert r2.status_code == 200
    doc2 = r2.json()
    assert doc2["files"][0]["data"].get("tax") is not None

    # Change options via PUT /options
    r3 = api(PIC).put(f"/documents/{doc_id}/options", json={"auto_tax": True})
    assert r3.status_code == 200
    assert r3.json()["auto_tax"] is True
