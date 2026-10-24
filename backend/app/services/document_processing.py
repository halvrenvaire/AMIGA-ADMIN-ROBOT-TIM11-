"""Alur otomatis setelah unggah atau perbaikan PIC (BPMN, SOP 7.2):

PROCESSING → AI membaca setiap invoice → hasil digabung untuk satu voucher → isian PIC didahulukan →
sistem memverifikasi → READY_FOR_REVIEW (reviewer ditugaskan) atau EXCEPTION (kode + alasan).

Dijalankan di background setelah respons dikirim, dengan sesi database sendiri.
"""
import io
import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from pypdf import PdfReader, PdfWriter
from sqlalchemy import select, update

from app import db as db_module
from app.config import settings
from app.models import (
    CATEGORY_REIMBURSE, TOTAL_ONLY, AuditLog, DocStatus, Document, DocumentFile, Extraction, IssueCode, LineItem, ValidationIssue,
    Vendor,
)
from app.services import audit_service, storage, tax_service
from app.services.account_check import MISMATCH, payee_checks
from app.services.extraction_service import (
    INVOICE, IRRELEVANT, RECEIPT, UNCERTAIN, ExtractedInvoice, ExtractedLine, ExtractionError, InvoiceExtractor,
)
from app.services.invoice_splitter import slice_pdf
from app.services.reviewer_assignment import pick_reviewer
from app.services.verification import InvoiceData, Issue, normalize, verify

log = logging.getLogger(__name__)

# Field yang boleh diisi/diperbaiki PIC (FR-3.4) beserta tipenya
PIC_FIELDS = {
    "vendor_name": str, "invoice_no": str, "invoice_date": date, "total": Decimal,
    "bank_name": str, "account_no": str, "account_name": str,
}

EXTRACTION_FAILED_MESSAGE = (
    "AI belum berhasil membaca invoice ini. Dokumen tetap tersimpan. Finance Reviewer dapat "
    "memproses ulang atau mengisi data secara manual."
)


def parse_pic_value(name: str, value: str):
    kind = PIC_FIELDS[name]
    if kind is date:
        return date.fromisoformat(value)
    if kind is Decimal:
        return Decimal(value)
    return value.strip()


def set_status(db, doc: Document, new: DocStatus, note: str | None = None) -> None:
    old = doc.status
    doc.status = new
    audit_service.record(db, None, "STATUS_CHANGED", document_id=doc.id, client_id=doc.client_id,
                         status_before=old.value if old else None, status_after=new.value, note=note)


def combine(parts: list[ExtractedInvoice]) -> ExtractedInvoice:
    """Gabungkan hasil baca beberapa invoice menjadi data satu voucher.

    Nomor invoice digabung dengan koma, total dijumlahkan, rincian barang diberi awalan nomor
    invoice. Vendor dan rekening diambil dari invoice pertama yang memuatnya; perbedaan antar
    invoice diperiksa sistem di verifikasi (VENDOR_MISMATCH)."""
    if len(parts) == 1:
        return parts[0]
    first = lambda name: next((getattr(p, name) for p in parts if getattr(p, name)), None)  # noqa: E731
    totals = [p.total for p in parts]
    lines = []
    for i, p in enumerate(parts, start=1):
        tag = p.invoice_no or f"Invoice {i}"
        lines += [ExtractedLine(description=f"[{tag}] {line.description or '-'}", qty=line.qty,
                                unit_price=line.unit_price, subtotal=line.subtotal) for line in p.line_items]
    numbers = [p.invoice_no for p in parts if p.invoice_no]
    dates = [p.invoice_date for p in parts if p.invoice_date]
    return ExtractedInvoice(
        vendor_name=first("vendor_name"),
        # Bila ada invoice tanpa nomor, field dibiarkan kosong supaya terdeteksi MISSING_EVIDENCE
        invoice_no=", ".join(numbers)[:500] if len(numbers) == len(parts) else None,
        invoice_date=min(dates) if len(dates) == len(parts) else None,
        line_items=lines,
        total=sum(totals, Decimal(0)) if all(t is not None for t in totals) else None,
        bank_name=first("bank_name"), account_no=first("account_no"), account_name=first("account_name"),
        raw={"invoices": [p.raw for p in parts],
             # Penerima per invoice, untuk cek satu voucher satu vendor & rekening
             "payees": [{"vendor_name": p.vendor_name, "account_no": p.account_no} for p in parts]},
    )


# --- Data per invoice (feedback owner: PIC mengedit per invoice) ---

DATA_FIELDS = ("vendor_name", "invoice_no", "invoice_date", "total", "bank_name", "account_no", "account_name")


def line_subtotal(qty, unit_price) -> Decimal | None:
    """Subtotal = qty × harga satuan (2 desimal) bila keduanya terisi; None = subtotal diisi manual (borongan)."""
    if qty in (None, "") or unit_price in (None, ""):
        return None
    value = (Decimal(str(qty)) * Decimal(str(unit_price))).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return value.quantize(Decimal(1)) if value == value.to_integral_value() else value


