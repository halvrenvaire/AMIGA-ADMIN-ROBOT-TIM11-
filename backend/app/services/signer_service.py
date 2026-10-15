"""Pemilihan penanda tangan voucher untuk satu dokumen.

Kotak "Diajukan oleh" selalu perusahaan klien yang dipilih PIC saat unggah. Kotak "Disetujui oleh"
dipilih dari daftar penanda tangan klien; bila PIC tidak memilih, satu kotak berisi penanda tangan
default klien. Yang disimpan di dokumen adalah salinan nama dan jabatan, supaya voucher yang sudah
terbit tidak berubah bila daftar diedit.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Signatory, SignatoryKind

MAX_PENYETUJU = 5
COMPANY_POSITION = "Perusahaan klien"


def company(client: Client) -> dict:
    return {"kind": SignatoryKind.PENGAJU.value, "name": client.name, "position": COMPANY_POSITION}


def _approver(s: Signatory) -> dict:
    return {"kind": SignatoryKind.PENYETUJU.value, "name": s.full_name, "position": s.position}


def resolve(db: Session, client_id: uuid.UUID, ids: list[uuid.UUID] | None) -> list[dict]:
    """[perusahaan, penyetuju...] sesuai urutan pilihan PIC (urutan = urutan kotak di voucher)."""
    client = db.get(Client, client_id)
    if ids is None:
        default = db.scalars(select(Signatory).where(
            Signatory.client_id == client_id, Signatory.kind == SignatoryKind.PENYETUJU,
            Signatory.is_active.is_(True), Signatory.is_default.is_(True)).order_by(Signatory.full_name).limit(1)).first()
        return [company(client)] + ([_approver(default)] if default else [])

    unique = list(dict.fromkeys(ids))
    found = {s.id: s for s in db.scalars(select(Signatory).where(Signatory.id.in_(unique)))}
    if len(found) != len(unique) or any(
            s.client_id != client_id or not s.is_active or s.kind != SignatoryKind.PENYETUJU for s in found.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Pemberi persetujuan tidak valid untuk perusahaan ini atau sudah dinonaktifkan.")
    if len(unique) > MAX_PENYETUJU:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Paling banyak {MAX_PENYETUJU} kotak \"Disetujui oleh\".")
    return [company(client)] + [_approver(found[i]) for i in unique]


def parse_ids(raw: str | None) -> list[uuid.UUID] | None:
    """Field formulir: tidak dikirim = pakai default; string kosong = tanpa pemberi persetujuan."""
    if raw is None:
        return None
    try:
        return [uuid.UUID(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Daftar penanda tangan tidak valid.")
