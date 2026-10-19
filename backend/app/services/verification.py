"""Verifikasi oleh SISTEM, bukan AI (FR-3.1): kelengkapan, angka, dan duplikasi (PRD bagian 6).

Pesan kendala ditulis dalam bahasa sederhana untuk PIC Klien (FR-3.3).
"""
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models import IssueCode

# Field wajib dan nama yang dipahami PIC
REQUIRED_FIELDS = {
    "vendor_name": "Nama vendor",
    "invoice_no": "Nomor invoice",
    "invoice_date": "Tanggal invoice",
    "total": "Total invoice",
    "bank_name": "Nama bank",
    "account_no": "Nomor rekening",
    "account_name": "Nama penerima",
}


@dataclass
class InvoiceData:
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: date | None
    total: Decimal | None
    bank_name: str | None
    account_no: str | None
    account_name: str | None
    subtotals: list[Decimal | None]


@dataclass
class Issue:
    code: IssueCode
    field: str | None
    message: str


def normalize(text: str | None) -> str | None:
    """Huruf kecil tanpa spasi dan tanda baca: "INV-001" dan "inv 001" menjadi "inv001"."""
    if not text:
        return None
    return re.sub(r"[\W_]+", "", text.lower()) or None


def rupiah(value: Decimal) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return "Rp " + (text[:-3] if text.endswith(",00") else text)


# Tarif PPN yang berlaku (11%, dan 12% sejak 2025): selisih sebesar ini hampir pasti PPN yang belum tercatat
PPN_RATES = (Decimal("0.11"), Decimal("0.12"))


def _tax_hint(line_sum: Decimal, total: Decimal) -> str:
    diff = total - line_sum
    for rate in PPN_RATES:
        if line_sum > 0 and abs(diff - line_sum * rate) <= 1:  # toleransi pembulatan Rp 1
            return (f" Selisihnya {rupiah(diff)} = {int(rate * 100)}% dari jumlah rincian, kemungkinan PPN yang "
                    "belum tercatat di rincian. Bila invoice mencantumkan PPN, tambahkan baris pajak sebesar itu.")
    return ""


# Reimburse (bon tol, parkir, makan): bon biasanya tanpa nomor invoice dan rekening, dan uangnya ke karyawan
REIMBURSE_REQUIRED = ("invoice_date", "total")


def verify(data: InvoiceData, duplicate_request_id: str | None = None,
           payees: list[tuple[str | None, str | None]] | None = None, reimburse: bool = False) -> list[Issue]:
    """`payees`: (vendor, rekening) ternormalisasi per invoice bila satu voucher berisi beberapa invoice.
    `reimburse`: Voucher Pengeluaran Reimburse; hanya tanggal dan total wajib, boleh banyak vendor."""
    issues: list[Issue] = []

    required = {k: v for k, v in REQUIRED_FIELDS.items() if not reimburse or k in REIMBURSE_REQUIRED}
    for name, label in required.items():
        if getattr(data, name) in (None, ""):
            issues.append(Issue(IssueCode.MISSING_EVIDENCE, name,
                                f"{label} tidak ditemukan di invoice. Lengkapi {label.lower()}, "
                                "lalu kirim perbaikan."))
    if not data.subtotals:
        issues.append(Issue(IssueCode.MISSING_EVIDENCE, "line_items",
                            "Rincian barang/jasa tidak ditemukan di invoice. "
                            "Pastikan invoice memuat daftar barang beserta subtotalnya."))
    elif any(s is None for s in data.subtotals):
        issues.append(Issue(IssueCode.MISSING_EVIDENCE, "line_items",
                            "Ada baris barang/jasa tanpa subtotal. Periksa kembali rincian invoice."))
    elif data.total is not None:
        line_sum = sum(data.subtotals, Decimal(0))
        if line_sum != data.total:
            issues.append(Issue(IssueCode.CALCULATION_DISCREPANCY, "total",
                                f"Jumlah rincian barang ({rupiah(line_sum)}) tidak sama dengan total "
                                f"invoice ({rupiah(data.total)}). Konfirmasi ke vendor mana yang benar."
                                + _tax_hint(line_sum, data.total)))

    vendors = {v for v, _ in payees or [] if v}
    accounts = {a for _, a in payees or [] if a}
    if not reimburse and (len(vendors) > 1 or len(accounts) > 1):
        what = "vendor" if len(vendors) > 1 else "nomor rekening tujuan"
        issues.append(Issue(IssueCode.VENDOR_MISMATCH, "vendor_name" if len(vendors) > 1 else "account_no",
                            f"Invoice dalam pengajuan ini memiliki {what} yang berbeda. Satu voucher hanya untuk "
                            "satu vendor dan satu rekening. Pisahkan invoice per vendor, lalu ajukan ulang."))

    if duplicate_request_id:
        issues.append(Issue(IssueCode.POSSIBLE_DUPLICATE, "invoice_no",
                            f"Invoice nomor {data.invoice_no} dari {data.vendor_name} sudah pernah "
                            f"diajukan dengan Request ID {duplicate_request_id}. Periksa apakah tagihan "
                            "ini sama, dan beri tahu Finance Reviewer bila memang ganda."))
    return issues
