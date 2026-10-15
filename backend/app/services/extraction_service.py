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
  "line_items": [{"kind": "item"|"fee"|"tax"|"discount"|"summary", "description": string|null, "qty": number|null, "unit_price": string|null, "subtotal": string|null}],
  "total": string|null,
  "bank_name": string|null,
  "account_no": string|null,
  "account_name": string|null
}
Aturan: "is_invoice" adalah hasil pemeriksaan langkah 1. "document_type" adalah jenis dokumen
dalam bahasa Indonesia (mis. "Invoice", "Purchase order", "Surat lamaran"). "not_invoice_reason"
diisi satu kalimat singkat bila is_invoice false, selain itu null. Tulis setiap angka uang PERSIS seperti di invoice sebagai teks, termasuk titik dan koma (contoh
"Rp 10.000", "2.695.000"); sistem yang mengubahnya menjadi angka. "qty" boleh berupa angka. 
"vendor_name" adalah nama penjual/penerbit invoice yang sebenarnya (mis. "tiket.com (PT Global Tiket
Network)"), BUKAN judul bagian seperti "Penjual", "Vendor", "Dari", atau "Seller".
"total" adalah jumlah akhir yang harus dibayar (Total Bayar / Grand Total / Jumlah Tagihan / Amount Due).
"account_no" adalah nomor rekening tujuan pembayaran, sebagai teks.
"line_items" berisi setiap baris berangka di invoice, berurutan, dan setiap baris diberi "kind":
- "item": barang/jasa yang dibeli (mis. tiket, kertas, jasa konsultasi)
- "fee": biaya tambahan (biaya layanan, ongkos kirim, biaya admin)
- "tax": pajak (PPN, PPh, Tax)
- "discount": potongan/diskon, subtotal ditulis negatif
- "summary": baris ringkasan yang nilainya penjumlahan baris lain, mis. "Subtotal", "Subtotal Tiket",
  "Total", "Total Bayar", "Grand Total", "Jumlah". Baris di bawah judul seperti "Ringkasan Biaya" yang
  menjumlahkan item sebelumnya juga "summary".
Untuk "description", tulis teks baris itu sendiri (mis. "Subtotal Tiket"), bukan judul bagiannya.
Pada invoice yang benar, jumlah subtotal semua baris selain "summary" sama dengan "total"."""


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


def drop_running_subtotals(lines: list[ExtractedLine], total: Decimal | None) -> tuple[list[ExtractedLine], list[str]]:
    """Pengaman bila AI tetap memasukkan baris subtotal sebagai item: baris yang nilainya persis jumlah
    semua baris sebelumnya dibuang, HANYA bila setelah dibuang jumlah rincian menjadi sama dengan total
    invoice. Selain itu rincian dibiarkan apa adanya (selisih tetap dilaporkan verifikasi sistem)."""
    if total is None or not lines or any(line.subtotal is None for line in lines):
        return lines, []
    if sum((line.subtotal for line in lines), Decimal(0)) == total:
        return lines, []
    kept, removed, running, since = [], [], Decimal(0), 0
    for line in lines:
        # Subtotal menjumlahkan minimal 2 baris; dua item berharga sama tidak dianggap subtotal
        if since >= 2 and line.subtotal == running and line.subtotal != 0:
            removed.append(line)
            continue
        kept.append(line)
        running += line.subtotal
        since += 1
    if not removed or running != total:
        return lines, []
    return kept, [line.description or "-" for line in removed]


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
    summaries = []
    for item in data.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        # Baris ringkasan (Subtotal/Total) bukan komponen tagihan; bila ikut, nilainya terhitung dua kali
        if str(item.get("kind") or "").lower() == "summary":
            summaries.append(to_text(item.get("description")) or "-")
            continue
        line = ExtractedLine(
            description=to_text(item.get("description")),
            qty=to_decimal(item.get("qty")),
            unit_price=to_decimal(item.get("unit_price")),
            subtotal=to_decimal(item.get("subtotal")),
        )
        if any(v is not None for v in vars(line).values()):
            lines.append(line)

    total = to_decimal(data.get("total"))
    lines, removed = drop_running_subtotals(lines, total)
    if summaries or removed:
        data = {**data, "summary_lines_skipped": summaries + removed}
    # Titik ribuan terbaca sebagai desimal ("2.695.000" → 2695): koreksi hanya bila total tepat
    # 1000x lebih kecil dari jumlah rincian, ciri pasti salah baca format angka Indonesia
    line_sum = sum((line.subtotal for line in lines if line.subtotal is not None), Decimal(0))
    if (total is not None and lines and all(line.subtotal is not None for line in lines)
            and total != line_sum and total * 1000 == line_sum):
        data = {**data, "total_corrected_from": str(total)}
        total = line_sum

    return ExtractedInvoice(
        vendor_name=to_text(data.get("vendor_name")),
        invoice_no=to_text(data.get("invoice_no")),
        invoice_date=to_date(data.get("invoice_date")),
        line_items=lines,
        total=total,
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
