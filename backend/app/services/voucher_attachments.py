"""Lampiran bukti di Voucher Pengeluaran (feedback owner): halaman 2 dst. berisi semua file yang diunggah PIC.

Halaman bukti ditempel apa adanya (vektor, bukan hasil foto ulang), sehingga teks invoice tetap tajam saat
diperbesar. Reimburse yang buktinya banyak (bon tol, parkir) digabung 4 per halaman; invoice vendor 1 per
halaman agar tetap terbaca.
"""
import io
import math

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter, Transformation

from app.models import CATEGORY_REIMBURSE, Document
from app.services import storage

A4_W, A4_H = 595.28, 841.89  # pt
MARGIN, HEADER, CAPTION, GAP = 30, 44, 16, 14
TEAL = (47, 111, 120)


def _t(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def evidence_pages(doc: Document) -> list[tuple[str, object]]:
    """(label, halaman PDF) untuk setiap halaman bukti, berurutan seperti diunggah."""
    sources = [(f.original_filename, f.file_key) for f in doc.files] or [(doc.original_filename, doc.file_key)]
    pages = []
    for i, (name, key) in enumerate(sources, start=1):
        reader = PdfReader(io.BytesIO(storage.load(key)))
        for p, page in enumerate(reader.pages, start=1):
            suffix = f" (hal. {p}/{len(reader.pages)})" if len(reader.pages) > 1 else ""
            pages.append((f"Lampiran {i}: {name}{suffix}", page))
    return pages


def _grid(per_page: int) -> tuple[int, int]:
    return (2, 2) if per_page == 4 else (1, 1)


def _slots(cols: int, rows: int) -> list[tuple[float, float, float, float]]:
    """Kotak (x, y_atas, lebar, tinggi) dalam pt, koordinat dari kiri atas."""
    w = (A4_W - 2 * MARGIN - GAP * (cols - 1)) / cols
    h = (A4_H - 2 * MARGIN - HEADER - GAP * (rows - 1)) / rows
    return [(MARGIN + c * (w + GAP), MARGIN + HEADER + r * (h + GAP), w, h) for r in range(rows) for c in range(cols)]


def append_attachments(voucher_pdf: bytes, doc: Document, voucher_no: str) -> bytes:
    pages = evidence_pages(doc)
    if not pages:
        return voucher_pdf
    per_page = 4 if doc.request_type == CATEGORY_REIMBURSE else 1
    cols, rows = _grid(per_page)
    slots = _slots(cols, rows)
    n_sheets = math.ceil(len(pages) / per_page)

    # Halaman lampiran: judul, bingkai, dan keterangan tiap bukti (bukti ditempel kemudian)
    sheet = FPDF(unit="pt", format="A4")
    sheet.set_auto_page_break(False)
    for s in range(n_sheets):
        sheet.add_page()
        sheet.set_text_color(*TEAL)
        sheet.set_font("Helvetica", "B", 13)
        sheet.set_xy(MARGIN, MARGIN)
        sheet.cell(0, 16, _t(f"LAMPIRAN BUKTI  ·  {voucher_no}"))
        sheet.set_font("Helvetica", "", 9)
        sheet.set_text_color(90, 105, 110)
        sheet.set_xy(MARGIN, MARGIN + 18)
        sheet.cell(0, 12, _t(f"Lembar {s + 1} dari {n_sheets}  ·  {len(pages)} halaman bukti yang diunggah PIC"))
        sheet.set_draw_color(*TEAL)
        sheet.set_line_width(1)
        sheet.line(MARGIN, MARGIN + 36, A4_W - MARGIN, MARGIN + 36)
        sheet.set_draw_color(200, 210, 212)
        sheet.set_line_width(0.6)
        for k, (x, y, w, h) in enumerate(slots):
            idx = s * per_page + k
            if idx >= len(pages):
                break
            sheet.rect(x, y, w, h)
            sheet.set_font("Helvetica", "B", 8.5)
            sheet.set_text_color(40, 50, 55)
            sheet.set_xy(x + 4, y + 3)
            label = pages[idx][0]
            while sheet.get_string_width(_t(label)) > w - 8 and len(label) > 10:
                label = label[:-4] + "..."
            sheet.cell(w - 8, 10, _t(label))

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(voucher_pdf)))
    first = len(writer.pages)
    for page in PdfReader(io.BytesIO(bytes(sheet.output()))).pages:
        writer.add_page(page)
    for idx, (_, src) in enumerate(pages):
        target = writer.pages[first + idx // per_page]
        x, y, w, h = slots[idx % per_page]
        box = src.mediabox
        sw, sh = float(box.width), float(box.height)
        if src.get("/Rotate", 0) in (90, 270):
            src.transfer_rotation_to_content()
            box = src.mediabox
            sw, sh = float(box.width), float(box.height)
        cw, ch = w - 8, h - CAPTION - 6
        scale = min(cw / sw, ch / sh)
        ox = x + 4 + (cw - sw * scale) / 2
        oy_top = y + CAPTION + 2 + (ch - sh * scale) / 2
        oy = A4_H - oy_top - sh * scale  # koordinat PDF dari kiri bawah
        t = Transformation().translate(-float(box.left), -float(box.bottom)).scale(scale).translate(ox, oy)
        target.merge_transformed_page(src, t)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
