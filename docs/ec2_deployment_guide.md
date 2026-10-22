# Panduan Lengkap Setup & Deploy AMIGA Robot Admin ke Amazon EC2

Dokumentasi ini mencakup panduan *end-to-end* implementasi, deployment, dan pemecahan masalah (*troubleshooting*) aplikasi **AMIGA Robot Admin** pada Amazon Web Services (AWS) EC2 Amazon Linux 2023.

Panduan ini disusun berdasarkan pengalaman deployment nyata yang mencakup penanganan arsitektur *single port* (Port 80), PostgreSQL lokal, integrasi AWS Bedrock via IAM Role, Telegram Bot long polling, serta troubleshooting komprehensif atas kendala lingkungan *insecure context* (HTTP) dan *proxy buffering*.

---

## Daftar Isi

1. [Arsitektur Deployment](#1-arsitektur-deployment)
2. [Prasyarat & Konfigurasi Awal AWS](#2-prasyarat--konfigurasi-awal-aws)
3. [Langkah Deployment Langkah-demi-Langkah](#3-langkah-deployment-langkah-demi-langkah)
4. [Konfigurasi Komponen Lanjutan](#4-konfigurasi-komponen-lanjutan)
   - [A. Mengatur Telegram Bot](#a-mengatur-telegram-bot)
   - [B. Menghapus / Menonaktifkan Telegram Bot](#b-menghapus--menonaktifkan-telegram-bot)
5. [Troubleshooting & Solusi Masalah Nyata](#5-troubleshooting--solusi-masalah-nyata)
   - [Kendala 1: Layar Hitam Kosong (Blank Screen) & `crypto.randomUUID is not a function`](#kendala-1-layar-hitam-kosong-blank-screen--cryptorandomuuid-is-not-a-function)
   - [Kendala 2: Error Kompilasi TypeScript (`TS1005: '}' expected`) Akibat Escaping Bash `sed`](#kendala-2-error-kompilasi-typescript-ts1005--expected-akibat-escaping-bash-sed)
   - [Kendala 3: Warning Nginx `an upstream response is buffered to a temporary file` & Ketiadaan Gzip](#kendala-3-warning-nginx-an-upstream-response-is-buffered-to-a-temporary-file--ketiadaan-gzip)
   - [Kendala 4: Peringatan PostgreSQL `could not change directory ... Permission denied`](#kendala-4-peringatan-postgresql-could-not-change-directory--permission-denied)
   - [Kendala 5: Browser Loading Selamanya / Timeout (Security Group Port 80)](#kendala-5-browser-loading-selamanya--timeout-security-group-port-80)
   - [Kendala 6: Telegram Bot Error `409 Conflict: terminated by other getUpdates request`](#kendala-6-telegram-bot-error-409-conflict-terminated-by-other-getupdates-request)
   - [Kendala 7: Error SQLAlchemy `e3q8` pada Step 5/8 (Migrasi Alembic)](#kendala-7-error-sqlalchemy-e3q8-pada-step-58-migrasi-alembic)
6. [Lembar Contek Operasional (Operational Cheat Sheet)](#6-lembar-contek-operasional-operational-cheat-sheet)

---

## 1. Arsitektur Deployment

Aplikasi didesain agar **Frontend, Backend API, Database, dan Telegram Bot** terintegrasi secara harmonis melalui satu pintu masuk publik di **Port 80 (HTTP)**:

```
                            Pengunjung / Browser Laptop
                                         │
                                         ▼ Port 80 (HTTP)
                           ┌───────────────────────────┐
                           │    Nginx Reverse Proxy    │
                           │   (Gzip + Proxy Buffers)  │
                           └─────────────┬─────────────┘
                                         │ proxy_pass http://127.0.0.1:3000
                                         ▼
                           ┌───────────────────────────┐
                           │   Uvicorn (app.serve:app) │
                           ├─────────────┬─────────────┤
                           │  Frontend   │ Backend API │
                           │ (React SPA) │   (/api/*)  │
                           └─────────────┴──────┬──────┘
                                                │
                   ┌────────────────────────────┼───────────────────────────┐
                   ▼                            ▼                           ▼
          ┌─────────────────┐          ┌─────────────────┐         ┌─────────────────┐
          │ PostgreSQL 15   │          │  AWS Bedrock    │         │ Telegram Bot    │
          │ 127.0.0.1:5432  │          │  (IAM Role EC2) │         │ (Long Polling)  │
          │ (Aman, Internal)│          │  (Nova & Titan) │         │ (Outbound HTTPS)│
          └─────────────────┘          └─────────────────┘         └─────────────────┘
```

- **Port 80 (Nginx)**: Menerima seluruh lalu lintas publik web browser, mengompres respons via Gzip, dan meneruskannya ke port lokal `3000`.
- **Port 3000 (`backend/app/serve.py`)**: Proses terpadu FastAPI yang:
  - Menyajikan antarmuka frontend React statis (`frontend/dist`) di root path (`/`).
  - Me-mount API FastAPI di jalur `/api/*`.
- **PostgreSQL 15**: Berjalan di `127.0.0.1:5432` secara terisolasi. Tidak dibuka ke internet demi keamanan.
- **Amazon Bedrock**: Diakses tanpa `AWS_ACCESS_KEY` menggunakan kredensial otomatis dari **IAM Instance Profile / IAM Role** yang terpasang pada EC2.
- **Telegram Bot (`bot.telegram_bot`)**: Menggunakan **long polling** (koneksi HTTPS keluar ke `api.telegram.org`), sehingga tidak membutuhkan port inbound khusus.

---

## 2. Prasyarat & Konfigurasi Awal AWS

### A. Konfigurasi EC2 Security Group
Sebelum mengakses aplikasi dari internet, pastikan **Security Group** instance mengizinkan lalu lintas Port 80:
1. Buka AWS Console > **EC2** > **Instances** > Pilih instance Anda.
2. Buka tab **Security** > Klik nama **Security groups**.
3. Di tab **Inbound rules**, klik **Edit inbound rules**.
4. Tambahkan rule berikut:
   - **Type**: `HTTP`
   - **Port range**: `80`
   - **Protocol**: `TCP`
   - **Source**: `0.0.0.0/0` (Anywhere-IPv4)
5. Klik **Save rules**.

### B. Pastikan IAM Role Terpasang
Instance EC2 harus memiliki IAM Role yang memiliki policy izin untuk Amazon Bedrock:
- `bedrock:InvokeModel` (Model: `us.amazon.nova-lite-v1:0` dan `amazon.titan-embed-text-v2:0` di region `us-east-1` atau `ap-southeast-1`).
- Jangan pernah memasukkan `AWS_ACCESS_KEY_ID` atau `AWS_SECRET_ACCESS_KEY` ke dalam file `.env` server.

---

## 3. Langkah Deployment Langkah-demi-Langkah

Semua perintah dijalankan melalui **AWS Systems Manager (SSM) Session Manager Terminal**.

### Langkah 1: Beralih ke User `ec2-user`
Ketika membuka Session Manager, Anda akan login sebagai `ssm-user`. Wajib beralih ke `ec2-user`:
```bash
sudo su - ec2-user
cloud-init status --wait
```
> **Catatan:** `cloud-init status --wait` memastikan OS selesai melakukan inisialisasi awal paket dnf/yum.

### Langkah 2: Clone Repository
```bash
git clone https://github.com/halvrenvaire/AMIGA-ADMIN-ROBOT-TIM11-.git
cd AMIGA-ADMIN-ROBOT-TIM11-
```
*(Bila repository bersifat privat, masukkan username GitHub dan Personal Access Token (PAT) saat diminta)*.

### Langkah 3: Eksekusi Skrip Otomatisasi Deploy
Jalankan skrip deployment bawaan:
```bash
bash scripts/deploy_ec2.sh
```

Skrip ini secara otomatis:
1. Membuat **Swap Memory 2 GB** (mencegah proses build dan instalasi dependensi terkena status *Killed/Out of Memory*).
2. Memasang paket sistem: Git, Python 3.12/3.11, PostgreSQL 15, dan Nginx.
3. Menginisialisasi PostgreSQL lokal dengan autentikasi `scram-sha-256`.
4. Membuat file `backend/.env` dengan rahasia acak (`JWT_SECRET`, password database, dll).
5. Memasang dependensi Python di virtualenv `.venv`, menjalankan migrasi Alembic, dan seeding data dummy (`seed.py`).
6. Memvalidasi koneksi ke Amazon Bedrock via IAM Role.
7. Memasang Node.js 22 via nvm dan mem-build frontend ke `frontend/dist`.
8. Menjalankan Uvicorn di `127.0.0.1:3000` dan mengonfigurasi Nginx di port 80.

> **PENTING:** Di baris paling akhir, terminal akan mencetak **Password akun dummy**. Salin password tersebut untuk login.

---

## 4. Konfigurasi Komponen Lanjutan

### A. Mengatur Telegram Bot
Secara default, token Telegram di `.env` masih kosong sehingga bot belum aktif. Untuk menyalakannya:

1. Buka file konfigurasi `.env`:
   ```bash
   nano backend/.env
   ```
2. Isi `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_BOT_USERNAME`:
   ```ini
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklmnoPQRstuVWXyz
   TELEGRAM_BOT_USERNAME=amiga_online_ro_bot
   ```
   *(Gunakan username bot tanpa awalan `@`)*.
3. Simpan file (`Ctrl+O`, `Enter`, lalu `Ctrl+X`).
4. Restart server backend agar FastAPI memuat token Telegram baru dari `.env`:
   ```bash
   kill $(cat ~/app.pid) 2>/dev/null || true
   cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend
   nohup .venv/bin/uvicorn app.serve:app --host 127.0.0.1 --port 3000 --proxy-headers --forwarded-allow-ips 127.0.0.1 > ~/app.log 2>&1 &
   echo $! > ~/app.pid
   ```
5. Jalankan bot di background:
   ```bash
   cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend
   nohup .venv/bin/python -m bot.telegram_bot > ~/bot.log 2>&1 &
   echo $! > ~/bot.pid
   ```
6. Pantau log bot:
   ```bash
   tail -f ~/bot.log
   ```

### B. Menghapus / Menonaktifkan Telegram Bot
Jika ingin aplikasi web berjalan murni tanpa bot Telegram:
1. Hentikan proses bot:
   ```bash
   pkill -f "bot.telegram_bot" 2>/dev/null || true
   rm -f ~/bot.pid
   ```
2. Kosongkan nilai token di `backend/.env`:
   ```bash
   sed -i 's|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=|' ~/AMIGA-ADMIN-ROBOT-TIM11-/backend/.env
   ```
3. Restart server backend:
   ```bash
   kill $(cat ~/app.pid) 2>/dev/null || true
   cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend
   nohup .venv/bin/uvicorn app.serve:app --host 127.0.0.1 --port 3000 --proxy-headers --forwarded-allow-ips 127.0.0.1 > ~/app.log 2>&1 &
   echo $! > ~/app.pid
   ```

---

## 5. Troubleshooting & Solusi Masalah Nyata

Berikut adalah dokumentasi kendala nyata yang ditemukan saat proses deployment beserta solusi tuntasnya:

---

### Kendala 1: Layar Hitam Kosong (Blank Screen) & `crypto.randomUUID is not a function`

#### Gejala
- Login berhasil dilakukan di `/login`.
- URL berpindah ke `/dashboard`.
- Halaman browser menampilkan **layar hitam kosong pekat** tanpa sidebar, navbar, atau teks apa pun.
- Di konsol Developer Tools (F12) muncul error:
  ```text
  Uncaught TypeError: crypto.randomUUID is not a function
      at Vo (index-Dq7nX541.js:11:58487)
      at xs (index-Dq7nX541.js:8:54005)
      at Object.useState (index-Dq7nX541.js:8:62048)
  ```

#### Penyebab
Spesifikasi Web Cryptography API membatasi fungsi `crypto.randomUUID()` **hanya untuk Secure Contexts** (`https://` atau `http://localhost`). Ketika aplikasi diakses melalui IP publik dengan HTTP biasa (`http://13.214.210.41/`), browser menganggap konteks tidak aman (*insecure*) sehingga `crypto.randomUUID` bernilai `undefined`.

Di dalam file `frontend/src/components/Assistant.tsx`, fungsi ini dipanggil pada inisialisasi state widget:
```ts
export const newSession = () => `web-${crypto.randomUUID()}`;
```
Karena komponen `Assistant` dimuat di dalam `Layout.tsx` yang membungkus semua halaman, React mengalami *fatal error* dan gagal merender seluruh DOM pohon aplikasi.

#### Solusi Tuntas
Ganti baris `newSession` pada [`frontend/src/components/Assistant.tsx`](file:///d:/Naufal/Personal/Own%20Project/belajar/main-alkademi/hackathon-main/AMIGA-ADMIN-ROBOT-TIM11-/frontend/src/components/Assistant.tsx#L24-L35) dengan fungsi fallback mandiri yang kompatibel dengan protokol HTTP:

```typescript
function genUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const newSession = () => `web-${genUUID()}`;
```

Setelah mengubah kode, lakukan build ulang frontend:
```bash
cd ~/AMIGA-ADMIN-ROBOT-TIM11-/frontend
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use 22
NODE_OPTIONS=--max-old-space-size=1536 npm run build
```

---

### Kendala 2: Error Kompilasi TypeScript (`TS1005: '}' expected`) Akibat Escaping Bash `sed`

#### Gejala
Saat menjalankan `npm run build`, muncul error:
```text
src/components/Assistant.tsx:24:70 - error TS1005: '}' expected.
24 export const newSession = () => `web-${typeof crypto !== "undefined" export const newSession = () => ...
```

#### Penyebab
Menggunakan perintah `sed -i` di terminal Bash yang berisi karakter template literal (`` ` ``) dan ekspresi `${...}` menyebabkan Bash salah menginterpretasikan tanda kurung kurawal sebagai *variable substitution*. Baris kode akhirnya ter-paste secara berulang dan merusak sintaks TypeScript.

#### Solusi Tuntas
Hindari penggunaan one-liner `sed` untuk kode JavaScript kompleks. Gunakan skrip Python inline dengan *quoted heredoc* (`<< 'EOF'`) yang kebal terhadap escaping shell:

```bash
cd ~/AMIGA-ADMIN-ROBOT-TIM11-/frontend
git checkout src/components/Assistant.tsx

python3 - << 'EOF'
with open("src/components/Assistant.tsx", "r", encoding="utf-8") as f:
    text = f.read()

old_target = "export const newSession = () => `web-${crypto.randomUUID()}`;"
replacement = """function genUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const newSession = () => `web-${genUUID()}`;"""

if old_target in text:
    text = text.replace(old_target, replacement)
    with open("src/components/Assistant.tsx", "w", encoding="utf-8") as f:
        f.write(text)
    print("✓ Berhasil patch Assistant.tsx")
EOF
```

---

### Kendala 3: Warning Nginx `an upstream response is buffered to a temporary file` & Ketiadaan Gzip

#### Gejala
Di log `/var/log/nginx/error.log` muncul peringatan:
```text
[warn] 37011#37011: *20 an upstream response is buffered to a temporary file /var/lib/nginx/tmp/proxy/... while reading upstream, client: ..., request: "GET /assets/Metrics-DnsyPulC.js"
```

#### Penyebab
1. Default buffer RAM Nginx (`proxy_buffer_size`) hanya 4 KB/8 KB.
2. File chunk frontend yang besar (seperti Recharts atau bundle utama berukuran > 300 KB) melebihi kapasitas buffer RAM, sehingga Nginx terpaksa menulis ke disk sementara.
3. Ketiadaan kompresi **Gzip** membuat browser klien mengunduh file JS mentah berukuran besar, berpotensi memicu transfer terputus (*`ERR_INCOMPLETE_CHUNKED_ENCODING`*).

#### Solusi Tuntas
Perbarui file `/etc/nginx/nginx.conf` dengan menambahkan konfigurasi Gzip dan alokasi buffer proxy RAM yang memadai (1 MB):

```bash
sudo tee /etc/nginx/nginx.conf > /dev/null << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log notice;
pid /run/nginx.pid;
events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log /var/log/nginx/access.log;
    sendfile on;
    server_tokens off;

    # 1. Kompresi Gzip: Mengurangi ukuran transfer JS/CSS hingga 70-80%
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;
    gzip_min_length 1024;

    server {
        listen 80 default_server;
        server_name _;
        client_max_body_size 110m;

        # 2. Buffer RAM agar response upstream tidak ditulis ke disk temporer
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 8 128k;
        proxy_busy_buffers_size 256k;

        location / {
            proxy_pass http://127.0.0.1:3000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 180s;
            proxy_send_timeout 180s;
        }
    }
}
EOF

sudo nginx -t && sudo systemctl restart nginx
```

---

### Kendala 4: Peringatan PostgreSQL `could not change directory ... Permission denied`

#### Gejala
Saat eksekusi skrip deploy muncul log:
```text
could not change directory to "/home/ec2-user/AMIGA-ADMIN-ROBOT-TIM11-": Permission denied
✓ PostgreSQL 15.19 berjalan
✓ Database amiga_robot_admin dan user amiga siap
```

#### Analisis & Solusi
Pesan ini muncul karena `sudo -u postgres psql ...` dijalankan saat direktori aktif berada di dalam `/home/ec2-user`. Linux membatasi user `postgres` membuka direktori home milik `ec2-user`.

> **Status:** Peringatan ini **TIDAK berbahaya**. Eksekusi SQL berhasil 100% via stdin pipes. Jika ingin menghilangkan warning ini sepenuhnya, skrip dapat berpindah ke folder `/tmp` sebelum memanggil `sudo -u postgres`.

---

### Kendala 5: Browser Loading Selamanya / Timeout (Security Group Port 80)

#### Gejala
Browser laptop berputar tanpa henti (*infinite loading*) lalu berakhir dengan pesan `ERR_CONNECTION_TIMED_OUT`.

#### Solusi
Buka AWS Management Console > EC2 > Security Groups. Pastikan port **80 (HTTP)** telah diizinkan dari sumber `0.0.0.0/0`. Periksa juga apakah firewall instance (iptables/firewalld) aktif dan memblokir port tersebut:
```bash
sudo iptables -L -n | grep 80
```

---

### Kendala 6: Telegram Bot Error `409 Conflict: terminated by other getUpdates request`

#### Gejala
Di log `~/bot.log` muncul error berulang:
```text
httpx.HTTPStatusError: Client error '409 Conflict' for url 'https://api.telegram.org/bot.../getUpdates'
```

#### Penyebab
Telegram Bot API melarang lebih dari satu proses melakukan *long polling* secara bersamaan pada token bot yang sama. Hal ini biasa terjadi jika bot masih berjalan di laptop lokal pengembang saat bot di server EC2 dinyalakan.

#### Solusi
1. Matikan bot di laptop lokal Anda (Ctrl+C di terminal lokal).
2. Di server EC2, restart bot:
   ```bash
   pkill -f "bot.telegram_bot" 2>/dev/null || true
   cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend
   nohup .venv/bin/python -m bot.telegram_bot > ~/bot.log 2>&1 &
   echo $! > ~/bot.pid
   ```

---

### Kendala 7: Error SQLAlchemy `e3q8` pada Step 5/8 (Migrasi Alembic)

#### Gejala
Pada saat eksekusi `bash scripts/deploy_ec2.sh`, proses terhenti mendadak di langkah `5/8` dengan output hanya berupa satu baris URL:
```text
==> 5/8 Backend: dependensi, migrasi database, data dummy
(Background on this error at: https://sqlalche.me/e/20/e3q8)
```

#### Penyebab
1. **Penyembunyian Log Error (`tail -1`)**: Di skrip `deploy_ec2.sh`, pemanggilan `.venv/bin/alembic upgrade head` di-pipe ke `tail -1`. Akibatnya, seluruh jejak pesan error (traceback) terpotong dan hanya baris penutup SQLAlchemy yang tercetak ke layar.
2. **Kredensial Database Tidak Cocok**: Tautan `https://sqlalche.me/e/20/e3q8` merujuk pada **`OperationalError`** (koneksi/autentikasi database gagal). Ini terjadi apabila file `backend/.env` sudah ada sebelum skrip berjalan (misalnya hasil *copy-paste* dari laptop lokal) yang menggunakan user `postgres` (misal: `DATABASE_URL=postgresql+psycopg://postgres:a@localhost:5432/...`). Sedangkan di EC2, PostgreSQL dikonfigurasi dengan user **`amiga`** dan otentikasi kata sandi `scram-sha-256`. Saat Alembic mencoba login dengan user `postgres`, PostgreSQL menolaknya (*password authentication failed*).

#### Solusi
- **Solusi Utama (Rekomendasi)**: Hapus file `backend/.env` di EC2 lalu jalankan ulang skrip deploy agar skrip men-generate kredensial resmi secara otomatis:
  ```bash
  rm ~/AMIGA-ADMIN-ROBOT-TIM11-/backend/.env
  bash scripts/deploy_ec2.sh
  ```
- **Solusi Alternatif (Manual)**: Buka `backend/.env` di EC2 dan sesuaikan user di `DATABASE_URL` agar menggunakan user `amiga`:
  ```ini
  DATABASE_URL=postgresql+psycopg://amiga:<password_amiga>@127.0.0.1:5432/amiga_robot_admin
  ```

---

## 6. Lembar Contek Operasional (Operational Cheat Sheet)

Gunakan perintah-perintah berikut untuk pemeliharaan rutin di terminal SSM EC2:

| Kebutuhan | Perintah Terminal |
| :--- | :--- |
| **Cek Log Backend (Uvicorn)** | `tail -f ~/app.log` |
| **Cek Log Telegram Bot** | `tail -f ~/bot.log` |
| **Cek Log Error Nginx** | `sudo tail -f /var/log/nginx/error.log` |
| **Cek Log Akses Nginx** | `sudo tail -f /var/log/nginx/access.log` |
| **Cek Status Service Nginx** | `sudo systemctl status nginx` |
| **Cek Status Database Lokal** | `sudo -u postgres psql -c "SELECT version();"` |
| **Health Check API Internal** | `curl -s http://127.0.0.1/api/health \| jq .` |
| **Melihat Password Akun Dummy** | `grep SEED_DEFAULT_PASSWORD ~/AMIGA-ADMIN-ROBOT-TIM11-/backend/.env` |
| **Restart Backend Cepat (1 Detik)** | `kill $(cat ~/app.pid) 2>/dev/null; cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend && nohup .venv/bin/uvicorn app.serve:app --host 127.0.0.1 --port 3000 --proxy-headers --forwarded-allow-ips 127.0.0.1 > ~/app.log 2>&1 & echo $! > ~/app.pid` |
| **Restart Bot Telegram** | `kill $(cat ~/bot.pid) 2>/dev/null; cd ~/AMIGA-ADMIN-ROBOT-TIM11-/backend && nohup .venv/bin/python -m bot.telegram_bot > ~/bot.log 2>&1 & echo $! > ~/bot.pid` |
| **Update Aplikasi Pasca Git Pull** | `cd ~/AMIGA-ADMIN-ROBOT-TIM11- && git pull && bash scripts/deploy_ec2.sh` |
