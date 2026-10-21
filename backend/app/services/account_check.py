"""Verifikasi rekening pembayaran terhadap data referensi tepercaya.

Rekening yang terbaca AI atau diisi PIC tidak dianggap benar dengan sendirinya. Acuannya adalah data
vendor di Data Referensi yang sudah DIVERIFIKASI Finance Reviewer (bukan oleh pendaftarnya):
- VERIFIED   : rekening sama dengan rekening vendor terverifikasi;
- MISMATCH   : vendor terverifikasi tetapi rekeningnya berbeda → kendala ACCOUNT_MISMATCH, voucher tertahan;
- UNVERIFIED : vendor belum terdaftar/terverifikasi → reviewer wajib mengonfirmasi pengecekan saat menyetujui;
- MISSING    : rekening tidak diisi (opsional, tidak menghalangi apa pun).
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from app.models import CATEGORY_REIMBURSE, Document, User, Vendor
from app.services import tax_service
from app.services.verification import normalize

VERIFIED, MISMATCH, UNVERIFIED, MISSING = "VERIFIED", "MISMATCH", "UNVERIFIED", "MISSING"
# Reimburse dibayarkan ke karyawan, bukan ke vendor di bon: rekening vendor tidak dicek
NOT_APPLICABLE = "NOT_APPLICABLE"


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


@dataclass
class AccountCheck:
    state: str
    message: str
    source: str  # "PIC" bila nomor rekening diisi/diubah PIC, "AI" bila dibaca dari dokumen
    vendor: str | None = None
    verified_by: str | None = None


def check_payee(db, vendor: Vendor | None, account_no: str | None, source: str) -> AccountCheck:
    """Cek satu rekening tujuan terhadap data vendor terverifikasi (`vendor` None = belum terdaftar)."""
    account = digits(account_no)
    by_pic = " Nomor rekening ini diisi PIC, bukan dibaca dari dokumen." if source == "PIC" else ""
    if not account:
        return AccountCheck(MISSING, "Rekening tidak diisi (opsional; tidak dicetak di voucher).", source)
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
        return AccountCheck(MISMATCH, f"Rekening {account_no} berbeda dengan rekening terverifikasi vendor {vendor.name} "
                                      f"({vendor.bank_name or '-'} {vendor.account_no}). Pastikan ke vendor sebelum "
                                      "membayar; bisa jadi rekening palsu." + by_pic, source, vendor.name, verifier)
    return AccountCheck(VERIFIED, f"Cocok dengan rekening vendor {vendor.name} yang diverifikasi {verifier or 'Finance Reviewer'}.",
                        source, vendor.name, verifier)


@dataclass
class PayeeCheck:
    """Satu penerima pembayaran (vendor + rekening) dalam voucher, dengan invoice yang dibayarkan kepadanya."""
    vendor_name: str | None
    bank_name: str | None
    account_no: str | None
    account_name: str | None
    invoices: list[int]  # posisi bukti
    gross: Decimal
    net: Decimal  # setelah potongan PPh
    check: AccountCheck
    vendor_id: str | None = None  # vendor di Data Referensi bila terdaftar
    vendor_verified: bool = False
    reference_matches: bool = False  # rekening di Data Referensi sama dengan rekening invoice


def _vendor(db, client_id, name: str | None) -> Vendor | None:
    norm = normalize(name)
    if not norm:
        return None
    return db.scalar(select(Vendor).where(Vendor.client_id == client_id, Vendor.name_norm == norm))


def payee_checks(db, doc: Document) -> list[PayeeCheck]:
    """Rekening per invoice (feedback owner: satu voucher boleh berisi beberapa vendor/rekening setelah PIC
    mengonfirmasi). Invoice dengan vendor dan rekening sama digabung menjadi satu baris."""
    if doc.request_type == CATEGORY_REIMBURSE or doc.extraction is None:
        return []
    from app.services.document_processing import file_data  # hindari import melingkar

    ex = doc.extraction
    single = len(doc.files or []) <= 1
    rows = [(f.position, file_data(doc, f)) for f in doc.files] or [(1, {
        "vendor_name": ex.vendor_name, "bank_name": ex.bank_name, "account_no": ex.account_no,
        "account_name": ex.account_name, "total": ex.total})]
    result: dict[tuple, PayeeCheck] = {}
    for position, data in rows:
        if single:  # data gabungan (bisa diubah lewat perbaikan PIC) = data satu-satunya invoice
            data = {**data, **{k: getattr(ex, k) for k in ("vendor_name", "bank_name", "account_no", "account_name")}}
        key = (normalize(data.get("vendor_name")), digits(data.get("account_no")))
        gross = Decimal(str(data.get("total") or 0))
        net = gross - tax_service.file_tax_total(data)
        if key in result:
            row = result[key]
            row.invoices.append(position)
            row.gross += gross
            row.net += net
            continue
        by_pic = data.get("account_by_pic") or (single and "account_no" in (doc.pic_overrides or {}))
        vendor = _vendor(db, doc.client_id, data.get("vendor_name"))
        result[key] = PayeeCheck(
            data.get("vendor_name"), data.get("bank_name"), data.get("account_no"), data.get("account_name"),
            [position], gross, net, check_payee(db, vendor, data.get("account_no"), "PIC" if by_pic else "AI"),
            str(vendor.id) if vendor else None, bool(vendor and vendor.verified_at and vendor.is_active),
            bool(vendor and key[1] and digits(vendor.account_no) == key[1]))
    return list(result.values())


def check_account(db, doc: Document) -> AccountCheck:
    """Ringkasan pemeriksaan semua rekening tujuan voucher (satu rekening: hasil cek rekening itu)."""
    if doc.request_type == CATEGORY_REIMBURSE:
        return AccountCheck(NOT_APPLICABLE, "Reimburse dibayarkan ke karyawan; rekening vendor tidak dicek.", "AI")
    payees = payee_checks(db, doc)
    if not payees:
        return AccountCheck(MISSING, "Rekening tidak diisi (opsional; tidak dicetak di voucher).", "AI")
    if len(payees) == 1:
        return payees[0].check
    source = "PIC" if any(p.check.source == "PIC" for p in payees) else "AI"
    label = lambda p: f"{p.vendor_name or 'vendor tanpa nama'} ({p.account_no or '-'})"  # noqa: E731
    bad = [p for p in payees if p.check.state == MISMATCH]
    if bad:
        return AccountCheck(MISMATCH, " ".join(f"{label(p)}: {p.check.message}" for p in bad), source)
    if all(p.check.state == MISSING for p in payees):
        return AccountCheck(MISSING, "Rekening tidak diisi (opsional; tidak dicetak di voucher).", source)
    unverified = [p for p in payees if p.check.state == UNVERIFIED]
    if unverified:
        return AccountCheck(UNVERIFIED, f"{len(unverified)} dari {len(payees)} rekening tujuan belum terverifikasi: "
                                        + "; ".join(label(p) for p in unverified) + ".", source)
    return AccountCheck(VERIFIED, f"Semua {len(payees)} rekening tujuan cocok dengan rekening vendor terverifikasi.",
                        source)
