"""Pemilihan Finance Reviewer: yang antrean READY_FOR_REVIEW-nya paling sedikit.

Dipakai saat dokumen lolos verifikasi, dan nanti saat pengalihan otomatis karena SoD (FR-4.4).
"""
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import DocStatus, Document, Role, User, UserClientAssignment, UserRole


def pick_reviewer(db: Session, client_id: uuid.UUID, exclude: set[uuid.UUID]) -> User | None:
    pending = (
        select(Document.assigned_reviewer_id, func.count().label("n"))
        .where(Document.status == DocStatus.READY_FOR_REVIEW)
        .group_by(Document.assigned_reviewer_id)
        .subquery()
    )
    query = (
        select(User)
        .join(UserRole, (UserRole.user_id == User.id) & (UserRole.role == Role.FINANCE_REVIEWER))
        .join(UserClientAssignment, UserClientAssignment.user_id == User.id)
        .outerjoin(pending, pending.c.assigned_reviewer_id == User.id)
        .where(
            User.is_active.is_(True),
            UserClientAssignment.client_id == client_id,
            or_(UserClientAssignment.valid_until.is_(None), UserClientAssignment.valid_until >= date.today()),
        )
        .order_by(func.coalesce(pending.c.n, 0), User.email)
    )
    if exclude:
        query = query.where(User.id.not_in(exclude))
    return db.scalars(query.limit(1)).first()
