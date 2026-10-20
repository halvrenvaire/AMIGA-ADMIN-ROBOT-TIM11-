"""Pembuatan voucher PDF setelah disetujui (F5). Target <= 3 detik (FR-5.1).

Kop memakai logo klien yang mengajukan. Teks batas otorisasi (FR-5.2) tidak lagi dicetak atas permintaan
owner (19 Okt 2026).
"""
import io
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fpdf import FPDF, FontFace
from PIL import Image
from fpdf.enums import TableCellFillMode
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, settings
from app.models import Document, User, Voucher
from app.services import audit_service, signature_service, storage, tax_service, voucher_attachments
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


def client_header(pdf: FPDF, client, title: str) -> None:
    """Kop Voucher Pengeluaran: logo klien yang mengajukan (nama klien bila belum ada logo), jenis dokumen
    di kanan. Logo dan tagline amiga tidak dicetak (feedback owner 19 Okt 2026)."""
    logo = getattr(client, "logo_png", None)
    if logo:
        with Image.open(io.BytesIO(logo)) as img:
            ratio = img.width / img.height
        h = 13 if 13 * ratio <= 70 else 70 / ratio  # tinggi 13 mm, lebar maks. 70 mm
        pdf.image(io.BytesIO(logo), x=12, y=7 + (13 - h) / 2, h=h)
    else:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(15, 23, 42)
        pdf.set_xy(12, 9)
        pdf.cell(110, 7, _t(client.name))
    pdf.set_text_color(51, 65, 85)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_xy(210 - 12 - 80, 10.5)
    pdf.cell(80, 5, title, align="R")
    pdf.set_draw_color(51, 65, 85)
    pdf.set_line_width(0.4)
    pdf.line(12, 24, 198, 24)
    pdf.set_line_width(0.2)
    pdf.set_text_color(15, 23, 42)


def _simulation_mark(pdf: FPDF) -> None:
    """Tanda SIMULASI diagonal di setiap halaman: tidak bisa dipakai sebagai voucher resmi."""
    pdf.set_auto_page_break(False)
    for page in range(1, pdf.page_no() + 1):
        pdf.page = page
        with pdf.local_context(fill_opacity=0.12, text_color=(176, 48, 106)):
            pdf.set_font("Helvetica", "B", 64)
            with pdf.rotation(35, x=105, y=150):
                pdf.set_xy(5, 140)
                pdf.cell(200, 24, "SIMULASI", align="C")
        pdf.set_xy(12, 287)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(176, 48, 106)
        pdf.cell(186, 4, "SIMULASI - bukan voucher resmi. Nomor voucher terbit setelah disetujui Finance Reviewer.",
                 align="C")
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
                   signatures: list[bytes | None] | None = None, simulation: bool = False) -> bytes:
    """`signatures`: spesimen tanda tangan elektronik per penanda tangan di `doc.signers` (urutan sama).
    `simulation`: simulasi untuk PIC sebelum dikirim ke reviewer; diberi tanda SIMULASI di setiap halaman."""
    ex = doc.extraction
    approved_at = approved_at.astimezone(WIB)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_page()

    client_header(pdf, doc.client, "Simulasi Voucher Pengeluaran" if simulation else "Voucher Pengeluaran")
    pdf.set_y(32)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, f"VOUCHER PENGELUARAN {voucher_no}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    # Klien, Request ID, vendor, serta nomor dan tanggal invoice tidak dicetak (feedback owner 19 Okt 2026)
    rows = [("Tgl. Voucher", "(terbit setelah disetujui)" if simulation else approved_at.strftime("%d-%m-%Y"))]
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
    rows, paid = voucher_rows(doc)
    with pdf.table(
        cell_fill_mode=TableCellFillMode.NONE,
        col_widths=(12, 136, 42),
        text_align=("CENTER", "LEFT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD", fill_color=(235, 245, 246)),
        line_height=5,
        padding=1.5,
        v_align="MIDDLE",
        first_row_as_headings=True,
        repeat_headings=1,
    ) as table:
        header = table.row()
        for title in ("No", "Uraian", "Jumlah"):
            header.cell(title, align="CENTER")
        for no, (text, amount, is_cut) in enumerate(rows, start=1):
            row = table.row()
            row.cell(str(no))
            row.cell(_t(text))
            row.cell(f"({_money(amount)})" if is_cut else _money(amount))
        total = table.row(style=FontFace(emphasis="BOLD", size_pt=10))
        total.cell("TOTAL DIBAYARKAN", colspan=2, align="RIGHT")
        total.cell(_money(paid))
    pdf.ln(12)

    # Rekening tujuan tidak dicetak (feedback owner): pengecekan rekening tetap berjalan di sistem
    pdf.ln(2)

    # Catatan tanda tangan elektronik dan kotak batas otorisasi tidak dicetak (feedback owner 19 Okt 2026);
    # pembubuhan tanda tangan tetap tercatat di jejak audit
    _signature_blocks(pdf, doc, signatures or [], approved_at)
    if simulation:
        _simulation_mark(pdf)
    return bytes(pdf.output())


