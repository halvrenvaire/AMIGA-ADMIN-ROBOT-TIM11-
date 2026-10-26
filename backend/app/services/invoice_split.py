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
from difflib import SequenceMatcher
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.models import Document, DocumentFile
from app.services import storage
from app.services.extraction_service import ExtractedInvoice, _positive, fee_from_amounts
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
    chunks: list[tuple[int, int]] = []  # potongan halaman yang sudah dipindai
    for first in range(1, limit + 1, step):
        last = min(first + step - 1, limit)
        chunk = pdf if (first, last) == (1, total_pages) else cut_pages(pdf, first, last)
        result = extractor.scan_chunk(chunk, first, last, include_account=include_account)
        for k in ("input_tokens", "output_tokens"):
            usage[k] = usage.get(k, 0) + int((result.usage or {}).get(k) or 0)
        if general is None:
            general = result.document
        chunks.append((first, last))  # semua potongan yang dipindai
        for inv in result.invoices:
            key = normalize(inv.invoice_no) or (inv.page, inv.total, normalize(inv.vendor_name))
            if key in seen:
                continue  # invoice yang sama terbaca lagi di potongan berikutnya
            seen.add(key)
            found.append(inv)
        if first == 1 and not found:
            break
    confirm_front_pages(extractor, pdf, found, chunks, usage)
    found.sort(key=lambda inv: inv.page or 1)
    return found, general or ExtractedInvoice()


def confirm_front_pages(extractor, pdf: bytes, found: list[ExtractedInvoice], chunks: list[tuple[int, int]],
                        usage: dict) -> None:
    """Periksa per halaman: halaman depan tiap invoice dan blok ringkasan jumlahnya.

    Pemindaian per potongan halaman sering menyebut halaman awal potongan, bukan halaman invoice sebenarnya (berkas
    DSS: invoice di halaman 5, 9, 13, 20 terbaca 3, 6, 11, 16), sehingga rentang halaman bukti salah. Bila ada beberapa
    invoice, setiap halaman yang dipindai diperiksa sendiri (paralel) dan halaman awal dicocokkan dari
    nomor invoicenya. Satu invoice: hanya halaman depannya, dan hanya bila AI melihat pemisahan imbalan jasa.
    Blok ringkasan dipakai untuk dasar potongan PPh 23 (fee_from_amounts). Gagal baca = hasil pindai tetap dipakai."""
    reader = getattr(extractor, "read_front_page", None)
    if reader is None or not found:
        return
    if len(found) > 1:
        # Semua halaman yang dipindai, termasuk potongan tanpa invoice terdaftar: pemindaian kadang melewatkan
        # invoice di satu potongan (berkas DSS sintetis: halaman 13 tidak terdaftar)
        pages = sorted({p for first, last in chunks for p in range(first, last + 1)})
    elif found[0].raw.get("service_fee") or found[0].service_fee is not None:
        pages = [found[0].page or 1]
    else:
        return
    page_usage = [dict() for _ in pages]

    def check(i: int):
        try:
            return reader(cut_pages(pdf, pages[i], pages[i]), page_usage[i])
        except Exception as e:  # noqa: BLE001 - halaman ini memakai hasil pindai
            log.warning("Halaman %d gagal diperiksa: %s", pages[i], e)
            return None

    with ThreadPoolExecutor(max_workers=max(1, settings.ai_split_workers)) as pool:
        infos = list(pool.map(check, range(len(pages))))
    for u in page_usage:
        for k in ("input_tokens", "output_tokens"):
            usage[k] = usage.get(k, 0) + int(u.get(k) or 0)
    fronts = [(p, info) for p, info in zip(pages, infos) if info is not None and info.starts_invoice]
    matches: dict[int, tuple[int, object]] = {}  # indeks invoice hasil pindai → (halaman, info halaman depan)
    used: set[int] = set()
    if len(found) == 1:
        if fronts:
            matches[0] = fronts[0]
            used.add(fronts[0][0])
    else:
        # 1) Nomor invoice sama persis
        for i, inv in enumerate(found):
            hit = next(((p, info) for p, info in fronts if p not in used and normalize(info.invoice_no)
                        and normalize(info.invoice_no) == normalize(inv.invoice_no)), None)
            if hit is not None:
                matches[i] = hit
                used.add(hit[0])
        # 2) Nomor terbaca sedikit berbeda: halaman depan yang belum terpakai di potongan halaman yang sama
        step = max(settings.ai_max_pages, 1)
        for i, inv in sorted(enumerate(found), key=lambda x: x[1].page or 1):
            if i in matches:
                continue
            first = ((inv.page or 1) - 1) // step * step + 1
            hit = next(((p, info) for p, info in fronts if p not in used and first <= p < first + step
                        and _same_invoice(inv, info)), None)
            if hit is not None:
                matches[i] = hit
                used.add(hit[0])
    if len(found) > 1:
        # Hasil pindai tanpa halaman depan yang cocok, padahal halaman yang disebut pemindaian sudah diperiksa dan
        # BUKAN halaman depan invoice (mis. lampiran rincian "005-DO2311-000001" di halaman 6 berkas DSS): dibuang.
        # Beberapa struk dalam satu halaman tetap aman karena halamannya sendiri halaman depan.
        checked = dict(zip(pages, infos))
        drop = {i for i, inv in enumerate(found) if i not in matches and (inv.page or 1) in checked
                and checked[inv.page or 1] is not None and not checked[inv.page or 1].starts_invoice}
        for i in drop:
            log.info("Halaman %s (%s) bukan halaman depan invoice; tidak dijadikan bukti", found[i].page,
                     found[i].invoice_no)
        kept = [(inv, matches.get(i)) for i, inv in enumerate(found) if i not in drop]
        found[:] = [inv for inv, _ in kept]
        matches = {i: m for i, (_, m) in enumerate(kept) if m is not None}
    for i, (page, info) in matches.items():
        inv = found[i]
        inv.page = page
        apply_fee_reading(inv, info.amounts)
        if inv.service_fee is None and inv.service_fee_unverified is not None:
            # Angka tidak saling cocok: baca ulang halaman depan itu sekali (AI kadang salah baca satu angka)
            again = check_page(reader, pdf, page, usage)
            if again is not None and again.starts_invoice:
                apply_fee_reading(inv, again.amounts)
    if len(found) > 1:
        # Halaman depan invoice yang terlewat saat pemindaian (berkas DSS: invoice ke-2 di halaman 5 kadang tidak
        # terdaftar). Ditambahkan sebagai bukti sendiri; data kepalanya dibaca AI dari potongan halamannya nanti.
        known = {normalize(inv.invoice_no) for inv in found if normalize(inv.invoice_no)}
        for page, info in fronts:
            if page in used or (normalize(info.invoice_no) and normalize(info.invoice_no) in known):
                continue
            missed = ExtractedInvoice(invoice_no=info.invoice_no, total=total_from_amounts(info.amounts), page=page,
                                      raw={"needs_read": True, "found_by": "pemeriksaan halaman"})
            apply_fee_reading(missed, info.amounts)
            found.append(missed)
            log.info("Invoice %s di halaman %d terlewat saat pemindaian; ditambahkan", info.invoice_no, page)


