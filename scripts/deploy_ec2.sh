#!/usr/bin/env bash
# Deploy AMIGA Robot Admin ke EC2 (Amazon Linux 2023), sesuai panduan "Deploy aplikasi ke EC2".
#
# Jalankan dari terminal Session Manager, sebagai ec2-user, di root repo hasil git clone:
#     bash scripts/deploy_ec2.sh            # port 3000
#     PORT=3001 bash scripts/deploy_ec2.sh  # bila mentor memberi port lain
# Aman dijalankan ulang (juga untuk update setelah `git pull`): langkah yang sudah selesai dilewati.
#
# Yang dilakukan:
#   1. Swap 2 GB (server 1 GB RAM)          5. Backend: venv, pip install, migrasi, data dummy
#   2. Paket: git, Python, PostgreSQL 15     6. Cek akses Bedrock lewat IAM role server
#   3. PostgreSQL di 127.0.0.1 + database    7. Frontend: Node 22, npm run build
#   4. backend/.env (tanpa access key AWS)   8. Jalankan di 0.0.0.0:$PORT, lalu tes
set -euo pipefail

PORT="${PORT:-3000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
ENV_FILE="$BACKEND/.env"
DB_NAME="amiga_robot_admin"
DB_USER="amiga"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok() { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
rand() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
env_get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true; }
env_set() {  # ganti atau tambah KEY=VALUE di .env
  if grep -qE "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >> "$ENV_FILE"; fi
}

if [ "$(id -un)" = "root" ]; then fail "Jangan jalankan sebagai root. Jalankan dulu: sudo su - ec2-user"; fi
command -v dnf >/dev/null || fail "Skrip ini untuk server Amazon Linux 2023 (dnf)."
if command -v cloud-init >/dev/null; then cloud-init status --wait >/dev/null 2>&1 || true; fi

# --- 1. Swap -----------------------------------------------------------------
step "1/8 Swap 2 GB (supaya pip install dan npm run build tidak 'Killed')"
if [ "$(awk '/SwapTotal/ {print $2}' /proc/meminfo)" -lt 1000000 ]; then
  if [ ! -f /swapfile ]; then
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
  fi
  sudo swapon /swapfile 2>/dev/null || true
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi
ok "Swap: $(free -h | awk '/Swap/ {print $2}')"

# --- 2. Paket ----------------------------------------------------------------
step "2/8 Paket: git, Python 3.12/3.11, PostgreSQL 15"
sudo dnf install -y -q git postgresql15-server postgresql15 >/dev/null
if ! command -v python3.12 >/dev/null && ! command -v python3.11 >/dev/null; then
  sudo dnf install -y -q python3.12 python3.12-pip >/dev/null 2>&1 \
    || sudo dnf install -y -q python3.11 python3.11-pip >/dev/null
fi
PY="$(command -v python3.12 || command -v python3.11)" || fail "Python 3.11/3.12 tidak bisa dipasang."
ok "$($PY --version) di $(uname -m)"

# --- 3. PostgreSQL -----------------------------------------------------------
step "3/8 PostgreSQL (hanya 127.0.0.1, port 5432 tidak dibuka ke internet)"
if ! sudo test -f /var/lib/pgsql/data/PG_VERSION; then
  sudo postgresql-setup --initdb >/dev/null
fi
HBA=/var/lib/pgsql/data/pg_hba.conf
# Bawaan Amazon Linux memakai "ident" untuk 127.0.0.1, sehingga aplikasi tidak bisa login dengan password
if sudo grep -qE '^host\s.*\s(ident|trust)\s*$' "$HBA"; then
  sudo sed -i -E 's/^(host\s.*\s)(ident|trust)\s*$/\1scram-sha-256/' "$HBA"
  NEED_RESTART=1
fi
sudo systemctl enable --now postgresql >/dev/null 2>&1
if [ "${NEED_RESTART:-0}" = 1 ]; then sudo systemctl restart postgresql; fi
ok "PostgreSQL $(sudo -u postgres psql -tAc 'show server_version') berjalan"

# --- 4. backend/.env ---------------------------------------------------------
step "4/8 Konfigurasi backend/.env (tanpa access key AWS: server memakai IAM role)"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  cat > "$ENV_FILE" <<EOF
# Dibuat oleh scripts/deploy_ec2.sh. Jangan commit file ini.
DATABASE_URL=postgresql+psycopg://$DB_USER:$(rand 24)@127.0.0.1:5432/$DB_NAME
JWT_SECRET=$(rand 48)
SEED_DEFAULT_PASSWORD=$(rand 12)
REINDEX_API_KEY=$(rand 24)

# AWS: kredensial dari IAM role server (JANGAN isi access key di sini)
AWS_REGION=us-east-1
AWS_BUCKET=
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=../storage
# Nova Lite (bisa membaca PDF/foto invoice). Nova Micro hanya teks, tidak bisa membaca invoice.
LLM_MODEL=us.amazon.nova-lite-v1:0
LLM_REGION=us-east-1
EMBED_MODEL=amazon.titan-embed-text-v2:0
EMBED_REGION=us-east-1

# Bot Telegram (opsional): isi token lalu jalankan ulang skrip ini
TELEGRAM_BOT_TOKEN=
EOF
  ok "backend/.env dibuat dengan rahasia acak"
