"""Dashboard antrean dan pengalihan reviewer oleh Service Lead (F6, Layar 01)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import settings
from app.db import get_db
from app.models import DocStatus, Role, User
from app.routers.documents import _detail, _get_document
from app.schemas.schemas import DashboardSummary, DocumentDetail, ReassignRequest, ReviewerLoadOut
from app.services import audit_service
from app.services.access_rules import accessible_client_ids
from app.services.document_processing import uploader_ids
from app.services.queue_service import summarize

router = APIRouter(tags=["Dashboard Antrean"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(user: User = Depends(require_roles(Role.SERVICE_LEAD, Role.FINANCE_REVIEWER)),
                      db: Session = Depends(get_db)):
    """Jumlah dokumen per status, dokumen bermasalah, tenggat, dan beban per reviewer (FR-6.1)."""
    s = summarize(db, accessible_client_ids(db, user))
    return DashboardSummary(
        counts=s.counts, problem=s.problem, due_soon=s.due_soon, overdue=s.overdue,
        reviewers=[ReviewerLoadOut.model_validate(r) for r in s.reviewers],
        overload_threshold=settings.reviewer_overload_threshold, due_soon_days=settings.due_soon_days,
    )


@router.post("/documents/{document_id}/reassign", response_model=DocumentDetail)
def reassign(document_id: uuid.UUID, body: ReassignRequest,
             user: User = Depends(require_roles(Role.SERVICE_LEAD)), db: Session = Depends(get_db)):
    """Service Lead mengalihkan dokumen ke reviewer lain untuk pemerataan beban (FR-6.3).
    Status dokumen tidak berubah, dan pengalihan dicatat di jejak audit."""
    doc = _get_document(db, user, document_id)
    if doc.status != DocStatus.READY_FOR_REVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Hanya dokumen READY_FOR_REVIEW yang bisa dialihkan (sekarang {doc.status.value}).")
    target = db.get(User, body.reviewer_id)
    if (target is None or not target.is_active or Role.FINANCE_REVIEWER not in target.roles
            or doc.client_id not in accessible_client_ids(db, target)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Pilih Finance Reviewer aktif yang ditugaskan untuk klien dokumen ini.")
    if target.id in uploader_ids(doc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Reviewer ini adalah pengunggah dokumen (Segregation of Duties). Pilih reviewer lain.")
    if target.id == doc.assigned_reviewer_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dokumen sudah ditugaskan ke reviewer ini.")

    old = db.get(User, doc.assigned_reviewer_id) if doc.assigned_reviewer_id else None
    doc.assigned_reviewer_id = target.id
    audit_service.record(db, user, "REVIEWER_REASSIGNED", document_id=doc.id, client_id=doc.client_id,
                         field="assigned_reviewer", old_value=old.full_name if old else "belum ada",
                         new_value=target.full_name,
                         note=(body.reason or "").strip() or "Pemerataan beban oleh Service Lead")
    db.commit()
    return _detail(db, doc)