def _same_invoice(inv: ExtractedInvoice, info) -> bool:
    """Nomor invoice hampir sama (salah baca 1-2 karakter) atau total akhirnya sama."""
    a, b = normalize(inv.invoice_no), normalize(info.invoice_no)
    if a and b and SequenceMatcher(None, a, b).ratio() >= 0.85:
        return True
    total = total_from_amounts(info.amounts)
    return inv.total is not None and total is not None and inv.total == total


def total_from_amounts(rows) -> Decimal | None:
    """Total akhir dari blok ringkasan (baris terakhir berlabel Total), bila ada."""
    for row in reversed(rows if isinstance(rows, list) else []):
        if isinstance(row, dict) and re.search(r"total", str(row.get("label") or ""), re.IGNORECASE):
            return _positive(row.get("amount"))
    return None


def check_page(reader, pdf: bytes, page: int, usage: dict):
    try:
        return reader(cut_pages(pdf, page, page), usage)
    except Exception as e:  # noqa: BLE001 - hasil sebelumnya tetap dipakai
        log.warning("Halaman %d gagal dibaca ulang: %s", page, e)
        return None


def apply_fee_reading(inv: ExtractedInvoice, amounts: list) -> None:
    """Dasar potongan PPh 23 dari blok ringkasan halaman depan. Hanya untuk invoice yang memisahkan imbalan jasa dari
    penggantian biaya; imbalan yang tidak cocok dengan PPN tercetak tidak dipakai (PIC mengisi DPP sendiri)."""
    reading = fee_from_amounts(amounts)
    if not reading.split:
        return
    inv.raw = {**(inv.raw or {}), "summary_amounts": amounts}
    if reading.fee is not None:
        inv.service_fee, inv.service_fee_unverified = reading.fee, None
        inv.vat_printed = reading.vat or inv.vat_printed
    else:
        inv.service_fee = None
        inv.service_fee_unverified = reading.unverified or inv.service_fee_unverified


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