def _num(value) -> str | None:
    return None if value is None else str(value)


def part_to_data(p: ExtractedInvoice) -> dict:
    """Data satu invoice dalam bentuk JSON (disimpan di document_files.data)."""
    data = {
        "vendor_name": p.vendor_name, "invoice_no": p.invoice_no,
        "invoice_date": p.invoice_date.isoformat() if p.invoice_date else None,
        "total": _num(p.total), "bank_name": p.bank_name, "account_no": p.account_no, "account_name": p.account_name,
        "line_items": [{"description": li.description, "qty": _num(li.qty), "unit_price": _num(li.unit_price),
                        "subtotal": _num(li.subtotal)} for li in p.line_items],
    }
    # Angka pajak yang tercetak di invoice (hanya bila ada): imbalan jasa penerbit dan PPN. Bukan isian PIC,
    # jadi tidak ikut diubah saat PIC menyimpan data invoice.
    if p.service_fee is not None:
        data["service_fee"] = _num(p.service_fee)
    if p.vat_printed is not None:
        data["vat_printed"] = _num(p.vat_printed)
    if p.service_fee_unverified is not None:
        data["service_fee_unverified"] = _num(p.service_fee_unverified)
    return data


def default_description(data: dict) -> str | None:
    """Uraian awal satu invoice di voucher mode TOTAL_ONLY: "Invoice {nomor} - {vendor}" (bisa diedit PIC)."""
    parts = [f"Invoice {data['invoice_no']}" if data.get("invoice_no") else None, data.get("vendor_name")]
    text = " - ".join(p for p in parts if p)
    return text or None


def data_to_part(d: dict | None) -> ExtractedInvoice:
    d = d or {}
    dec = lambda v: None if v in (None, "") else Decimal(str(v))  # noqa: E731
    return ExtractedInvoice(
        vendor_name=d.get("vendor_name"), invoice_no=d.get("invoice_no"),
        invoice_date=date.fromisoformat(d["invoice_date"]) if d.get("invoice_date") else None,
        total=dec(d.get("total")), bank_name=d.get("bank_name"), account_no=d.get("account_no"),
        account_name=d.get("account_name"),
        line_items=[ExtractedLine(li.get("description"), dec(li.get("qty")), dec(li.get("unit_price")),
                                  dec(li.get("subtotal"))) for li in d.get("line_items") or []],
        service_fee=dec(d.get("service_fee")), vat_printed=dec(d.get("vat_printed")),
        service_fee_unverified=dec(d.get("service_fee_unverified")),
    )


def file_data(doc: Document, f: DocumentFile) -> dict:
    """Data per invoice; dokumen lama tanpa data per file memakai data gabungan (1 file) atau kosong."""
    if f.data is not None:
        return f.data
    ex = doc.extraction
    if ex is not None and len(doc.files) == 1:
        return part_to_data(ExtractedInvoice(
            **{k: getattr(ex, k) for k in DATA_FIELDS},
            line_items=[ExtractedLine(li.description, li.qty, li.unit_price, li.subtotal) for li in ex.line_items]))
    return part_to_data(ExtractedInvoice())


def vendor_npwp(db, client_id, vendor_name: str | None) -> bool | None:
    """NPWP vendor dari data referensi klien: True/False, atau None bila vendor belum terdaftar."""
    norm = normalize(vendor_name)
    if not norm:
        return None
    npwp = db.execute(select(Vendor.npwp).where(Vendor.client_id == client_id, Vendor.name_norm == norm)).first()
    return None if npwp is None else bool((npwp[0] or "").strip())


def prefill_tax(db, doc: Document, bedrock, only: set | None = None) -> None:
    """Saran pajak per invoice dari AI (cadangan: aturan) dan NPWP vendor dari data referensi.
    Pajak TIDAK dipilih otomatis: PIC wajib memilihnya sendiri sebelum draf dikirim (keputusan owner).
    `only`: id file yang baru dibaca; file lain (pilihan pajak PIC) tidak disentuh."""
    files = [f for f in doc.files or [] if only is None or f.id in only]
    table = tax_service.rates(db)
    if not files or not table:
        return
    items = [f.data or {} for f in files]
    suggestions = tax_service.suggest(bedrock, items, doc.request_type == CATEGORY_REIMBURSE, set(table))
    for f, data, sug in zip(files, items, suggestions):
        known = vendor_npwp(db, doc.client_id, data.get("vendor_name"))
        rate = table.get(sug.code) or table[tax_service.NONE]
        suggestion = {"code": rate.code, "name": rate.name, "reason": sug.reason, "source": sug.source}
        if sug.base is not None:
            suggestion["base"] = str(sug.base)  # dasar potongan: imbalan jasa saja (bukan seluruh tagihan)
        f.data = {**{k: v for k, v in data.items() if k != "tax"}, "npwp_known": known, "tax_suggestion": suggestion}


