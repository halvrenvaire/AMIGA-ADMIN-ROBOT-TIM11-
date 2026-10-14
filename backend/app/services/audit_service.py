"""Pencatatan jejak audit (F8). Tabel audit_logs append-only: hanya INSERT."""
import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    *,
    client_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    on_behalf_of: uuid.UUID | None = None,
    status_before: str | None = None,
    status_after: str | None = None,
    field: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    note: str | None = None,
) -> AuditLog:
    """Tambahkan satu catatan audit ke sesi. Pemanggil yang melakukan commit."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_label=f"{actor.full_name} <{actor.email}>" if actor else "Sistem",
        action=action,
        client_id=client_id,
        document_id=document_id,
        on_behalf_of=on_behalf_of,
        status_before=status_before,
        status_after=status_after,
        field=field,
        old_value=old_value,
        new_value=new_value,
        note=note,
    )
    db.add(entry)
    return entry
