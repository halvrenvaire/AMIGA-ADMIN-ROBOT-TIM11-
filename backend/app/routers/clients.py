import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ensure_client_access, get_current_user
from app.db import get_db
from app.models import Client, User
from app.schemas.schemas import ClientRef
from app.services.access_rules import accessible_client_ids

router = APIRouter(prefix="/clients", tags=["Klien"])


@router.get("", response_model=list[ClientRef])
def list_clients(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Klien yang ditugaskan kepada pengguna (mis. pilihan klien di formulir unggah)."""
    ids = accessible_client_ids(db, user)
    return db.scalars(select(Client).where(Client.id.in_(ids)).order_by(Client.name)).all()


@router.get("/{client_id}", response_model=ClientRef)
def get_client(client_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detail satu klien. Klien yang tidak ditugaskan ditolak dan dicatat di jejak audit."""
    ensure_client_access(db, user, client_id)
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(404, "Klien tidak ditemukan.")
    return client