def rebuild_from_files(db, doc: Document) -> Extraction:
    """Susun ulang data voucher (gabungan) dari data per invoice setelah PIC mengedit."""
    parts = [data_to_part(file_data(doc, f)) for f in doc.files]
    data = combine(parts)
    ex = doc.extraction or Extraction(document_id=doc.id, extracted_at=datetime.now(timezone.utc))
    raw = dict(ex.raw_json or {}) if isinstance(ex.raw_json, dict) else {}
    for name in PIC_FIELDS:
        setattr(ex, name, getattr(data, name))
    raw["payees"] = [{"vendor_name": p.vendor_name, "account_no": p.account_no} for p in parts]
    ex.raw_json = raw
    ex.line_items = [LineItem(position=i, description=li.description, qty=li.qty, unit_price=li.unit_price,
                              subtotal=li.subtotal) for i, li in enumerate(data.line_items, start=1)]
    for f, p in zip(doc.files, parts):
        f.invoice_no_norm = normalize(p.invoice_no)
    doc.extraction = ex
    db.add(ex)
    db.flush()
    return ex


# Kendala yang wajib dibereskan PIC sebelum dikirim ke reviewer. Kendala lain (kemungkinan duplikat,
# struk/nota, perlu pemeriksaan manual, catatan pengembalian) diputuskan Finance Reviewer.
# Rekening berbeda (ACCOUNT_MISMATCH) tidak lagi menahan draf (Tahap 14): rekening adalah fitur tambahan dan
# perbedaannya menjadi peringatan yang dicek Finance Reviewer saat menyetujui.
BLOCKING = {IssueCode.MISSING_EVIDENCE, IssueCode.CALCULATION_DISCREPANCY, IssueCode.NOT_AN_INVOICE,
            IssueCode.EXTRACTION_FAILED}
# Peringatan pengingat (Tahap 14: soft-warning). Tidak membuat dokumen "Ada kendala" dan tidak menahan pengiriman;
# PIC boleh mengonfirmasinya beserta alasan (tampil untuk reviewer), tetapi tidak wajib.
ACKNOWLEDGEABLE = {IssueCode.VENDOR_MISMATCH}
# Peringatan yang tidak menahan pengiriman maupun persetujuan (rekening berbeda dikonfirmasi reviewer saat menyetujui)
WARNINGS = {IssueCode.VENDOR_MISMATCH, IssueCode.ACCOUNT_MISMATCH}


def payee_fingerprint(extraction: Extraction | None) -> str:
    """Sidik daftar vendor+rekening; konfirmasi PIC gugur bila daftar ini berubah."""
    pairs = sorted({f"{v or ''}|{a or ''}" for v, a in _payees(extraction)}) if extraction else []
    return ";".join(pairs)


def acknowledgement(extraction: Extraction | None, code: IssueCode) -> dict | None:
    """Konfirmasi PIC atas peringatan `code` yang masih berlaku (daftar vendor/rekening belum berubah)."""
    raw = extraction.raw_json if extraction and isinstance(extraction.raw_json, dict) else {}
    ack = (raw.get("acknowledged") or {}).get(code.value)
    return ack if ack and ack.get("fingerprint") == payee_fingerprint(extraction) else None


def settle_status(db, doc: Document, issues: list, note: str) -> None:
    """Draf bila tidak ada kendala wajib; Ada kendala (EXCEPTION) bila masih ada. PIC yang mengirim ke reviewer.
    Saat isi manual (AI tidak membaca), data yang belum diisi tidak membuat dokumen "Ada kendala": dokumen tetap Draf
    supaya tidak tampak rusak, tetapi tetap tidak bisa dikirim sebelum lengkap (dicek saat kirim)."""
    manual = manual_entry(doc.extraction) is not None
    blocking = sorted({i.code.value for i in issues if i.code in BLOCKING
                       and not (manual and i.code == IssueCode.MISSING_EVIDENCE)})
    new = DocStatus.EXCEPTION if blocking else DocStatus.DRAFT
    if doc.status != new:
        set_status(db, doc, new, f"{note}: {', '.join(blocking)}" if blocking else note)


def document_checks(names: list[str], parts: list[ExtractedInvoice]) -> list[dict]:
    """Hasil pemeriksaan jenis dokumen per file, disimpan di raw_json untuk verifikasi."""
    return [{"file": name, "doc_class": p.doc_class, "is_invoice": p.is_invoice, "document_type": p.document_type,
             "reason": p.not_invoice_reason} for name, p in zip(names, parts)]


def file_class(check: dict) -> str:
    """Kelas file; data lama (sebelum klasifikasi 4 kelas) hanya punya is_invoice."""
    return check.get("doc_class") or (INVOICE if check.get("is_invoice") is not False else IRRELEVANT)


