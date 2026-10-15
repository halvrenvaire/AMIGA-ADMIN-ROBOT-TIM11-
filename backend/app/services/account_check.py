"""Verifikasi rekening pembayaran terhadap data referensi tepercaya.

Rekening yang terbaca AI atau diisi PIC tidak dianggap benar dengan sendirinya. Acuannya adalah data
vendor di Data Referensi yang sudah DIVERIFIKASI Finance Reviewer (bukan oleh pendaftarnya):
- VERIFIED   : rekening sama dengan rekening vendor terverifikasi;
- MISMATCH   : vendor terverifikasi tetapi rekeningnya berbeda → kendala ACCOUNT_MISMATCH, voucher tertahan;
- UNVERIFIED : vendor belum terdaftar/terverifikasi → reviewer wajib mengonfirmasi pengecekan saat menyetujui;
- MISSING    : rekening tidak ada (sudah tercatat sebagai MISSING_EVIDENCE).
"""
import re
from dataclasses import dataclass

from app.models import Document, User

VERIFIED, MISMATCH, UNVERIFIED, MISSING = "VERIFIED", "MISMATCH", "UNVERIFIED", "MISSING"


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


@dataclass
class AccountCheck:
    state: str
    message: str
    source: str  # "PIC" bila nomor rekening diisi/diubah PIC, "AI" bila dibaca dari dokumen
    vendor: str | None = None
    verified_by: str | None = None


def check_account(db, doc: Document) -> AccountCheck:
    ex = doc.extraction
    account = digits(ex.account_no if ex else None)
    source = "PIC" if "account_no" in (doc.pic_overrides or {}) else "AI"
    by_pic = " Nomor rekening ini diisi PIC, bukan dibaca dari dokumen." if source == "PIC" else ""
    if not account:
        return AccountCheck(MISSING, "Nomor rekening tujuan belum ada.", source)

    vendor = doc.vendor
    if vendor is None:
        return AccountCheck(UNVERIFIED, "Vendor belum terdaftar di Data Referensi, jadi rekening belum bisa dicocokkan "
                                        "dengan sumber tepercaya." + by_pic, source)
    reference = digits(vendor.account_no)
    if vendor.verified_at is None or not reference or not vendor.is_active:
        same = " Nomornya sama dengan data referensi, tetapi" if reference and reference == account else ""
        return AccountCheck(UNVERIFIED, (f"{same} data rekening vendor {vendor.name} belum diverifikasi Finance Reviewer."
                                         if same else f"Data rekening vendor {vendor.name} belum diverifikasi Finance "
                                                      "Reviewer.").strip() + by_pic, source, vendor.name)
    verifier = db.get(User, vendor.verified_by).full_name if vendor.verified_by else None
    if reference != account:
        return AccountCheck(MISMATCH, f"Rekening {ex.account_no} berbeda dengan rekening terverifikasi vendor {vendor.name} "
                                      f"({vendor.bank_name or '-'} {vendor.account_no}). Pastikan ke vendor sebelum "
                                      "membayar; bisa jadi rekening palsu." + by_pic, source, vendor.name, verifier)
    return AccountCheck(VERIFIED, f"Cocok dengan rekening vendor {vendor.name} yang diverifikasi {verifier or 'Finance Reviewer'}.",
                        source, vendor.name, verifier)
