"""Unggah invoice, status, dan perbaikan oleh PIC (F1–F3, Layar 02 Unggah Dokumen)."""
import io
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
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
    CATEGORY_REIMBURSE, ITEMIZED, REQUEST_CATEGORIES, TOTAL_ONLY, AuditLog, Client, DocStatus, Document, DocumentFile,
    Extraction, IssueCode, Role, TaxRate, User, UserClientAssignment, ValidationIssue,
)
from app.schemas.schemas import (
    CancellationOut, ClientRef, DocumentDetail, DocumentFileOut, DocumentSummary, ExtractionOut, FileDataUpdate,
    AcknowledgeRequest, FileAdd, FilePagesUpdate, FixRequest, IssueItem, OptionsUpdate, ReasonRequest, SignatureIn, SignersUpdate, TaxChoice,
    TaxSummaryOut, VoucherOut,
)
from app.services import (
    audit_service, file_conversion, invoice_split, signature_service, signer_service, storage, tax_service, voucher_attachments,
    voucher_service,
)
from app.services.access_rules import accessible_client_ids
from app.services.bedrock_client import BedrockError
from app.services.extraction_service import ExtractedInvoice
from app.services.account_check import check_account, payee_checks
from app.services.document_processing import (
    ACKNOWLEDGEABLE, BLOCKING, DATA_FIELDS, PIC_FIELDS, acknowledgement, classification, default_description, file_data,
    line_subtotal, manual_entry, parse_pic_value, part_to_data, payee_fingerprint, process_document, rebuild_from_files,
    run_verification, send_to_review, set_status, settle_status,
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
        extraction_mode=doc.extraction_mode or ITEMIZED, include_account=bool(doc.include_account),
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
        files=[DocumentFileOut.model_validate(f).model_copy(update={
                   "data": _with_suggestions(doc, file_data(doc, f)),
                   "upload_name": invoice_split.base_name(f.original_filename)}) for f in doc.files],
        cancellation=_cancellation(db, doc),
        classification=classification(doc.extraction),
        account_check=vars(check_account(db, doc)) if doc.extraction else None,
        tax_summary=_tax_summary(doc) if doc.extraction else None,
        ai_manual=_manual_info(doc), ai_enabled=settings.ai_extraction_enabled,
        invoice_limit=(doc.extraction.raw_json or {}).get("invoice_limit")
        if doc.extraction and isinstance(doc.extraction.raw_json, dict) else None,
        payees=[_payee_out(p) for p in payee_checks(db, doc)] if doc.extraction else [],
        acknowledgements={c.value: {k: ack[k] for k in ("reason", "by", "at")}
                          for c in ACKNOWLEDGEABLE if (ack := acknowledgement(doc.extraction, c))},
        submitter_signature=doc.submitter_signature_png is not None,
    )


def _payee_out(p) -> dict:
    return {**{k: getattr(p, k) for k in ("vendor_name", "bank_name", "account_no", "account_name", "invoices", "gross",
                                          "net", "vendor_id", "vendor_verified", "reference_matches")},
            "state": p.check.state, "message": p.check.message, "source": p.check.source}


def _manual_info(doc: Document) -> dict | None:
    info = manual_entry(doc.extraction)
    if info is None:
        return None
    # Pesan teknis (mis. kredensial AWS) hanya di log dan riwayat, bukan di layar
    return {"status": info.get("status"), "files": info.get("files") or [], "message": info.get("message")}


def _tax_summary(doc: Document) -> TaxSummaryOut:
    t = tax_service.summary(doc)
    return TaxSummaryOut(gross=t.gross, tax_total=t.tax_total, net=t.net, lines=[vars(line) for line in t.lines],
                         vat=[vars(v) for v in t.vat])


