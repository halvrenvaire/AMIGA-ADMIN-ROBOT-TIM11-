"""Unggah invoice, status, dan perbaikan oleh PIC (F1–F3, Layar 02 Unggah Dokumen)."""
import io
import secrets
import uuid
from datetime import date
from decimal import InvalidOperation
from typing import Annotated, Literal

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from fastapi.responses import Response
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ensure_client_access, get_current_user, require_roles
from app.config import settings
from app.db import get_db
from app.models import (
    DocStatus, Document, IssueCode, Role, User, UserClientAssignment, ValidationIssue,
)
from app.schemas.schemas import (
    ClientRef, DocumentDetail, DocumentSummary, ExtractionOut, FixRequest, IssueItem, VoucherOut,
)
from app.services import audit_service, storage
from app.services.access_rules import accessible_client_ids
from app.services.document_processing import PIC_FIELDS, parse_pic_value, process_document, set_status

router = APIRouter(prefix="/documents", tags=["Dokumen Invoice"])

uploader_roles = require_roles(Role.PIC_KLIEN, Role.INTAKE_SUPPORT)

Channel = Literal["Email", "WhatsApp", "Lainnya"]


# --- Helper ---

def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).tuples().all())


def _summary(doc: Document, names: dict[uuid.UUID, str]) -> dict:
    extraction = doc.extraction
    return dict(
        id=doc.id, request_id=doc.request_id, client=ClientRef(id=doc.client.id, name=doc.client.name),
        status=doc.status, request_type=doc.request_type, channel=doc.channel,
        submitted_date=doc.submitted_date, due_date=doc.due_date,
        original_filename=doc.original_filename, page_count=doc.page_count,
        uploaded_by=names.get(doc.uploaded_by, "-"),
        on_behalf_of=names.get(doc.on_behalf_of) if doc.on_behalf_of else None,
        assigned_reviewer=names.get(doc.assigned_reviewer_id) if doc.assigned_reviewer_id else None,
        vendor_name=extraction.vendor_name if extraction else None,
        total=extraction.total if extraction else None,
        created_at=doc.created_at, updated_at=doc.updated_at,
    )


def _people(doc: Document) -> set:
    return {doc.uploaded_by, doc.on_behalf_of, doc.assigned_reviewer_id}


def _detail(db: Session, doc: Document) -> DocumentDetail:
    db.refresh(doc)
    open_issues = db.scalars(
        select(ValidationIssue)
        .where(ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False))
        .order_by(ValidationIssue.created_at, ValidationIssue.code)
    ).all()
    return DocumentDetail(
        **_summary(doc, _names(db, _people(doc))),
        issues=[IssueItem.model_validate(i) for i in open_issues],
        extraction=ExtractionOut.model_validate(doc.extraction) if doc.extraction else None,
        pic_overrides=doc.pic_overrides or {},
        voucher=VoucherOut.model_validate(doc.voucher) if doc.voucher else None,
    )


def _get_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumen tidak ditemukan.")
    ensure_client_access(db, user, doc.client_id)
    return doc


def _new_request_id(db: Session) -> str:
    while True:
        request_id = f"REQ-{date.today():%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not db.scalar(select(Document.id).where(Document.request_id == request_id)):
            return request_id


def _count_pdf_pages(data: bytes) -> int:
    """Tolak file selain PDF yang bisa dibaca (FR-1.5). Pesan ditujukan ke PIC."""
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "File harus berformat PDF. Simpan atau ekspor invoice sebagai PDF, lalu unggah ulang.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "PDF dilindungi password. Unggah versi tanpa password.")
        return len(reader.pages)
    except (PdfReadError, ValueError, OSError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "File PDF rusak atau tidak bisa dibaca. Coba unduh ulang invoice dari vendor.")


# --- Endpoint ---

