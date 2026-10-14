"""Ringkasan antrean (F6) untuk dashboard dan Asisten AI.

Semua angka dihitung hanya dari klien yang ditugaskan kepada pengguna, sehingga
dashboard dan asisten tidak pernah memperlihatkan data klien lain.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Client, DocStatus, Document, Extraction, Role, User, UserClientAssignment, UserRole, ValidationIssue,
)

DONE = (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT)


@dataclass
class ReviewerLoad:
    id: uuid.UUID
    name: str
    email: str
    pending: int
    overloaded: bool


@dataclass
class QueueSummary:
    counts: dict[str, int]
    problem: int
    due_soon: int
    overdue: int
    reviewers: list[ReviewerLoad] = field(default_factory=list)


def summarize(db: Session, client_ids: set[uuid.UUID], today: date | None = None) -> QueueSummary:
    today = today or date.today()
    in_scope = Document.client_id.in_(client_ids)
    counts = {s.value: 0 for s in DocStatus}
    for status, n in db.execute(select(Document.status, func.count()).where(in_scope).group_by(Document.status)):
        counts[status.value] = n
    open_docs = select(func.count()).select_from(Document).where(in_scope, Document.status.not_in(DONE))
    due_soon = db.scalar(open_docs.where(Document.due_date.between(today, today + timedelta(days=settings.due_soon_days))))
    overdue = db.scalar(open_docs.where(Document.due_date < today))

    pending = (
        select(Document.assigned_reviewer_id.label("rid"), func.count().label("n"))
        .where(in_scope, Document.status == DocStatus.READY_FOR_REVIEW)
        .group_by(Document.assigned_reviewer_id).subquery()
    )
    reviewers_of_scope = select(UserClientAssignment.user_id).where(
        UserClientAssignment.client_id.in_(client_ids),
        or_(UserClientAssignment.valid_until.is_(None), UserClientAssignment.valid_until >= today),
    )
    load = func.coalesce(pending.c.n, 0)
    rows = db.execute(
        select(User.id, User.full_name, User.email, load)
        .join(UserRole, (UserRole.user_id == User.id) & (UserRole.role == Role.FINANCE_REVIEWER))
        .outerjoin(pending, pending.c.rid == User.id)
        .where(User.is_active.is_(True), User.id.in_(reviewers_of_scope))
        .order_by(load.desc(), User.full_name)
    ).all()
    reviewers = [ReviewerLoad(rid, name, email, n, n > settings.reviewer_overload_threshold)
                 for rid, name, email, n in rows]
    return QueueSummary(counts=counts, problem=counts[DocStatus.EXCEPTION.value],
                        due_soon=due_soon, overdue=overdue, reviewers=reviewers)


def _doc_line(request_id, client, status, vendor, total, due) -> str:
    total_text = f"Rp {total:,.0f}".replace(",", ".") if total is not None else "-"
    return (f"- {request_id} | klien: {client} | status: {status.value} | vendor: {vendor or '-'} | "
            f"total: {total_text} | tenggat: {due.isoformat() if due else '-'}")


def assistant_context(db: Session, user: User, client_ids: set[uuid.UUID], limit: int = 15) -> str:
    """Data antrean dalam bentuk teks untuk Asisten AI, sesuai hak akses pengguna."""
    summary = summarize(db, client_ids)
    clients = db.scalars(select(Client.name).where(Client.id.in_(client_ids)).order_by(Client.name)).all()
    lines = [
        f"Pengguna: {user.full_name} (peran: {', '.join(sorted(r.value for r in user.roles))})",
        f"Tanggal hari ini: {date.today().isoformat()}",
        f"Klien yang ditugaskan: {', '.join(clients) or '-'}",
        "Jumlah dokumen per status: " + ", ".join(f"{k}={v}" for k, v in summary.counts.items()),
        f"Tenggat <= {settings.due_soon_days} hari (belum selesai): {summary.due_soon}; "
        f"lewat tenggat: {summary.overdue}",
        f"Beban reviewer (dokumen READY_FOR_REVIEW; berlebih bila > {settings.reviewer_overload_threshold}): "
        + ("; ".join(f"{r.name}={r.pending}{' (berlebih)' if r.overloaded else ''}" for r in summary.reviewers)
           or "-"),
    ]

    base = (select(Document.request_id, Client.name, Document.status, Extraction.vendor_name,
                   Extraction.total, Document.due_date)
            .join(Client, Client.id == Document.client_id)
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .where(Document.client_id.in_(client_ids)))
    due_order = (Document.due_date.is_(None), Document.due_date, Document.created_at)

    if Role.FINANCE_REVIEWER in user.roles:
        mine = db.execute(base.where(Document.assigned_reviewer_id == user.id,
                                     Document.status == DocStatus.READY_FOR_REVIEW)
                          .order_by(*due_order).limit(limit)).all()
        lines.append(f"\nDokumen READY_FOR_REVIEW yang ditugaskan kepada {user.full_name} ({len(mine)}):")
        lines += [_doc_line(*row) for row in mine] or ["- (tidak ada)"]

    problems = db.execute(base.where(Document.status == DocStatus.EXCEPTION)
                          .order_by(*due_order).limit(limit)).all()
    codes = dict(db.execute(
        select(Document.request_id, func.string_agg(cast(ValidationIssue.code, String), ", "))
        .join(ValidationIssue, ValidationIssue.document_id == Document.id)
        .where(Document.client_id.in_(client_ids), Document.status == DocStatus.EXCEPTION,
               ValidationIssue.resolved.is_(False))
        .group_by(Document.request_id)).tuples().all())
    lines.append(f"\nDokumen EXCEPTION ({summary.problem}, maks. {limit} ditampilkan):")
    lines += [f"{_doc_line(*row)} | kendala: {codes.get(row[0], '-')}" for row in problems] or ["- (tidak ada)"]

    recent = db.execute(base.order_by(Document.updated_at.desc()).limit(limit)).all()
    lines.append(f"\nDokumen terakhir diperbarui (maks. {limit}):")
    lines += [_doc_line(*row) for row in recent] or ["- (tidak ada)"]
    return "\n".join(lines)