def _with_suggestions(doc: Document, data: dict) -> dict:
    """Saran PPh per baris untuk layar (aturan kata kunci, atau hasil AI yang tersimpan); tidak disimpan."""
    if not data.get("line_items"):
        return data
    return {**data, "line_suggestions": tax_service.line_suggestions(data, doc.request_type == CATEGORY_REIMBURSE)}


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
    request_type: Annotated[str, Form(min_length=1, max_length=100,
                                      description="Kategori: " + " / ".join(REQUEST_CATEGORIES))],
    submitted_date: Annotated[date, Form(description="Tanggal pengajuan")],
    files: Annotated[list[UploadFile], File(description="1–10 file bukti untuk satu voucher (Reimburse: sampai 20); jumlah halaman tidak dibatasi")],
    channel: Annotated[Channel | None, Form(description="Asal pengajuan invoice (opsional, isian tambahan)")] = None,
    due_date: Annotated[date | None, Form(description="Tenggat (opsional)")] = None,
    extraction_mode: Annotated[Literal["TOTAL_ONLY", "ITEMIZED"], Form(description=(
        "Mode baca AI: TOTAL_ONLY (bawaan) = hanya total per invoice, 1 baris voucher per invoice; "
        "ITEMIZED = rincian barang/jasa, 1 baris voucher per item"))] = TOTAL_ONLY,
    include_account: Annotated[bool, Form(description="Fitur tambahan: isi, cek, dan cetak rekening tujuan")] = False,
    submitter_source: Annotated[Literal["PIC", "MANUAL"] | None, Form(description=(
        "Sumber \"Diajukan oleh\": PIC = profil akun PIC Klien (dikunci, termasuk tanda tangan); MANUAL = nama, "
        "jabatan, perusahaan, dan tanda tangan diisi di sini (tidak diingat). Tidak dikirim = MANUAL bila ada isian "
        "nama/jabatan/perusahaan/tanda tangan, selain itu PIC"))] = None,
    submitter_position: Annotated[str | None, Form(max_length=120, description=(
        "Mode MANUAL: jabatan di kotak \"Diajukan oleh\""))] = None,
    submitter_company: Annotated[str | None, Form(max_length=200, description=(
        "Mode MANUAL: perusahaan/unit di kotak \"Diajukan oleh\". Kosong = nama klien"))] = None,
    submitter_signature: Annotated[UploadFile | None, File(description=(
        "Mode MANUAL: gambar tanda tangan (PNG/JPG/WEBP, maks. 2 MB). Kosong = tanda tangan basah"))] = None,
    signatory_ids: Annotated[str | None, Form(
        description="ID pemberi persetujuan (\"Disetujui oleh\") dipisah koma, berurutan. "
                    "Tidak dikirim = 1 kotak default klien; kosong = tanpa pemberi persetujuan")] = None,
    submitter_name: Annotated[str | None, Form(max_length=200, description=(
        "Mode MANUAL: nama di kotak \"Diajukan oleh\" (wajib)"))] = None,
    user: User = Depends(uploader_roles),
    db: Session = Depends(get_db),
):
    """Unggah 1–10 invoice PDF yang digabung dalam satu voucher (FR-1.1–1.5). Sistem menerbitkan
    satu Request ID dengan status QUEUED, lalu AI membaca setiap invoice dan sistem memverifikasinya
    di background."""
    if request_type.strip() not in REQUEST_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Kategori tidak dikenal. Pilih salah satu: " + ", ".join(REQUEST_CATEGORIES) + ".")
    ensure_submit_access(db, user, client_id)
    max_files = settings.max_reimburse_files if request_type.strip() == CATEGORY_REIMBURSE else settings.max_upload_files
    if not 1 <= len(files) <= max_files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Unggah minimal 1 dan maksimal {max_files} file bukti untuk kategori ini.")

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
        parts.append(_UploadPart(name, prepared.pdf, pages, data if prepared.converted else None,
                                 prepared.source_format))

    # Intake Support mengunggah atas nama PIC yang mendelegasikan (FR-1.4)
    on_behalf_of = None
    if Role.PIC_KLIEN not in user.roles:
        on_behalf_of = db.scalar(select(UserClientAssignment.delegated_by).where(
            UserClientAssignment.user_id == user.id, UserClientAssignment.client_id == client_id))

    # "Diajukan oleh" di voucher (Tahap 15): mode PIC = profil akun PIC Klien (pengunggah, atau PIC yang diwakili
    # Intake Support) beserta tanda tangannya; mode MANUAL = isian formulir ini, tidak diingat untuk pengajuan berikutnya
    submitter = db.get(User, on_behalf_of) if on_behalf_of else user
    has_upload = submitter_signature is not None and bool(submitter_signature.filename)
    source = submitter_source or (signer_service.MANUAL if has_upload or any(
        (v or "").strip() for v in (submitter_name, submitter_position, submitter_company)) else signer_service.PIC)
    if source == signer_service.PIC:
        profile = signer_service.default_profile(submitter, db.get(Client, client_id))
        name, position, company = profile["name"], profile["position"], profile["company"]
        signature = submitter.signature_png
    else:
        name = (submitter_name or "").strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Isi nama pengaju di bagian \"Diajukan oleh\".")
        position = (submitter_position or "").strip()
        company = (submitter_company or "").strip() or db.get(Client, client_id).name
        signature = signature_service.normalize_bytes(
            await submitter_signature.read(signature_service.MAX_UPLOAD_BYTES + 1)) if has_upload else None
    signers = signer_service.resolve(db, client_id, signer_service.parse_ids(signatory_ids),
                                     signer_service.pengaju_profile(name, position, company, signature is not None,
                                                                    source))

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
        signers=signers, extraction_mode=extraction_mode, include_account=include_account,
        submitter_signature_png=signature,
        files=[DocumentFile(position=i, file_key=key, original_filename=part.name, page_count=part.pages,
                            source_file_key=source_key, source_format=part.source_format)
               for i, (key, source_key, part) in enumerate(zip(file_keys, source_keys, parts), start=1)],
    )
    db.add(doc)
    db.flush()
    audit_service.record(db, user, "DOCUMENT_UPLOADED", document_id=doc.id, client_id=client_id,
                         on_behalf_of=on_behalf_of, status_after=DocStatus.QUEUED.value,
                         note=(f"{len(parts)} file, {total_pages} hal. via {channel or '-'}, mode "
                               f"{'total saja' if extraction_mode == TOTAL_ONLY else 'rincian'}"
                               f"{', rekening dicantumkan' if include_account else ''}: {', '.join(names)}")[:1000])
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
    request_type: Annotated[str | None, Query(max_length=100, description="Kategori pengajuan")] = None,
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
    if request_type:
        query = query.where(Document.request_type == request_type)
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


