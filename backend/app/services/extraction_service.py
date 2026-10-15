"""AI Engine: hanya MEMBACA invoice (FR-2.2). Tidak memverifikasi dan tidak menyetujui.

Hasilnya data mentah sesuai PRD bagian 6. Verifikasi dijalankan sistem di verification.py.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.config import settings
from app.services.bedrock_client import BedrockClient, BedrockError

SYSTEM_PROMPT = """Kamu adalah Invoice Verification Officer berpengalaman di bagian keuangan (back office).
Tugasmu dua, berurutan:

1. Pastikan dokumen PDF ini benar-benar sebuah INVOICE, yaitu dokumen tagihan dari penjual/vendor
   kepada pembeli yang meminta pembayaran. Ciri umumnya: nama penjual, nomor dan tanggal invoice,
   rincian barang/jasa, jumlah yang harus dibayar, dan biasanya rekening tujuan pembayaran.
   Invoice, faktur, tagihan, dan nota tagihan termasuk invoice, dalam bahasa apa pun.
   BUKAN invoice: penawaran harga (quotation), purchase order, surat jalan / delivery note,
   bukti transfer / bukti bayar, kontrak, surat, CV, laporan, artikel, materi presentasi, formulir,
   foto atau dokumen lain yang tidak menagih pembayaran.
   Nilai dari isi dan bentuk dokumen, bukan dari nama file. Bila dokumen jelas sebuah tagihan meski
   ada data yang kurang, tetap anggap invoice (kekurangan data diperiksa sistem, bukan olehmu).

2. Bila invoice, salin datanya ke JSON. Kamu TIDAK memeriksa, menghitung ulang, atau memperbaiki
   angka: salin persis seperti tertulis di invoice. Jika sebuah data tidak ada, isi null. Jangan menebak.
   Bila bukan invoice, isi semua field data dengan null dan line_items dengan []."""

INSTRUCTION = """Kembalikan HANYA satu objek JSON (tanpa teks lain) dengan bentuk:
{
  "is_invoice": true|false,
  "document_type": string,
  "not_invoice_reason": string|null,
  "vendor_name": string|null,
  "invoice_no": string|null,
  "invoice_date": "YYYY-MM-DD"|null,
  "line_items": [{"description": string|null, "qty": number|null, "unit_price": number|null, "subtotal": number|null}],
  "total": number|null,
  "bank_name": string|null,
  "account_no": string|null,
  "account_name": string|null
}
Aturan: "is_invoice" adalah hasil pemeriksaan langkah 1. "document_type" adalah jenis dokumen
dalam bahasa Indonesia (mis. "Invoice", "Purchase order", "Surat lamaran"). "not_invoice_reason"
diisi satu kalimat singkat bila is_invoice false, selain itu null. Angka ditulis tanpa pemisah ribuan dan tanpa "Rp" (contoh 1250000.50). "total" adalah total
akhir yang tertulis di invoice. "account_no" adalah nomor rekening tujuan pembayaran, sebagai teks.
"line_items" berisi setiap baris barang/jasa, berurutan seperti di invoice."""


class ExtractionError(Exception):
    """AI gagal membaca invoice; dokumen tetap tersimpan (FR-2.5)."""


@dataclass
class ExtractedLine:
    description: str | None = None
    qty: Decimal | None = None
    unit_price: Decimal | None = None
    subtotal: Decimal | None = None


@dataclass
class ExtractedInvoice:
    vendor_name: str | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    line_items: list[ExtractedLine] = field(default_factory=list)
    total: Decimal | None = None
    bank_name: str | None = None
    account_no: str | None = None
    account_name: str | None = None
    # Pemeriksaan jenis dokumen oleh AI: PDF yang bukan invoice tidak diproses lebih lanjut
    is_invoice: bool = True
    document_type: str | None = None
    not_invoice_reason: str | None = None
    raw: dict = field(default_factory=dict)


def to_decimal(value) -> Decimal | None:
    """Angka dari AI: number, atau teks seperti "Rp 1.250.000,50" / "1,250,000.50"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        # Pemisah yang muncul terakhir adalah pemisah desimal
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal_sep == "," else ",", "").replace(decimal_sep, ".")
    elif text.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")  # format Indonesia: titik = ribuan
    elif text.count(",") > 1 or re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def to_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_response(text: str) -> ExtractedInvoice:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ExtractionError("Jawaban AI tidak berisi JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ExtractionError(f"JSON dari AI tidak valid: {e}") from e
    if not isinstance(data, dict):
        raise ExtractionError("JSON dari AI bukan objek")

    lines = []
    for item in data.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        line = ExtractedLine(
            description=to_text(item.get("description")),
            qty=to_decimal(item.get("qty")),
            unit_price=to_decimal(item.get("unit_price")),
            subtotal=to_decimal(item.get("subtotal")),
        )
        if any(v is not None for v in vars(line).values()):
            lines.append(line)

    return ExtractedInvoice(
        vendor_name=to_text(data.get("vendor_name")),
        invoice_no=to_text(data.get("invoice_no")),
        invoice_date=to_date(data.get("invoice_date")),
        line_items=lines,
        total=to_decimal(data.get("total")),
        bank_name=to_text(data.get("bank_name")),
        account_no=to_text(data.get("account_no")),
        account_name=to_text(data.get("account_name")),
        # Hanya false yang eksplisit dianggap bukan invoice, supaya jawaban AI yang tidak lengkap
        # tidak menolak invoice yang sah
        is_invoice=data.get("is_invoice") is not False,
        document_type=to_text(data.get("document_type")),
        not_invoice_reason=to_text(data.get("not_invoice_reason")),
        raw=data,
    )


class InvoiceExtractor:
    def __init__(self, bedrock: BedrockClient):
        self.bedrock = bedrock

    def extract(self, pdf_bytes: bytes) -> ExtractedInvoice:
        try:
            text = self.bedrock.read_pdf(SYSTEM_PROMPT, pdf_bytes, INSTRUCTION,
                                         max_tokens=settings.extraction_max_tokens)
        except BedrockError as e:
            raise ExtractionError(str(e)) from e
        return parse_response(text)
