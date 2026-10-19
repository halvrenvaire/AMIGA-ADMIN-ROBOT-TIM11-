"""Data referensi milik klien: vendor dan penanda tangan voucher (permintaan owner 14 Okt 2026).

Dikelola PIC Klien (vendor juga oleh Intake Support) untuk klien yang ditugaskan; dibaca semua
pengguna yang punya akses ke klien itu, mis. untuk dropdown filter dan formulir.
"""
import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import ensure_client_access, get_current_user, require_roles
from app.db import get_db
from app.models import Document, Extraction, Role, Signatory, SignatoryKind, TaxRate, User, Vendor
from app.schemas.schemas import (
    ActiveUpdate, ClientRef, SignatoryCreate, SignatoryIn, SignatoryOut, SignatureIn, TaxRateOut, TaxRateUpdate, VendorCheck, VendorCreate, VendorIn, VendorOut,
)
from app.services import audit_service, signature_service
from app.services.access_rules import accessible_client_ids
from app.services.verification import normalize

router = APIRouter(tags=["Data Referensi"])

vendor_editors = require_roles(Role.PIC_KLIEN, Role.INTAKE_SUPPORT)
signatory_editors = require_roles(Role.PIC_KLIEN)
VENDOR_FIELDS = ("name", "npwp", "address", "contact_name", "phone", "email",
                 "bank_name", "account_no", "account_name", "notes")
# Perubahan field ini membatalkan verifikasi rekening vendor
BANK_FIELDS = ("name", "bank_name", "account_no", "account_name")
reviewer_only = require_roles(Role.FINANCE_REVIEWER)


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _vendor_out(db: Session, v: Vendor) -> VendorOut:
    docs = db.scalar(select(func.count()).select_from(Document).where(Document.vendor_id == v.id))
    verifier = db.get(User, v.verified_by) if v.verified_by else None
    return VendorOut(**{f: getattr(v, f) for f in VENDOR_FIELDS}, id=v.id, is_active=v.is_active,
                     client=ClientRef(id=v.client.id, name=v.client.name), documents=docs,
                     created_at=v.created_at, updated_at=v.updated_at,
                     verified_at=v.verified_at, verified_by=verifier.full_name if verifier else None)


def _find_by_name(db: Session, client_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None) -> Vendor | None:
    norm = normalize(name)
    query = select(Vendor).where(Vendor.client_id == client_id, Vendor.name_norm == norm)
    if exclude:
        query = query.where(Vendor.id != exclude)
    return db.scalar(query)


def link_documents(db: Session, vendor: Vendor) -> None:
    """Tautkan dokumen klien yang nama vendornya cocok (dinormalisasi) dan belum punya vendor."""
    matching = select(Extraction.document_id).where(Extraction.vendor_norm == vendor.name_norm)
    db.execute(update(Document)
               .where(Document.client_id == vendor.client_id, Document.vendor_id.is_(None), Document.id.in_(matching))
               .values(vendor_id=vendor.id))


def _get_vendor(db: Session, user: User, vendor_id: uuid.UUID) -> Vendor:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor tidak ditemukan.")
    ensure_client_access(db, user, vendor.client_id)
    return vendor


# --- Vendor ---

