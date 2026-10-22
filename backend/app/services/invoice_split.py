"""Satu PDF berisi beberapa invoice/struk (Tahap 15).

AI memindai halaman per `ai_max_pages` halaman (sampai `ai_max_scan_pages` per file) dan mendaftar setiap tagihan
beserta halaman awalnya. Setiap tagihan menjadi satu bukti (tab, uraian, pajak, satu baris voucher):
- beberapa invoice di halaman berbeda: PDF dipotong per rentang halaman (invoice + lampirannya, mis. rincian dan
  Faktur Pajak) sampai halaman sebelum invoice berikutnya;
- beberapa struk di satu halaman: beberapa bukti menunjuk halaman yang sama.
PDF unggahan tetap disimpan utuh (`upload_key`) dan dilampirkan sekali di voucher. PIC boleh mengubah rentang
halaman, menghapus, atau menambah bukti dari halaman unggahan.
"""
import io
import logging
import re
import uuid

from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.models import Document, DocumentFile
from app.services import storage
from app.services.extraction_service import ExtractedInvoice
from app.services.verification import normalize

log = logging.getLogger(__name__)

SPLIT_SUFFIX = re.compile(r" \(invoice \d+, hal\. [\d–]+\)$")


def page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def cut_pages(pdf: bytes, first: int, last: int) -> bytes:
    """Halaman `first`..`last` (mulai 1) sebagai PDF baru."""
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for page in reader.pages[first - 1:last]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def base_name(name: str) -> str:
    """Nama file unggahan tanpa keterangan "(invoice k, hal. a–b)"."""
    return SPLIT_SUFFIX.sub("", name)


def pages_label(first: int, last: int) -> str:
    return str(first) if first == last else f"{first}–{last}"


def upload_key(f: DocumentFile) -> str:
    return f.upload_key or f.file_key


def scan(extractor, pdf: bytes, include_account: bool, usage: dict) -> tuple[list[ExtractedInvoice], ExtractedInvoice]:
    """Pindai berkas per potongan halaman. Hasil: tagihan unik berurutan (dengan `page`) dan klasifikasi umum
    potongan pertama (dipakai bila tidak ada tagihan). Bila potongan pertama tidak memuat tagihan, pemindaian
    berhenti (berkas bukan kumpulan tagihan; hemat token)."""
    total_pages = page_count(pdf)
    limit = min(total_pages, max(settings.ai_max_scan_pages, 1))
    step = max(settings.ai_max_pages, 1)
    found: list[ExtractedInvoice] = []
    seen: set = set()
    general = None
    for first in range(1, limit + 1, step):
        last = min(first + step - 1, limit)
        chunk = pdf if (first, last) == (1, total_pages) else cut_pages(pdf, first, last)
        result = extractor.scan_chunk(chunk, first, last, include_account=include_account)
        for k in ("input_tokens", "output_tokens"):
            usage[k] = usage.get(k, 0) + int((result.usage or {}).get(k) or 0)
        if general is None:
            general = result.document
        for inv in result.invoices:
            key = normalize(inv.invoice_no) or (inv.page, inv.total, normalize(inv.vendor_name))
            if key in seen:
                continue  # invoice yang sama terbaca lagi di potongan berikutnya
            seen.add(key)
            found.append(inv)
        if first == 1 and not found:
            break
    found.sort(key=lambda inv: inv.page or 1)
    return found, general or ExtractedInvoice()


def plan(invoices: list[ExtractedInvoice], total_pages: int) -> list[tuple[ExtractedInvoice, int, int]]:
    """Rentang halaman tiap tagihan: dari halaman awalnya sampai sebelum halaman awal tagihan berikutnya; tagihan
    terakhir sampai akhir berkas. Halaman sebelum tagihan pertama (mis. sampul) ikut tagihan pertama."""
    starts = sorted({inv.page or 1 for inv in invoices})
    result = []
    for inv in invoices:
        page = inv.page or 1
        later = [s for s in starts if s > page]
        first = 1 if page == starts[0] else page
        result.append((inv, first, (later[0] - 1) if later else total_pages))
    return result


def renumber(db, doc: Document, ordered: list[DocumentFile]) -> None:
    """Atur ulang nomor urut bukti (dua langkah, karena (document_id, position) unik)."""
    for f in ordered:
        f.position = f.position + 1000
    db.flush()
    for i, f in enumerate(ordered, start=1):
        f.position = i
    db.flush()


def rename_group(doc: Document, key: str) -> dict[str, str]:
    """Nama bukti dari satu unggahan: "nama.pdf (invoice k, hal. a–b)" bila unggahan itu menjadi beberapa bukti,
    selain itu nama aslinya. Hasil: nama lama → nama baru (untuk memperbarui hasil cek jenis dokumen)."""
    group = [f for f in doc.files if upload_key(f) == key]
    renamed = {}
    for k, f in enumerate(group, start=1):
        base = base_name(f.original_filename)
        new = base if len(group) == 1 or f.page_from is None else \
            f"{base} (invoice {k}, hal. {pages_label(f.page_from, f.page_to)})"
        if new != f.original_filename:
            renamed[f.original_filename] = new
            f.original_filename = new[:300]
    return renamed


def piece_key(key: str, first: int, last: int) -> str:
    stem = key[:-4] if key.lower().endswith(".pdf") else key
    return f"{stem}-hal{first}-{last}-{uuid.uuid4().hex[:6]}.pdf"


def save_piece(upload: bytes, key: str, first: int, last: int, total_pages: int) -> str:
    """Simpan potongan halaman sebagai file bukti; seluruh berkas tidak perlu dipotong."""
    if (first, last) == (1, total_pages):
        return key
    new_key = piece_key(key, first, last)
    storage.save(new_key, cut_pages(upload, first, last))
    return new_key


def focus(doc: Document, f: DocumentFile, data: dict | None) -> str | None:
    """Ciri tagihan untuk dibaca ulang AI bila halaman bukti ini juga dipakai bukti lain (beberapa struk dalam
    satu halaman)."""
    if f.page_from is None:
        return None
    shared = any(o is not f and upload_key(o) == upload_key(f) and o.page_from is not None
                 and o.page_from <= f.page_to and f.page_from <= o.page_to for o in doc.files)
    if not shared or not data:
        return None
    parts = [f"nomor {data['invoice_no']}" if data.get("invoice_no") else None,
             f"penjual {data['vendor_name']}" if data.get("vendor_name") else None,
             f"total {data['total']}" if data.get("total") else None]
    text = ", ".join(p for p in parts if p)
    return text or None
