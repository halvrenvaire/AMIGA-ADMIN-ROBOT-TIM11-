"""Ekstraksi sungguhan dengan Amazon Nova (butuh kredensial AWS di .env).

Jalankan:  .venv/bin/python -m pytest -m integration tests/test_extraction_integration.py
"""
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.bedrock_client import BedrockClient
from app.services.extraction_service import InvoiceExtractor
from app.services.verification import normalize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_dummy_invoices import INVOICES, render  # noqa: E402

pytestmark = pytest.mark.integration

SAMPLES = {inv.filename: inv for inv in INVOICES}


@pytest.fixture(scope="module")
def extractor():
    return InvoiceExtractor(BedrockClient())


def test_normal_invoice_is_read_completely_within_15_seconds(extractor):
    inv = SAMPLES["01_normal_3_baris.pdf"]
    started = time.monotonic()
    result = extractor.extract(render(inv))
    assert time.monotonic() - started <= 15
    assert result.invoice_no == inv.invoice_no
    assert result.account_no == inv.account_no
    assert [line.subtotal for line in result.line_items] == [Decimal(q * p) for _, q, p in inv.lines]
    assert result.total == sum(Decimal(q * p) for _, q, p in inv.lines)


def test_missing_account_number_is_not_invented(extractor):
    result = extractor.extract(render(SAMPLES["02_tanpa_rekening.pdf"]))
    assert result.account_no is None


def test_duplicate_variant_normalizes_to_same_keys(extractor):
    a = extractor.extract(render(SAMPLES["01_normal_3_baris.pdf"]))
    b = extractor.extract(render(SAMPLES["03_duplikat_dari_01.pdf"]))
    assert normalize(a.invoice_no) == normalize(b.invoice_no)
    assert normalize(a.vendor_name) == normalize(b.vendor_name)
