"""Manajemen voucher: daftar voucher pembayaran dari invoice di sistem (permintaan owner 14 Okt 2026)."""
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Client, DocStatus, Document, Extraction, User, Voucher
from app.schemas.schemas import ClientRef, VoucherRow
from app.services.access_rules import accessible_client_ids

router = APIRouter(tags=["Manajemen Voucher"])
WIB = ZoneInfo("Asia/Jakarta")


@router.get("/vouchers", response_model=list[VoucherRow])
def list_vouchers(
    client_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = None,
    vendor: Annotated[str | None, Query(max_length=300, description="Nama vendor (sebagian)")] = None,
    status_filter: Annotated[Literal["AMIGA_REVIEWED", "SENT_TO_CLIENT"] | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Nomor voucher, Request ID, atau nomor invoice")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Voucher klien yang ditugaskan, terbaru di atas. Pengelompokan dilakukan di tampilan."""
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    query = (
        select(Voucher, Document, Client, Extraction, User.full_name)
        .join(Document, Document.id == Voucher.document_id)
        .join(Client, Client.id == Document.client_id)
        .outerjoin(Extraction, Extraction.document_id == Document.id)
        .join(User, User.id == Voucher.generated_by)
        .where(Document.client_id.in_(ids))
        .order_by(Voucher.generated_at.desc())
    )
    if vendor_id is not None:
        query = query.where(Document.vendor_id == vendor_id)
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
            status=doc.status, approved_by=approver,
        )
        for v, doc, client, ex, approver in db.execute(query).all()
    ]
