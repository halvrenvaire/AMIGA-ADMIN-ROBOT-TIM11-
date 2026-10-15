"""Rekap voucher per periode untuk Service Lead, sebagai PDF (permintaan owner 16 Okt 2026).

Isi: ringkasan, rekap per perusahaan, rekap per Finance Reviewer, dan daftar lengkap voucher.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from fpdf import FPDF, FontFace
from fpdf.enums import TableCellFillMode

from app.models import DocStatus
from app.schemas.schemas import VoucherRow
from app.services.voucher_service import TEAL, WIB, _money, _t, brand_header

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
STATUS_TEXT = {DocStatus.AMIGA_REVIEWED: "Disetujui", DocStatus.SENT_TO_CLIENT: "Terkirim ke klien"}
HEAD = FontFace(emphasis="BOLD", fill_color=(235, 245, 246))


def tgl(d: date) -> str:
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


@dataclass
class Group:
    name: str
    count: int = 0
    total: Decimal = Decimal(0)
    pics: list[str] = field(default_factory=list)


def _groups(rows: list[VoucherRow], key) -> list[Group]:
    groups: dict[str, Group] = defaultdict(lambda: Group(""))
    for r in rows:
        g = groups[key(r)]
        g.name = key(r)
        g.count += 1
        g.total += r.total or 0
        if r.pic_name and r.pic_name not in g.pics:
            g.pics.append(r.pic_name)
    return sorted(groups.values(), key=lambda g: (-g.total, g.name))


def company_with_pic(name: str, pics: list[str]) -> str:
    return f"{name}\nPIC: {', '.join(pics)}" if pics else name


def _table(pdf: FPDF, headings: tuple[str, ...], widths: tuple[float, ...], aligns: tuple[str, ...],
           rows: list[tuple[str, ...]], footer: tuple[str, ...] | None = None) -> None:
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_draw_color(150, 160, 165)
    with pdf.table(cell_fill_mode=TableCellFillMode.NONE, col_widths=widths, text_align=aligns,
                   headings_style=HEAD, line_height=4.6, padding=1.4, v_align="MIDDLE",
                   first_row_as_headings=True, repeat_headings=1, width=sum(widths), align="LEFT") as table:
        head = table.row()
        for h in headings:
            head.cell(h, align="CENTER")
        for values in rows:
            row = table.row()
            for v in values:
                row.cell(_t(v))
        if footer:
            row = table.row(style=FontFace(emphasis="BOLD"))
            for v in footer:
                row.cell(_t(v) if v else "")


def _section(pdf: FPDF, title: str) -> None:
    # Judul tidak tertinggal sendirian di bawah halaman
    if pdf.will_page_break(30):
        pdf.add_page()
    else:
        pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*TEAL)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(15, 23, 42)


class ReportPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-10)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(110, 120, 125)
        self.cell(0, 5, f"AMIGA Robot Admin - Rekap Voucher  |  Halaman {self.page_no()}/{{nb}}", align="R")


def render_report(rows: list[VoucherRow], date_from: date, date_to: date, period_label: str,
                  printed_by: str, now: datetime) -> bytes:
    pdf = ReportPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(True, margin=14)
    pdf.alias_nb_pages()
    pdf.add_page()

    brand_header(pdf, 297, "Rekap Voucher Pembayaran Vendor")
    pdf.set_y(31)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 7, f"REKAP VOUCHER  {period_label.upper()}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    span = tgl(date_from) if date_from == date_to else f"{tgl(date_from)} - {tgl(date_to)}"
    pdf.cell(0, 5.5, f"Periode: {span} (tanggal voucher terbit, WIB)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5.5, _t(f"Dicetak oleh {printed_by} pada {tgl(now.date())} {now:%H:%M} WIB"),
             new_x="LMARGIN", new_y="NEXT")

    total = sum((r.total or 0 for r in rows), Decimal(0))
    sent = sum(r.status == DocStatus.SENT_TO_CLIENT for r in rows)
    stats = [("Jumlah voucher", str(len(rows))), ("Total nilai", _money(total)),
             ("Terkirim ke klien", str(sent)), ("Belum diunduh klien", str(len(rows) - sent)),
             ("Perusahaan", str(len({r.client.id for r in rows})))]
    pdf.ln(3)
    w, gap, top = (pdf.epw - 4 * 4) / 5, 4, pdf.get_y()
    for i, (label, value) in enumerate(stats):
        x = pdf.l_margin + i * (w + gap)
        pdf.set_fill_color(240, 248, 249)
        pdf.set_draw_color(205, 226, 229)
        pdf.rect(x, top, w, 17, style="DF")
        pdf.set_xy(x + 3, top + 2.5)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(70, 85, 90)
        pdf.cell(w - 6, 4, label)
        pdf.set_xy(x + 3, top + 8)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(w - 6, 6, _t(value))
    pdf.set_y(top + 19)

    if not rows:
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "Tidak ada voucher yang terbit pada periode ini.")
        return bytes(pdf.output())

    _section(pdf, "Rekap per perusahaan")
    groups = _groups(rows, lambda r: r.client.name)
    _table(pdf, ("Perusahaan", "Jumlah voucher", "Total nilai"), (110, 35, 50), ("LEFT", "CENTER", "RIGHT"),
           [(company_with_pic(g.name, g.pics), str(g.count), _money(g.total)) for g in groups],
           ("Total", str(len(rows)), _money(total)))

    _section(pdf, "Rekap per Finance Reviewer (penyetuju)")
    groups = _groups(rows, lambda r: r.approved_by)
    _table(pdf, ("Finance Reviewer", "Jumlah voucher", "Total nilai"), (110, 35, 50), ("LEFT", "CENTER", "RIGHT"),
           [(g.name, str(g.count), _money(g.total)) for g in groups])

    _section(pdf, "Daftar voucher")
    detail = [(str(i), r.voucher_no, r.generated_at.astimezone(WIB).strftime("%d-%m-%Y %H:%M"), r.request_id,
               company_with_pic(r.client.name, [r.pic_name] if r.pic_name else []), r.vendor_name or "-", r.invoice_no or "-", _money(r.total), r.approved_by,
               STATUS_TEXT.get(r.status, r.status.value))
              for i, r in enumerate(sorted(rows, key=lambda r: r.generated_at), start=1)]
    _table(pdf, ("No", "No. Voucher", "Terbit", "Request ID", "Perusahaan", "Vendor", "No. Invoice", "Total",
                 "Disetujui oleh", "Status"),
           (9, 30, 25, 36, 38, 31, 27, 27, 31, 23),
           ("CENTER", "LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "LEFT", "LEFT"),
           detail, ("", "", "", "", "", "", "Total", _money(total), "", ""))

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 100, 105)
    pdf.multi_cell(0, 4, "Rekap ini disusun otomatis oleh AMIGA Robot Admin dari voucher yang telah disetujui Finance "
                         "Reviewer. Voucher bukan persetujuan pembayaran; keputusan pembayaran tetap wewenang Client Approver.")
    return bytes(pdf.output())
