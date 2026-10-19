"""Alur otomatis setelah unggah atau perbaikan PIC (BPMN, SOP 7.2):

PROCESSING → AI membaca setiap invoice → hasil digabung untuk satu voucher → isian PIC didahulukan →
sistem memverifikasi → READY_FOR_REVIEW (reviewer ditugaskan) atau EXCEPTION (kode + alasan).

Dijalankan di background setelah respons dikirim, dengan sesi database sendiri.
"""
import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app import db as db_module
from app.models import (
    CATEGORY_REIMBURSE, AuditLog, DocStatus, Document, DocumentFile, Extraction, IssueCode, LineItem, ValidationIssue,
    Vendor,
)
from app.services import audit_service, storage, tax_service
from app.services.account_check import MISMATCH, check_account
from app.services.extraction_service import (
    INVOICE, IRRELEVANT, RECEIPT, UNCERTAIN, ExtractedInvoice, ExtractedLine, ExtractionError, InvoiceExtractor,
)
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


def _num(value) -> str | None:
    return None if value is None else str(value)


def part_to_data(p: ExtractedInvoice) -> dict:
    """Data satu invoice dalam bentuk JSON (disimpan di document_files.data)."""
    return {
        "vendor_name": p.vendor_name, "invoice_no": p.invoice_no,
        "invoice_date": p.invoice_date.isoformat() if p.invoice_date else None,
        "total": _num(p.total), "bank_name": p.bank_name, "account_no": p.account_no, "account_name": p.account_name,
        "line_items": [{"description": li.description, "qty": _num(li.qty), "unit_price": _num(li.unit_price),
                        "subtotal": _num(li.subtotal)} for li in p.line_items],
    }


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


def prefill_tax(db, doc: Document, bedrock) -> None:
    """Isian awal pajak per invoice dari saran AI (cadangan: aturan). PIC tetap memeriksa dan bisa mengubahnya."""
    files = doc.files or []
    table = tax_service.rates(db)
    if not files or not table:
        return
    items = [f.data or {} for f in files]
    suggestions = tax_service.suggest(bedrock, items, doc.request_type == CATEGORY_REIMBURSE, set(table))
    for f, data, sug in zip(files, items, suggestions):
        known = vendor_npwp(db, doc.client_id, data.get("vendor_name"))
        rate = table.get(sug.code) or table[tax_service.NONE]
        f.data = {**data, "npwp_known": known,
                  "tax_suggestion": {"code": rate.code, "name": rate.name, "reason": sug.reason, "source": sug.source},
                  "tax": tax_service.build(rate, known is not False, None, True, data, source=sug.source)}


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
BLOCKING = {IssueCode.MISSING_EVIDENCE, IssueCode.CALCULATION_DISCREPANCY, IssueCode.VENDOR_MISMATCH,
            IssueCode.NOT_AN_INVOICE, IssueCode.EXTRACTION_FAILED, IssueCode.ACCOUNT_MISMATCH}


def settle_status(db, doc: Document, issues: list, note: str) -> None:
    """Draf bila tidak ada kendala wajib; Ada kendala (EXCEPTION) bila masih ada. PIC yang mengirim ke reviewer."""
    blocking = sorted({i.code.value for i in issues if i.code in BLOCKING})
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
    class_issues, rejected = _classification_issues(extraction, reimburse)
    if rejected:
        # Pemeriksaan data tidak relevan bila ada file yang bukan dokumen tagihan
        _resolve_open_issues(db, doc)
        for issue in class_issues:
            db.add(ValidationIssue(document_id=doc.id, code=issue.code, field=issue.field, message=issue.message))
        db.flush()
        return class_issues
    issues = class_issues + verify(invoice, _duplicate_of(db, doc, extraction), _payees(extraction), reimburse)
    db.flush()  # vendor_id baru dipakai pemeriksaan rekening
    db.refresh(doc, ["vendor"])
    account = check_account(db, doc)
    if account.state == MISMATCH:
        issues.append(Issue(IssueCode.ACCOUNT_MISMATCH, "account_no", account.message))
    if _same_batch_duplicate(doc):
        issues.append(Issue(IssueCode.POSSIBLE_DUPLICATE, "invoice_no",
                            "Ada nomor invoice yang sama lebih dari sekali dalam pengajuan ini. Periksa apakah "
                            "file yang sama terunggah dua kali."))
    _resolve_open_issues(db, doc)
    for issue in issues:
        db.add(ValidationIssue(document_id=doc.id, code=issue.code, field=issue.field, message=issue.message))
    db.flush()
    return issues


def _payees(extraction: Extraction) -> list[tuple[str | None, str | None]]:
    """(vendor, rekening) per invoice dari hasil baca AI, untuk cek satu voucher satu penerima."""
    payees = extraction.raw_json.get("payees") if isinstance(extraction.raw_json, dict) else None
    return [(normalize(p.get("vendor_name")), normalize(p.get("account_no"))) for p in payees or []]


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


def process_document(document_id: uuid.UUID, extractor: InvoiceExtractor) -> None:
    with db_module.SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("Dokumen %s tidak ditemukan untuk diproses", document_id)
            return
        if doc.status != DocStatus.PROCESSING:
            set_status(db, doc, DocStatus.PROCESSING, "AI mulai membaca invoice")
        for f in doc.files or []:
            f.read_at = None
        db.commit()

        started = time.monotonic()
        files = doc.files or []
        try:
            if files:
                parts = []
                for f in files:
                    try:
                        parts.append(extractor.extract(storage.load(f.file_key)))
                    except ExtractionError as e:
                        raise ExtractionError(f"{f.original_filename}: {e}" if len(files) > 1 else str(e)) from e
                    f.invoice_no_norm = normalize(parts[-1].invoice_no)
                    # Disimpan per file supaya layar detail menampilkan progres yang nyata
                    f.read_at = datetime.now(timezone.utc)
                    db.commit()
                names = [f.original_filename for f in files]
            else:
                parts, names = [extractor.extract(storage.load(doc.file_key))], [doc.original_filename]
            data = combine(parts)
            data.raw = {**data.raw, "document_checks": document_checks(names, parts)}
            for f, p in zip(files, parts):
                f.data = part_to_data(p)
            prefill_tax(db, doc, getattr(extractor, "bedrock", None))
        except (ExtractionError, storage.StorageError) as e:
            log.warning("Ekstraksi %s gagal: %s", doc.request_id, e)
            _resolve_open_issues(db, doc)
            db.add(ValidationIssue(document_id=doc.id, code=IssueCode.EXTRACTION_FAILED,
                                   message=EXTRACTION_FAILED_MESSAGE))
            set_status(db, doc, DocStatus.EXCEPTION, f"Ekstraksi gagal: {str(e)[:300]}")
            db.commit()
            return
        duration_ms = int((time.monotonic() - started) * 1000)

        extraction = _save_extraction(db, doc, data, duration_ms)
        audit_service.record(db, None, "EXTRACTED", document_id=doc.id, client_id=doc.client_id,
                             note=f"AI membaca {len(files) or 1} invoice, {len(extraction.line_items)} baris "
                                  f"dalam {duration_ms} ms")

        issues = run_verification(db, doc)
        settle_status(db, doc, issues, "AI selesai membaca; menunggu PIC memeriksa dan mengirim ke reviewer")
        db.commit()
