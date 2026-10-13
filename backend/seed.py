"""Seed data dummy untuk PoC: 2 klien dan user untuk setiap peran.

Jalankan dari folder backend/:  .venv/bin/python seed.py
Aman dijalankan berulang (data yang sudah ada dilewati).
Semua akun memakai password dari SEED_DEFAULT_PASSWORD di .env.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Role, User, UserClientAssignment
from app.security import hash_password

load_dotenv()

CLIENTS = ["PT Klien Alpha", "PT Klien Beta"]

# (email, nama, peran, klien yang ditugaskan)
USERS = [
    ("pic.alpha@amiga.test", "Rina (PIC Alpha)", Role.PIC_KLIEN, ["PT Klien Alpha"]),
    ("pic.beta@amiga.test", "Budi (PIC Beta)", Role.PIC_KLIEN, ["PT Klien Beta"]),
    ("intake@amiga.test", "Sari (Intake Support)", Role.INTAKE_SUPPORT, ["PT Klien Alpha"]),
    ("reviewer1@amiga.test", "Dewi (Finance Reviewer)", Role.FINANCE_REVIEWER, CLIENTS),
    ("reviewer2@amiga.test", "Agus (Finance Reviewer)", Role.FINANCE_REVIEWER, CLIENTS),
    ("lead@amiga.test", "Hendra (Service Lead)", Role.SERVICE_LEAD, CLIENTS),
    ("admin@amiga.test", "Admin Sistem", Role.SYSTEM_ADMIN, []),
]


def main() -> None:
    password = os.environ.get("SEED_DEFAULT_PASSWORD")
    if not password:
        raise SystemExit("SEED_DEFAULT_PASSWORD belum diisi di .env")

    with SessionLocal() as db:
        clients: dict[str, Client] = {}
        for name in CLIENTS:
            client = db.scalar(select(Client).where(Client.name == name))
            if client is None:
                client = Client(name=name)
                db.add(client)
            clients[name] = client
        db.flush()

        users: dict[str, User] = {}
        for email, full_name, role, _ in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, full_name=full_name, role=role,
                            password_hash=hash_password(password))
                db.add(user)
            users[email] = user
        db.flush()

        pic_alpha = users["pic.alpha@amiga.test"]
        for email, _, role, client_names in USERS:
            for client_name in client_names:
                user, client = users[email], clients[client_name]
                exists = db.scalar(select(UserClientAssignment).where(
                    UserClientAssignment.user_id == user.id,
                    UserClientAssignment.client_id == client.id,
                ))
                if exists is None:
                    db.add(UserClientAssignment(
                        user_id=user.id,
                        client_id=client.id,
                        # Intake Support bekerja atas delegasi PIC Alpha (FR-1.4)
                        delegated_by=pic_alpha.id if role == Role.INTAKE_SUPPORT else None,
                    ))
        db.commit()

    print(f"Seed selesai: {len(CLIENTS)} klien, {len(USERS)} user.")
    for email, full_name, role, client_names in USERS:
        print(f"  {role.value:<17} {email:<24} klien: {', '.join(client_names) or '-'}")


if __name__ == "__main__":
    main()
