"""Pemilihan penanda tangan voucher untuk satu dokumen.

Kotak "Diajukan oleh" berisi PIC Klien yang mengajukan (nama + perusahaan). Kotak "Disetujui oleh"
dipilih dari daftar penanda tangan klien; bila PIC tidak memilih, satu kotak berisi penanda tangan
default klien. Yang disimpan di dokumen adalah salinan nama dan jabatan, supaya voucher yang sudah
terbit tidak berubah bila daftar diedit.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Signatory, SignatoryKind, User

MAX_PENYETUJU = 5
# Snapshot lama (sebelum 16 Okt 2026) mencetak nama perusahaan di kotak "Diajukan oleh"
COMPANY_POSITION = "Perusahaan klien"


def pengaju(submitter: User, client: Client, name: str | None = None) -> dict:
    """Kotak "Diajukan oleh": default PIC pengaju. Nama boleh diganti karyawan lain (feedback owner); bila diganti,
    tautan ke akun PIC dilepas supaya spesimen tanda tangan PIC tidak tercetak atas nama orang lain."""
    name = (name or "").strip()
    if name and name != submitter.full_name:
        return {"kind": SignatoryKind.PENGAJU.value, "name": name[:200], "position": client.name}
    return {"kind": SignatoryKind.PENGAJU.value, "name": submitter.full_name, "position": f"PIC Klien, {client.name}",
            "user_id": str(submitter.id)}


PIC, MANUAL = "PIC", "MANUAL"


def default_profile(owner: User | None, client: Client) -> dict:
    """Profil "Diajukan oleh" mode PIC (Tahap 15): dikunci ke akun PIC Klien. Nama = nama akun; jabatan dan
    perusahaan/unit diatur di halaman Akun (kosong = "PIC Klien" dan nama perusahaan klien)."""
    saved = (getattr(owner, "submitter_profile", None) or {}) if owner else {}
    companies = saved.get("companies") or {}  # format Tahap 14: perusahaan per klien
    return {"name": owner.full_name if owner else "",
            "position": (saved.get("position") or "").strip() or "PIC Klien",
            "company": (saved.get("company") or "").strip() or companies.get(str(client.id)) or client.name}


def pengaju_profile(name: str, position: str | None, company: str | None, signed: bool,
                    source: str = MANUAL) -> dict:
    """Kotak "Diajukan oleh" dari profil pengaju: nama, jabatan, perusahaan/unit, apakah ada spesimen tanda tangan
    yang tersimpan di dokumen (`documents.submitter_signature_png`), dan sumbernya (PIC = profil akun, MANUAL)."""
    return {"kind": SignatoryKind.PENGAJU.value, "name": name.strip()[:200], "position": (position or "").strip()[:120],
            "company": (company or "").strip()[:200], "signature": signed, "source": source}


def _approver(s: Signatory) -> dict:
    # id disimpan supaya spesimen tanda tangan elektronik bisa ditempel saat voucher terbit
    return {"kind": SignatoryKind.PENYETUJU.value, "name": s.full_name, "position": s.position,
            "signatory_id": str(s.id)}


def resolve(db: Session, client_id: uuid.UUID, ids: list[uuid.UUID] | None,
            submitter: User | dict | None, submitter_name: str | None = None) -> list[dict]:
    """[PIC pengaju, penyetuju...] sesuai urutan pilihan PIC (urutan = urutan kotak di voucher).
    `submitter`: akun PIC (format lama), kotak "Diajukan oleh" yang sudah jadi (dict, profil pengaju), atau None =
    hanya kotak "Disetujui oleh" (dipakai saat mengganti penanda tangan)."""
    client = db.get(Client, client_id)
    head = [submitter] if isinstance(submitter, dict) else [pengaju(submitter, client, submitter_name)] if submitter else []
    if ids is None:
        default = db.scalars(select(Signatory).where(
            Signatory.client_id == client_id, Signatory.kind == SignatoryKind.PENYETUJU,
            Signatory.is_active.is_(True), Signatory.is_default.is_(True)).order_by(Signatory.full_name).limit(1)).first()
        return head + ([_approver(default)] if default else [])

    unique = list(dict.fromkeys(ids))
    found = {s.id: s for s in db.scalars(select(Signatory).where(Signatory.id.in_(unique)))}
    if len(found) != len(unique) or any(
            s.client_id != client_id or not s.is_active or s.kind != SignatoryKind.PENYETUJU for s in found.values()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Pemberi persetujuan tidak valid untuk perusahaan ini atau sudah dinonaktifkan.")
    if len(unique) > MAX_PENYETUJU:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Paling banyak {MAX_PENYETUJU} kotak \"Disetujui oleh\".")
    return head + [_approver(found[i]) for i in unique]


def parse_ids(raw: str | None) -> list[uuid.UUID] | None:
    """Field formulir: tidak dikirim = pakai default; string kosong = tanpa pemberi persetujuan."""
    if raw is None:
        return None
    try:
        return [uuid.UUID(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Daftar penanda tangan tidak valid.")