def classification(extraction: Extraction | None) -> dict | None:
    """Ringkasan klasifikasi untuk layar detail: kelas dokumen, per file, dan keputusan reviewer."""
    raw = extraction.raw_json if extraction and isinstance(extraction.raw_json, dict) else {}
    checks = raw.get("document_checks") or []
    if not checks:
        return None
    classes = [file_class(c) for c in checks]
    overall = next((k for k in (IRRELEVANT, UNCERTAIN, RECEIPT) if k in classes), INVOICE)
    return {"doc_class": overall, "files": [{**c, "doc_class": file_class(c)} for c in checks],
            "decision": raw.get("classification_decision")}


def _classification_issues(extraction: Extraction, reimburse: bool = False) -> tuple[list[Issue], bool]:
    """(kendala klasifikasi, tolak?) Tidak relevan → NOT_AN_INVOICE dan verifikasi lain dilewati.
    Struk/nota → RECEIPT_NOT_INVOICE; meragukan → NEEDS_MANUAL_REVIEW; datanya tetap diverifikasi sebagai
    draft supaya kekurangan terlihat. Keputusan Finance Reviewer (classification_decision) menutup keduanya."""
    info = classification(extraction)
    if info is None:
        return [], False
    decision = (info["decision"] or {}).get("decision")
    rejected, issues = [], []
    for c in info["files"]:
        kind = f" (terbaca sebagai: {c['document_type']})" if c.get("document_type") else ""
        reason = f" {c['reason'].rstrip('.')}." if c.get("reason") else ""
        name = c.get("file") or "ini"
        if c["doc_class"] == IRRELEVANT:
            rejected.append(Issue(IssueCode.NOT_AN_INVOICE, None,
                                  f"File {name} ditolak karena bukan dokumen tagihan{kind}.{reason} Unggah ulang pengajuan "
                                  "hanya dengan file invoice/tagihan dari vendor."))
        elif decision in ("INVOICE", "RECEIPT_ACCEPTED"):
            continue
        elif c["doc_class"] == RECEIPT and reimburse:
            continue  # struk/nota adalah bukti sah untuk reimburse
        elif c["doc_class"] == RECEIPT:
            issues.append(Issue(IssueCode.RECEIPT_NOT_INVOICE, None,
                                f"File {name} adalah struk/nota pembelian{kind}, bukan invoice resmi vendor.{reason} Datanya "
                                "disusun sebagai draft. Minta invoice resmi ke vendor dan unggah ulang, atau Finance "
                                "Reviewer menerimanya sebagai dasar pembayaran setelah data wajib lengkap dan rekening "
                                "terverifikasi."))
        elif c["doc_class"] == UNCERTAIN:
            issues.append(Issue(IssueCode.NEEDS_MANUAL_REVIEW, None,
                                f"Jenis dokumen {name} meragukan{kind}.{reason} Finance Reviewer akan memeriksanya secara "
                                "manual."))
    return (rejected, True) if rejected else (issues, False)


def _save_extraction(db, doc: Document, data: ExtractedInvoice, duration_ms: int) -> Extraction:
    extraction = doc.extraction or Extraction(document_id=doc.id)
    for name in PIC_FIELDS:
        setattr(extraction, name, getattr(data, name))
    # Isian PIC didahulukan atas hasil AI, supaya perbaikan tidak hilang saat ekstraksi ulang
    for name, value in (doc.pic_overrides or {}).items():
        if name in PIC_FIELDS:
            setattr(extraction, name, parse_pic_value(name, value))
    extraction.raw_json = data.raw
    extraction.extracted_at = datetime.now(timezone.utc)
    extraction.duration_ms = duration_ms
    extraction.line_items = [
        LineItem(position=i, description=line.description, qty=line.qty,
                 unit_price=line.unit_price, subtotal=line.subtotal)
        for i, line in enumerate(data.line_items, start=1)
    ]
    doc.extraction = extraction
    db.add(extraction)
    db.flush()
    return extraction


def _invoice_norms(doc: Document, extraction: Extraction) -> set[str]:
    """Nomor invoice (dinormalisasi) di pengajuan ini: per file, atau isian gabungan bila diubah."""
    norms = {f.invoice_no_norm for f in doc.files if f.invoice_no_norm}
    if extraction.invoice_no:
        norms |= {n for part in extraction.invoice_no.split(",") if (n := normalize(part))}
    return norms


def _duplicate_of(db, doc: Document, extraction: Extraction) -> str | None:
    """Request ID pengajuan lain milik klien yang sama dengan vendor sama dan salah satu nomor invoice sama."""
    norms = _invoice_norms(doc, extraction)
    if not extraction.vendor_norm or not norms:
        return None
    return db.scalar(
        select(Document.request_id)
        .join(Extraction, Extraction.document_id == Document.id)
        .outerjoin(DocumentFile, DocumentFile.document_id == Document.id)
        .where(
            Document.client_id == doc.client_id,
            Document.id != doc.id,
            Document.status != DocStatus.CANCELLED,  # pengajuan batal boleh diajukan ulang
            Extraction.vendor_norm == extraction.vendor_norm,
            (Extraction.invoice_no_norm.in_(norms) | DocumentFile.invoice_no_norm.in_(norms)),
        )
        .order_by(Document.created_at)
        .limit(1)
    )


