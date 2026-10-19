"""Pembuatan voucher PDF setelah disetujui (F5). Target <= 3 detik (FR-5.1).

Teks batas otorisasi dicetak di dalam PDF sehingga tidak bisa dihapus dari layar (FR-5.2).
"""
import io
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fpdf import FPDF, FontFace
from fpdf.enums import TableCellFillMode
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, settings
from app.models import Document, User, Voucher
from app.services import audit_service, signature_service, storage
from app.services.signer_service import COMPANY_POSITION
from app.services.verification import rupiah

TEAL = (54, 127, 137)  # #367F89, teal brand amiga yang cukup kontras untuk teks putih
PINK = (255, 128, 180)  # #FF80B4
WIB = ZoneInfo("Asia/Jakarta")


LOGO = BACKEND_DIR / "app" / "assets" / "logo-amiga.png"  # logo resmi amiga (250x78 px)


def brand_header(pdf: FPDF, page_width: float, title: str) -> None:
    """Kop dokumen: logo amiga di kiri, jenis dokumen di kanan, garis teal + pink di bawah."""
    pdf.image(str(LOGO), x=12, y=7, h=13)  # lebar mengikuti rasio logo
    pdf.set_text_color(*TEAL)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(page_width - 12 - 120, 8.5)
    pdf.cell(120, 5, title, align="R")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(90, 105, 110)
    pdf.set_xy(page_width - 12 - 120, 14)
    pdf.cell(120, 4.5, "Back Office as A Service", align="R")
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 24, page_width, 1.2, style="F")
    pdf.set_fill_color(*PINK)
    pdf.rect(0, 25.2, page_width, 0.8, style="F")
    pdf.set_text_color(15, 23, 42)


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


