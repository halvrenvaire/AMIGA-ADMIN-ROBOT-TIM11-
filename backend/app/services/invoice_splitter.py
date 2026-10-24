"""Memecah berkas PDF gabungan menjadi satu bagian per invoice.

Satu berkas bisa berisi beberapa invoice berurutan (masing-masing dengan lampiran rincian, Faktur Pajak, dan
timesheet). AI hanya menandai halaman mana yang merupakan HALAMAN DEPAN sebuah invoice beserta nomornya (extraction_service);
pemecahan itu sendiri murni aturan di sini, supaya hasilnya bisa diuji tanpa AI.
"""
import io
import logging
import re
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter

log = logging.getLogger(__name__)


@dataclass
class PageInfo:
    """Hasil pemeriksaan satu halaman oleh AI."""
    starts_invoice: bool = False
    invoice_no: str | None = None


@dataclass
class Segment:
    """Satu invoice: halaman `start` sampai sebelum `end` (indeks mulai 0)."""
    start: int
    end: int
    invoice_no: str | None = None

    @property
    def pages(self) -> int:
        return self.end - self.start


def _norm(value: str | None) -> str:
    """Nomor invoice tanpa spasi dan tanda baca, huruf kecil (sama maksudnya dengan verification.normalize)."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _is_tax_serial(number: str) -> bool:
    """Nomor seri Faktur Pajak (16-17 digit angka saja) sering terbaca sebagai nomor invoice di halaman Faktur Pajak.
    Ditemukan pada pembacaan nyata: 6 dari 6 Faktur Pajak salah ditandai sebagai halaman depan invoice."""
    return number.isdigit() and len(number) >= 15


def find_segments(infos: list[PageInfo], max_invoices: int = 30) -> list[Segment]:
    """Segmen invoice dari hasil pemeriksaan tiap halaman. Kosong = tidak dipecah.

    Invoice baru dimulai di halaman yang ditandai halaman depan DAN bernomor invoice yang berbeda dari invoice
    sebelumnya. Halaman lampiran, Faktur Pajak, dan timesheet ikut invoice di depannya. Halaman sebelum halaman
    depan pertama ikut invoice pertama. Kurang dari dua invoice, atau lebih dari `max_invoices`, berarti tidak
    dipecah (berkas dianggap satu invoice seperti biasa)."""
    starts: list[tuple[int, str | None]] = []
    current = ""
    for i, info in enumerate(infos):
        number = _norm(info.invoice_no)
        if info.starts_invoice and number and not _is_tax_serial(number) and number != current:
            starts.append((i, info.invoice_no.strip()))
            current = number
    if len(starts) < 2 or len(starts) > max_invoices:
        return []
    segments = []
    for k, (start, number) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(infos)
        segments.append(Segment(0 if k == 0 else start, end, number))
    return segments


def split_pages(pdf: bytes) -> list[bytes]:
    """Setiap halaman sebagai PDF sendiri. Kosong bila PDF tidak bisa dibuka."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        pages = []
        for page in reader.pages:
            writer = PdfWriter()
            writer.add_page(page)
            out = io.BytesIO()
            writer.write(out)
            pages.append(out.getvalue())
        return pages
    except Exception:  # noqa: BLE001 - PDF aneh: berkas diproses utuh seperti biasa
        log.warning("PDF tidak bisa dipisah per halaman")
        return []


def slice_pdf(pdf: bytes, start: int, end: int) -> bytes:
    """PDF berisi halaman `start` sampai sebelum `end` (indeks mulai 0)."""
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for page in reader.pages[start:end]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
