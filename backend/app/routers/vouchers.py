"""Manajemen voucher: daftar voucher pembayaran dari invoice di sistem (permintaan owner 14 Okt 2026)."""
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.db import get_db
from app.models import Client, DocStatus, Document, Extraction, Role, User, Voucher
from app.schemas.schemas import ClientRef, VoucherRow
from app.services import audit_service
from app.services.access_rules import accessible_client_ids
from app.services.voucher_report import render_report

router = APIRouter(tags=["Manajemen Voucher"])
WIB = ZoneInfo("Asia/Jakarta")


def _rows(db: Session, ids: set[uuid.UUID], *, vendor_id=None, vendor=None, status_filter=None,
          date_from: date | None = None, date_to: date | None = None, q=None, request_type=None) -> list[VoucherRow]:
    approver, pic = aliased(User), aliased(User)
    query = (
        select(Voucher, Document, Client, Extraction, approver.full_name, pic.full_name)
        .join(Document, Document.id == Voucher.document_id)
        .join(Client, Client.id == Document.client_id)
        .outerjoin(Extraction, Extraction.document_id == Document.id)
        .join(approver, approver.id == Voucher.generated_by)
        .join(pic, pic.id == func.coalesce(Document.on_behalf_of, Document.uploaded_by))
        .where(Document.client_id.in_(ids))
        .order_by(Voucher.generated_at.desc())
    )
    if vendor_id is not None:
        query = query.where(Document.vendor_id == vendor_id)
    if request_type:
        query = query.where(Document.request_type == request_type)
    if vendor and vendor.strip():
        query = query.where(Extraction.vendor_name.ilike(f"%{vendor.strip()}%"))
    if status_filter:
        query = query.where(Document.status == DocStatus(status_filter))
    if date_from:
        query = query.where(Voucher.generated_at >= datetime.combine(date_from, datetime.min.time(), WIB))
    if date_to:
        query = query.where(Voucher.generated_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), WIB))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.where(Voucher.voucher_no.ilike(like) | Document.request_id.ilike(like)
                            | Extraction.invoice_no.ilike(like))
    return [
        VoucherRow(
            document_id=doc.id, voucher_no=v.voucher_no, generated_at=v.generated_at, request_id=doc.request_id,
            client=ClientRef(id=client.id, name=client.name), vendor_id=doc.vendor_id,
            vendor_name=ex.vendor_name if ex else None, invoice_no=ex.invoice_no if ex else None,
            invoice_date=ex.invoice_date if ex else None, total=ex.total if ex else None,
            status=doc.status, approved_by=approved_by, pic_name=pic_name, request_type=doc.request_type,
        )
        for v, doc, client, ex, approved_by, pic_name in db.execute(query).all()
    ]


@router.get("/vouchers", response_model=list[VoucherRow])
def list_vouchers(
    client_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    vendor: Annotated[str | None, Query(max_length=300, description="Nama vendor (sebagian)")] = None,
    status_filter: Annotated[Literal["AMIGA_REVIEWED", "SENT_TO_CLIENT"] | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Nomor voucher, Request ID, atau nomor invoice")] = None,
    request_type: Annotated[str | None, Query(max_length=100, description="Kategori pengajuan")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Voucher klien yang ditugaskan, terbaru di atas. Pengelompokan dilakukan di tampilan."""
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    return _rows(db, ids, vendor_id=vendor_id, vendor=vendor, status_filter=status_filter,
                 date_from=date_from, date_to=date_to, q=q, request_type=request_type)


PERIOD_DAYS = {"1": 1, "7": 7, "30": 30}
PERIOD_LABEL = {"1": "Hari ini", "7": "7 hari terakhir", "30": "30 hari terakhir", "custom": "Periode kustom"}


def report_range(period: str, date_from: date | None, date_to: date | None, today: date) -> tuple[date, date]:
    """1/7/30 = hari ini dan N-1 hari sebelumnya (WIB); custom = tanggal pilihan, maks. 366 hari."""
    if period in PERIOD_DAYS:
        return today - timedelta(days=PERIOD_DAYS[period] - 1), today
    if not date_from or not date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Isi tanggal mulai dan tanggal akhir.")
    if date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Tanggal mulai harus sebelum tanggal akhir.")
    if (date_to - date_from).days > 365:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Periode kustom paling panjang 366 hari.")
    return date_from, date_to


@router.get("/vouchers/report", response_class=Response)
def voucher_report(
    period: Literal["1", "7", "30", "custom"] = "7",
    date_from: date | None = None,
    date_to: date | None = None,
    client_id: uuid.UUID | None = None,
    user: User = Depends(require_roles(Role.SERVICE_LEAD)),
    db: Session = Depends(get_db),
):
    """Service Lead: unduh rekap voucher yang terbit dalam 1, 7, atau 30 hari terakhir, atau periode
    kustom, sebagai PDF. Tanggal mengikuti WIB."""
    now = datetime.now(WIB)
    start, end = report_range(period, date_from, date_to, now.date())
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    rows = _rows(db, ids, date_from=start, date_to=end)
    pdf = render_report(rows, start, end, PERIOD_LABEL[period], user.full_name, now)
    audit_service.record(db, user, "VOUCHER_REPORT_DOWNLOADED", client_id=client_id,
                         note=f"{PERIOD_LABEL[period]}: {start.isoformat()} s.d. {end.isoformat()}, {len(rows)} voucher")
    db.commit()
    filename = f"rekap-voucher_{start:%Y%m%d}-{end:%Y%m%d}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