def _same_batch_duplicate(doc: Document) -> bool:
    norms = [f.invoice_no_norm for f in doc.files if f.invoice_no_norm]
    return len(norms) != len(set(norms))


def uploader_ids(doc: Document) -> set[uuid.UUID]:
    """Pengunggah dan PIC yang diwakili: keduanya dianggap "pengunggah" untuk aturan SoD."""
    return {doc.uploaded_by} | ({doc.on_behalf_of} if doc.on_behalf_of else set())


# Tindakan sisi pengaju. Siapa pun yang melakukannya pada sebuah dokumen dianggap "pengaju" dokumen
# itu, termasuk pengguna peran ganda (mis. Intake Support + Finance Reviewer) yang memperbaiki data.
SUBMITTER_ACTIONS = ("DOCUMENT_UPLOADED", "FIXED_BY_PIC", "PIC_NOTE", "SIGNERS_CHANGED", "SUBMITTED_TO_REVIEW")


def submitter_ids(db, doc: Document) -> set[uuid.UUID]:
    """Semua pihak pengaju dokumen: tidak boleh meninjau, menandai bukan duplikat, atau menyetujuinya (SoD)."""
    db.flush()  # sesi tanpa autoflush: catatan audit yang baru ditambahkan (mis. pengiriman draf) ikut terbaca
    actors = db.scalars(select(AuditLog.actor_id).where(
        AuditLog.document_id == doc.id, AuditLog.action.in_(SUBMITTER_ACTIONS), AuditLog.actor_id.is_not(None)))
    return uploader_ids(doc) | set(actors)


def run_verification(db, doc: Document) -> list:
    """Verifikasi sistem atas data ekstraksi saat ini; kendala lama diganti yang baru."""
    extraction = doc.extraction
    extraction.vendor_norm = normalize(extraction.vendor_name)
    extraction.invoice_no_norm = normalize(extraction.invoice_no)
    doc.vendor_id = db.scalar(select(Vendor.id).where(
        Vendor.client_id == doc.client_id, Vendor.name_norm == extraction.vendor_norm)) if extraction.vendor_norm else None
    invoice = InvoiceData(
        vendor_name=extraction.vendor_name, invoice_no=extraction.invoice_no,
        invoice_date=extraction.invoice_date, total=extraction.total,
        bank_name=extraction.bank_name, account_no=extraction.account_no,
        account_name=extraction.account_name,
        subtotals=[line.subtotal for line in extraction.line_items],
    )
    reimburse = doc.request_type == CATEGORY_REIMBURSE
    itemized = getattr(doc, "extraction_mode", None) != TOTAL_ONLY
    class_issues, rejected = _classification_issues(extraction, reimburse)
    if rejected:
        # Pemeriksaan data tidak relevan bila ada file yang bukan dokumen tagihan
        _resolve_open_issues(db, doc)
        for issue in class_issues:
            db.add(ValidationIssue(document_id=doc.id, code=issue.code, field=issue.field, message=issue.message))
        db.flush()
        return class_issues
    issues = class_issues + verify(invoice, _duplicate_of(db, doc, extraction),
                                   _payees(extraction, bool(getattr(doc, "include_account", False))), reimburse, itemized)
    issues = [i for i in issues if not (i.code in ACKNOWLEDGEABLE and acknowledgement(extraction, i.code))]
    db.flush()  # vendor_id baru dipakai pemeriksaan rekening
    db.refresh(doc, ["vendor"])
    # Rekening dicek per invoice: setiap rekening tujuan harus cocok dengan vendornya masing-masing
    for payee in payee_checks(db, doc):
        if payee.check.state == MISMATCH:
            issues.append(Issue(IssueCode.ACCOUNT_MISMATCH, "account_no", payee.check.message))
    if _same_batch_duplicate(doc):
        issues.append(Issue(IssueCode.POSSIBLE_DUPLICATE, "invoice_no",
                            "Ada nomor invoice yang sama lebih dari sekali dalam pengajuan ini. Periksa apakah "
                            "file yang sama terunggah dua kali."))
    _resolve_open_issues(db, doc)
    for issue in issues:
        db.add(ValidationIssue(document_id=doc.id, code=issue.code, field=issue.field, message=issue.message))
    db.flush()
    return issues


def _payees(extraction: Extraction, include_account: bool = True) -> list[tuple[str | None, str | None]]:
    """(vendor, rekening) per invoice dari hasil baca AI, untuk cek satu voucher satu penerima.
    Rekening diabaikan bila fitur rekening dimatikan untuk pengajuan ini."""
    payees = extraction.raw_json.get("payees") if isinstance(extraction.raw_json, dict) else None
    return [(normalize(p.get("vendor_name")), normalize(p.get("account_no")) if include_account else None)
            for p in payees or []]


