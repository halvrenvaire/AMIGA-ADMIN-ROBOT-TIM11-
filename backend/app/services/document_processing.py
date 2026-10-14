"""Alur otomatis setelah unggah atau perbaikan PIC (BPMN, SOP 7.2):

PROCESSING → AI membaca invoice → isian PIC didahulukan → sistem memverifikasi →
READY_FOR_REVIEW (reviewer ditugaskan) atau EXCEPTION (kode + alasan).

Dijalankan di background setelah respons dikirim, dengan sesi database sendiri.
"""
import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app import db as db_module
from app.models import DocStatus, Document, Extraction, IssueCode, LineItem, ValidationIssue
from app.services import audit_service, storage
from app.services.extraction_service import ExtractedInvoice, ExtractionError, InvoiceExtractor
from app.services.reviewer_assignment import pick_reviewer
from app.services.verification import InvoiceData, normalize, verify

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


def _duplicate_of(db, doc: Document, extraction: Extraction) -> str | None:
    """Request ID invoice lain milik klien yang sama dengan vendor dan nomor invoice sama."""
    if not extraction.vendor_norm or not extraction.invoice_no_norm:
        return None
    return db.scalar(
        select(Document.request_id)
        .join(Extraction, Extraction.document_id == Document.id)
        .where(
            Document.client_id == doc.client_id,
            Document.id != doc.id,
            Extraction.vendor_norm == extraction.vendor_norm,
            Extraction.invoice_no_norm == extraction.invoice_no_norm,
        )
        .order_by(Document.created_at)
        .limit(1)
    )


def uploader_ids(doc: Document) -> set[uuid.UUID]:
    """Pengunggah dan PIC yang diwakili: keduanya dianggap "pengunggah" untuk aturan SoD."""
    return {doc.uploaded_by} | ({doc.on_behalf_of} if doc.on_behalf_of else set())


def run_verification(db, doc: Document) -> list:
    """Verifikasi sistem atas data ekstraksi saat ini; kendala lama diganti yang baru."""
    extraction = doc.extraction
    extraction.vendor_norm = normalize(extraction.vendor_name)
    extraction.invoice_no_norm = normalize(extraction.invoice_no)
    invoice = InvoiceData(
        vendor_name=extraction.vendor_name, invoice_no=extraction.invoice_no,
        invoice_date=extraction.invoice_date, total=extraction.total,
        bank_name=extraction.bank_name, account_no=extraction.account_no,
        account_name=extraction.account_name,
        subtotals=[line.subtotal for line in extraction.line_items],
    )
    issues = verify(invoice, _duplicate_of(db, doc, extraction))
    _resolve_open_issues(db, doc)
    for issue in issues:
        db.add(ValidationIssue(document_id=doc.id, code=issue.code, field=issue.field, message=issue.message))
    db.flush()
    return issues


def send_to_review(db, doc: Document, note: str) -> None:
    """READY_FOR_REVIEW dan tugaskan reviewer dengan antrean paling sedikit, bukan pengunggah."""
    reviewer = pick_reviewer(db, doc.client_id, uploader_ids(doc))
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
            db.commit()

        started = time.monotonic()
        try:
            data = extractor.extract(storage.load(doc.file_key))
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
                             note=f"AI membaca {len(extraction.line_items)} baris dalam {duration_ms} ms")

        issues = run_verification(db, doc)
        if issues:
            codes = ", ".join(sorted({i.code.value for i in issues}))
            set_status(db, doc, DocStatus.EXCEPTION, f"Verifikasi sistem: {codes}")
        else:
            send_to_review(db, doc, "Lolos verifikasi")
        db.commit()