@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(client_id: uuid.UUID | None = None, q: str | None = Query(None, max_length=100),
                 include_inactive: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vendor milik klien yang ditugaskan (untuk tabel data referensi dan dropdown)."""
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    query = select(Vendor).where(Vendor.client_id.in_(ids)).order_by(Vendor.name)
    if not include_inactive:
        query = query.where(Vendor.is_active.is_(True))
    if q and q.strip():
        query = query.where(Vendor.name.ilike(f"%{q.strip()}%") | Vendor.npwp.ilike(f"%{q.strip()}%"))
    return [_vendor_out(db, v) for v in db.scalars(query)]


@router.get("/vendors/check", response_model=VendorCheck)
def check_vendor(client_id: uuid.UUID, name: str = Query(min_length=1, max_length=300),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cek apakah nama vendor sudah terdaftar (huruf besar/kecil, spasi, dan tanda baca diabaikan)."""
    ensure_client_access(db, user, client_id)
    vendor = _find_by_name(db, client_id, name)
    return VendorCheck(exists=vendor is not None, vendor=_vendor_out(db, vendor) if vendor else None)


@router.post("/vendors", response_model=VendorOut, status_code=201)
def create_vendor(body: VendorCreate, user: User = Depends(vendor_editors), db: Session = Depends(get_db)):
    ensure_client_access(db, user, body.client_id)
    existing = _find_by_name(db, body.client_id, body.name)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Vendor \"{existing.name}\" sudah terdaftar. Gunakan data yang ada.")
    data = {f: _clean(getattr(body, f)) for f in VENDOR_FIELDS}
    vendor = Vendor(**data, client_id=body.client_id, name_norm=normalize(data["name"]), created_by=user.id,
                    bank_updated_by=user.id)
    db.add(vendor)
    db.flush()
    link_documents(db, vendor)
    audit_service.record(db, user, "VENDOR_CREATED", client_id=body.client_id, new_value=vendor.name)
    db.commit()
    db.refresh(vendor)
    return _vendor_out(db, vendor)


@router.put("/vendors/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: uuid.UUID, body: VendorIn, user: User = Depends(vendor_editors),
                  db: Session = Depends(get_db)):
    vendor = _get_vendor(db, user, vendor_id)
    if _find_by_name(db, vendor.client_id, body.name, exclude=vendor.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nama vendor itu sudah dipakai vendor lain.")
    for f in VENDOR_FIELDS:
        new = _clean(getattr(body, f))
        old = getattr(vendor, f)
        if new != old:
            audit_service.record(db, user, "VENDOR_UPDATED", client_id=vendor.client_id, field=f,
                                 old_value=old, new_value=new, note=vendor.name)
            setattr(vendor, f, new)
            if f in BANK_FIELDS:
                vendor.bank_updated_by = user.id
                if vendor.verified_at is not None:
                    vendor.verified_at = vendor.verified_by = None
                    audit_service.record(db, user, "VENDOR_VERIFICATION_RESET", client_id=vendor.client_id,
                                         field=f, note=f"{vendor.name}: data bank berubah, perlu diverifikasi ulang")
    vendor.name_norm = normalize(vendor.name)
    link_documents(db, vendor)
    db.commit()
    db.refresh(vendor)
    return _vendor_out(db, vendor)


@router.patch("/vendors/{vendor_id}/active", response_model=VendorOut)
def set_vendor_active(vendor_id: uuid.UUID, body: ActiveUpdate, user: User = Depends(vendor_editors),
                      db: Session = Depends(get_db)):
    """Nonaktifkan/aktifkan vendor. Vendor tidak dihapus agar riwayat voucher tetap utuh."""
    vendor = _get_vendor(db, user, vendor_id)
    if vendor.is_active != body.is_active:
        vendor.is_active = body.is_active
        audit_service.record(db, user, "VENDOR_ACTIVATED" if body.is_active else "VENDOR_DEACTIVATED",
                             client_id=vendor.client_id, note=vendor.name)
        db.commit()
        db.refresh(vendor)
    return _vendor_out(db, vendor)


@router.post("/vendors/{vendor_id}/verify", response_model=VendorOut)
def verify_vendor(vendor_id: uuid.UUID, user: User = Depends(reviewer_only), db: Session = Depends(get_db)):
    """Finance Reviewer menyatakan rekening vendor sudah dicek ke sumber tepercaya (mis. konfirmasi langsung ke
    vendor). Menjadi acuan pemeriksaan rekening invoice. Tidak oleh pendaftar/pengubah terakhir data bank (SoD)."""
    vendor = _get_vendor(db, user, vendor_id)
    if not vendor.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vendor nonaktif tidak bisa diverifikasi.")
    if not (vendor.bank_name and vendor.account_no and vendor.account_name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Lengkapi nama bank, nomor rekening, dan nama pemilik rekening sebelum diverifikasi.")
    if user.id in {vendor.created_by, vendor.bank_updated_by}:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Anda yang mendaftarkan atau terakhir mengubah data bank vendor ini, jadi tidak boleh "
                            "memverifikasinya sendiri (Segregation of Duties).")
    vendor.verified_at = datetime.now(timezone.utc)
    vendor.verified_by = user.id
    audit_service.record(db, user, "VENDOR_VERIFIED", client_id=vendor.client_id, field="account_no",
                         new_value=f"{vendor.bank_name} {vendor.account_no} a.n. {vendor.account_name}", note=vendor.name)
    db.commit()
    db.refresh(vendor)
    return _vendor_out(db, vendor)


# --- Penanda tangan voucher ---

def _get_signatory(db: Session, user: User, signatory_id: uuid.UUID) -> Signatory:
    sig = db.get(Signatory, signatory_id)
    if sig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penanda tangan tidak ditemukan.")
    ensure_client_access(db, user, sig.client_id)
    return sig


def _apply_default(db: Session, sig: Signatory) -> None:
    """Satu default per klien: kotak "Disetujui oleh" pertama yang terisi otomatis saat unggah."""
    if sig.is_default:
        db.execute(update(Signatory).where(Signatory.client_id == sig.client_id, Signatory.id != sig.id,
                                           Signatory.kind == sig.kind).values(is_default=False))


def _only_approvers(kind: SignatoryKind) -> None:
    if kind != SignatoryKind.PENYETUJU:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Kotak \"Diajukan oleh\" otomatis berisi perusahaan klien; daftar ini hanya untuk "
                            "pemberi persetujuan (\"Disetujui oleh\").")