def send_to_review(db, doc: Document, note: str) -> None:
    """READY_FOR_REVIEW dan tugaskan reviewer dengan antrean paling sedikit, bukan pengunggah."""
    reviewer = pick_reviewer(db, doc.client_id, submitter_ids(db, doc))
    doc.assigned_reviewer_id = reviewer.id if reviewer else None
    set_status(db, doc, DocStatus.READY_FOR_REVIEW,
               f"{note}; reviewer: {reviewer.email if reviewer else 'belum ada'}")


def _resolve_open_issues(db, doc: Document) -> None:
    db.execute(update(ValidationIssue)
               .where(ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False))
               .values(resolved=True))


def manual_entry(extraction: Extraction | None) -> dict | None:
    """Info isi manual bila AI tidak membaca sebagian/semua invoice: {status: off|failed, files, message}."""
    raw = extraction.raw_json if extraction and isinstance(extraction.raw_json, dict) else {}
    info = raw.get("ai")
    return info if isinstance(info, dict) and info.get("files") else None


def _manual_message(status: str, files: list[str], total: int, lines_only: bool = False) -> str:
    which = ("invoice ini" if total == 1 else "semua invoice" if len(files) == total
             else f"{len(files)} dari {total} invoice ({', '.join(files)})")
    if lines_only:
        return (f"AI belum berhasil membaca rincian barang/jasa {which}. Data invoice lain tetap tersimpan. Isi rincian "
                "secara manual dari file bukti, atau kembali ke mode total saja.")
    if status == "off":
        return (f"Pembacaan otomatis oleh AI sedang dimatikan, jadi data {which} belum terisi. Isi data invoice "
                "secara manual dari file bukti, lalu simpan.")
    return (f"AI sedang bermasalah dan belum berhasil membaca {which}. Dokumen tetap tersimpan. Isi data invoice "
            "secara manual dari file bukti, atau coba baca ulang dengan AI nanti.")


