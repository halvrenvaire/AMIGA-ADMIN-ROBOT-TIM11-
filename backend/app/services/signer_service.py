"""Pemilihan penanda tangan voucher untuk satu dokumen.

Bila PIC tidak memilih, penanda tangan default klien dipakai. Yang disimpan di dokumen adalah
salinan nama dan jabatan, supaya voucher yang sudah terbit tidak berubah bila daftar diedit.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Signatory, SignatoryKind

MAX_PENGAJU = 1
MAX_PENYETUJU = 3


def snapshot(signatories: list[Signatory]) -> list[dict]:
    order = {SignatoryKind.PENGAJU: 0, SignatoryKind.PENYETUJU: 1}
    return [{"kind": s.kind.value, "name": s.full_name, "position": s.position}
            for s in sorted(signatories, key=lambda s: (order[s.kind], s.full_name))]


def resolve(db: Session, client_id: uuid.UUID, ids: list[uuid.UUID] | None) -> list[dict]:
    if ids is None:
        chosen = list(db.scalars(select(Signatory).where(
            Signatory.client_id == client_id, Signatory.is_active.is_(True), Signatory.is_default.is_(True))))
        # Default "Disetujui oleh" bisa lebih dari batas voucher; ambil sesuai urutan nama
        pengaju = [s for s in chosen if s.kind == SignatoryKind.PENGAJU][:MAX_PENGAJU]
        penyetuju = sorted((s for s in chosen if s.kind == SignatoryKind.PENYETUJU),
                           key=lambda s: s.full_name)[:MAX_PENYETUJU]
        return snapshot(pengaju + penyetuju)

    unique = list(dict.fromkeys(ids))
    found = list(db.scalars(select(Signatory).where(Signatory.id.in_(unique))))
    if len(found) != len(unique) or any(s.client_id != client_id or not s.is_active for s in found):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Penanda tangan tidak valid untuk klien ini atau sudah dinonaktifkan.")
    if sum(s.kind == SignatoryKind.PENGAJU for s in found) > MAX_PENGAJU:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pilih paling banyak 1 penanda tangan \"Diajukan oleh\".")
    if sum(s.kind == SignatoryKind.PENYETUJU for s in found) > MAX_PENYETUJU:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Pilih paling banyak {MAX_PENYETUJU} penanda tangan \"Disetujui oleh\".")
    return snapshot(found)


def parse_ids(raw: str | None) -> list[uuid.UUID] | None:
    """Field formulir: tidak dikirim = pakai default; string kosong = tanpa penanda tangan."""
    if raw is None:
        return None
    try:
        return [uuid.UUID(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Daftar penanda tangan tidak valid.")
