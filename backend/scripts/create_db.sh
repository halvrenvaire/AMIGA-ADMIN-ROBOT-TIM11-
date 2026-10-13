#!/usr/bin/env bash
# Membuat role & database PostgreSQL lokal sesuai DATABASE_URL di backend/.env.
# Jalankan dari folder backend/:  bash scripts/create_db.sh   (akan meminta password sudo)
set -euo pipefail
cd "$(dirname "$0")/.."
URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
read -r DB_USER DB_PASS DB_NAME < <(python3 - "$URL" <<'PY'
import sys
from urllib.parse import urlparse, unquote
u = urlparse(sys.argv[1])
print(unquote(u.username), unquote(u.password), u.path.lstrip("/"))
PY
)
sudo -u postgres psql -v ON_ERROR_STOP=1 -v u="$DB_USER" -v p="$DB_PASS" -v d="$DB_NAME" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'u', :'p')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'u') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'d', :'u')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'d') \gexec
SQL
echo "Selesai: role '$DB_USER' dan database '$DB_NAME' siap."