@router.get("/signatories", response_model=list[SignatoryOut])
def list_signatories(client_id: uuid.UUID | None = None, include_inactive: bool = False,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_client_ids(db, user)
    if client_id is not None:
        ids &= {client_id}
    # "Diajukan oleh" kini perusahaan klien; data PENGAJU lama tidak ditampilkan lagi
    query = select(Signatory).where(Signatory.client_id.in_(ids), Signatory.kind == SignatoryKind.PENYETUJU) \
        .order_by(Signatory.is_default.desc(), Signatory.full_name)
    if not include_inactive:
        query = query.where(Signatory.is_active.is_(True))
    return db.scalars(query).all()


@router.post("/signatories", response_model=SignatoryOut, status_code=201)
def create_signatory(body: SignatoryCreate, user: User = Depends(signatory_editors), db: Session = Depends(get_db)):
    ensure_client_access(db, user, body.client_id)
    _only_approvers(body.kind)
    sig = Signatory(client_id=body.client_id, kind=body.kind, full_name=body.full_name.strip(),
                    position=body.position.strip(), is_default=body.is_default, created_by=user.id)
    db.add(sig)
    db.flush()
    _apply_default(db, sig)
    audit_service.record(db, user, "SIGNATORY_CREATED", client_id=body.client_id,
                         new_value=f"{sig.full_name} ({sig.position})", note=sig.kind.value)
    db.commit()
    db.refresh(sig)
    return sig


@router.put("/signatories/{signatory_id}", response_model=SignatoryOut)
def update_signatory(signatory_id: uuid.UUID, body: SignatoryIn, user: User = Depends(signatory_editors),
                     db: Session = Depends(get_db)):
    sig = _get_signatory(db, user, signatory_id)
    _only_approvers(body.kind)
    old = f"{sig.full_name} ({sig.position}) {sig.kind.value}{' default' if sig.is_default else ''}"
    sig.kind, sig.full_name, sig.position, sig.is_default = (body.kind, body.full_name.strip(),
                                                             body.position.strip(), body.is_default)
    _apply_default(db, sig)
    audit_service.record(db, user, "SIGNATORY_UPDATED", client_id=sig.client_id, old_value=old,
                         new_value=f"{sig.full_name} ({sig.position}) {sig.kind.value}{' default' if sig.is_default else ''}")
    db.commit()
    db.refresh(sig)
    return sig


@router.patch("/signatories/{signatory_id}/active", response_model=SignatoryOut)
def set_signatory_active(signatory_id: uuid.UUID, body: ActiveUpdate, user: User = Depends(signatory_editors),
                         db: Session = Depends(get_db)):
    sig = _get_signatory(db, user, signatory_id)
    if sig.is_active != body.is_active:
        sig.is_active = body.is_active
        if not body.is_active:
            sig.is_default = False
        audit_service.record(db, user, "SIGNATORY_ACTIVATED" if body.is_active else "SIGNATORY_DEACTIVATED",
                             client_id=sig.client_id, note=f"{sig.full_name} ({sig.position})")
        db.commit()
        db.refresh(sig)
    return sig


@router.get("/signatories/{signatory_id}/signature")
def get_signature(signatory_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Spesimen tanda tangan elektronik pemberi persetujuan (PNG)."""
    sig = _get_signatory(db, user, signatory_id)
    if sig.signature_png is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Belum ada tanda tangan elektronik.")
    return Response(sig.signature_png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.put("/signatories/{signatory_id}/signature", response_model=SignatoryOut)
def set_signature(signatory_id: uuid.UUID, body: SignatureIn, user: User = Depends(signatory_editors),
                  db: Session = Depends(get_db)):
    """PIC Klien mendaftarkan tanda tangan elektronik pemberi persetujuan (digoreskan atau diunggah)."""
    sig = _get_signatory(db, user, signatory_id)
    replaced = sig.signature_png is not None
    sig.signature_png = signature_service.normalize(body.image)
    sig.signature_updated_at = datetime.now(timezone.utc)
    audit_service.record(db, user, "SIGNATURE_UPDATED", client_id=sig.client_id, field="signature",
                         note=f"Tanda tangan elektronik {sig.full_name} ({sig.position}) "
                              + ("diganti" if replaced else "didaftarkan"))
    db.commit()
    db.refresh(sig)
    return sig


@router.delete("/signatories/{signatory_id}/signature", response_model=SignatoryOut)
def delete_signature(signatory_id: uuid.UUID, user: User = Depends(signatory_editors), db: Session = Depends(get_db)):
    sig = _get_signatory(db, user, signatory_id)
    if sig.signature_png is not None:
        sig.signature_png, sig.signature_updated_at = None, None
        audit_service.record(db, user, "SIGNATURE_REMOVED", client_id=sig.client_id, field="signature",
                             note=f"Tanda tangan elektronik {sig.full_name} ({sig.position}) dihapus")
        db.commit()
        db.refresh(sig)
    return sig


# --- Tarif pajak (Tahap 4 feedback owner) ---
tax_editors = require_roles(Role.SERVICE_LEAD, Role.SYSTEM_ADMIN)


@router.get("/tax-rates", response_model=list[TaxRateOut])
def list_tax_rates(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Jenis dan tarif potongan pajak yang bisa dipilih PIC per invoice."""
    return db.scalars(select(TaxRate).order_by(TaxRate.position)).all()


@router.put("/tax-rates/{code}", response_model=TaxRateOut)
def update_tax_rate(code: str, body: TaxRateUpdate, user: User = Depends(tax_editors), db: Session = Depends(get_db)):
    """Ubah tarif (mis. setelah dikonfirmasi konsultan pajak). Draf dan voucher yang sudah ada tidak berubah
    karena tarif disalin ke data invoice saat dipilih."""
    rate = db.get(TaxRate, code)
    if rate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jenis pajak tidak ditemukan.")
    if code == "NONE" and (body.rate_npwp or body.rate_no_npwp or body.is_active is False):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "\"Tanpa potongan\" selalu 0% dan selalu aktif.")
    for name, value in body.model_dump(exclude_unset=True).items():
        old = getattr(rate, name)
        if value is None or old == value:
            continue
        audit_service.record(db, user, "TAX_RATE_CHANGED", field=f"{code}.{name}",
                             old_value=str(old), new_value=str(value))
        setattr(rate, name, value)
    rate.updated_by = user.id
    rate.updated_at = datetime.now(timezone.utc)
    db.commit()
    return rate
