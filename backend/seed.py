"""Seed data dummy untuk PoC: 2 klien dan user untuk setiap peran, termasuk satu user peran ganda.

Jalankan dari folder backend/:  .venv/bin/python seed.py
Aman dijalankan berulang (data yang sudah ada dilewati).
Semua akun memakai password dari SEED_DEFAULT_PASSWORD di .env.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Role, Signatory, SignatoryKind, User, UserClientAssignment, UserRole, Vendor
from app.services.verification import normalize
from app.security import hash_password

load_dotenv()

CLIENTS = ["PT Klien Alpha", "PT Klien Beta"]

# (email, nama, peran, klien yang ditugaskan)
USERS = [
    ("pic.alpha@amiga.test", "Rina (PIC Alpha)", [Role.PIC_KLIEN], ["PT Klien Alpha"]),
    ("pic.beta@amiga.test", "Budi (PIC Beta)", [Role.PIC_KLIEN], ["PT Klien Beta"]),
    ("intake@amiga.test", "Sari (Intake Support)", [Role.INTAKE_SUPPORT], ["PT Klien Alpha"]),
    ("reviewer1@amiga.test", "Dewi (Finance Reviewer)", [Role.FINANCE_REVIEWER], CLIENTS),
    ("reviewer2@amiga.test", "Agus (Finance Reviewer)", [Role.FINANCE_REVIEWER], CLIENTS),
    # Peran ganda: bisa mengunggah lalu mencoba menyetujui sendiri (UAT 5, Segregation of Duties)
    ("multi@amiga.test", "Yoga (Intake + Reviewer)", [Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER],
     ["PT Klien Alpha"]),
    ("lead@amiga.test", "Hendra (Service Lead)", [Role.SERVICE_LEAD], CLIENTS),
    ("admin@amiga.test", "Admin Sistem", [Role.SYSTEM_ADMIN], []),
]


# Data referensi contoh (fiktif): (klien, jenis, nama, jabatan) dan (klien, vendor, bank, rekening)
SIGNATORIES = [
    ("PT Klien Alpha", SignatoryKind.PENGAJU, "Rina Kartika", "Staf Keuangan"),
    ("PT Klien Alpha", SignatoryKind.PENYETUJU, "Budi Santoso", "Direktur"),
    ("PT Klien Alpha", SignatoryKind.PENYETUJU, "Sari Dewi", "Bendahara"),
    ("PT Klien Beta", SignatoryKind.PENGAJU, "Budi Hartono", "Admin Keuangan"),
    ("PT Klien Beta", SignatoryKind.PENYETUJU, "Lestari Wulan", "Direktur Utama"),
]
VENDORS = [
    ("PT Klien Alpha", "PT Sumber Kertas Nusantara", "Bank Central Asia (BCA)", "1234567890"),
    ("PT Klien Alpha", "PT Bersih Sejahtera Abadi", "Bank Mandiri", "1370012345678"),
    ("PT Klien Beta", "PT Teknologi Jaringan Prima", "Bank Central Asia (BCA)", "1234567890"),
]


def seed_reference(db, clients: dict[str, Client], pic_by_client: dict[str, User]) -> None:
    for client_name, kind, name, position in SIGNATORIES:
        client = clients[client_name]
        if db.scalar(select(Signatory).where(Signatory.client_id == client.id, Signatory.full_name == name)) is None:
            db.add(Signatory(client_id=client.id, kind=kind, full_name=name, position=position, is_default=True,
                             created_by=pic_by_client[client_name].id))
    for client_name, name, bank, account in VENDORS:
        client = clients[client_name]
        if db.scalar(select(Vendor).where(Vendor.client_id == client.id, Vendor.name_norm == normalize(name))) is None:
            db.add(Vendor(client_id=client.id, name=name, name_norm=normalize(name), bank_name=bank,
                          account_no=account, account_name=name, created_by=pic_by_client[client_name].id))


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
        for email, full_name, roles, _ in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, full_name=full_name, password_hash=hash_password(password))
                db.add(user)
            for role in set(roles) - user.roles:
                user.role_links.append(UserRole(role=role))
            users[email] = user
        db.flush()

        pic_alpha = users["pic.alpha@amiga.test"]
        for email, _, roles, client_names in USERS:
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
                        delegated_by=pic_alpha.id if Role.INTAKE_SUPPORT in roles else None,
                    ))
        seed_reference(db, clients, {"PT Klien Alpha": pic_alpha, "PT Klien Beta": users["pic.beta@amiga.test"]})
        db.commit()

    print(f"Seed selesai: {len(CLIENTS)} klien, {len(USERS)} user, {len(SIGNATORIES)} penanda tangan, {len(VENDORS)} vendor.")
    for email, full_name, roles, client_names in USERS:
        role_text = " + ".join(r.value for r in roles)
        print(f"  {role_text:<35} {email:<24} klien: {', '.join(client_names) or '-'}")


if __name__ == "__main__":
    main()
