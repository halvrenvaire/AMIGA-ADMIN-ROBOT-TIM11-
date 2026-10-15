"""Peninjauan Finance Reviewer, voucher, dan riwayat (F4, F5, F8; Layar 03, 04, 05).

Aturan SoD (FR-4.4): pengunggah dokumen, termasuk PIC yang diwakili, tidak boleh menyetujui.
Sistem menolak persetujuan itu dan mengalihkan dokumen otomatis ke reviewer lain.
"""
import time
import uuid
from decimal import InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models import AuditLog, DocStatus, Document, IssueCode, LineItem, Role, User, ValidationIssue
from app.routers.documents import _detail, _get_document
from app.schemas.schemas import AuditItem, DocumentDetail, ReasonRequest, ReviewUpdate
from app.services import audit_service, storage
from app.services.access_rules import can_access_client
from app.services.document_processing import (
    PIC_FIELDS, parse_pic_value, run_verification, send_to_review, set_status, submitter_ids, uploader_ids,
)
from app.services.reviewer_assignment import pick_reviewer
from app.services.voucher_service import create_voucher

router = APIRouter(prefix="/documents", tags=["Peninjauan & Voucher"])

reviewer_only = require_roles(Role.FINANCE_REVIEWER)
LINE_ATTRS = ("description", "qty", "unit_price", "subtotal")


def _require_status(doc: Document, *allowed: DocStatus) -> None:
    if doc.status not in allowed:
        names = " atau ".join(s.value for s in allowed)
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Aksi ini hanya untuk dokumen berstatus {names} (sekarang {doc.status.value}).")


def _open_issues(db: Session, doc: Document) -> list[ValidationIssue]:
    return list(db.scalars(select(ValidationIssue).where(
        ValidationIssue.document_id == doc.id, ValidationIssue.resolved.is_(False))))


def _text(value) -> str | None:
    return None if value is None else str(value)


def _name(db: Session, user_id: uuid.UUID | None) -> str:
    user = db.get(User, user_id) if user_id else None
    return user.full_name if user else "belum ada"