def _file(doc: Document, position: int) -> DocumentFile:
    part = next((f for f in doc.files if f.position == position), None)
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File bukti tidak ditemukan.")
    return part


@router.get("/{document_id}/files/{position}", response_class=Response)
def get_single_file(document_id: uuid.UUID, position: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """PDF satu file bukti (dipakai saat PIC mengedit per invoice)."""
    doc = _get_document(db, user, document_id)
    part = _file(doc, position)
    try:
        data = storage.load(part.file_key)
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File PDF tidak ditemukan di penyimpanan.")
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{doc.request_id}-{position:02d}.pdf"'})


EDITABLE = (DocStatus.DRAFT, DocStatus.EXCEPTION)


def _fmt(value) -> str | None:
    return None if value in (None, "") else str(value)


def _line_in(li) -> dict:
    # Qty dan harga satuan terisi → subtotal dihitung sistem (qty × harga); selain itu subtotal diisi manual
    subtotal = line_subtotal(li.qty, li.unit_price)
    line = {"description": (li.description or "").strip() or None, "qty": _fmt(li.qty),
            "unit_price": _fmt(li.unit_price), "subtotal": _fmt(li.subtotal if subtotal is None or subtotal == li.subtotal else subtotal)}
    # Pengaturan pajak baris (dari panel pajak) ikut disimpan bila dikirim
    line.update({k: v for k, v in (("pph", li.pph), ("vat", li.vat), ("kind", li.kind)) if v is not None})
    return line


@router.put("/{document_id}/files/{position}/data", response_model=DocumentDetail)
def update_file_data(document_id: uuid.UUID, position: int, body: FileDataUpdate,
                     user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """PIC melengkapi/mengedit data SATU invoice (feedback owner: edit per invoice; reviewer tidak mengedit).
    Data voucher disusun ulang dari semua invoice, diverifikasi ulang, dan statusnya menjadi Draf atau Ada kendala.
    Setiap perubahan dicatat nilai awal → nilai baru."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Data hanya bisa diedit saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    part = _file(doc, position)
    old = file_data(doc, part)
    new = {"vendor_name": (body.vendor_name or "").strip() or None, "invoice_no": (body.invoice_no or "").strip() or None,
           "invoice_date": body.invoice_date.isoformat() if body.invoice_date else None, "total": _fmt(body.total),
           "bank_name": (body.bank_name or "").strip() or None, "account_no": (body.account_no or "").strip() or None,
           "account_name": (body.account_name or "").strip() or None,
           # Mode total saja: tanpa rincian; satu baris voucher per invoice berisi uraian transaksi
           "line_items": [] if doc.extraction_mode == TOTAL_ONLY else [_line_in(li) for li in body.line_items]}
    if not doc.include_account:
        # Fitur rekening mati: kolom rekening tidak ditampilkan, jadi nilai lama tetap disimpan apa adanya
        new.update({k: old.get(k) for k in ("bank_name", "account_no", "account_name")})
    if body.description is not None:
        new["description"] = (body.description or "").strip() or None
    label = f"Bukti {position} ({part.original_filename})"
    changes = [(k, _fmt(old.get(k)), _fmt(new[k])) for k in (*DATA_FIELDS, "description")
               if k in new and (_fmt(old.get(k)) or "") != (_fmt(new[k]) or "")]
    if (old.get("line_items") or []) != new["line_items"]:
        changes.append(("line_items", f"{len(old.get('line_items') or [])} baris", f"{len(new['line_items'])} baris"))
    if not changes:
        return _detail(db, doc)
    for field, before, after in changes:
        audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                             field=f"{label}.{field}", old_value=before, new_value=after)
    # Pilihan pajak dan saran AI ikut disimpan; potongan dihitung ulang dari data baru
    extras = {k: v for k, v in old.items() if k not in new}
    new = {**extras, **new, "tax": tax_service.recompute(old.get("tax"), new)}
    part.data = new
    if any(f == "account_no" for f, _, _ in changes):
        doc.pic_overrides = {**(doc.pic_overrides or {}), "account_no": new["account_no"] or ""}
        new["account_by_pic"] = True  # cek rekening per invoice: nomor ini diisi PIC, bukan dibaca dari dokumen
    rebuild_from_files(db, doc)
    issues = run_verification(db, doc)
    settle_status(db, doc, issues, "Data diperbarui PIC")
    db.commit()
    return _detail(db, doc)


# --- Bukti per invoice dalam satu PDF (Tahap 15) ---

def _editable_files(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Bukti hanya bisa diubah saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    return doc


def _upload_of(part: DocumentFile) -> tuple[str, bytes, int]:
    """(key, isi, jumlah halaman) PDF unggahan asal bukti ini."""
    key = invoice_split.upload_key(part)
    try:
        upload = storage.load(key)
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File PDF tidak ditemukan di penyimpanan.")
    return key, upload, part.upload_pages or invoice_split.page_count(upload)


def _check_range(first: int, last: int, pages: int) -> None:
    if not 1 <= first <= last <= pages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Rentang halaman tidak valid. Pilih halaman 1 sampai {pages}, dan halaman awal tidak "
                            "boleh setelah halaman akhir.")


def _rekey_checks(doc: Document, renamed: dict[str, str], removed: str | None = None) -> None:
    """Hasil cek jenis dokumen disimpan per nama bukti; ikut diperbarui bila nama berubah atau bukti dihapus."""
    ex = doc.extraction
    if ex is None or not isinstance(ex.raw_json, dict) or not ex.raw_json.get("document_checks"):
        return
    checks = [{**c, "file": renamed.get(c.get("file"), c.get("file"))}
              for c in ex.raw_json["document_checks"] if removed is None or c.get("file") != removed]
    ex.raw_json = {**ex.raw_json, "document_checks": checks}


def _after_files_changed(db: Session, doc: Document) -> DocumentDetail:
    rebuild_from_files(db, doc)
    issues = run_verification(db, doc)
    settle_status(db, doc, issues, "Bukti diperbarui PIC")
    db.commit()
    return _detail(db, doc)


@router.put("/{document_id}/files/{position}/pages", response_model=DocumentDetail)
def set_file_pages(document_id: uuid.UUID, position: int, body: FilePagesUpdate,
                   user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """Ubah rentang halaman satu bukti dari PDF unggahannya (mis. invoice + Faktur Pajak + rincian). Data invoice yang
    sudah terisi tetap; lampiran voucher tetap memuat PDF unggahan utuh."""
    doc = _editable_files(db, user, document_id)
    part = _file(doc, position)
    key, upload, pages = _upload_of(part)
    _check_range(body.page_from, body.page_to, pages)
    before = invoice_split.pages_label(part.page_from or 1, part.page_to or pages)
    after = invoice_split.pages_label(body.page_from, body.page_to)
    if before == after and part.page_from is not None:
        return _detail(db, doc)
    try:
        part.file_key = invoice_split.save_piece(upload, key, body.page_from, body.page_to, pages)
    except storage.StorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File gagal disimpan. Coba lagi beberapa saat lagi.")
    audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                         field=f"Bukti {position} ({part.original_filename}).halaman", old_value=before, new_value=after)
    part.upload_key, part.upload_pages = key, pages
    part.page_from, part.page_to, part.page_count = body.page_from, body.page_to, body.page_to - body.page_from + 1
    _rekey_checks(doc, invoice_split.rename_group(doc, key))
    return _after_files_changed(db, doc)


@router.post("/{document_id}/files", response_model=DocumentDetail, status_code=201)
def add_file(document_id: uuid.UUID, body: FileAdd, request: Request, background: BackgroundTasks,
             user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """Tambah bukti dari halaman PDF unggahan (invoice yang terlewat AI, atau beberapa struk dalam satu halaman).
    `read_ai`: AI membaca bukti baru (bukti lain tetap); selain itu PIC mengisi datanya sendiri."""
    doc = _editable_files(db, user, document_id)
    if len(doc.files) >= settings.max_invoices_per_voucher:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Satu voucher paling banyak {settings.max_invoices_per_voucher} invoice/bukti.")
    source = _file(doc, body.source_position)
    key, upload, pages = _upload_of(source)
    _check_range(body.page_from, body.page_to, pages)
    try:
        piece = invoice_split.save_piece(upload, key, body.page_from, body.page_to, pages)
    except storage.StorageError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "File gagal disimpan. Coba lagi beberapa saat lagi.")
    if source.page_from is None:  # bukti lama/belum dipindai: seluruh file unggahan
        source.upload_key, source.upload_pages, source.page_from, source.page_to = key, pages, 1, pages
    read_ai = body.read_ai and settings.ai_extraction_enabled and request.app.state.extractor is not None
    empty = part_to_data(ExtractedInvoice())
    new = DocumentFile(id=uuid.uuid4(), document_id=doc.id, position=2000, file_key=piece,
                       original_filename=invoice_split.base_name(source.original_filename),
                       page_count=body.page_to - body.page_from + 1, source_file_key=source.source_file_key,
                       source_format=source.source_format, upload_key=key, upload_pages=pages,
                       page_from=body.page_from, page_to=body.page_to,
                       data=None if read_ai else {**empty, "description": None})
    db.add(new)
    # Bukti baru diletakkan setelah bukti terakhir dari unggahan yang sama
    group_end = max(i for i, f in enumerate(doc.files) if invoice_split.upload_key(f) == key)
    ordered = doc.files[:group_end + 1] + [new] + doc.files[group_end + 1:]
    db.flush()
    invoice_split.renumber(db, doc, ordered)
    db.expire(doc, ["files"])
    _rekey_checks(doc, invoice_split.rename_group(doc, key))
    audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                         field=f"Bukti {new.position}", old_value=None,
                         new_value=f"Ditambahkan dari {invoice_split.base_name(source.original_filename)} hal. "
                                   f"{invoice_split.pages_label(body.page_from, body.page_to)}")
    if read_ai:
        # Hanya bukti baru yang dibaca AI; data bukti lain tetap
        set_status(db, doc, DocStatus.PROCESSING, f"AI membaca bukti tambahan dari {user.full_name}")
        db.commit()
        background.add_task(process_document, doc.id, request.app.state.extractor, True)
        return _detail(db, doc)
    return _after_files_changed(db, doc)


@router.delete("/{document_id}/files/{position}", response_model=DocumentDetail)
def delete_file(document_id: uuid.UUID, position: int, user: User = Depends(uploader_roles),
                db: Session = Depends(get_db)):
    """Hapus satu bukti (mis. halaman yang keliru terbaca sebagai invoice). Minimal 1 bukti tersisa."""
    doc = _editable_files(db, user, document_id)
    part = _file(doc, position)
    if len(doc.files) <= 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Voucher minimal berisi 1 bukti.")
    key, name = invoice_split.upload_key(part), part.original_filename
    audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                         field=f"Bukti {position} ({name})", old_value=_fmt((part.data or {}).get("invoice_no")) or name,
                         new_value="Dihapus")
    rest = [f for f in doc.files if f is not part]
    db.delete(part)
    db.flush()
    invoice_split.renumber(db, doc, rest)
    db.expire(doc, ["files"])
    _rekey_checks(doc, invoice_split.rename_group(doc, key), removed=name)
    return _after_files_changed(db, doc)


@router.put("/{document_id}/files/{position}/tax", response_model=DocumentDetail)
def set_file_tax(document_id: uuid.UUID, position: int, body: TaxChoice,
                 user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """PIC memilih potongan pajak untuk SATU invoice (Tahap 4). Tarif diambil dari tabel tarif sesuai NPWP,
    disalin ke data invoice; voucher membayar nilai bersih. Perubahan dicatat nilai awal → nilai baru."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Pajak hanya bisa diubah saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    table = tax_service.rates(db)
    active = {code for code, r in table.items() if r.is_active}
    rate = table.get(body.code)
    if body.mode == "invoice" and (rate is None or not rate.is_active):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Jenis pajak tidak dikenal.")
    unknown = {c.pph for c in body.lines if c.pph and c.pph not in active}
    if body.mode == "line" and unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Jenis pajak tidak dikenal: {', '.join(sorted(unknown))}.")
    part = _file(doc, position)
    data = dict(file_data(doc, part))
    lines = [dict(li) for li in data.get("line_items") or []]
    if any(c.index >= len(lines) for c in body.lines):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Baris rincian tidak ditemukan. Muat ulang halaman.")
    for c in body.lines:
        li = lines[c.index]
        if c.kind is not None:
            li["kind"] = c.kind
        if c.vat is not None:
            li["vat"] = c.vat
        if body.mode == "line":
            if c.pph and c.pph != tax_service.NONE:
                li["pph"] = c.pph
            else:
                li.pop("pph", None)
    data["line_items"] = lines
    old = data.get("tax")
    vat = body.vat.model_dump(mode="json") if body.vat else (old or {}).get("vat")
    if not body.calc:
        if body.mode != "invoice":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Hitung manual hanya untuk satu jenis PPh per invoice.")
        # Hitung otomatis dimatikan: DPP, PPN, dan potongan diisi PIC
        vat = {**(vat or {}), "amount": str(body.vat_amount or 0)}
    new = tax_service.build(rate, body.npwp, body.base, body.base is None, data, mode=body.mode, table=table, vat=vat,
                            calc=body.calc, manual_amount=body.amount)
    old_lines = (file_data(doc, part).get("line_items") or [])
    skip = ("source",)
    if old and {k: v for k, v in old.items() if k not in skip} == {k: v for k, v in new.items() if k not in skip} \
            and old_lines == lines:
        return _detail(db, doc)
    audit_service.record(db, user, "FIXED_BY_PIC", document_id=doc.id, client_id=doc.client_id,
                         field=f"Bukti {position} ({part.original_filename}).pajak",
                         old_value=tax_service.label(old) if old else None, new_value=tax_service.label(new))
    part.data = {**data, "tax": new}
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/files/{position}/tax/ai-suggest", response_model=DocumentDetail)
def suggest_line_taxes_ai(document_id: uuid.UUID, position: int, request: Request,
                          user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """Rekomendasi PPh per baris dari AI, atas permintaan PIC. Hanya saran: disimpan sebagai saran dan baru
    berlaku setelah PIC menerapkan pajak. Bila AI tidak tersedia, saran berbasis aturan tetap dipakai."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Pajak hanya bisa diubah saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    part = _file(doc, position)
    data = dict(file_data(doc, part))
    if not tax_service.item_lines(data):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Belum ada baris rincian untuk dianalisis.")
    valid = {code for code, r in tax_service.rates(db).items() if r.is_active}
    try:
        items = tax_service.suggest_lines_ai(request.app.state.bedrock, data, valid)
    except (BedrockError, AttributeError) as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Layanan AI sedang tidak tersedia. Saran berbasis aturan tetap dapat Anda gunakan, "
                            "atau pilih jenis PPh secara manual.") from e
    part.data = {**data, "line_suggestions_ai": {"key": tax_service.descriptions_key(data), "items": items}}
    audit_service.record(db, user, "TAX_AI_SUGGESTED", document_id=doc.id, client_id=doc.client_id,
                         note=f"Rekomendasi AI PPh per baris untuk bukti {position}")
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/submit", response_model=DocumentDetail)
def submit_to_review(document_id: uuid.UUID, user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """PIC mengirim draf ke Finance Reviewer (feedback owner). Ditolak bila masih ada kendala wajib;
    kendala yang diputuskan reviewer (kemungkinan duplikat, struk, perlu pemeriksaan manual) ikut terkirim."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Hanya draf yang bisa dikirim ke reviewer (sekarang {doc.status.value}).")
    if doc.extraction is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Data invoice belum ada. Lengkapi data per invoice dulu.")
    open_issues = list(db.scalars(select(ValidationIssue).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False))))
    blocking = sorted({i.code.value for i in open_issues if i.code in BLOCKING})
    if blocking:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Masih ada kendala yang harus dilengkapi dulu: {', '.join(blocking)}.")
    # Peringatan vendor/rekening berbeda hanya pengingat (Tahap 14), tidak menahan pengiriman
    if doc.extraction_mode == TOTAL_ONLY:
        # Mode total saja: setiap invoice dicetak satu baris, jadi uraian transaksinya wajib ada
        no_desc = [str(f.position) for f in doc.files if not (file_data(doc, f).get("description") or "").strip()]
        if no_desc:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Isi uraian transaksi dulu untuk bukti {', '.join(no_desc)}.")
    # PIC wajib memilih pajak sendiri untuk setiap bukti (termasuk "Tanpa potongan"); AI hanya menyarankan
    no_tax = [str(f.position) for f in doc.files if not file_data(doc, f).get("tax")]
    if no_tax:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Pilih pajak dulu untuk bukti {', '.join(no_tax)} (boleh \"Tanpa potongan\").")
    for issue in open_issues:
        if issue.code == IssueCode.RETURNED_BY_REVIEWER:
            issue.resolved = True  # catatan pengembalian sudah ditindaklanjuti PIC
    audit_service.record(db, user, "SUBMITTED_TO_REVIEW", document_id=doc.id, client_id=doc.client_id,
                         status_before=doc.status.value, status_after=DocStatus.READY_FOR_REVIEW.value)
    send_to_review(db, doc, "Dikirim PIC ke Finance Reviewer")
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/acknowledge", response_model=DocumentDetail)
def acknowledge_warning(document_id: uuid.UUID, body: AcknowledgeRequest, user: User = Depends(uploader_roles),
                        db: Session = Depends(get_db)):
    """PIC mengonfirmasi peringatan beserta alasannya (mis. beberapa vendor/rekening dalam satu voucher).
    Tercatat di riwayat dan tampil untuk reviewer, tidak dicetak di voucher. Konfirmasi gugur bila daftar
    vendor/rekening berubah."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Peringatan hanya bisa dikonfirmasi saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    if body.code not in ACKNOWLEDGEABLE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Kendala ini tidak bisa dikonfirmasi; perbaiki datanya.")
    open_codes = set(db.scalars(select(ValidationIssue.code).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False))))
    if body.code not in open_codes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Peringatan ini sudah tidak ada atau sudah dikonfirmasi.")
    ex = doc.extraction
    raw = dict(ex.raw_json or {}) if isinstance(ex.raw_json, dict) else {}
    reason = body.reason.strip()
    raw["acknowledged"] = {**(raw.get("acknowledged") or {}), body.code.value: {
        "reason": reason, "by": user.full_name, "at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": payee_fingerprint(ex)}}
    ex.raw_json = raw
    audit_service.record(db, user, "WARNING_ACKNOWLEDGED", document_id=doc.id, client_id=doc.client_id,
                         field=body.code.value, note=reason)
    issues = run_verification(db, doc)
    settle_status(db, doc, issues, "Peringatan dikonfirmasi PIC")
    db.commit()
    return _detail(db, doc)


@router.get("/{document_id}/voucher-preview", response_class=Response)
def voucher_preview(document_id: uuid.UUID, attachments: bool = True, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Simulasi Voucher Pengeluaran sebelum disetujui: bertanda SIMULASI, tanpa nomor voucher, lengkap dengan lampiran
    bukti (`attachments=false`: halaman voucher saja, untuk pratinjau cepat). Tanda tangan "Diajukan oleh" yang
    tersimpan di pengajuan ikut tampil; tanda tangan pemberi persetujuan baru dibubuhkan saat voucher terbit."""
    doc = _get_document(db, user, document_id)
    if doc.extraction is None or doc.status in (DocStatus.CANCELLED, DocStatus.QUEUED, DocStatus.PROCESSING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Simulasi tersedia setelah AI selesai membaca invoice.")
    now = datetime.now(timezone.utc)
    signers = doc.signers or []
    signatures = [img if s.get("kind") == "PENGAJU" and s.get("signature") is True else None
                  for s, img in zip(signers, signature_service.for_signers(db, signers, doc))]
    pdf = voucher_service.render_voucher(doc, "SIMULASI", user, now, signatures, simulation=True)
    if not attachments:
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="simulasi-{doc.request_id}.pdf"'})
    try:
        pdf = voucher_attachments.append_attachments(pdf, doc, "SIMULASI")
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File bukti tidak ditemukan di penyimpanan.")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="simulasi-{doc.request_id}.pdf"'})


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
    user: User = Depends(require_roles(Role.PIC_KLIEN, Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER)),
    db: Session = Depends(get_db),
):
    """Proses ulang dokumen yang gagal dibaca AI (FR-2.5), oleh PIC dari draf atau oleh Finance Reviewer.
    Pada draf isi manual (AI sempat bermasalah), hanya invoice yang belum terbaca AI yang dibaca ulang."""
    doc = _get_document(db, user, document_id)
    failed = db.scalar(select(ValidationIssue.id).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False),
        ValidationIssue.code == IssueCode.EXTRACTION_FAILED))
    if Role.FINANCE_REVIEWER not in user.roles:
        ensure_submit_access(db, user, doc.client_id)
    manual = doc.status in EDITABLE and manual_entry(doc.extraction) is not None
    if not (doc.status == DocStatus.EXCEPTION and failed is not None) and not manual:
        raise HTTPException(status.HTTP_409_CONFLICT, "Proses ulang hanya untuk dokumen yang gagal dibaca AI.")
    if not settings.ai_extraction_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Pembacaan otomatis oleh AI sedang dimatikan. Isi data invoice secara manual.")
    audit_service.record(db, user, "REPROCESS_REQUESTED", document_id=doc.id, client_id=doc.client_id)
    set_status(db, doc, DocStatus.PROCESSING, f"Diproses ulang oleh {user.full_name}")
    db.commit()

    background.add_task(process_document, doc.id, request.app.state.extractor, manual)
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
    # Kotak "Diajukan oleh" tetap kecuali sumber/profilnya diubah; kotak "Disetujui oleh" diganti sesuai pilihan
    pengaju = [s for s in doc.signers or [] if s["kind"] == "PENGAJU"]
    current = pengaju[0] if pengaju else {}
    source = body.submitter_source
    if source is None and body.submitter_name is not None and not body.submitter_name.strip():
        source = signer_service.PIC  # format lama: nama dikosongkan = kembali ke PIC pengaju
    elif source is None and any(v is not None for v in (body.submitter_name, body.submitter_position,
                                                         body.submitter_company)):
        source = signer_service.MANUAL
    if source == signer_service.PIC:
        # Profil dan tanda tangan disalin dari akun PIC Klien saat ini
        pic = db.get(User, doc.on_behalf_of or doc.uploaded_by)
        profile = signer_service.default_profile(pic, doc.client)
        doc.submitter_signature_png = pic.signature_png
        pengaju = [signer_service.pengaju_profile(profile["name"], profile["position"], profile["company"],
                                                  pic.signature_png is not None, signer_service.PIC)]
    elif source == signer_service.MANUAL:
        legacy = "company" not in current  # salinan lama: jabatan berisi "PIC Klien, <perusahaan>" atau nama perusahaan
        was_pic = current.get("source") == signer_service.PIC
        name = (body.submitter_name or "").strip() or ("" if was_pic else current.get("name", ""))
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Isi nama pengaju di bagian \"Diajukan oleh\".")
        position = (body.submitter_position.strip() if body.submitter_position is not None
                    else "" if was_pic else "PIC Klien" if legacy else current.get("position"))
        company = ((body.submitter_company or "").strip()
                   or ("" if legacy or was_pic else current.get("company")) or doc.client.name)
        if was_pic:
            doc.submitter_signature_png = None  # tanda tangan PIC tidak dipakai untuk nama lain
        pengaju = [signer_service.pengaju_profile(name, position, company, doc.submitter_signature_png is not None)]
    new = pengaju + signer_service.resolve(db, doc.client_id, body.signatory_ids, None)
    describe = lambda items: "; ".join(f"{s['name']} ({s['position']})" for s in items) or "-"  # noqa: E731
    audit_service.record(db, user, "SIGNERS_CHANGED", document_id=doc.id, client_id=doc.client_id,
                         field="signers", old_value=describe(doc.signers or []), new_value=describe(new))
    doc.signers = new
    db.commit()
    return _detail(db, doc)


