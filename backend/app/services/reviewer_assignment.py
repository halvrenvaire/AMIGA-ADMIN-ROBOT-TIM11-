"""Pembagian dokumen ke Finance Reviewer.

Semua Finance Reviewer aktif menangani pengajuan dari perusahaan mana pun. Dokumen diberikan ke
reviewer dengan jumlah kasus paling sedikit, sehingga kasus terbagi rata (mis. 20 dokumen untuk 3
reviewer → 7, 7, 6); bila beberapa reviewer seri, sistem memilih secara acak. Pihak pengaju
dokumen tidak pernah dipilih (Segregation of Duties, FR-4.4).
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, Role, User, UserRole


def pick_reviewer(db: Session, client_id: uuid.UUID, exclude: set[uuid.UUID]) -> User | None:
    cases = (
        select(Document.assigned_reviewer_id, func.count().label("n"))
        .where(Document.assigned_reviewer_id.is_not(None))
        .group_by(Document.assigned_reviewer_id)
        .subquery()
    )
    query = (
        select(User)
        .join(UserRole, (UserRole.user_id == User.id) & (UserRole.role == Role.FINANCE_REVIEWER))
        .outerjoin(cases, cases.c.assigned_reviewer_id == User.id)
        .where(User.is_active.is_(True))
        .order_by(func.coalesce(cases.c.n, 0), func.random())
    )
    if exclude:
        query = query.where(User.id.not_in(exclude))
    return db.scalars(query.limit(1)).first()
