#!/usr/bin/env bash
# Menjalankan 8 skenario UAT end-to-end (Cypress) terhadap database TERPISAH <nama>_test:
#   backend :8001 (database dikosongkan + seed ulang) → frontend :5180 → Cypress.
# Persiapan sekali:  cd backend && bash scripts/create_db.sh amiga_robot_admin_test
# Jalankan dari root repo:  bash scripts/run_e2e.sh   (tambahkan --open untuk Cypress interaktif)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/frontend/cypress/logs"
mkdir -p "$LOG_DIR"

PASSWORD=$(grep '^SEED_DEFAULT_PASSWORD=' "$ROOT/backend/.env" | cut -d= -f2-)
if [[ -z "$PASSWORD" ]]; then
  echo "SEED_DEFAULT_PASSWORD belum diisi di backend/.env" >&2
  exit 1
fi

# Setiap server berjalan di grup prosesnya sendiri (setsid) supaya proses anaknya
# (uvicorn, vite di bawah npm) ikut dihentikan saat selesai
# Port E2E harus kosong. Bila sudah dipakai proses lain (mis. dev server yang pindah port),
# test akan berjalan ke server yang salah dan mengisi database dev.
for port in 8001 5180; do
  if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "Port $port sudah dipakai proses lain. Hentikan proses itu dulu (lihat: ss -ltnp 'sport = :$port')." >&2
    exit 1
  fi
done

pids=()
cleanup() { for p in "${pids[@]}"; do kill -- "-$p" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_for() {  # url, nama, detik
  for _ in $(seq "$3"); do curl -sf -o /dev/null "$1" && return 0; sleep 1; done
  echo "$2 tidak menyala dalam $3 detik; lihat $LOG_DIR" >&2
  exit 1
}

setsid bash "$ROOT/backend/scripts/e2e_server.sh" >"$LOG_DIR/backend.log" 2>&1 &
pids+=($!)
wait_for http://localhost:8001/health "Backend E2E" 90

(cd "$ROOT/frontend" && exec setsid npm run dev:e2e) >"$LOG_DIR/frontend.log" 2>&1 &
pids+=($!)
wait_for http://localhost:5180 "Frontend E2E" 60

cd "$ROOT/frontend"
if [[ "${1:-}" == "--open" ]]; then
  CYPRESS_SEED_PASSWORD="$PASSWORD" npx cypress open --e2e
else
  # UAT dulu, lalu system testing; hasil per test disimpan sebagai JUnit XML di cypress/results/
  rm -rf cypress/results
  CYPRESS_SEED_PASSWORD="$PASSWORD" npx cypress run \
    --spec "${E2E_SPEC:-cypress/e2e/uat.cy.ts,cypress/e2e/system.cy.ts}" \
    --reporter junit --reporter-options "mochaFile=cypress/results/[hash].xml,toConsole=false"
fi
