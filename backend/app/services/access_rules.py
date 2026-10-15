"""Aturan hak akses (PRD bagian 2, F7): kombinasi peran dan isolasi klien.

Fungsi di sini dipakai oleh dependency auth dan endpoint admin, supaya aturan yang sama
berlaku di setiap pintu masuk.
"""
import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Client, Role, User, UserClientAssignment

# Peran yang menangani semua perusahaan tanpa penugasan klien oleh System Admin
ALL_CLIENT_ROLES = {Role.FINANCE_REVIEWER, Role.SERVICE_LEAD}

INTERNAL_ROLES = {Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER, Role.SERVICE_LEAD, Role.SYSTEM_ADMIN}

# Asisten AI terbuka untuk semua peran. Data yang dijawab tetap dibatasi accessible_client_ids
# (PIC Klien / Intake Support: klien yang ditugaskan; Reviewer / Lead: semua); System Admin: SOP saja.
ASSISTANT_ROLES = set(Role)


class RoleCombinationError(ValueError):
    pass


def validate_role_combination(roles: set[Role]) -> None:
    """Tolak kombinasi peran yang dilarang (Keputusan desain: peran ganda)."""
    if not roles:
        raise RoleCombinationError("Pengguna harus punya minimal satu peran.")
    if Role.PIC_KLIEN in roles and len(roles) > 1:
        raise RoleCombinationError("PIC Klien tidak boleh digabung dengan peran internal.")
    if {Role.SYSTEM_ADMIN, Role.FINANCE_REVIEWER} <= roles:
        raise RoleCombinationError(
            "System Admin tidak boleh sekaligus Finance Reviewer (System Admin tidak boleh menyetujui dokumen)."
        )


def accessible_client_ids(db: Session, user: User) -> set[uuid.UUID]:
    """Klien yang boleh dibuka pengguna. Finance Reviewer (pembagian kasus diatur sistem) dan Service Lead
    (mengawasi semua invoice) menangani semua perusahaan tanpa penugasan; peran lain hanya penugasan aktif."""
    if user.roles & ALL_CLIENT_ROLES:
        return all_client_ids(db)
    return assigned_client_ids(db, user)


def all_client_ids(db: Session) -> set[uuid.UUID]:
    return set(db.scalars(select(Client.id)))


def assigned_client_ids(db: Session, user: User) -> set[uuid.UUID]:
    """Penugasan klien aktif oleh System Admin (delegasi yang lewat masa berlaku diabaikan). Dipakai
    untuk sisi pengaju: PIC Klien / Intake Support hanya boleh mengajukan untuk perusahaan ini."""
    rows = db.scalars(
        select(UserClientAssignment.client_id).where(
            UserClientAssignment.user_id == user.id,
            or_(UserClientAssignment.valid_until.is_(None),
                UserClientAssignment.valid_until >= date.today()),
        )
    )
    return set(rows)


def can_access_client(db: Session, user: User, client_id: uuid.UUID) -> bool:
    return client_id in accessible_client_ids(db, user)