@router.put("/{document_id}/extraction", response_model=DocumentDetail)
def correct_extraction(document_id: uuid.UUID, body: ReviewUpdate, user: User = Depends(reviewer_only),
                       db: Session = Depends(get_db)):
    """Simpan & verifikasi ulang (FR-4.2). Setiap perubahan dicatat nilai awal → nilai baru (FR-8.2).
    Field yang gagal verifikasi muncul sebagai kendala dan menahan persetujuan."""
    doc = _get_document(db, user, document_id)
    _require_status(doc, DocStatus.READY_FOR_REVIEW)
    if doc.extraction is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokumen belum punya data ekstraksi.")
    unknown = set(body.fields) - set(PIC_FIELDS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Field tidak bisa dikoreksi: {', '.join(sorted(unknown))}.")

    ex = doc.extraction
    changes: list[tuple[str, str | None, str | None]] = []
    for name, raw in body.fields.items():
        try:
            new = parse_pic_value(name, raw) if raw is not None and raw.strip() else None
        except (ValueError, InvalidOperation):
            hint = "format YYYY-MM-DD" if name == "invoice_date" else "angka tanpa titik ribuan, mis. 1250000"
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Nilai {name} tidak valid ({hint}).")
        old = getattr(ex, name)
        if old != new:
            setattr(ex, name, new)
            changes.append((name, _text(old), _text(new)))

    if body.line_items is not None:
        old_lines = {line.position: line for line in ex.line_items}
        new_lines = [LineItem(position=i, **item.model_dump()) for i, item in enumerate(body.line_items, start=1)]
        for line in new_lines:
            before = old_lines.get(line.position)
            for attr in LINE_ATTRS:
                old, new = (getattr(before, attr) if before else None), getattr(line, attr)
                if old != new:
                    changes.append((f"line_items[{line.position}].{attr}", _text(old), _text(new)))
        for position in sorted(set(old_lines) - {line.position for line in new_lines}):
            changes.append((f"line_items[{position}]", old_lines[position].description, "(dihapus)"))
        ex.line_items = new_lines

    for field, old, new in changes:
        audit_service.record(db, user, "CORRECTED_BY_REVIEWER", document_id=doc.id, client_id=doc.client_id,
                             field=field, old_value=old, new_value=new)
    db.flush()
    issues = run_verification(db, doc)
    if issues:
        audit_service.record(db, user, "REVERIFIED", document_id=doc.id, client_id=doc.client_id,
                             note="Kendala: " + ", ".join(sorted({i.code.value for i in issues})))
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/approve", response_model=DocumentDetail)
def approve(document_id: uuid.UUID, user: User = Depends(reviewer_only), db: Session = Depends(get_db)):
    """Setujui (FR-4.3–4.5). Sistem mengecek SoD; bila lolos → AMIGA_REVIEWED dan voucher dibuat."""
    doc = _get_document(db, user, document_id)
    _require_status(doc, DocStatus.READY_FOR_REVIEW)
    open_issues = _open_issues(db, doc)
    if open_issues:
        codes = ", ".join(sorted({i.code.value for i in open_issues}))
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Masih ada kendala ({codes}). Koreksi datanya atau kembalikan ke PIC.")

    submitters = submitter_ids(db, doc)
    if user.id in submitters:
        old_reviewer = doc.assigned_reviewer_id
        new_reviewer = pick_reviewer(db, doc.client_id, submitters | {user.id})
        doc.assigned_reviewer_id = new_reviewer.id if new_reviewer else None
        audit_service.record(db, user, "SOD_REJECTED", document_id=doc.id, client_id=doc.client_id,
                             status_before=doc.status.value, status_after=doc.status.value,
                             note="Penyetuju adalah pihak pengaju dokumen (Segregation of Duties)")
        audit_service.record(db, None, "REVIEWER_REASSIGNED", document_id=doc.id, client_id=doc.client_id,
                             field="assigned_reviewer", old_value=_name(db, old_reviewer),
                             new_value=_name(db, doc.assigned_reviewer_id), note="Otomatis karena SoD")
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Persetujuan ditolak: Anda adalah pihak pengaju dokumen ini (mengunggah atau memperbaiki "
                            "datanya), sesuai Segregation of Duties. "
                            f"Dokumen otomatis dialihkan ke {_name(db, doc.assigned_reviewer_id)}.")

    started = time.monotonic()
    set_status(db, doc, DocStatus.AMIGA_REVIEWED, "Disetujui Finance Reviewer")
    audit_service.record(db, user, "APPROVED", document_id=doc.id, client_id=doc.client_id,
                         status_before=DocStatus.READY_FOR_REVIEW.value, status_after=DocStatus.AMIGA_REVIEWED.value)
    try:
        voucher = create_voucher(db, doc, user)
    except storage.StorageError:
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Voucher gagal disimpan. Coba setujui lagi.")
    audit_service.record(db, None, "VOUCHER_CREATED", document_id=doc.id, client_id=doc.client_id,
                         new_value=voucher.voucher_no,
                         note=f"Dibuat dalam {int((time.monotonic() - started) * 1000)} ms")
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/return", response_model=DocumentDetail)
def return_to_pic(document_id: uuid.UUID, body: ReasonRequest, user: User = Depends(reviewer_only),
                  db: Session = Depends(get_db)):
    """Kembalikan ke PIC dengan alasan wajib (FR-4.3) → EXCEPTION, kode RETURNED_BY_REVIEWER."""
    doc = _get_document(db, user, document_id)
    _require_status(doc, DocStatus.READY_FOR_REVIEW)
    reason = body.reason.strip()
    db.add(ValidationIssue(document_id=doc.id, code=IssueCode.RETURNED_BY_REVIEWER,
                           message=f"Dikembalikan oleh Finance Reviewer: {reason}"))
    audit_service.record(db, user, "RETURNED_TO_PIC", document_id=doc.id, client_id=doc.client_id,
                         status_before=doc.status.value, status_after=DocStatus.EXCEPTION.value, note=reason)
    set_status(db, doc, DocStatus.EXCEPTION, "Dikembalikan ke PIC")
    db.commit()
    return _detail(db, doc)


@router.post("/{document_id}/dismiss-duplicate", response_model=DocumentDetail)
def dismiss_duplicate(document_id: uuid.UUID, body: ReasonRequest, user: User = Depends(reviewer_only),
                      db: Session = Depends(get_db)):
    """Tandai bukan duplikat dengan alasan wajib, lalu lanjut ke peninjauan. Hanya bila kendala
    yang tersisa POSSIBLE_DUPLICATE, dan tidak oleh pengunggah dokumen."""
    doc = _get_document(db, user, document_id)
    _require_status(doc, DocStatus.EXCEPTION)
    open_issues = _open_issues(db, doc)
    if not open_issues or any(i.code != IssueCode.POSSIBLE_DUPLICATE for i in open_issues):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Hanya untuk dokumen yang kendalanya tinggal POSSIBLE_DUPLICATE.")
    if user.id in submitter_ids(db, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Pihak pengaju (pengunggah atau yang memperbaiki data) tidak boleh menandai "
                            "dokumen ini bukan duplikat.")
    for issue in open_issues:
        issue.resolved = True
    audit_service.record(db, user, "DUPLICATE_DISMISSED", document_id=doc.id, client_id=doc.client_id,
                         note=body.reason.strip())
    send_to_review(db, doc, "Ditandai bukan duplikat")
    db.commit()
    return _detail(db, doc)


@router.get("/{document_id}/voucher", response_class=Response)
def get_voucher(
    document_id: uuid.UUID,
    download: bool = Query(False, description="true = unduh (PIC/Intake: status jadi SENT_TO_CLIENT)"),
    user: User = Depends(require_roles(Role.PIC_KLIEN, Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER)),
    db: Session = Depends(get_db),
):
    """Pratinjau atau unduh voucher PDF (Layar 04). Unduhan oleh PIC Klien, atau Intake Support
    yang mengunggah dokumen itu, mengubah status menjadi SENT_TO_CLIENT (FR-5.3)."""
    doc = _get_document(db, user, document_id)
    _require_status(doc, DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT)
    try:
        data = storage.load(doc.voucher.file_key)
    except storage.StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File voucher tidak ditemukan di penyimpanan.")

    if download:
        on_behalf = doc.on_behalf_of if Role.PIC_KLIEN not in user.roles else None
        audit_service.record(db, user, "VOUCHER_DOWNLOADED", document_id=doc.id, client_id=doc.client_id,
                             on_behalf_of=on_behalf, new_value=doc.voucher.voucher_no)
        # Serah terima hanya oleh pihak klien: PIC Klien, atau Intake Support yang mengunggahnya.
        # Pengguna peran ganda yang mengunduh sebagai reviewer tidak dihitung.
        hands_over = Role.PIC_KLIEN in user.roles or (
            Role.INTAKE_SUPPORT in user.roles and user.id in uploader_ids(doc))
        if hands_over and doc.status == DocStatus.AMIGA_REVIEWED:
            set_status(db, doc, DocStatus.SENT_TO_CLIENT, "Voucher diunduh PIC Klien")
        db.commit()

    filename = doc.voucher.voucher_no.replace("/", "-") + ".pdf"
    disposition = "attachment" if download else "inline"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


@router.get("/{document_id}/history", response_model=list[AuditItem])
def history(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Riwayat & jejak audit satu dokumen, urut dari yang paling lama (Layar 05)."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumen tidak ditemukan.")
    # System Admin boleh melihat jejak audit tanpa penugasan klien (PRD bagian 2)
    if Role.SYSTEM_ADMIN not in user.roles and not can_access_client(db, user, doc.client_id):
        _get_document(db, user, document_id)  # menolak dan mencatat ACCESS_DENIED
    return db.scalars(select(AuditLog).where(AuditLog.document_id == doc.id).order_by(AuditLog.id)).all()
