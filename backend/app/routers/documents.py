"""Unggah invoice, status, dan perbaikan oleh PIC (F1–F3, Layar 02 Unggah Dokumen)."""
import io
import secrets
import uuid
from datetime import date, timedelta
from decimal import InvalidOperation
from typing import Annotated, Literal, NamedTuple

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from fastapi.responses import Response
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.auth import ensure_client_access, ensure_submit_access, get_current_user, require_roles
from app.config import settings
from app.db import get_db
from app.models import (
    AuditLog, DocStatus, Document, DocumentFile, Extraction, IssueCode, Role, User, UserClientAssignment, ValidationIssue,
)
from app.schemas.schemas import (
    CancellationOut, ClientRef, DocumentDetail, DocumentFileOut, DocumentSummary, ReasonRequest, ExtractionOut, FixRequest, IssueItem, SignersUpdate, VoucherOut,
)
from app.services import audit_service, file_conversion, signer_service, storage
from app.services.access_rules import accessible_client_ids
from app.services.account_check import check_account
from app.services.document_processing import (
    PIC_FIELDS, classification, parse_pic_value, process_document, set_status,
)

router = APIRouter(prefix="/documents", tags=["Dokumen Invoice"])

uploader_roles = require_roles(Role.PIC_KLIEN, Role.INTAKE_SUPPORT)

# "Telegram" diisi otomatis oleh bot @amiga_ro_bot (unggah dari chat pribadi PIC yang terhubung)
Channel = Literal["Email", "WhatsApp", "Lainnya", "Telegram"]


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
        vendor=ClientRef(id=doc.vendor.id, name=doc.vendor.name) if doc.vendor else None,
        signers=doc.signers or [],
        files=[DocumentFileOut.model_validate(f) for f in doc.files],
        cancellation=_cancellation(db, doc),
        classification=classification(doc.extraction),
        account_check=vars(check_account(db, doc)) if doc.extraction else None,
    )


def _cancellation(db: Session, doc: Document) -> CancellationOut | None:
    if doc.status != DocStatus.CANCELLED:
        return None
    log = db.scalars(select(AuditLog).where(AuditLog.document_id == doc.id, AuditLog.action == "DOCUMENT_CANCELLED")
                     .order_by(AuditLog.created_at.desc()).limit(1)).first()
    return CancellationOut(by=log.actor_label, at=log.created_at, reason=log.note or "-") if log else None


def _get_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumen tidak ditemukan.")
    ensure_client_access(db, user, doc.client_id)
    return doc


class _UploadPart(NamedTuple):
    name: str
    pdf: bytes
    pages: int
    source: bytes | None  # file asli bila dikonversi dari foto
    source_format: str | None


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