def render_voucher(doc: Document, voucher_no: str, approver: User, approved_at: datetime,
                   signatures: list[bytes | None] | None = None) -> bytes:
    """`signatures`: spesimen tanda tangan elektronik per penanda tangan di `doc.signers` (urutan sama)."""
    ex = doc.extraction
    approved_at = approved_at.astimezone(WIB)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()

    brand_header(pdf, 210, "Voucher Pengeluaran")
    pdf.set_y(32)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, f"VOUCHER PENGELUARAN {voucher_no}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    n_files = len(getattr(doc, "files", None) or [])
    rows = [
        ("Klien", doc.client.name), ("Request ID", doc.request_id),
        ("Vendor", ex.vendor_name), ("No. Invoice" if n_files <= 1 else f"No. Invoice ({n_files})", ex.invoice_no),
        ("Tgl. Invoice", ex.invoice_date.strftime("%d-%m-%Y") if ex.invoice_date else None),
        ("Tgl. Voucher", approved_at.strftime("%d-%m-%Y")),
    ]
    for label, value in rows:
        pdf.cell(32, 6, label)
        # multi_cell: beberapa nomor invoice dalam satu voucher bisa lebih dari satu baris
        pdf.multi_cell(0, 6, f": {_t(value)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Tabel fpdf2: uraian panjang dibungkus ke baris berikutnya dan tinggi baris menyesuaikan,
    # sehingga teks tidak meluber ke kolom lain. Header diulang bila tabel berlanjut ke halaman baru.
    pdf.set_draw_color(150, 160, 165)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Helvetica", "", 9)
    with pdf.table(
        cell_fill_mode=TableCellFillMode.NONE,
        col_widths=(10, 84, 18, 38, 40),
        text_align=("CENTER", "LEFT", "CENTER", "RIGHT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD", fill_color=(235, 245, 246)),
        line_height=5,
        padding=1.5,
        v_align="MIDDLE",
        first_row_as_headings=True,
        repeat_headings=1,
    ) as table:
        header = table.row()
        for title in ("No", "Uraian", "Qty", "Harga Satuan", "Subtotal"):
            header.cell(title, align="CENTER")
        for line in ex.line_items:
            qty = "-" if line.qty is None else f"{line.qty.normalize():f}"
            row = table.row()
            for text in (str(line.position), _t(line.description), qty,
                         _money(line.unit_price), _money(line.subtotal)):
                row.cell(text)
        total = table.row(style=FontFace(emphasis="BOLD", size_pt=10))
        total.cell("TOTAL DIBAYARKAN", colspan=4, align="RIGHT")
        total.cell(_money(ex.total))
    pdf.ln(12)

    # Rekening tujuan tidak dicetak (feedback owner): pengecekan rekening tetap berjalan di sistem
    pdf.ln(2)

    signed = _signature_blocks(pdf, doc, signatures or [], approved_at)
    if signed:
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(90, 100, 105)
        pdf.multi_cell(0, 3.6, f"Tanda tangan elektronik pada {signed} kotak dibubuhkan sistem AMIGA saat voucher terbit "
                               f"({approved_at.strftime('%d-%m-%Y %H:%M')} WIB) dari spesimen yang didaftarkan PIC Klien. "
                               f"Pembubuhan tercatat di jejak audit {doc.request_id}.",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(15, 23, 42)
        pdf.ln(2)
    pdf.ln(1)

    pdf.set_draw_color(*TEAL)
    pdf.set_fill_color(254, 243, 227)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, _t(settings.voucher_authorization_text), border=1, fill=True, padding=3)
    return bytes(pdf.output())


SIGN_BLOCK_H = 46  # mm per kotak: judul, ruang tanda tangan, garis, tiga baris keterangan
SIGN_MAX_PER_ROW = 3
BLANK = "..............................................."


def _sign_boxes(doc: Document) -> list[tuple[str, str, list[str], bool]]:
    """(judul, petunjuk, baris keterangan, opsional). Hanya pihak klien: diajukan → disetujui.
    Persetujuan Finance Reviewer AMIGA tidak ditandatangani di voucher (keputusan owner); tercatat di jejak audit."""
    signers = getattr(doc, "signers", None) or []
    pengaju = [s for s in signers if s["kind"] == "PENGAJU"]
    penyetuju = [s for s in signers if s["kind"] == "PENYETUJU"]
    client_lines = lambda s: [_t(s["name"]), _t(s["position"]), f"Tanggal: {BLANK[:30]}"]  # noqa: E731
    # Diajukan oleh = perusahaan klien; nama penanda tangan ditulis tangan
    company_lines = lambda s: [_t(s["name"]), f"Nama: {BLANK[:26]}", f"Tanggal: {BLANK[:24]}"]  # noqa: E731
    boxes = [("Diajukan oleh", "Tanda tangan & cap perusahaan" if p["position"] == COMPANY_POSITION else "Tanda tangan",
              (company_lines if p["position"] == COMPANY_POSITION else client_lines)(p), False) for p in pengaju] or [
        ("Diajukan oleh", "Tanda tangan", [f"Nama: {BLANK[:26]}", "Jabatan: PIC Klien", f"Tanggal: {BLANK[:24]}"], False)]
    boxes += [("Disetujui oleh", "Tanda tangan", client_lines(p), False) for p in penyetuju] or [
        ("Disetujui oleh (opsional)", "Tanda tangan bila diperlukan klien",
         [f"Nama: {BLANK[:26]}", "Jabatan: Client Approver", f"Tanggal: {BLANK[:24]}"], True)]
    return boxes


def _box_images(doc: Document, signatures: list[bytes | None]) -> list[bytes | None]:
    """Spesimen untuk tiap kotak dari _sign_boxes (pengaju dulu, lalu penyetuju)."""
    signers = getattr(doc, "signers", None) or []
    paired = list(zip(signers, signatures + [None] * len(signers)))
    return ([img for s, img in paired if s["kind"] == "PENGAJU"] or [None]) + \
           ([img for s, img in paired if s["kind"] == "PENYETUJU"] or [None])


def _signature_blocks(pdf: FPDF, doc: Document, signatures: list[bytes | None], signed_at: datetime) -> int:
    """Kotak tanda tangan agar voucher sah. Satu baris kotak tidak pernah terbelah halaman.
    Kotak dengan spesimen elektronik berisi gambar tanda tangan; kotak lain kosong untuk tanda tangan basah.
    Mengembalikan jumlah kotak yang ditandatangani secara elektronik."""
    boxes = _sign_boxes(doc)
    images = _box_images(doc, signatures)
    signed = 0
    # 2 atau 4 kotak → 2 per baris; selain itu maks. 3 per baris
    per_row = 2 if len(boxes) in (2, 4) else min(SIGN_MAX_PER_ROW, len(boxes))
    gap = 8
    width = (pdf.epw - gap * (per_row - 1)) / per_row
    for row_start in range(0, len(boxes), per_row):
        if pdf.will_page_break(SIGN_BLOCK_H + 4):
            pdf.add_page()
        top = pdf.get_y()
        for i, (title, hint, lines, optional) in enumerate(boxes[row_start:row_start + per_row]):
            x = pdf.l_margin + i * (width + gap)
            image = images[row_start + i] if row_start + i < len(images) else None
            if image:
                signed += 1
                hint = "Tanda tangan elektronik"
                lines = lines[:-1] + [f"Ditandatangani: {signed_at.strftime('%d-%m-%Y %H:%M')} WIB"]
            pdf.set_line_width(0.3)
            pdf.set_draw_color(150, 160, 165)
            if optional:
                pdf.set_dash_pattern(dash=1.2, gap=1)
            pdf.rect(x, top, width, SIGN_BLOCK_H)
            pdf.set_dash_pattern()

            pdf.set_xy(x + 3, top + 2.5)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(40, 50, 55)
            pdf.cell(width - 6, 5, title)
            pdf.set_xy(x + 3, top + 7)
            pdf.set_font("Helvetica", "", 6.5)
            pdf.set_text_color(120, 130, 135)
            pdf.cell(width - 6, 4, hint)
            pdf.set_text_color(15, 23, 42)

            line_y = top + 29
            if image:
                # Gambar menyesuaikan kotak (rasio dijaga, rata tengah) di atas garis tanda tangan
                pdf.image(io.BytesIO(image), x=x + 5, y=top + 11.5, w=width - 10, h=line_y - top - 12.5,
                          keep_aspect_ratio=True)
            pdf.set_draw_color(120, 130, 135)
            pdf.line(x + 3, line_y, x + width - 3, line_y)
            pdf.set_y(line_y + 1.2)
            for n, text in enumerate(lines):
                pdf.set_font("Helvetica", "B" if n == 0 and not text.startswith("Nama:") else "", 7.5)
                pdf.set_x(x + 3)
                pdf.cell(width - 6, 4.6, text[:48], new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(top + SIGN_BLOCK_H + 4)
    pdf.set_draw_color(*TEAL)
    return signed


def create_voucher(db: Session, doc: Document, approver: User) -> Voucher:
    now = datetime.now(timezone.utc)
    voucher_no = next_voucher_no(db, now)
    file_key = f"vouchers/{voucher_no.replace('/', '-')}.pdf"
    signers = getattr(doc, "signers", None) or []
    signatures = signature_service.for_signers(db, signers)
    storage.save(file_key, render_voucher(doc, voucher_no, approver, now, signatures))
    names = [s["name"] for s, img in zip(signers, signatures) if img]
    if names:
        audit_service.record(db, approver, "E_SIGNATURE_APPLIED", document_id=doc.id, client_id=doc.client_id,
                             new_value="; ".join(names),
                             note=f"Tanda tangan elektronik dibubuhkan pada voucher {voucher_no}")
    voucher = Voucher(document_id=doc.id, voucher_no=voucher_no, file_key=file_key, generated_by=approver.id)
    db.add(voucher)
    db.flush()
    return voucher
