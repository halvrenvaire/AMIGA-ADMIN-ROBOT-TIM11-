"""Dashboard antrean dan pengalihan reviewer oleh Service Lead (F6, Layar 01)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.config import settings
from app.db import get_db
from app.models import DocStatus, Role, User
from app.routers.documents import _detail, _get_document
from app.schemas.schemas import (
    DashboardMetrics, DashboardSummary, DocumentDetail, ReassignRequest, ReviewerLoadOut, TrendPoint,
)
from app.services import audit_service
from app.services import access_rules
from app.services.access_rules import accessible_client_ids
from app.services.document_processing import submitter_ids
from app.services import metrics_service
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


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
def dashboard_metrics(
    days: int = Query(30, ge=7, le=365, description="Panjang periode (hari)"),
    client_id: uuid.UUID | None = None,
    user: User = Depends(require_roles(Role.SERVICE_LEAD, Role.FINANCE_REVIEWER, Role.PIC_KLIEN, Role.INTAKE_SUPPORT)),
    db: Session = Depends(get_db),
):
    """Metrik utama: status, tren harian, kecepatan proses, kualitas, dan nilai pembayaran,
    dibandingkan dengan periode sebelumnya yang sama panjang."""
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    m = metrics_service.compute(db, ids, days)
    return DashboardMetrics(**{k: v for k, v in vars(m).items() if k != "trend"},
                            trend=[TrendPoint(**t) for t in m.trend])


@router.get("/documents/{document_id}/reviewer-options", response_model=list[ReviewerLoadOut])
def reviewer_options(document_id: uuid.UUID, user: User = Depends(require_roles(Role.SERVICE_LEAD)),
                     db: Session = Depends(get_db)):
    """Reviewer yang sah untuk dokumen ini: Finance Reviewer aktif klien dokumen, bukan pengunggah
    (SoD) dan bukan reviewer saat ini, beserta bebannya."""
    doc = _get_document(db, user, document_id)
    excluded = submitter_ids(db, doc) | ({doc.assigned_reviewer_id} if doc.assigned_reviewer_id else set())
    # Reviewer menangani semua perusahaan: beban dihitung dari seluruh antrean
    return [ReviewerLoadOut.model_validate(r) for r in summarize(db, access_rules.all_client_ids(db)).reviewers
            if r.id not in excluded]


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
    if target is None or not target.is_active or Role.FINANCE_REVIEWER not in target.roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pilih Finance Reviewer yang aktif.")
    if target.id in submitter_ids(db, doc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Reviewer ini adalah pihak pengaju dokumen (Segregation of Duties). Pilih reviewer lain.")
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