def _merge_pdfs(parts: list[bytes]) -> bytes:
    """Satu PDF gabungan untuk layar peninjauan, berurutan sesuai unggahan."""
    writer = PdfWriter()
    for data in parts:
        writer.append(io.BytesIO(data))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@router.post("", response_model=DocumentSummary, status_code=201)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    client_id: Annotated[uuid.UUID, Form(description="Perusahaan klien yang mengajukan (\"Diajukan oleh\")")],
    request_type: Annotated[str, Form(min_length=1, max_length=100, description="Jenis permintaan")],
    channel: Annotated[Channel, Form(description="Asal pengajuan invoice")],
    submitted_date: Annotated[date, Form(description="Tanggal pengajuan")],
    files: Annotated[list[UploadFile], File(description="1–10 invoice PDF untuk satu voucher, masing-masing maks. 5 halaman")],
    due_date: Annotated[date | None, Form(description="Tenggat (opsional)")] = None,
    signatory_ids: Annotated[str | None, Form(
        description="ID pemberi persetujuan (\"Disetujui oleh\") dipisah koma, berurutan. "
                    "Tidak dikirim = 1 kotak default klien; kosong = tanpa pemberi persetujuan")] = None,
    user: User = Depends(uploader_roles),
    db: Session = Depends(get_db),
):
    """Unggah 1–10 invoice PDF yang digabung dalam satu voucher (FR-1.1–1.5). Sistem menerbitkan
    satu Request ID dengan status QUEUED, lalu AI membaca setiap invoice dan sistem memverifikasinya
    di background."""
    ensure_submit_access(db, user, client_id)
    if not 1 <= len(files) <= settings.max_upload_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Unggah minimal 1 dan maksimal {settings.max_upload_files} file invoice.")

    limit = settings.max_upload_mb * 1024 * 1024
    parts: list[_UploadPart] = []
    for upload in files:
        name = (upload.filename or "invoice.pdf")[:300]
        data = await upload.read(limit + 1)
        label = f"{name}: " if len(files) > 1 else ""
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                                f"{label}Ukuran file melebihi {settings.max_upload_mb} MB.")
        # Foto (JPG/PNG/WEBP) diubah menjadi PDF; alur selanjutnya selalu memakai PDF
        try:
            prepared = file_conversion.to_pdf(data)
        except file_conversion.UnsupportedFile as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label}{e}")
        try:
            pages = _count_pdf_pages(prepared.pdf)
        except HTTPException as e:
            raise HTTPException(e.status_code, f"{label}{e.detail}")
        if pages > settings.max_pdf_pages:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                f"{label}Invoice berisi {pages} halaman. Maksimal {settings.max_pdf_pages} halaman per file.")
        parts.append(_UploadPart(name, prepared.pdf, pages, data if prepared.converted else None,
                                 prepared.source_format))

    # Intake Support mengunggah atas nama PIC yang mendelegasikan (FR-1.4)
    on_behalf_of = None
    if Role.PIC_KLIEN not in user.roles:
        on_behalf_of = db.scalar(select(UserClientAssignment.delegated_by).where(
            UserClientAssignment.user_id == user.id, UserClientAssignment.client_id == client_id))

    # "Diajukan oleh" di voucher = PIC Klien: pengunggah, atau PIC yang diwakili Intake Support
    submitter = db.get(User, on_behalf_of) if on_behalf_of else user
    signers = signer_service.resolve(db, client_id, signer_service.parse_ids(signatory_ids), submitter)

    request_id = _new_request_id(db)
    total_pages = sum(p.pages for p in parts)
    # File asli foto disimpan sebagai bukti di samping PDF hasil konversi
    source_keys = [f"invoices/{request_id}-asli-{i:02d}.{p.source_format}" if p.source_format else None
                   for i, p in enumerate(parts, start=1)]
    try:
        if len(parts) == 1:
            file_keys = [f"invoices/{request_id}.pdf"]
            storage.save(file_keys[0], parts[0].pdf)
            main_key = file_keys[0]
        else:
            file_keys = [f"invoices/{request_id}/{i:02d}.pdf" for i in range(1, len(parts) + 1)]
            for key, part in zip(file_keys, parts):
                storage.save(key, part.pdf)
            main_key = f"invoices/{request_id}.pdf"
            storage.save(main_key, _merge_pdfs([p.pdf for p in parts]))
        for key, part in zip(source_keys, parts):
            if key:
                storage.save(key, part.source)
    except storage.StorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File gagal disimpan. Coba lagi beberapa saat lagi.")

    names = [p.name + (f" (foto {p.source_format.upper()} → PDF)" if p.source_format else "") for p in parts]
    plain_names = [p.name for p in parts]
    summary_name = plain_names[0] if len(parts) == 1 else f"{len(parts)} invoice: {', '.join(plain_names)}"
    doc = Document(
        request_id=request_id, client_id=client_id, uploaded_by=user.id, on_behalf_of=on_behalf_of,
        request_type=request_type.strip(), channel=channel, submitted_date=submitted_date, due_date=due_date,
        status=DocStatus.QUEUED, file_key=main_key,
        original_filename=summary_name[:300], page_count=total_pages, pic_overrides={},
        signers=signers,
        files=[DocumentFile(position=i, file_key=key, original_filename=part.name, page_count=part.pages,
                            source_file_key=source_key, source_format=part.source_format)
               for i, (key, source_key, part) in enumerate(zip(file_keys, source_keys, parts), start=1)],
    )
    db.add(doc)
    db.flush()
    audit_service.record(db, user, "DOCUMENT_UPLOADED", document_id=doc.id, client_id=client_id,
                         on_behalf_of=on_behalf_of, status_after=DocStatus.QUEUED.value,
                         note=f"{len(parts)} file, {total_pages} hal. via {channel}: {', '.join(names)}"[:1000])
    db.commit()
    db.refresh(doc)

    background.add_task(process_document, doc.id, request.app.state.extractor)
    return DocumentSummary(**_summary(doc, _names(db, _people(doc))))


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    status_filter: Annotated[DocStatus | None, Query(alias="status")] = None,
    client_id: uuid.UUID | None = None,
    reviewer_id: uuid.UUID | None = None,
    problem: Annotated[bool, Query(description="Hanya dokumen bermasalah (EXCEPTION)")] = False,
    due_within_days: Annotated[int | None, Query(ge=0, le=365, description="Tenggat <= N hari lagi, belum selesai")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Cari Request ID atau vendor")] = None,
    sort: Literal["terbaru", "tenggat"] = "terbaru",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dokumen milik klien yang ditugaskan kepada Anda, dengan filter klien, status, reviewer,
    tenggat, dan dokumen bermasalah (FR-6.2)."""
    client_ids = accessible_client_ids(db, user)
    if client_id is not None:
        client_ids &= {client_id}
    query = select(Document).where(Document.client_id.in_(client_ids))
    if status_filter is not None:
        query = query.where(Document.status == status_filter)
    if problem:
        query = query.where(Document.status == DocStatus.EXCEPTION)
    if reviewer_id is not None:
        query = query.where(Document.assigned_reviewer_id == reviewer_id)
    if due_within_days is not None:
        query = query.where(
            Document.due_date <= date.today() + timedelta(days=due_within_days),
            Document.status.not_in((DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT, DocStatus.CANCELLED)),
        )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.outerjoin(Extraction, Extraction.document_id == Document.id).where(
            or_(Document.request_id.ilike(pattern), Extraction.vendor_name.ilike(pattern)))
    if sort == "tenggat":
        query = query.order_by(Document.due_date.is_(None), Document.due_date, Document.created_at)
    else:
        query = query.order_by(Document.created_at.desc())
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


@router.get("/{document_id}/files/{position}/original", response_class=Response)
def get_original_file(document_id: uuid.UUID, position: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """File asli (foto) sebelum dikonversi ke PDF, untuk dicek bila hasil konversi meragukan."""
    doc = _get_document(db, user, document_id)
    part = next((f for f in doc.files if f.position == position), None)
    if part is None or not part.source_file_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File ini diunggah sebagai PDF; tidak ada file asli lain.")
    try:
        data = storage.load(part.source_file_key)
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File asli tidak ditemukan di penyimpanan.")
    filename = f"{doc.request_id}-{position:02d}.{part.source_format}"
    return Response(data, media_type=file_conversion.IMAGE_TYPES[part.source_format],
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


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
    ensure_submit_access(db, user, doc.client_id)
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


@router.put("/{document_id}/signers", response_model=DocumentDetail)
def set_signers(document_id: uuid.UUID, body: SignersUpdate, user: User = Depends(uploader_roles),
                db: Session = Depends(get_db)):
    """Ganti penanda tangan voucher selama voucher belum terbit (PIC Klien / Intake Support)."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status in (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT, DocStatus.CANCELLED):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Voucher sudah terbit atau pengajuan dibatalkan; penanda tangan tidak bisa diubah.")
    # Kotak "Diajukan oleh" (PIC) tetap; hanya kotak "Disetujui oleh" yang diganti
    pengaju = [s for s in doc.signers or [] if s["kind"] == "PENGAJU"]
    new = pengaju + signer_service.resolve(db, doc.client_id, body.signatory_ids, None)
    describe = lambda items: "; ".join(f"{s['name']} ({s['position']})" for s in items) or "-"  # noqa: E731
    audit_service.record(db, user, "SIGNERS_CHANGED", document_id=doc.id, client_id=doc.client_id,
                         field="signers", old_value=describe(doc.signers or []), new_value=describe(new))
    doc.signers = new
    db.commit()
    return _detail(db, doc)


