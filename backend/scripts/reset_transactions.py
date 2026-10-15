"""Mengosongkan data transaksi (mis. sebelum Demo Day): dokumen, ekstraksi, kendala, voucher,
jejak audit, dan file PDF. Akun, klien, vendor, dan penanda tangan TIDAK dihapus.

Jejak audit sengaja tidak bisa dihapus lewat aplikasi (trigger append-only). Skrip ini menonaktifkan
trigger itu hanya di dalam satu transaksi database lalu mengaktifkannya kembali sebelum commit.

Jalankan dari folder backend/:  .venv/bin/python scripts/reset_transactions.py --yes
"""
import shutil
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import BACKEND_DIR, settings  # noqa: E402
from app.db import engine  # noqa: E402

TABLES = ["line_items", "extractions", "validation_issues", "vouchers", "audit_logs", "document_files", "documents"]


def main() -> None:
    if "--yes" not in sys.argv:
        raise SystemExit("Data transaksi akan dihapus permanen. Jalankan ulang dengan --yes untuk melanjutkan.")

    with engine.begin() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        before = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in TABLES}
        conn.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_update_delete"))
        for table in TABLES:  # urutan mengikuti foreign key
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_update_delete"))

    removed = []
    if settings.storage_backend == "local":
        base = (BACKEND_DIR / settings.local_storage_dir).resolve()
        for folder in ("invoices", "vouchers"):
            path = base / folder
            if path.exists():
                shutil.rmtree(path)
                removed.append(str(path))

    print(f"Database {db} dibersihkan:")
    for table, n in before.items():
        print(f"  {table:<18} {n:>5} baris dihapus")
    print("File dihapus:", ", ".join(removed) if removed else "-")
    if settings.storage_backend == "s3":
        print("Catatan: STORAGE_BACKEND=s3, file di bucket S3 tidak ikut dihapus.")


if __name__ == "__main__":
    main()