else
  ok "backend/.env sudah ada, dipakai ulang"
fi
chmod 600 "$ENV_FILE"
for key in AWS_ACCESS_KEY AWS_SECRET_ACCESS_KEY AWS_PROFILE AWS_ACCESS_KEY_ID; do
  if [ -n "$(env_get "$key")" ]; then
    fail "$key terisi di backend/.env. Hapus nilainya: server harus memakai IAM role, bukan access key."
  fi
done
IMDS_TOKEN="$(curl -s -m 3 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' || true)"
PUBLIC_IP="$(curl -s -m 3 -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)"
[ -n "$PUBLIC_IP" ] || PUBLIC_IP="IP-PUBLIK"
# IP publik berubah setiap server di-stop/start: tautan di pesan bot ikut diperbarui
env_set FRONTEND_URL "http://$PUBLIC_IP:$PORT"
env_set BOT_API_BASE_URL "http://127.0.0.1:$PORT/api"
ok "Alamat aplikasi: http://$PUBLIC_IP:$PORT"

DB_PASS="$(env_get DATABASE_URL | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')"
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -v u="$DB_USER" -v p="$DB_PASS" -v d="$DB_NAME" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'u', :'p')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'u') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'u', :'p') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'d', :'u')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'d') \gexec
SQL
ok "Database $DB_NAME dan user $DB_USER siap"

# --- 5. Backend --------------------------------------------------------------
step "5/8 Backend: dependensi, migrasi database, data dummy"
cd "$BACKEND"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/alembic upgrade head 2>&1 | tail -1
.venv/bin/python seed.py > /tmp/amiga-seed.log
head -1 /tmp/amiga-seed.log

# --- 6. Bedrock --------------------------------------------------------------
step "6/8 Cek akses Amazon Bedrock lewat IAM role server"
if .venv/bin/python - <<'PY'
from app.config import settings
from app.services.bedrock_client import BedrockClient
b = BedrockClient()
assert len(b.embed("tes")) == settings.embed_dimension
assert b.generate("Jawab satu kata.", [{"role": "user", "content": "halo"}], max_tokens=5)
print(f"    LLM {settings.llm_model} dan embedding {settings.embed_model} di {settings.llm_region}")
PY
then ok "Bedrock bisa dipanggil"
else warn "Bedrock GAGAL dipanggil. Aplikasi tetap jalan, tapi AI tidak berfungsi. Kirim error di atas ke mentor."
fi

# --- 7. Frontend -------------------------------------------------------------
step "7/8 Frontend: Node 22 dan npm run build"
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] || curl -s -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash >/dev/null
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
nvm install 22 >/dev/null 2>&1 && nvm use 22 >/dev/null
cd "$ROOT/frontend"
npm ci --no-audit --no-fund --loglevel=error
NODE_OPTIONS=--max-old-space-size=1536 npm run build >/dev/null
ok "Frontend di-build ke frontend/dist"

# --- 8. Jalankan -------------------------------------------------------------
step "8/8 Menjalankan aplikasi di 0.0.0.0:$PORT"
stop() { if [ -f "$1" ]; then kill "$(cat "$1")" 2>/dev/null || true; rm -f "$1"; fi; }
stop ~/app.pid
pkill -f "uvicorn app.serve:app" 2>/dev/null || true
sleep 1
cd "$BACKEND"
nohup .venv/bin/uvicorn app.serve:app --host 0.0.0.0 --port "$PORT" > ~/app.log 2>&1 &
echo $! > ~/app.pid
for _ in $(seq 1 90); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/api/health" && break
  sleep 1
done
CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/")"
[ "$CODE" = 200 ] || fail "Aplikasi tidak merespons (HTTP $CODE). Lihat log: tail -n 50 ~/app.log"
ok "curl -I http://localhost:$PORT → 200 OK"
HEALTH="$(curl -s "http://127.0.0.1:$PORT/api/health")"
ok "Health: $HEALTH"

if [ -n "$(env_get TELEGRAM_BOT_TOKEN)" ]; then
  stop ~/bot.pid
  pkill -f "bot.telegram_bot" 2>/dev/null || true
  nohup .venv/bin/python -m bot.telegram_bot > ~/bot.log 2>&1 &
  echo $! > ~/bot.pid
  ok "Bot Telegram berjalan (log: ~/bot.log). Pastikan bot TIDAK sedang berjalan di laptop lain."
fi

cat <<EOF

$(printf '\033[1;32m')Deploy selesai.$(printf '\033[0m')
  Buka di browser laptop : http://$PUBLIC_IP:$PORT   (http, bukan https)
  Dokumentasi API        : http://$PUBLIC_IP:$PORT/api/docs
  Login akun dummy       : pic.alpha@amiga.test, reviewer1@amiga.test, lead@amiga.test, admin@amiga.test, ...
  Password akun dummy    : $(env_get SEED_DEFAULT_PASSWORD)   (jangan dibagikan di grup)
  Log aplikasi           : tail -f ~/app.log
  Update setelah git pull: bash scripts/deploy_ec2.sh
  Lapor ke form          : IP $PUBLIC_IP, port $PORT
EOF
