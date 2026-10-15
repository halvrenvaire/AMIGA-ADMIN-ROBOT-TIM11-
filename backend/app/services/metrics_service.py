"""Metrik dashboard: status, tren harian, kecepatan proses, kualitas, dan nilai pembayaran.

Semua angka dihitung hanya dari klien yang ditugaskan kepada pengguna. Hari dihitung dalam WIB.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, literal_column, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Client, DocStatus, Document, Extraction, ValidationIssue, Voucher

WIB = ZoneInfo("Asia/Jakarta")
DONE = (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT, DocStatus.CANCELLED)


def _wib_day(column):
    # Zona ditulis sebagai literal SQL: bila dikirim sebagai parameter, ekspresi di SELECT dan
    # GROUP BY dianggap berbeda oleh PostgreSQL
    return cast(func.timezone(literal_column("'Asia/Jakarta'"), column), Date)


@dataclass
class Metrics:
    period_days: int
    start: date
    end: date
    status_counts: dict[str, int]
    received: int
    received_prev: int
    approved: int
    approved_prev: int
    trend: list[dict] = field(default_factory=list)
    avg_hours_to_voucher: float | None = None
    avg_extraction_seconds: float | None = None
    sla_on_time: int = 0
    sla_total: int = 0
    first_pass: int = 0
    first_pass_total: int = 0
    top_issues: list[dict] = field(default_factory=list)
    corrected_docs: int = 0
    reviewed_docs: int = 0
    total_value: Decimal = Decimal(0)
    total_value_prev: Decimal = Decimal(0)
    value_by_client: list[dict] = field(default_factory=list)
    top_vendors: list[dict] = field(default_factory=list)


def compute(db: Session, client_ids: set[uuid.UUID], days: int, today: date | None = None) -> Metrics:
    today = today or datetime.now(WIB).date()
    start = today - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    start_ts = datetime.combine(start, datetime.min.time(), WIB)
    prev_ts = datetime.combine(prev_start, datetime.min.time(), WIB)
    end_ts = datetime.combine(today + timedelta(days=1), datetime.min.time(), WIB)

    scope = Document.client_id.in_(client_ids)
    in_period = and_(Document.created_at >= start_ts, Document.created_at < end_ts)
    in_prev = and_(Document.created_at >= prev_ts, Document.created_at < start_ts)

    # --- Status saat ini (semua dokumen klien) dan volume periode ---
    status_counts = {s.value: 0 for s in DocStatus}
    for status, n in db.execute(select(Document.status, func.count()).where(scope).group_by(Document.status)):
        status_counts[status.value] = n
    count_docs = lambda cond: db.scalar(select(func.count()).select_from(Document).where(scope, cond))  # noqa: E731
    received, received_prev = count_docs(in_period), count_docs(in_prev)

    v_in = and_(Voucher.generated_at >= start_ts, Voucher.generated_at < end_ts)
    v_prev = and_(Voucher.generated_at >= prev_ts, Voucher.generated_at < start_ts)
    count_v = lambda cond: db.scalar(  # noqa: E731
        select(func.count()).select_from(Voucher).join(Document, Document.id == Voucher.document_id).where(scope, cond))
    approved, approved_prev = count_v(v_in), count_v(v_prev)

    # --- Tren harian: masuk, disetujui (voucher terbit), bermasalah (pertama kali EXCEPTION) ---
    days_list = [start + timedelta(days=i) for i in range(days)]
    trend = {d: {"date": d.isoformat(), "received": 0, "approved": 0, "exception": 0} for d in days_list}
    for d, n in db.execute(select(_wib_day(Document.created_at), func.count()).where(scope, in_period)
                           .group_by(_wib_day(Document.created_at))):
        trend[d]["received"] = n
    for d, n in db.execute(select(_wib_day(Voucher.generated_at), func.count())
                           .join(Document, Document.id == Voucher.document_id).where(scope, v_in)
                           .group_by(_wib_day(Voucher.generated_at))):
        trend[d]["approved"] = n
    # Disaring lewat klien dokumen, bukan client_id di jejak audit
    first_exc = (select(AuditLog.document_id, func.min(AuditLog.created_at).label("at"))
                 .join(Document, Document.id == AuditLog.document_id)
                 .where(AuditLog.action == "STATUS_CHANGED", AuditLog.status_after == DocStatus.EXCEPTION.value, scope)
                 .group_by(AuditLog.document_id).subquery())
    for d, n in db.execute(select(_wib_day(first_exc.c.at), func.count())
                           .where(first_exc.c.at >= start_ts, first_exc.c.at < end_ts)
                           .group_by(_wib_day(first_exc.c.at))):
        trend[d]["exception"] = n

    # --- Kecepatan proses (dokumen yang vouchernya terbit dalam periode) ---
    hours = db.scalar(select(func.avg(func.extract("epoch", Voucher.generated_at - Document.created_at) / 3600))
                      .join(Document, Document.id == Voucher.document_id).where(scope, v_in))
    ai_ms = db.scalar(select(func.avg(Extraction.duration_ms)).join(Document, Document.id == Extraction.document_id)
                      .where(scope, in_period, Extraction.duration_ms.is_not(None)))
    sla_rows = db.execute(select(Voucher.generated_at, Document.due_date)
                          .join(Document, Document.id == Voucher.document_id)
                          .where(scope, v_in, Document.due_date.is_not(None))).all()
    sla_on_time = sum(1 for gen, due in sla_rows if gen.astimezone(WIB).date() <= due)

    # --- Kualitas: lolos verifikasi pertama, kendala teratas, koreksi reviewer ---
    processed = select(Document.id).where(scope, in_period, Document.status.not_in(
        (DocStatus.QUEUED, DocStatus.PROCESSING, DocStatus.CANCELLED))).subquery()
    first_pass_total = db.scalar(select(func.count()).select_from(processed))
    with_issue = db.scalar(select(func.count(func.distinct(ValidationIssue.document_id)))
                           .where(ValidationIssue.document_id.in_(select(processed.c.id))))
    top_issues = [{"code": c.value, "count": n} for c, n in db.execute(
        select(ValidationIssue.code, func.count()).join(Document, Document.id == ValidationIssue.document_id)
        .where(scope, in_period).group_by(ValidationIssue.code).order_by(func.count().desc()))]
    reviewed_docs = approved
    corrected_docs = db.scalar(
        select(func.count(func.distinct(AuditLog.document_id)))
        .join(Voucher, Voucher.document_id == AuditLog.document_id)
        .join(Document, Document.id == AuditLog.document_id)
        .where(AuditLog.action == "CORRECTED_BY_REVIEWER", scope, v_in))

    # --- Nilai pembayaran (voucher terbit) ---
    value = lambda cond: db.scalar(  # noqa: E731
        select(func.coalesce(func.sum(Extraction.total), 0)).select_from(Voucher)
        .join(Document, Document.id == Voucher.document_id)
        .join(Extraction, Extraction.document_id == Document.id).where(scope, cond))
    by_client = [{"client": name, "value": v, "count": n} for name, v, n in db.execute(
        select(Client.name, func.coalesce(func.sum(Extraction.total), 0), func.count()).select_from(Voucher)
        .join(Document, Document.id == Voucher.document_id).join(Client, Client.id == Document.client_id)
        .join(Extraction, Extraction.document_id == Document.id).where(scope, v_in)
        .group_by(Client.name).order_by(func.sum(Extraction.total).desc()))]
    top_vendors = [{"vendor": name, "value": v, "count": n} for name, v, n in db.execute(
        select(Extraction.vendor_name, func.coalesce(func.sum(Extraction.total), 0), func.count()).select_from(Voucher)
        .join(Document, Document.id == Voucher.document_id)
        .join(Extraction, Extraction.document_id == Document.id).where(scope, v_in, Extraction.vendor_name.is_not(None))
        .group_by(Extraction.vendor_name).order_by(func.sum(Extraction.total).desc()).limit(5))]

    return Metrics(
        period_days=days, start=start, end=today, status_counts=status_counts,
        received=received, received_prev=received_prev, approved=approved, approved_prev=approved_prev,
        trend=[trend[d] for d in days_list],
        avg_hours_to_voucher=float(hours) if hours is not None else None,
        avg_extraction_seconds=float(ai_ms) / 1000 if ai_ms is not None else None,
        sla_on_time=sla_on_time, sla_total=len(sla_rows),
        first_pass=first_pass_total - with_issue, first_pass_total=first_pass_total, top_issues=top_issues,
        corrected_docs=corrected_docs, reviewed_docs=reviewed_docs,
        total_value=value(v_in), total_value_prev=value(v_prev),
        value_by_client=by_client, top_vendors=top_vendors,
    )