def _set_pengaju_signature(db: Session, doc: Document, signed: bool) -> None:
    """Tandai kotak "Diajukan oleh" memakai (atau tidak lagi memakai) spesimen yang tersimpan di dokumen."""
    signers = []
    for s in doc.signers or []:
        if s["kind"] == "PENGAJU":
            if "company" not in s:  # salinan lama: diubah ke format profil pengaju
                s = signer_service.pengaju_profile(s["name"], "PIC Klien", doc.client.name, signed)
            s = {**{k: v for k, v in s.items() if k != "user_id"}, "signature": signed}
        signers.append(s)
    if not any(s["kind"] == "PENGAJU" for s in signers):
        pic = db.get(User, doc.on_behalf_of or doc.uploaded_by)
        signers.insert(0, signer_service.pengaju_profile(pic.full_name, "PIC Klien", doc.client.name, signed))
    doc.signers = signers


def _signature_editable(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status in (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT, DocStatus.CANCELLED):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Voucher sudah terbit atau pengajuan dibatalkan; tanda tangan tidak bisa diubah.")
    if any(s["kind"] == "PENGAJU" and s.get("source") == signer_service.PIC for s in doc.signers or []):
        raise HTTPException(status.HTTP_409_CONFLICT, "\"Diajukan oleh\" memakai profil PIC Klien; tanda tangannya "
                            "diatur di halaman Akun. Pilih \"Diisi manual\" untuk memakai tanda tangan lain.")
    return doc


@router.get("/{document_id}/submitter-signature", response_class=Response)
def get_submitter_signature(document_id: uuid.UUID, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Spesimen tanda tangan "Diajukan oleh" yang tersimpan di pengajuan ini (PNG transparan)."""
    doc = _get_document(db, user, document_id)
    if doc.submitter_signature_png is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Belum ada tanda tangan pengaju.")
    return Response(doc.submitter_signature_png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.put("/{document_id}/submitter-signature", response_model=DocumentDetail)
def set_submitter_signature(document_id: uuid.UUID, body: SignatureIn, user: User = Depends(uploader_roles),
                            db: Session = Depends(get_db)):
    """Unggah/ganti tanda tangan "Diajukan oleh" mode manual (PNG/JPG/WEBP) selama voucher belum terbit. Hanya untuk
    pengajuan ini; tanda tangan mode PIC diatur di halaman Akun."""
    doc = _signature_editable(db, user, document_id)
    doc.submitter_signature_png = signature_service.normalize(body.image)
    _set_pengaju_signature(db, doc, True)
    audit_service.record(db, user, "SIGNERS_CHANGED", document_id=doc.id, client_id=doc.client_id,
                         field="signature", new_value="Tanda tangan pengaju diunggah")
    db.commit()
    return _detail(db, doc)


@router.delete("/{document_id}/submitter-signature", response_model=DocumentDetail)
def delete_submitter_signature(document_id: uuid.UUID, user: User = Depends(uploader_roles),
                               db: Session = Depends(get_db)):
    """Hapus tanda tangan "Diajukan oleh" dari pengajuan ini; kotaknya dicetak kosong untuk tanda tangan basah."""
    doc = _signature_editable(db, user, document_id)
    if doc.submitter_signature_png is not None:
        doc.submitter_signature_png = None
        _set_pengaju_signature(db, doc, False)
        audit_service.record(db, user, "SIGNERS_CHANGED", document_id=doc.id, client_id=doc.client_id,
                             field="signature", new_value="Tanda tangan pengaju dihapus")
        db.commit()
    return _detail(db, doc)


@router.put("/{document_id}/options", response_model=DocumentDetail)
def set_options(document_id: uuid.UUID, body: OptionsUpdate, request: Request, background: BackgroundTasks,
                user: User = Depends(uploader_roles), db: Session = Depends(get_db)):
    """Ganti mode baca AI atau fitur rekening dari halaman detail (Tahap 14), selama Draf/Ada kendala.
    - TOTAL_ONLY → ITEMIZED: AI membaca rincian barang/jasa; data kepala invoice, uraian, dan pajak tetap.
    - ITEMIZED → TOTAL_ONLY: rincian disembunyikan dari voucher; total invoice tetap. PPh per baris dipilih ulang.
    - Rekening: dicantumkan (diisi, dicek ke data vendor, dicetak) atau tidak. Data rekening lama tetap tersimpan."""
    doc = _get_document(db, user, document_id)
    ensure_submit_access(db, user, doc.client_id)
    if doc.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Pengaturan hanya bisa diubah saat Draf atau Ada kendala (sekarang {doc.status.value}).")
    changed = reread = False
    if body.include_account is not None and body.include_account != bool(doc.include_account):
        audit_service.record(db, user, "OPTION_CHANGED", document_id=doc.id, client_id=doc.client_id,
                             field="include_account", old_value=str(bool(doc.include_account)).lower(),
                             new_value=str(body.include_account).lower())
        doc.include_account = body.include_account
        changed = True
    if body.extraction_mode and body.extraction_mode != (doc.extraction_mode or ITEMIZED):
        audit_service.record(db, user, "EXTRACTION_MODE_CHANGED", document_id=doc.id, client_id=doc.client_id,
                             field="extraction_mode", old_value=doc.extraction_mode, new_value=body.extraction_mode)
        doc.extraction_mode = body.extraction_mode
        if body.extraction_mode == TOTAL_ONLY:
            for f in doc.files:
                data = {k: v for k, v in file_data(doc, f).items() if k != "line_suggestions_ai"}
                data["line_items"] = []
                data["description"] = (data.get("description") or "").strip() or default_description(data)
                tax = data.get("tax")
                if tax and tax.get("mode") == "line":
                    data.pop("tax")  # PPh per baris tidak berlaku tanpa rincian: PIC memilih ulang
                elif tax:
                    data["tax"] = tax_service.recompute(tax, data)
                f.data = data
            changed = True
        else:
            reread = True
    if reread:
        # AI dimatikan/gagal: bukti ditandai untuk diisi rinciannya secara manual oleh PIC
        set_status(db, doc, DocStatus.PROCESSING, "Mode diganti ke rincian; AI membaca rincian barang/jasa")
        db.commit()
        background.add_task(process_document, doc.id, request.app.state.extractor, False, True)
        return _detail(db, doc)
    if changed:
        rebuild_from_files(db, doc)
        issues = run_verification(db, doc)
        settle_status(db, doc, issues, "Pengaturan pengajuan diubah PIC")
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