CANCELLABLE = (DocStatus.EXCEPTION, DocStatus.READY_FOR_REVIEW)


@router.post("/{document_id}/cancel", response_model=DocumentDetail)
def cancel_document(document_id: uuid.UUID, body: ReasonRequest, user: User = Depends(uploader_roles),
                    db: Session = Depends(get_db)):
    """Batalkan pengajuan (mis. salah unggah) dengan alasan wajib, selama voucher belum terbit.
    Dokumen tidak dihapus: status menjadi CANCELLED, kendala ditutup, dan pembatalan tercatat di jejak audit.
    Pengajuan yang dibatalkan tidak dihitung sebagai duplikat, sehingga invoice bisa diajukan ulang."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status in (DocStatus.QUEUED, DocStatus.PROCESSING):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "AI sedang membaca invoice ini. Tunggu sampai selesai (beberapa detik), lalu batalkan.")
    if doc.status not in CANCELLABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Pengajuan tidak bisa dibatalkan karena berstatus {doc.status.value}.")
    db.execute(update(ValidationIssue).where(ValidationIssue.document_id == doc.id,
                                             ValidationIssue.resolved.is_(False)).values(resolved=True))
    audit_service.record(db, user, "DOCUMENT_CANCELLED", document_id=doc.id, client_id=doc.client_id,
                         status_before=doc.status.value, status_after=DocStatus.CANCELLED.value,
                         note=body.reason.strip())
    set_status(db, doc, DocStatus.CANCELLED, f"Dibatalkan oleh {user.full_name}")
    db.commit()
    return _detail(db, doc)