def first_pages(pdf: bytes, limit: int) -> bytes:
    """Hanya N halaman pertama yang dikirim ke AI (data invoice dan Faktur Pajak ada di depan; timesheet dan
    lampiran lain di belakang tidak perlu dibaca). PDF yang tidak bisa dipotong dikirim apa adanya."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if len(reader.pages) <= limit:
            return pdf
        writer = PdfWriter()
        for page in reader.pages[:limit]:
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:  # noqa: BLE001 - PDF aneh tetap dicoba dibaca utuh
        log.warning("PDF tidak bisa dipotong untuk AI; dikirim utuh")
        return pdf


def split_combined_files(db, doc: Document, extractor, only: set[int] | None = None) -> dict:
    """Pecah berkas gabungan (beberapa invoice dalam satu PDF) menjadi satu bagian per invoice.

    Tiap bagian menjadi satu file/invoice sendiri (tab bukti sendiri, baris voucher sendiri, pajak sendiri), berurutan
    di tempat berkas asalnya. Semua halaman tetap ada: bagian-bagian itu menggantikan berkas asal, dan PDF gabungan
    di `documents.file_key` tidak berubah. Berkas yang sudah pernah dibaca AI tidak diperiksa lagi (kecuali yang
    sebelumnya diisi manual). `only`: posisi bukti yang diminta PIC lewat tombol; bukti itu diperiksa walau sudah pernah
    dibaca AI. Mengembalikan token AI yang terpakai untuk pemeriksaan halaman."""
    usage = {"input_tokens": 0, "output_tokens": 0}
    locate = getattr(extractor, "locate_invoices", None)
    if locate is None or not settings.ai_split_enabled:
        return usage
    plan: dict[uuid.UUID, tuple[bytes, list]] = {}
    for f in doc.files or []:
        already_read = f.data is not None and not f.data.get("manual")
        if only is not None:
            if f.position not in only:
                continue
        elif already_read:
            continue
        if not settings.ai_split_min_pages <= f.page_count <= settings.ai_split_max_pages or f.source_format:
            continue  # terlalu pendek, atau terlalu panjang (biaya token: ~2.000 token per halaman)
        try:
            pdf = storage.load(f.file_key)
            segments, used = locate(pdf)
        except Exception as e:  # noqa: BLE001 - pemeriksaan gagal: berkas diproses utuh seperti biasa
            log.warning("Berkas %s tidak bisa diperiksa untuk dipecah: %s", f.original_filename, e)
            continue
        for k in usage:
            usage[k] += int((used or {}).get(k) or 0)
        if segments:
            plan[f.id] = (pdf, segments)
    if not plan:
        if only:
            audit_service.record(db, None, "INVOICES_SPLIT_CHECKED", document_id=doc.id, client_id=doc.client_id,
                                 note="AI tidak menemukan lebih dari satu invoice pada bukti " + ", ".join(map(str, sorted(only))))
        return usage

    final: list[DocumentFile] = []
    created: list[str] = []
    for f in doc.files:
        if f.id not in plan:
            final.append(f)
            continue
        pdf, segments = plan[f.id]
        for n, seg in enumerate(segments, start=1):
            key = f"invoices/{doc.request_id}/pisah-{f.position:02d}-{n:02d}.pdf"
            storage.save(key, slice_pdf(pdf, seg.start, seg.end))
            label = f"{f.original_filename} - invoice {n}" + (f" ({seg.invoice_no})" if seg.invoice_no else "")
            final.append(DocumentFile(document_id=doc.id, file_key=key, original_filename=label[:300],
                                      page_count=seg.pages))
        created.append(f"{f.original_filename}: {len(segments)} invoice "
                       f"({', '.join(s.invoice_no or '-' for s in segments)})")
    replaced = [f for f in doc.files if f.id in plan]
    kept = [f for f in final if f.id is not None]
    for f in replaced:
        db.delete(f)
    db.flush()
    # Posisi harus unik per dokumen: geser dulu semua yang tetap, baru beri nomor urut baru
    for f in kept:
        f.position += 1000
    db.flush()
    for position, f in enumerate(final, start=1):
        f.position = position
        if f.id is None:
            db.add(f)
    db.flush()
    db.expire(doc, ["files"])
    audit_service.record(db, None, "INVOICES_SPLIT", document_id=doc.id, client_id=doc.client_id,
                         note=f"Berkas gabungan dipisah per invoice. {'; '.join(created)}"[:1000])
    return usage


def process_document(document_id: uuid.UUID, extractor: InvoiceExtractor, retry_manual: bool = False,
                     lines_only: bool = False, split_positions: set[int] | None = None) -> None:
    """`retry_manual`: hanya baca ulang invoice yang sebelumnya diisi manual karena AI gagal; data invoice lain tetap.
    `lines_only`: mode diganti TOTAL_ONLY → ITEMIZED; AI hanya mengisi rincian barang/jasa, sedangkan data kepala
    invoice, uraian, dan pilihan pajak yang sudah diisi PIC tetap dipakai.
    `split_positions`: PIC meminta bukti pada posisi ini diperiksa dan dipecah bila berisi beberapa invoice (tombol
    "Pisahkan otomatis"); gunakan bersama `retry_manual` supaya bukti lain yang sudah terbaca tidak dibaca ulang."""
    with db_module.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("Dokumen %s tidak ditemukan untuk diproses", document_id)
            return
        if doc.status != DocStatus.PROCESSING:
            set_status(db, doc, DocStatus.PROCESSING, "AI mulai membaca invoice")
        db.commit()
        split_usage = {"input_tokens": 0, "output_tokens": 0}
        if settings.ai_extraction_enabled and extractor is not None and (settings.ai_split_auto or split_positions):
            try:
                split_usage = split_combined_files(db, doc, extractor, split_positions)
                db.commit()
            except Exception:  # noqa: BLE001 - gagal memecah tidak boleh membuat dokumen macet; diproses utuh
                db.rollback()
                doc = db.get(Document, document_id)
                log.exception("Berkas gabungan %s gagal dipecah; diproses utuh", document_id)
        previous = (doc.extraction.raw_json if doc.extraction and isinstance(doc.extraction.raw_json, dict) else {})
        old_checks = {c.get("file"): c for c in previous.get("document_checks") or []}
        keep = {f.id for f in doc.files or [] if retry_manual and f.data is not None and not f.data.get("manual")}
        for f in doc.files or []:
            if f.id not in keep:
                f.read_at = None
        db.commit()

        mode = getattr(doc, "extraction_mode", None) or "ITEMIZED"
        total_only = mode == TOTAL_ONLY
        ai_on = settings.ai_extraction_enabled and extractor is not None
        started = time.monotonic()
        files = doc.files or []
        sources = [(f, f.original_filename, f.file_key) for f in files] or [(None, doc.original_filename, doc.file_key)]
        parts, checks, manual, errors, fresh, read = [], [], [], [], set(), 0
        usage = dict(split_usage)
        try:
            for f, name, key in sources:
                if f is not None and f.id in keep:
                    parts.append(data_to_part(f.data))
                    if name in old_checks:
                        checks.append(old_checks[name])
                    continue
                part = None
                if ai_on:
                    pdf = first_pages(storage.load(key), settings.ai_max_pages)
                    try:
                        part = extractor.extract(pdf, mode=mode, include_account=bool(doc.include_account))
                    except ExtractionError as e:
                        errors.append(f"{name}: {e}")
                    except Exception as e:  # noqa: BLE001 - AI tidak boleh membuat dokumen macet di PROCESSING
                        log.exception("Pembacaan AI %s gagal tak terduga", name)
                        errors.append(f"{name}: {type(e).__name__}")
                    if part is not None:
                        for k in usage:
                            usage[k] += int((getattr(part, "usage", None) or {}).get(k) or 0)
                if lines_only and f is not None:
                    # Ganti mode ke rincian: hanya baris barang/jasa yang diambil dari AI
                    old = file_data(doc, f)
                    new = {k: v for k, v in old.items() if k not in ("manual", "hidden_line_items")}
                    if part is None:
                        manual.append(name)
                        new["manual"] = True
                    else:
                        read += 1
                        new["line_items"] = part_to_data(part)["line_items"]
                    new["tax"] = tax_service.recompute(old.get("tax"), new)
                    f.data = new
                    parts.append(data_to_part(new))
                    if name in old_checks:
                        checks.append(old_checks[name])
                    f.read_at = datetime.now(timezone.utc)
                    db.commit()
                    continue
                if part is None and f is not None and f.data and not f.data.get("manual"):
                    # Pembacaan ulang gagal: data sebelumnya (hasil AI dan isian PIC) tetap dipakai
                    parts.append(data_to_part(f.data))
                    if name in old_checks:
                        checks.append(old_checks[name])
                    f.read_at = datetime.now(timezone.utc)
                    continue
                if f is not None:
                    fresh.add(f.id)
                if part is None:
                    manual.append(name)
                    part = ExtractedInvoice()
                else:
                    checks += document_checks([name], [part])
                    read += 1
                if total_only:
                    part.line_items = []  # mode total: satu baris voucher per invoice
                parts.append(part)
                if f is not None:
                    f.invoice_no_norm = normalize(part.invoice_no)
                    data = part_to_data(part)
                    if total_only:
                        data["description"] = default_description(data)
                    f.data = {**data, **({"manual": True} if name in manual else {})}
                    # Disimpan per file supaya layar detail menampilkan progres yang nyata
                    f.read_at = datetime.now(timezone.utc)
                    db.commit()
            data = combine(parts)
            data.raw = {**data.raw, "document_checks": checks}
            if manual:
                status = "failed" if ai_on else "off"
                data.raw["ai"] = {"status": status, "files": manual, "error": "; ".join(errors)[:500] or None,
                                  "message": _manual_message(status, manual, len(sources), lines_only)}
            # Saran pajak tetap ada tanpa AI (aturan kata kunci)
            prefill_tax(db, doc, getattr(extractor, "bedrock", None) if ai_on else None, fresh)
        except storage.StorageError as e:
            log.warning("File %s tidak bisa dibuka: %s", doc.request_id, e)
            _resolve_open_issues(db, doc)
            db.add(ValidationIssue(document_id=doc.id, code=IssueCode.EXTRACTION_FAILED,
                                   message=EXTRACTION_FAILED_MESSAGE))
            set_status(db, doc, DocStatus.EXCEPTION, f"Ekstraksi gagal: {str(e)[:300]}")
            db.commit()
            return
        duration_ms = int((time.monotonic() - started) * 1000)

        if lines_only:
            # Data kepala invoice tidak berubah; data gabungan disusun ulang dari data per invoice
            extraction = rebuild_from_files(db, doc)
            raw = dict(extraction.raw_json or {})
            raw["document_checks"] = checks
            raw.pop("ai", None)
            if manual:
                raw["ai"] = data.raw["ai"]
            extraction.raw_json = raw
            extraction.extracted_at = datetime.now(timezone.utc)
            extraction.duration_ms = duration_ms
        else:
            extraction = _save_extraction(db, doc, data, duration_ms)
        extraction.ai_input_tokens = (extraction.ai_input_tokens or 0) + usage["input_tokens"]
        extraction.ai_output_tokens = (extraction.ai_output_tokens or 0) + usage["output_tokens"]
        if manual or errors:
            log.warning("AI tidak membaca %s (AI %s): %s", doc.request_id, "menyala" if ai_on else "dimatikan",
                        "; ".join(errors))
            audit_service.record(db, None, "AI_UNAVAILABLE", document_id=doc.id, client_id=doc.client_id,
                                 note=("AI dimatikan" if not ai_on else f"AI gagal membaca: {'; '.join(errors)[:300]}")
                                      + (f". {len(manual)} bukti diisi manual oleh PIC" if manual
                                         else ". Data sebelumnya tetap dipakai"))
        if read:
            what = "rincian" if lines_only else ("total" if total_only else "rincian lengkap")
            audit_service.record(db, None, "EXTRACTED", document_id=doc.id, client_id=doc.client_id,
                                 note=f"AI membaca {read} invoice (mode {what}), {len(extraction.line_items)} baris "
                                      f"dalam {duration_ms} ms")

        issues = run_verification(db, doc)
        settle_status(db, doc, issues, "Menunggu PIC mengisi data secara manual" if manual else
                      "AI selesai membaca; menunggu PIC memeriksa dan mengirim ke reviewer")
        db.commit()