def _dec(value) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


def voucher_rows(doc) -> tuple[list[tuple[str, Decimal, bool]], Decimal]:
    """Baris tabel voucher (feedback owner 20 Okt 2026): per invoice, barangnya dengan PPN dilebur ke nilai
    barang (dibagi proporsional; sisa pembulatan ke barang terakhir), lalu baris potongan PPh tepat di bawahnya.
    Jumlah semua baris = total dibayarkan. Hasil: [(uraian, jumlah, potongan?)], total dibayarkan."""
    from app.services.document_processing import file_data  # hindari import melingkar

    files = getattr(doc, "files", None) or []
    if files:
        groups = [file_data(doc, f) for f in files]
    else:  # dokumen lama tanpa data per invoice
        ex = doc.extraction
        groups = [{"invoice_no": ex.invoice_no, "total": ex.total,
                   "line_items": [{"description": li.description, "qty": li.qty, "unit_price": li.unit_price,
                                   "subtotal": li.subtotal} for li in ex.line_items]}]
    multi = len(groups) > 1
    rows: list[tuple[str, Decimal, bool]] = []
    for data in groups:
        lines = data.get("line_items") or []
        items = [li for li in lines if not tax_service.is_vat_line(li.get("description"))]
        has_vat = len(items) < len(lines)
        subtotals = [_dec(li.get("subtotal")) or Decimal(0) for li in items]
        base_sum = sum(subtotals, Decimal(0))
        total = _dec(data.get("total"))
        # PPN tidak dicetak sendiri: selisih total invoice dengan jumlah barang dilebur ke barang
        vat = (total - base_sum) if has_vat and total is not None else Decimal(0)
        shares = [Decimal(0)] * len(items)
        if vat and base_sum:
            for i, sub in enumerate(subtotals[:-1]):
                shares[i] = (vat * sub / base_sum).quantize(Decimal("0.01"))
            shares[-1] = vat - sum(shares[:-1], Decimal(0))
        tag = f"[{data.get('invoice_no')}] " if multi and data.get("invoice_no") else ""
        for li, sub, share in zip(items, subtotals, shares):
            qty, unit = _dec(li.get("qty")), _dec(li.get("unit_price"))
            detail = [f"{_qty(qty)} x {_money(unit)}"] if qty is not None and unit is not None else []
            if share:
                detail.append("termasuk PPN")
            text = f"{tag}{li.get('description') or '-'}" + (f" ({', '.join(detail)})" if detail else "")
            rows.append((text, sub + share, False))
        if not items and total is not None:  # invoice tanpa rincian: satu baris total
            rows.append((f"{tag}Invoice {data.get('invoice_no') or ''}".strip(), total, False))
        tax = data.get("tax")
        if tax and tax.get("code") != tax_service.NONE and _dec(tax.get("amount")):
            what = items[0].get("description") if len(items) == 1 else (data.get("invoice_no") or "invoice ini")
            rate = _qty(Decimal(str(tax["rate"])))
            rows.append((f"Potongan {tax['name']} {rate}%{'' if tax.get('npwp') else ' (tanpa NPWP)'} x DPP "
                         f"{_money(_dec(tax.get('base')))} ({what})", _dec(tax["amount"]), True))
    paid = sum((-a if cut else a for _, a, cut in rows), Decimal(0))
    return rows, paid


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
    pdf = render_voucher(doc, voucher_no, approver, now, signatures)
    storage.save(file_key, voucher_attachments.append_attachments(pdf, doc, voucher_no))
    names = [s["name"] for s, img in zip(signers, signatures) if img]
    if names:
        audit_service.record(db, approver, "E_SIGNATURE_APPLIED", document_id=doc.id, client_id=doc.client_id,
                             new_value="; ".join(names),
                             note=f"Tanda tangan elektronik dibubuhkan pada voucher {voucher_no}")
    voucher = Voucher(document_id=doc.id, voucher_no=voucher_no, file_key=file_key, generated_by=approver.id)
    db.add(voucher)
    db.flush()
    return voucher
