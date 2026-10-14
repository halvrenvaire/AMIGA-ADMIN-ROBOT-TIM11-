#!/usr/bin/env bash
# Backend untuk test E2E: database TERPISAH (<nama>_test) yang dikosongkan setiap kali dijalankan,
# folder file sendiri, dan port 8001. Database dev tidak disentuh.
# Jalankan dari folder backend/:  bash scripts/e2e_server.sh
# Sekali saja sebelumnya:          bash scripts/create_db.sh amiga_robot_admin_test
set -euo pipefail
cd "$(dirname "$0")/.."

DEV_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
export DATABASE_URL="${E2E_DATABASE_URL:-${DEV_URL%/*}/$(basename "${DEV_URL%%\?*}")_test}"
DB_NAME=$(basename "${DATABASE_URL%%\?*}")
if [[ "$DB_NAME" != *_test ]]; then
  echo "Menolak: database E2E harus berakhiran _test (sekarang: $DB_NAME)" >&2
  exit 1
fi
export LOCAL_STORAGE_DIR="../storage-e2e"
export STORAGE_BACKEND="local"
export E2E_PORT="${E2E_PORT:-8001}"

echo "Mengosongkan database $DB_NAME ..."
# Jejak audit append-only tidak bisa dihapus per baris, jadi seluruh skema dibuat ulang
.venv/bin/alembic downgrade base >/dev/null
.venv/bin/alembic upgrade head >/dev/null
.venv/bin/python seed.py >/dev/null
rm -rf ../storage-e2e

echo "Backend E2E siap di http://localhost:$E2E_PORT (database $DB_NAME)"
exec .venv/bin/uvicorn app.main:app --port "$E2E_PORT"