@router.post("", response_model=DocumentSummary, status_code=201)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    client_id: Annotated[uuid.UUID, Form(description="Klien yang ditugaskan kepada Anda")],
    request_type: Annotated[str, Form(min_length=1, max_length=100, description="Jenis permintaan")],
    channel: Annotated[Channel, Form(description="Asal pengajuan invoice")],
    submitted_date: Annotated[date, Form(description="Tanggal pengajuan")],
    file: Annotated[UploadFile, File(description="Invoice PDF, maksimal 5 halaman")],
    due_date: Annotated[date | None, Form(description="Tenggat (opsional)")] = None,
    user: User = Depends(uploader_roles),
    db: Session = Depends(get_db),
):
    """Unggah satu invoice PDF (FR-1.1–1.5). Sistem menerbitkan Request ID dengan status QUEUED,
    lalu AI membaca invoice dan sistem memverifikasinya di background."""
    ensure_client_access(db, user, client_id)

    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"Ukuran file melebihi {settings.max_upload_mb} MB.")
    pages = _count_pdf_pages(data)
    if pages > settings.max_pdf_pages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Invoice berisi {pages} halaman. Maksimal {settings.max_pdf_pages} halaman per unggahan.")

    # Intake Support mengunggah atas nama PIC yang mendelegasikan (FR-1.4)
    on_behalf_of = None
    if Role.PIC_KLIEN not in user.roles:
        on_behalf_of = db.scalar(select(UserClientAssignment.delegated_by).where(
            UserClientAssignment.user_id == user.id, UserClientAssignment.client_id == client_id))

    request_id = _new_request_id(db)
    file_key = f"invoices/{request_id}.pdf"
    try:
        storage.save(file_key, data)
    except storage.StorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File gagal disimpan. Coba lagi beberapa saat lagi.")

    doc = Document(
        request_id=request_id, client_id=client_id, uploaded_by=user.id, on_behalf_of=on_behalf_of,
        request_type=request_type.strip(), channel=channel, submitted_date=submitted_date, due_date=due_date,
        status=DocStatus.QUEUED, file_key=file_key,
        original_filename=(file.filename or "invoice.pdf")[:300], page_count=pages, pic_overrides={},
    )
    db.add(doc)
    db.flush()
    audit_service.record(db, user, "DOCUMENT_UPLOADED", document_id=doc.id, client_id=client_id,
                         on_behalf_of=on_behalf_of, status_after=DocStatus.QUEUED.value,
                         note=f"{doc.original_filename} ({pages} hal.) via {channel}")
    db.commit()
    db.refresh(doc)

    background.add_task(process_document, doc.id, request.app.state.extractor)
    return DocumentSummary(**_summary(doc, _names(db, _people(doc))))


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    status_filter: Annotated[DocStatus | None, Query(alias="status")] = None,
    client_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dokumen milik klien yang ditugaskan kepada Anda, terbaru di atas."""
    client_ids = accessible_client_ids(db, user)
    if client_id is not None:
        client_ids &= {client_id}
    query = select(Document).where(Document.client_id.in_(client_ids)).order_by(Document.created_at.desc())
    if status_filter is not None:
        query = query.where(Document.status == status_filter)
    docs = db.scalars(query).all()
    names = _names(db, set().union(*(_people(d) for d in docs)) if docs else set())
    return [DocumentSummary(**_summary(d, names)) for d in docs]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Status, kode dan alasan kendala, serta data hasil ekstraksi."""
    return _detail(db, _get_document(db, user, document_id))


@router.get("/{document_id}/file", response_class=Response)
def get_document_file(document_id: uuid.UUID, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """PDF asli (ditampilkan di layar peninjauan)."""
    doc = _get_document(db, user, document_id)
    try:
        data = storage.load(doc.file_key)
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File PDF tidak ditemukan di penyimpanan.")
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc.request_id}.pdf"'})


@router.post("/{document_id}/fix", response_model=DocumentDetail)
def fix_document(
    document_id: uuid.UUID,
    body: FixRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(uploader_roles),
    db: Session = Depends(get_db),
):
    """Kirim perbaikan saat EXCEPTION (FR-3.4). Dokumen kembali ke ekstraksi dengan Request ID
    yang sama (FR-2.4), dan isian Anda tidak ditimpa hasil AI."""
    doc = _get_document(db, user, document_id)
    if doc.status != DocStatus.EXCEPTION:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Perbaikan hanya bisa dikirim saat status EXCEPTION (sekarang {doc.status.value}).")
    unknown = set(body.fields) - set(PIC_FIELDS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Field tidak bisa diperbaiki: {', '.join(sorted(unknown))}.")
    if not body.fields and not (body.note and body.note.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Isi minimal satu perbaikan atau catatan.")

    overrides = dict(doc.pic_overrides or {})
    for name, raw in body.fields.items():
        value = raw.strip()
        if not value:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Field {name} tidak boleh kosong.")
        try:
            parse_pic_value(name, value)
        except (ValueError, InvalidOperation):
            hint = "format YYYY-MM-DD" if name == "invoice_date" else "angka tanpa titik ribuan, mis. 1250000"
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Nilai {name} tidak valid ({hint}).")
        current = getattr(doc.extraction, name, None) if doc.extraction else None
        overrides[name] = value
        audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                             field=name, old_value=None if current is None else str(current), new_value=value)
    doc.pic_overrides = overrides
    if body.note and body.note.strip():
        audit_service.record(db, user, "PIC_NOTE", document_id=doc.id, client_id=doc.client_id,
                             note=body.note.strip())
    set_status(db, doc, DocStatus.PROCESSING, "Perbaikan PIC dikirim; ekstraksi ulang dengan Request ID sama")
    db.commit()

    background.add_task(process_document, doc.id, request.app.state.extractor)
    return _detail(db, doc)


@router.post("/{document_id}/reprocess", response_model=DocumentDetail)
def reprocess_document(
    document_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_roles(Role.FINANCE_REVIEWER)),
    db: Session = Depends(get_db),
):
    """Proses ulang dokumen yang gagal dibaca AI (FR-2.5)."""
    doc = _get_document(db, user, document_id)
    failed = db.scalar(select(ValidationIssue.id).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False),
        ValidationIssue.code == IssueCode.EXTRACTION_FAILED))
    if doc.status != DocStatus.EXCEPTION or failed is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Proses ulang hanya untuk dokumen yang gagal dibaca AI.")
    audit_service.record(db, user, "REPROCESS_REQUESTED", document_id=doc.id, client_id=doc.client_id)
    set_status(db, doc, DocStatus.PROCESSING, "Diproses ulang oleh Finance Reviewer")
    db.commit()

    background.add_task(process_document, doc.id, request.app.state.extractor)
    return _detail(db, doc)
