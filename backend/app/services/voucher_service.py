"""Pembuatan voucher PDF setelah disetujui (F5). Target <= 3 detik (FR-5.1).

Teks batas otorisasi dicetak di dalam PDF sehingga tidak bisa dihapus dari layar (FR-5.2).
"""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, User, Voucher
from app.services import storage
from app.services.verification import rupiah

TEAL = (54, 127, 137)  # #367F89, teal brand amiga yang cukup kontras untuk teks putih
PINK = (255, 128, 180)  # #FF80B4
WIB = ZoneInfo("Asia/Jakarta")


def next_voucher_no(db: Session, now: datetime) -> str:
    """VCH/2026/10/0001: urut per bulan (WIB)."""
    now = now.astimezone(WIB)
    prefix = f"{settings.voucher_prefix}/{now:%Y/%m}/"
    count = db.scalar(select(func.count()).select_from(Voucher).where(Voucher.voucher_no.like(f"{prefix}%")))
    return f"{prefix}{count + 1:04d}"


def _t(value) -> str:
    """Font bawaan PDF hanya Latin-1; karakter lain diganti tanda tanya, bukan error."""
    return ("-" if value in (None, "") else str(value)).encode("latin-1", "replace").decode("latin-1")


def _money(value: Decimal | None) -> str:
    return "-" if value is None else rupiah(value)


def render_voucher(doc: Document, voucher_no: str, approver: User, approved_at: datetime) -> bytes:
    ex = doc.extraction
    approved_at = approved_at.astimezone(WIB)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, 210, 26, style="F")
    pdf.set_fill_color(*PINK)
    pdf.rect(0, 26, 210, 1.2, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(12, 7)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 7, "amiga  Robot Admin", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Voucher Pembayaran Vendor  |  Back Office as A Service")
    pdf.set_text_color(15, 23, 42)
    pdf.set_y(32)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, f"VOUCHER {voucher_no}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    rows = [
        ("Klien", doc.client.name), ("Request ID", doc.request_id),
        ("Vendor", ex.vendor_name), ("No. Invoice", ex.invoice_no),
        ("Tgl. Invoice", ex.invoice_date.strftime("%d-%m-%Y") if ex.invoice_date else None),
        ("Tgl. Voucher", approved_at.strftime("%d-%m-%Y")),
    ]
    for label, value in rows:
        pdf.cell(32, 6, label)
        pdf.cell(0, 6, f": {_t(value)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = (10, 84, 18, 38, 40)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(235, 245, 246)
    for w, h in zip(widths, ("No", "Uraian", "Qty", "Harga Satuan", "Subtotal")):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for line in ex.line_items:
        qty = "-" if line.qty is None else f"{line.qty.normalize():f}"
        for w, text, align in zip(widths, (str(line.position), _t(line.description)[:60], qty,
                                           _money(line.unit_price), _money(line.subtotal)),
                                  ("C", "L", "C", "R", "R")):
            pdf.cell(w, 7, text, border=1, align=align)
        pdf.ln()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(sum(widths[:4]), 8, "TOTAL DIBAYARKAN", border=1, align="R")
    pdf.cell(widths[4], 8, _money(ex.total), border=1, align="R")
    pdf.ln(12)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Rekening tujuan", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, value in [("Bank", ex.bank_name), ("No. Rekening", ex.account_no), ("Atas Nama", ex.account_name)]:
        pdf.cell(32, 6, label)
        pdf.cell(0, 6, f": {_t(value)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _t(f"Ditinjau dan disetujui oleh Finance Reviewer AMIGA: {approver.full_name}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Waktu persetujuan: {approved_at:%d-%m-%Y %H:%M} WIB", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_draw_color(*TEAL)
    pdf.set_fill_color(254, 243, 227)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, _t(settings.voucher_authorization_text), border=1, fill=True, padding=3)
    return bytes(pdf.output())


def create_voucher(db: Session, doc: Document, approver: User) -> Voucher:
    now = datetime.now(timezone.utc)
    voucher_no = next_voucher_no(db, now)
    file_key = f"vouchers/{voucher_no.replace('/', '-')}.pdf"
    storage.save(file_key, render_voucher(doc, voucher_no, approver, now))
    voucher = Voucher(document_id=doc.id, voucher_no=voucher_no, file_key=file_key, generated_by=approver.id)
    db.add(voucher)
    db.flush()
    return voucher
