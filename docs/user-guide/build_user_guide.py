"""Membuat User Guide Book AMIGA Robot Admin (PDF).

Jalankan dari folder induk repo:
    backend/.venv/bin/python docs/user-guide/build_user_guide.py

Hasil: readme/User_Guide_Book_AMIGA_Robot_Admin_v4.0.pdf. Gambar diambil dari docs/user-guide/img/ (screenshot
aplikasi). Font: Noto Sans atau DejaVu Sans dari sistem (Linux: paket fonts-noto-core / fonts-dejavu).
"""
import re
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

ROOT = Path(__file__).resolve().parents[2]
IMG = Path(__file__).resolve().parent / "img"
OUT = ROOT / "readme" / "User_Guide_Book_AMIGA_Robot_Admin_v4.0.pdf"
LOGO = ROOT / "frontend" / "public" / "brand" / "logo-amiga.png"
VERSION, UPDATED = "4.0", "26 Oktober 2026"

PRIMARY = (54, 127, 137)
DARK = (17, 34, 38)
MUTED = (90, 105, 110)
LIGHT = (234, 243, 244)
CODE_BG = (243, 245, 246)

FONT_DIRS = [Path("/usr/share/fonts/truetype/noto"), Path("/usr/share/fonts/noto"), Path("/usr/share/fonts/truetype/dejavu"),
             Path("/Library/Fonts"), Path("C:/Windows/Fonts")]
FONT_SETS = [("NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSans-Italic.ttf", "NotoSansMono-Regular.ttf"),
             ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSansMono.ttf")]


def find_fonts() -> tuple[Path, Path, Path, Path]:
    for names in FONT_SETS:
        for d in FONT_DIRS:
            paths = [d / n for n in names]
            if all(p.exists() for p in paths):
                return tuple(paths)  # type: ignore[return-value]
    raise SystemExit("Font Noto Sans / DejaVu Sans tidak ditemukan. Pasang paket fonts-noto-core atau fonts-dejavu.")


def plain(text: str) -> str:
    """Tanda kode Markdown (`...`) tidak didukung fpdf: dibuang, teksnya tetap."""
    text = text.replace("`", "")
    # *miring* satu bintang juga tidak didukung; **tebal** tetap
    return re.sub(r"(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)", r"\1", text)


class Guide(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        regular, bold, italic, mono = find_fonts()
        self.add_font("body", "", regular)
        self.add_font("body", "B", bold)
        self.add_font("body", "I", italic)
        self.add_font("mono", "", mono)
        self.set_auto_page_break(True, margin=18)
        self.set_margins(18, 18, 18)
        self.set_title("User Guide Book AMIGA Robot Admin")
        self.set_author("Kelompok 11 · MAIN Hackathon 2026")
        self.set_subject("Panduan instalasi, konfigurasi, menjalankan, dan memakai AMIGA Robot Admin")
        self.chapter_no = 0
        self.section_no = 0
        self.figure_no = 0

    def multi_cell(self, *args, **kwargs):
        # Setelah satu paragraf, kursor kembali ke margin kiri baris berikutnya
        if len(args) >= 3 and isinstance(args[2], str):
            args = (*args[:2], plain(args[2]), *args[3:])
        kwargs.setdefault("new_x", XPos.LMARGIN)
        kwargs.setdefault("new_y", YPos.NEXT)
        return super().multi_cell(*args, **kwargs)

    # --- kepala dan kaki halaman ---
    def header(self):
        if self.page_no() <= 1:
            return
        self.set_y(8)
        self.set_font("body", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"AMIGA Robot Admin · User Guide Book v{VERSION}", align="L")
        self.set_y(20)

    def footer(self):
        if self.page_no() <= 1:
            return
        self.set_y(-12)
        self.set_font("body", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Halaman {self.page_no()}", align="R")

    # --- blok isi ---
    def chapter(self, title: str):
        self.add_page()
        self.chapter_no += 1
        self.section_no = 0
        full = f"{self.chapter_no}. {title}"
        self.start_section(full, level=0)
        self.set_fill_color(*PRIMARY)
        self.rect(self.l_margin, self.get_y(), 14, 1.6, style="F")
        self.ln(5)
        self.set_font("body", "B", 20)
        self.set_text_color(*DARK)
        self.multi_cell(0, 10, full)
        self.ln(2)

    def section(self, title: str):
        self.section_no += 1
        full = f"{self.chapter_no}.{self.section_no} {title}"
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(3)
        self.start_section(full, level=1)
        self.set_font("body", "B", 13)
        self.set_text_color(*PRIMARY)
        self.multi_cell(0, 7, full)
        self.ln(1)

    def sub(self, title: str):
        if self.get_y() > self.h - 40:
            self.add_page()
        self.ln(1)
        self.set_font("body", "B", 10.5)
        self.set_text_color(*DARK)
        self.multi_cell(0, 6, title)

    def p(self, text: str):
        self.set_font("body", "", 10)
        self.set_text_color(*DARK)
        self.multi_cell(0, 5.4, text, markdown=True)
        self.ln(1.8)

    def bullets(self, items: list[str], numbered: bool = False):
        self.set_font("body", "", 10)
        self.set_text_color(*DARK)
        for i, item in enumerate(items, start=1):
            mark = f"{i}." if numbered else "•"
            x = self.l_margin
            self.set_x(x + 2)
            self.cell(6, 5.4, mark)
            self.set_x(x + 8)
            self.multi_cell(self.epw - 8, 5.4, item, markdown=True)
            self.ln(0.6)
        self.ln(1.2)

    def code(self, lines: list[str]):
        self.set_font("mono", "", 8.6)
        self.set_text_color(*DARK)
        self.set_fill_color(*CODE_BG)
        h = 4.4 * len(lines) + 4
        if self.get_y() + h > self.h - 18:
            self.add_page()
        y = self.get_y()
        self.rect(self.l_margin, y, self.epw, h, style="F")
        self.set_y(y + 2)
        for line in lines:
            self.set_x(self.l_margin + 3)
            self.cell(self.epw - 6, 4.4, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y + h + 2.5)

    def note(self, text: str, kind: str = "info"):
        color = {"info": PRIMARY, "warn": (190, 120, 20)}[kind]
        self.set_font("body", "", 9.5)
        self.set_text_color(*DARK)
        self.set_fill_color(*LIGHT if kind == "info" else (252, 243, 225))
        x, y = self.l_margin, self.get_y()
        # tinggi kotak: tulis dulu tanpa menampilkan, lalu gambar latar
        lines = self.multi_cell(self.epw - 8, 5, text, markdown=True, dry_run=True, output="LINES")
        h = 5 * len(lines) + 4
        if y + h > self.h - 18:
            self.add_page()
            y = self.get_y()
        self.rect(x, y, self.epw, h, style="F")
        self.set_fill_color(*color)
        self.rect(x, y, 1.4, h, style="F")
        self.set_xy(x + 5, y + 2)
        self.multi_cell(self.epw - 8, 5, text, markdown=True)
        self.set_y(y + h + 3)

    def grid(self, rows: list[list[str]], widths: tuple[float, ...], font_size: float = 9):
        self.set_font("body", "", font_size)
        self.set_text_color(*DARK)
        self.set_x(self.l_margin)
        self.set_draw_color(215, 222, 224)
        head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=PRIMARY)
        with self.table(col_widths=widths, headings_style=head, line_height=4.8, padding=1.6,
                        cell_fill_color=(244, 248, 248), cell_fill_mode="EVEN_ROWS", borders_layout="HORIZONTAL_LINES",
                        markdown=True) as t:
            for row in rows:
                r = t.row()
                for c in row:
                    r.cell(plain(c))
        self.ln(3)

    def figure(self, name: str, caption: str, width: float | None = None):
        path = IMG / name
        width = width or self.epw
        from PIL import Image
        w_px, h_px = Image.open(path).size
        h = width * h_px / w_px
        if self.get_y() + h + 10 > self.h - 18:
            self.add_page()
        x = self.l_margin + (self.epw - width) / 2
        y = self.get_y()
        self.image(str(path), x=x, y=y, w=width)
        self.set_draw_color(215, 222, 224)
        self.rect(x, y, width, h)
        self.set_y(y + h + 1.5)
        self.figure_no += 1
        self.set_font("body", "I", 8.5)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 4.5, f"Gambar {self.figure_no}. {caption}", align="C")
        self.ln(3)


def render_toc(pdf: Guide, outline):
    pdf.set_font("body", "B", 20)
    pdf.set_text_color(*DARK)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 12, "Daftar isi", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    for entry in outline:
        level = entry.level
        pdf.set_font("body", "B" if level == 0 else "", 10 if level == 0 else 9.4)
        pdf.set_text_color(*(DARK if level == 0 else MUTED))
        if level == 0:
            pdf.ln(1.2)
        indent = 0 if level == 0 else 7
        link = pdf.add_link(page=entry.page_number)
        pdf.set_x(pdf.l_margin + indent)
        pdf.cell(pdf.epw - indent - 12, 5.6, entry.name, link=link)
        pdf.cell(12, 5.6, str(entry.page_number), align="R", link=link, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def cover(pdf: Guide):
    pdf.add_page()
    pdf.set_fill_color(*LIGHT)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, pdf.w, 8, style="F")
    if LOGO.exists():
        pdf.image(str(LOGO), x=pdf.l_margin, y=36, h=18)
    pdf.set_y(70)
    pdf.set_font("body", "B", 12)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 8, "USER GUIDE BOOK", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("body", "B", 30)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(0, 14, "AMIGA Robot Admin")
    pdf.set_font("body", "", 14)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 7.5, "Intelligent Vendor Invoice-to-Voucher Processing\n"
                           "Panduan persyaratan sistem, instalasi, konfigurasi, menjalankan aplikasi, dan fitur")
    pdf.ln(10)
    pdf.set_font("body", "", 10.5)
    pdf.set_text_color(*DARK)
    for label, value in [("Versi dokumen", f"{VERSION} · {UPDATED}"), ("Proyek", "Proyek Akhir MAIN Hackathon 2026 · Kelompok 11"),
                         ("Login aplikasi", "http://13.212.201.121/login"),
                         ("Kode sumber", "github.com/halvrenvaire/AMIGA-ADMIN-ROBOT-TIM11-"),
                         ("Bot Telegram", "@amiga_online_ro_bot")]:
        pdf.set_font("body", "B", 10.5)
        pdf.cell(42, 7, label)
        pdf.set_font("body", "", 10.5)
        pdf.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(pdf.h - 30)
    pdf.set_font("body", "I", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, "We Run Your Ops, So You Can Run the Business · AMIGA Back Office as a Service.\n"
                         "Semua data invoice di dokumen ini adalah data uji coba.")


def build():
    pdf = Guide()
    cover(pdf)
    pdf.add_page()
    pdf.insert_toc_placeholder(render_toc, pages=2)

    # 1 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Tentang AMIGA Robot Admin")
    pdf.p("AMIGA Robot Admin membantu tim back office AMIGA mengubah **invoice vendor** dan **bukti reimburse** dari klien "
          "menjadi **Voucher Pengeluaran** yang siap dibayar. AI (Amazon Nova Lite di AWS Bedrock) membaca PDF atau foto "
          "invoice, sistem memverifikasi angka dan kelengkapan data, menyarankan potongan pajak, lalu Finance Reviewer "
          "menyetujui sebelum voucher resmi terbit. Setiap langkah tercatat di jejak audit.")
    pdf.section("Masalah yang diselesaikan")
    pdf.bullets([
        "Penginputan invoice manual memakan waktu dan rawan salah ketik, terutama untuk berkas berisi banyak invoice.",
        "Perhitungan potongan pajak (PPh 21, PPh 23, PPh 4 ayat 2) dan PPN sering tidak konsisten antarstaf.",
        "Status pengajuan sulit dipantau oleh klien, reviewer, dan Service Lead.",
    ])
    pdf.section("Alur satu voucher")
    pdf.bullets([
        "**PIC Klien** mengunggah invoice (dashboard atau bot Telegram), memilih klien, kategori, dan penanda tangan.",
        "**AI membaca** setiap invoice: vendor, nomor, tanggal, total, PPN tercetak, dan imbalan jasa. Satu PDF boleh berisi "
        "beberapa invoice; sistem memisahkannya menjadi bukti per invoice.",
        "**Sistem memverifikasi** kelengkapan dan hitungan, lalu **menyarankan pajak** (PPN dan potongan PPh).",
        "PIC memeriksa **draf**, mengubah bila perlu, melihat **simulasi voucher**, lalu **mengajukan** ke reviewer.",
        "**Finance Reviewer** memeriksa dan **menyetujui** (voucher resmi terbit dengan nomor) atau **mengembalikan** ke PIC.",
    ], numbered=True)
    pdf.section("Peran pengguna")
    pdf.grid([
        ["Peran", "Tugas utama", "Menu utama"],
        ["PIC Klien", "Mengunggah invoice, memeriksa draf, memilih pajak, mengajukan", "Pembuatan Voucher, Pengajuan Saya"],
        ["Intake Support", "Mengunggah atas nama PIC (delegasi)", "Pembuatan Voucher, Pengajuan Saya"],
        ["Finance Reviewer", "Memeriksa dan menyetujui atau mengembalikan pengajuan", "Peninjauan Saya, Dashboard Antrean"],
        ["Service Lead", "Memantau antrean dan kinerja, mengalihkan reviewer, rekap voucher", "Dashboard, Dashboard Antrean, Rekap Voucher"],
        ["System Admin", "Mengelola akun, peran, dan klien (tanpa akses data invoice)", "Pengguna & Peran, Klien"],
    ], (32, 82, 60))
    pdf.section("Teknologi")
    pdf.grid([
        ["Bagian", "Teknologi"],
        ["Backend API", "Python, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL"],
        ["Frontend", "React 19, TypeScript, Vite"],
        ["AI", "Amazon Bedrock: Nova Lite (membaca invoice, Asisten AI), Titan Text Embeddings v2 (pencarian SOP)"],
        ["Dokumen", "fpdf2 (voucher PDF), pypdf (memotong PDF), Pillow (foto ke PDF)"],
        ["Penyimpanan file", "Folder lokal atau Amazon S3"],
        ["Bot", "Telegram Bot API (long polling)"],
        ["Pengujian", "pytest (backend), Cypress (end-to-end)"],
    ], (40, 134))

    # 2 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Persyaratan sistem")
    pdf.section("Untuk pengguna (memakai aplikasi)")
    pdf.bullets([
        "Browser terbaru: Google Chrome, Microsoft Edge, Mozilla Firefox, atau Safari.",
        "Laptop/PC, atau HP dengan lebar layar minimal 360 px (tampilan menyesuaikan HP).",
        "Koneksi internet dan akun AMIGA dari System Admin.",
        "Opsional: aplikasi Telegram untuk memakai bot @amiga_online_ro_bot.",
    ])
    pdf.section("Untuk memasang dan menjalankan (server atau komputer pengembang)")
    pdf.grid([
        ["Komponen", "Kebutuhan", "Catatan"],
        ["Sistem operasi", "Linux, macOS, atau Windows (disarankan WSL2)", "Diuji di Ubuntu dan Amazon Linux 2023"],
        ["Python", "3.12 atau lebih baru (3.11 untuk server EC2)", "Dikembangkan dengan 3.14"],
        ["Node.js", "20.19+ atau 22.12+ dengan npm", "Untuk frontend dan Cypress"],
        ["PostgreSQL", "13 atau lebih baru", "Dikembangkan dengan 18; bisa juga Neon (cloud)"],
        ["Git", "Versi terbaru", "Untuk mengambil kode"],
        ["Perangkat keras", "RAM minimal 4 GB, ruang disk 2 GB", "Lebih lega untuk build frontend"],
        ["AWS", "Akun dengan akses Amazon Bedrock", "Nova Lite (ap-southeast-1) dan Titan Embeddings v2 (us-east-1)"],
        ["Amazon S3", "Opsional", "Penyimpanan file bukti di cloud; bawaan folder lokal"],
        ["Telegram", "Opsional: token bot dari @BotFather", "Untuk bot unggah invoice dan tanya jawab"],
    ], (32, 72, 70))
    pdf.note("Tanpa kredensial AWS aplikasi tetap berjalan: AI dimatikan (`AI_EXTRACTION_ENABLED=false`) dan PIC mengisi "
             "data invoice secara manual. Saran pajak berbasis aturan tetap tersedia.")

    # 3 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Instalasi")
    pdf.section("Mengambil kode")
    pdf.code(["git clone https://github.com/halvrenvaire/AMIGA-ADMIN-ROBOT-TIM11-.git amiga-robot-admin",
              "cd amiga-robot-admin"])
    pdf.p("Struktur utama: `backend/` (API, bot Telegram, migrasi database, test), `frontend/` (dashboard web dan test "
          "Cypress), `docs/` (SOP, daftar tugas, panduan deploy), `readme/` (BRD, PRD, BPMN, dan buku panduan ini).")
    pdf.section("Backend: Python dan dependensi")
    pdf.code(["cd backend",
              "python3 -m venv .venv",
              ".venv/bin/pip install -r requirements.txt",
              "# Windows: .venv\\Scripts\\pip install -r requirements.txt"])
    pdf.section("Database PostgreSQL")
    pdf.p("Buat role dan database sesuai `DATABASE_URL` di `.env`. Skrip berikut membuatnya otomatis (meminta password sudo):")
    pdf.code(["bash scripts/create_db.sh                        # database utama",
              "bash scripts/create_db.sh amiga_robot_admin_test # database untuk test (sekali saja)"])
    pdf.p("Cara manual lewat `psql` sebagai superuser:")
    pdf.code(["CREATE ROLE amiga LOGIN PASSWORD '<password-anda>';",
              "CREATE DATABASE amiga_robot_admin OWNER amiga;"])
    pdf.section("Konfigurasi .env")
    pdf.p("Salin contoh konfigurasi lalu isi nilainya. **Jangan pernah membagikan atau meng-commit `.env`** (sudah ada di "
          "`.gitignore`).")
    pdf.code(["cp .env.example .env"])
    pdf.grid([
        ["Variabel", "Wajib", "Keterangan"],
        ["`DATABASE_URL`", "Ya", "postgresql+psycopg://user:password@host:5432/amiga_robot_admin"],
        ["`JWT_SECRET`", "Ya", "Kunci token login, minimal 32 karakter acak"],
        ["`SEED_DEFAULT_PASSWORD`", "Ya", "Password semua akun demo yang dibuat `seed.py`"],
        ["`AWS_ACCESS_KEY`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`", "Untuk AI", "Kredensial AWS dengan akses Bedrock"],
        ["`AI_EXTRACTION_ENABLED`", "Tidak", "`false` = AI dimatikan, data diisi manual"],
        ["`STORAGE_BACKEND`, `LOCAL_STORAGE_DIR`, `AWS_BUCKET`", "Tidak", "`local` (bawaan) atau `s3`"],
        ["`AI_MAX_SCAN_PAGES`, `MAX_INVOICES_PER_VOUCHER`", "Tidak", "Batas pemindaian halaman dan jumlah invoice per voucher"],
        ["`CORS_ORIGINS`, `FRONTEND_URL`", "Untuk deploy", "Alamat dashboard (dipisah koma) dan tautan di pesan bot"],
        ["`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`", "Untuk bot", "Token dan nama bot dari @BotFather"],
        ["`BOT_API_BASE_URL`", "Untuk bot", "Alamat API yang dipanggil bot, mis. http://localhost:8000"],
        ["`REINDEX_API_KEY`", "Tidak", "Kunci untuk membangun ulang index SOP Asisten AI"],
    ], (64, 22, 88), font_size=8.6)
    pdf.section("Membuat tabel dan data demo")
    pdf.code([".venv/bin/alembic upgrade head   # membuat/memperbarui tabel",
              ".venv/bin/python seed.py         # akun demo, klien, vendor, penanda tangan, tarif pajak"])
    pdf.section("Frontend")
    pdf.code(["cd ../frontend",
              "npm install"])
    pdf.p("Dalam mode pengembangan, permintaan ke `/api/*` diteruskan Vite ke `http://localhost:8000` (ubah lewat "
          "`VITE_API_TARGET`). Untuk build produksi yang memanggil API di alamat lain, isi `VITE_API_URL`.")

    # 4 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Menjalankan aplikasi")
    pdf.section("Menjalankan di komputer sendiri")
    pdf.p("Buka dua terminal:")
    pdf.code(["# Terminal 1: backend API (http://localhost:8000, dokumentasi API di /docs)",
              "cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000",
              "",
              "# Terminal 2: dashboard (http://localhost:5173)",
              "cd frontend && npm run dev"])
    pdf.note("Untuk mencoba tanpa memasang apa pun, buka aplikasi yang sudah berjalan di server tim: "
             "**http://13.212.201.121/login** (ketik lengkap dengan http://), dan bot Telegram **@amiga_online_ro_bot**.")
    pdf.p("Buka **http://localhost:5173** lalu login dengan salah satu akun demo. Saat pertama dijalankan, backend "
          "membangun index SOP untuk Asisten AI (sekitar 10 detik).")
    pdf.sub("Akun demo (hasil seed.py)")
    pdf.grid([
        ["Email", "Peran", "Klien"],
        ["pic.alpha@amiga.test", "PIC Klien", "PT Klien Alpha"],
        ["pic.beta@amiga.test", "PIC Klien", "PT Klien Beta"],
        ["intake@amiga.test", "Intake Support (delegasi PIC Alpha)", "PT Klien Alpha"],
        ["reviewer1@amiga.test, reviewer2@amiga.test", "Finance Reviewer", "Alpha, Beta"],
        ["multi@amiga.test", "Intake Support + Finance Reviewer", "PT Klien Alpha"],
        ["lead@amiga.test", "Service Lead", "Alpha, Beta"],
        ["admin@amiga.test", "System Admin", "-"],
    ], (70, 60, 44))
    pdf.note("Password semua akun demo adalah nilai `SEED_DEFAULT_PASSWORD` di `backend/.env` (lokal) atau di file "
             "konfigurasi produksi. Password tidak dicantumkan di dokumen ini; minta ke tim pengembang.")
    pdf.section("Setelah mengambil kode terbaru (git pull)")
    pdf.p("Bila ada file baru di `backend/alembic/versions/`, perbarui struktur database dulu. Tanpa langkah ini login "
          "bisa gagal seolah password salah, karena kolom baru belum ada.")
    pdf.code(["cd backend && .venv/bin/alembic upgrade head",
              "cd ../frontend && npm install    # bila package.json berubah"])
    pdf.section("Menjalankan bot Telegram")
    pdf.bullets([
        "Isi `TELEGRAM_BOT_TOKEN` dan `BOT_API_BASE_URL` di `backend/.env`.",
        "Pastikan backend API berjalan, lalu di terminal lain jalankan: `cd backend && .venv/bin/python -m bot.telegram_bot`.",
        "Hubungkan akun: dashboard > **Pengaturan akun** > **Hubungkan Telegram** > buka bot dan tekan **Start** "
        "(atau kirim `/login <kode>`). Password tidak pernah diketik di chat.",
    ], numbered=True)
    pdf.section("Menjalankan pengujian")
    pdf.code(["cd backend",
              ".venv/bin/python -m pytest -m \"not integration\"   # cepat, tanpa AWS",
              ".venv/bin/python -m pytest                        # termasuk uji ke Bedrock",
              "",
              "cd .. && bash scripts/run_e2e.sh                  # Cypress end-to-end (UAT)"])
    pdf.section("Deploy publik")
    pdf.p("Versi publik memakai tiga layanan: database **Neon** (PostgreSQL cloud), backend **FastAPI Cloud**, dan "
          "frontend **Vercel**. Alternatif satu server: **AWS EC2** (lihat `docs/ec2_deployment_guide.md`).")
    pdf.code(["# Migrasi dan data demo ke database produksi (DATABASE_URL produksi)",
              "cd backend && DATABASE_URL=<url-produksi> .venv/bin/alembic upgrade head",
              "",
              "# Deploy backend dari folder induk repo (sekali saja: backend/.venv/bin/fastapi login)",
              "backend/.venv/bin/fastapi deploy .",
              "",
              "# Frontend: hubungkan repo ke Vercel, Root Directory = frontend,",
              "# variabel VITE_API_URL = alamat backend. Vercel men-deploy otomatis setiap push ke main."])
    pdf.grid([
        ["Layanan", "Alamat"],
        ["**Aplikasi utama (AWS EC2)**", "**http://13.212.201.121/login** (ketik lengkap dengan http://)"],
        ["Bot Telegram (server EC2)", "@amiga_online_ro_bot"],
        ["Alternatif: dashboard (Vercel)", "https://amiga-admin-robot-tim-11.vercel.app"],
        ["Alternatif: backend API (FastAPI Cloud)", "https://amiga-robot-admin.fastapicloud.dev"],
    ], (60, 114))

    # 5 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Panduan fitur")
    pdf.section("Login dan pengaturan akun")
    pdf.p("Masuk dengan email dan password akun. Di **Pengaturan akun** (klik nama di kanan atas) Anda bisa mengganti "
          "password, mengisi profil \"Diajukan oleh\" (jabatan, perusahaan, tanda tangan elektronik), dan menghubungkan bot "
          "Telegram.")
    pdf.figure("01-login.jpg", "Halaman login.")
    pdf.figure("15-akun.jpg", "Pengaturan akun: profil, keamanan, tanda tangan, dan Telegram.")
    pdf.section("Tutorial di dalam aplikasi (tombol ?)")
    pdf.p("Tombol **?** di kanan atas membuka tutorial langkah demi langkah untuk halaman yang sedang dibuka. Bagian yang "
          "dijelaskan disorot dan sekelilingnya digelapkan. Langkahnya menyesuaikan peran Anda; bagian yang tidak tampil "
          "dilewati. Gunakan **Lanjut**/**Sebelumnya** atau tombol panah, dan **Esc** untuk menutup. Titik berkedip di "
          "tombol ? menandakan Anda belum pernah membuka tutorial.")
    pdf.figure("06-tutorial.jpg", "Tutorial halaman Pembuatan Voucher: langkah \"Klien\" sedang disorot.")
    pdf.section("Dashboard")
    pdf.p("Ringkasan dokumen per status, invoice masuk, voucher terbit, nilai pembayaran, dan tren harian. Klik kartu status "
          "untuk membuka daftar dokumen dengan status itu.")
    pdf.figure("02-dashboard-pic.jpg", "Dashboard PIC Klien.")

    pdf.section("Membuat voucher (PIC Klien / Intake Support)")
    pdf.p("Menu **Pembuatan Voucher**. Isi formulir dari atas ke bawah:")
    pdf.bullets([
        "**Data pengajuan**: klien, kategori (Vendor, Reimburse, Lainnya), dan tanggal pengajuan.",
        "**Diajukan oleh**: profil akun PIC (terkunci) atau isi manual, termasuk tanda tangan.",
        "**Disetujui oleh**: pemberi persetujuan dari pihak klien (boleh dikosongkan).",
        "**Mode baca AI**: *Total saja* (bawaan, satu baris voucher per invoice, lebih hemat) atau *Rincian barang/jasa* "
        "(satu baris per item).",
        "**Fitur tambahan**: saluran dan tenggat, rekening tujuan, dan **Atur pajak secara otomatis** (saran PPN dan PPh "
        "langsung terpasang, tetap bisa diubah).",
        "**File bukti**: PDF atau foto (JPG, PNG, WEBP), maksimal 10 file (Reimburse 20), 10 MB per file. Satu PDF boleh berisi "
        "beberapa invoice beserta Faktur Pajak dan timesheet.",
        "Tekan **Simpan draf & lanjutkan**. AI mulai membaca dan Anda dibawa ke halaman draf.",
    ], numbered=True)
    pdf.figure("03-unggah-atas.jpg", "Pembuatan voucher: data pengajuan dan Diajukan oleh.")
    pdf.figure("04-unggah-mode.jpg", "Mode baca AI dan fitur tambahan.")
    pdf.figure("05-unggah-file.jpg", "Area unggah file bukti.")

    pdf.section("Memeriksa draf per bukti")
    pdf.p("Di kiri tampil bukti asli, di kanan data hasil baca AI. **Navigasi cepat** menandai bagian yang masih perlu "
          "diisi (kuning/merah). Bila satu PDF berisi beberapa invoice, setiap invoice menjadi satu **bukti** (tab) dengan "
          "data, uraian, dan pajaknya sendiri. Contoh di bawah: satu PDF DSS 32 halaman dipisah otomatis menjadi 6 bukti "
          "(invoice + rincian + Faktur Pajak + timesheet per bukti).")
    pdf.figure("07-draf-atas.jpg", "Halaman draf: bukti asli, navigasi cepat, dan informasi dokumen.")
    pdf.figure("08-draf-bukti.jpg", "Tab bukti per invoice dan informasi utama hasil baca AI.")
    pdf.bullets([
        "Cocokkan **vendor, nomor, tanggal, dan total** dengan bukti asli; bila salah, ubah lalu tekan **Simpan bukti**.",
        "Isi **uraian transaksi**: teks yang dicetak sebagai satu baris di voucher (mode Total saja). Periksa uraian dari AI; "
        "mis. ubah menjadi \"Management Fee & Development Driver A\" sesuai kebutuhan.",
        "Halaman bukti salah? Ubah **rentang halaman**, tambah bukti dari halaman yang terlewat, atau tekan "
        "**Pisahkan otomatis (AI)**.",
        "Bila AI tidak bisa membaca (mis. foto buram), isi data secara manual atau tekan **Baca ulang dengan AI**.",
    ])

    pdf.section("Mengatur PPN dan potongan PPh")
    pdf.p("Bagian **Pajak** menampilkan saran AI dan angka pajak yang tercetak di invoice. Keputusan tetap di PIC.")
    pdf.figure("09-draf-pajak.jpg", "Pengaturan PPN: harga sudah termasuk PPN, nilai PPN dari invoice.")
    pdf.figure("10-draf-pajak-saran.jpg", "Saran AI PPh 23 dan PPN, beserta dasar potongan (DPP).")
    pdf.sub("PPN")
    pdf.bullets([
        "**Harga sudah termasuk PPN**: total invoice sudah berisi PPN. Bila invoice mencetak PPN, nilai PPN **persis angka "
        "tercetak** yang dipakai, bukan 11% dari total.",
        "**Harga belum termasuk PPN**: PPN ditambahkan ke harga (DPP + tarif × DPP).",
        "**Tidak ada PPN**. Centang *Tampilkan rincian PPN* bila PPN ingin dicetak sebagai baris sendiri di voucher.",
    ])
    pdf.sub("Potongan PPh")
    pdf.bullets([
        "Pilih jenis PPh: **Tanpa potongan**, **PPh 21** (jasa orang pribadi), **PPh 23** (jasa oleh badan usaha), "
        "**PPh 4 ayat 2** (sewa tanah/bangunan, konstruksi), atau **PPh 26** (vendor luar negeri).",
        "Tarif mengikuti NPWP vendor (tanpa NPWP umumnya dua kali lipat). Tabel tarif ada di menu **Tarif pajak**.",
        "Mode **Rincian**: PPh bisa dipilih **berbeda per baris** (mis. barang tanpa potongan, jasa PPh 23).",
        "Matikan **Hitung pajak otomatis** bila ingin mengisi DPP, PPN, dan potongan sendiri sesuai invoice.",
    ])
    pdf.sub("Batasan dasar potongan PPh 23 untuk invoice jasa (contoh DSS)")
    pdf.p("Pada invoice jasa yang memisahkan **imbalan jasa** vendor dari **penggantian biaya** (gaji/Basic Fee, BPJS, "
          "lembur driver), PPh 23 dipotong **hanya dari imbalan jasa**, yaitu bagian tagihan yang dikenai PPN (mis. "
          "*Management Fee & Development*). Sistem membaca angka itu dari invoice dan memastikannya cocok dengan PPN "
          "tercetak (imbalan × 11% = PPN). Bila tidak cocok, pajak **tidak dipasang otomatis** dan muncul peringatan agar "
          "PIC mengisi DPP sendiri.")
    pdf.grid([
        ["Invoice DSS", "Total invoice", "Imbalan jasa (DPP)", "PPh 23 2%"],
        ["005-PI-2604-00322 s.d. 00324", "Rp 8.933.846 (×3)", "Rp 2.304.696", "Rp 46.094 (×3)"],
        ["005-PI-2604-00325", "Rp 7.683.712", "Rp 988.047", "Rp 19.761"],
        ["005-PI-2604-00326", "Rp 4.348.350", "Rp 559.153", "Rp 11.183"],
        ["005-PI-2604-00327", "Rp 3.062.638", "Rp 393.824", "Rp 7.876"],
        ["**Total**", "**Rp 41.896.238**", "", "**Rp 177.102**"],
    ], (52, 42, 42, 38))
    pdf.p("Total dibayarkan = Rp 41.896.238 - Rp 177.102 = **Rp 41.719.136**, sama dengan voucher bayar owner.")

    pdf.section("Pratinjau, simulasi voucher, dan mengajukan")
    pdf.p("**Pratinjau voucher** di halaman draf diperbarui setiap kali data atau pajak disimpan. **Lihat simulasi voucher** "
          "membuka PDF lengkap dengan lampiran bukti (bisa layar penuh, tab baru, atau diunduh). Setiap invoice dicetak satu "
          "baris, diikuti baris potongan PPh dengan format *Potongan PPh 23 (DPP × tarif)*.")
    pdf.figure("11-draf-pratinjau.jpg", "Pratinjau voucher di halaman draf.")
    pdf.figure("50-simulasi.jpg", "Simulasi Voucher Pengeluaran berkas DSS: 6 invoice, potongan PPh 23, total Rp 41.719.136.",
               width=120)
    pdf.p("Tekan **Ajukan untuk Direview** setelah kendala wajib beres, uraian terisi, dan pajak setiap bukti dipilih. "
          "Pengajuan otomatis ditugaskan ke Finance Reviewer.")
    pdf.figure("12-draf-ajukan.jpg", "Tombol Simpan bukti, Lihat simulasi voucher, dan Ajukan untuk Direview.")
    pdf.section("Pengajuan Saya")
    pdf.p("Daftar semua pengajuan klien Anda beserta statusnya. Saring menurut status atau kategori, dan klik judul kolom "
          "untuk mengurutkan.")
    pdf.figure("13-pengajuan.jpg", "Pengajuan Saya.")

    pdf.section("Finance Reviewer: memeriksa dan memutuskan")
    pdf.bullets([
        "Buka **Peninjauan Saya** (dokumen yang ditugaskan kepada Anda) atau **Dashboard Antrean**.",
        "Periksa data invoice, pajak, kendala, dan simulasi voucher. Reviewer tidak mengedit data; kesalahan dikembalikan ke PIC.",
        "**Setujui**: voucher resmi terbit dengan nomor. **Kembalikan ke PIC**: tulis alasan yang jelas.",
        "Rekening yang berbeda atau belum terverifikasi perlu dicek ke sumber tepercaya sebelum disetujui.",
    ], numbered=True)
    pdf.figure("40-peninjauan.jpg", "Peninjauan Saya (Finance Reviewer).")
    pdf.figure("42-review-keputusan.jpg", "Ringkasan potongan pajak dan tombol keputusan reviewer.")
    pdf.section("Voucher")
    pdf.p("Daftar voucher resmi yang sudah terbit. Buka untuk mengunduh PDF voucher beserta lampiran bukti.")
    pdf.figure("43-voucher-daftar.jpg", "Daftar voucher.")

    pdf.section("Service Lead: antrean, dashboard, dan rekap")
    pdf.p("**Dashboard Antrean** menampilkan semua dokumen menurut tenggat dan beban tiap reviewer; Service Lead bisa "
          "**mengalihkan reviewer**. **Rekap Voucher** membuat laporan PDF voucher per periode.")
    pdf.figure("20-antrean.jpg", "Dashboard Antrean.")
    pdf.figure("21-dashboard-lead.jpg", "Dashboard Service Lead.")
    pdf.figure("22-rekap.jpg", "Rekap Voucher.")

    pdf.section("Data referensi")
    pdf.bullets([
        "**Vendor**: nama, NPWP, dan rekening terverifikasi. Dipakai untuk saran tarif PPh dan cek rekening.",
        "**Penanda tangan**: daftar pemberi persetujuan per klien, beserta logo klien untuk kop voucher.",
        "**Tarif pajak**: tarif PPh dengan dan tanpa NPWP (diubah oleh Service Lead).",
    ])
    pdf.figure("17-vendor.jpg", "Data vendor.")
    pdf.figure("14-tarif.jpg", "Tarif pajak.")
    pdf.section("Riwayat dan jejak audit")
    pdf.p("Setiap aksi tercatat permanen: unggah, pembacaan AI, perubahan nilai (nilai awal menjadi nilai baru), pengajuan, "
          "pengembalian, persetujuan, dan pengalihan reviewer.")
    pdf.figure("18-riwayat.jpg", "Riwayat & Audit.")
    pdf.section("Asisten AI")
    pdf.p("Tanya dengan kalimat biasa soal SOP, status invoice, atau cara memakai aplikasi, mis. \"Apa yang harus "
          "dilakukan kalau kena MISSING_EVIDENCE?\". Bisa dibuka dari menu **Asisten AI** atau tombol **Tanya Asisten**.")
    pdf.figure("16-asisten.jpg", "Asisten AI.")

    pdf.section("Bot Telegram @amiga_online_ro_bot")
    pdf.p("PIC Klien dan Intake Support bisa mengajukan voucher langsung dari chat Telegram:")
    pdf.bullets([
        "Kirim file PDF atau foto invoice (boleh beberapa file untuk satu voucher). Kirim foto sebagai **File** agar tidak dikompres.",
        "Pilih **perusahaan** dan **kategori** lewat tombol, lalu tekan **Kirim ke AMIGA**.",
        "AI membaca total dan PPN, lalu menyarankan potongan PPh untuk tiap invoice (pajak otomatis aktif).",
        "Bot mengirim **ringkasan per bukti**: uraian, PPN, PPh (DPP × tarif = potongan) dan alasan AI, beserta total, "
        "potongan, dan jumlah dibayarkan.",
        "Ubah bila perlu: **Pajak bukti N** (pilih jenis PPh atau tanpa potongan), **Uraian bukti N** (balas dengan teks), "
        "**Simulasi voucher (PDF)** dikirim ke chat.",
        "Tekan **Ajukan ke reviewer**.",
    ], numbered=True)
    pdf.grid([
        ["Perintah", "Fungsi"],
        ["/login <kode>", "Menghubungkan Telegram dengan akun AMIGA (kode dari Pengaturan akun)"],
        ["/terakhir", "5 invoice terbaru"],
        ["/kendala", "Invoice yang terkendala, tenggat terdekat di atas"],
        ["/status REQ-...", "Detail satu dokumen"],
        ["/reset, /logout, /bantuan", "Percakapan baru, putuskan akun, daftar perintah"],
        ["(kalimat biasa)", "Dijawab Asisten AI"],
    ], (50, 124))
    pdf.section("System Admin")
    pdf.p("Mengelola akun, peran (satu akun boleh peran ganda dengan pemisahan tugas otomatis), penugasan klien, dan "
          "data klien. System Admin tidak bisa melihat data invoice.")
    pdf.figure("23-admin-pengguna.jpg", "Pengguna & Peran.")
    pdf.figure("24-admin-klien.jpg", "Klien.")
    pdf.section("Tampilan HP")
    pdf.p("Di HP, menu samping menjadi laci yang dibuka dengan tombol menu (tiga garis) (berisi kotak pencarian), tabel bisa digeser ke "
          "samping, dan tombol keputusan tersusun dua kolom.")
    pdf.figure("30-hp-daftar.jpg", "Pengajuan Saya di HP.", width=62)
    pdf.figure("31-hp-laci.jpg", "Laci menu dan pencarian di HP.", width=62)

    # 6 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Status dokumen dan kode kendala")
    pdf.section("Status dokumen")
    pdf.grid([
        ["Status", "Arti"],
        ["Antre / Diproses AI", "File sudah diterima; AI sedang membaca"],
        ["Draf", "Hasil AI siap diperiksa PIC sebelum diajukan"],
        ["Ada kendala", "Masih ada data yang harus dilengkapi atau diperbaiki PIC"],
        ["Siap ditinjau", "Sudah diajukan dan menunggu Finance Reviewer"],
        ["Disetujui", "Voucher resmi terbit"],
        ["Diserahkan", "Voucher sudah diserahkan ke klien"],
        ["Dibatalkan", "Pengajuan dibatalkan (data dan riwayat tetap tersimpan)"],
    ], (44, 130))
    pdf.section("Kode kendala")
    pdf.grid([
        ["Kode", "Arti dan tindakan"],
        ["MISSING_EVIDENCE", "Data wajib kosong (vendor, nomor, tanggal, total). Lengkapi di draf."],
        ["CALCULATION_DISCREPANCY", "Jumlah rincian tidak sama dengan total. Periksa baris dan total."],
        ["POSSIBLE_DUPLICATE", "Nomor invoice pernah diajukan. Reviewer memutuskan."],
        ["NOT_AN_INVOICE", "Dokumen bukan tagihan (mis. penawaran, surat). Ganti file."],
        ["RECEIPT_NOT_INVOICE", "Struk/nota, bukan invoice resmi. Reviewer memutuskan."],
        ["EXTRACTION_FAILED", "AI gagal membaca. Isi manual atau baca ulang."],
        ["VENDOR_MISMATCH / ACCOUNT_MISMATCH", "Vendor atau rekening berbeda dengan data referensi. Pengingat untuk dicek."],
        ["RETURNED_BY_REVIEWER", "Dikembalikan reviewer. Baca alasannya, perbaiki, ajukan lagi."],
    ], (62, 112))

    # 7 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Pemecahan masalah")
    pdf.grid([
        ["Masalah", "Penyebab dan solusi"],
        ["Login gagal padahal password benar (setelah git pull)", "Struktur database belum diperbarui. Jalankan "
         "`cd backend && .venv/bin/alembic upgrade head`."],
        ["Alamat EC2 berpindah sendiri ke https:// dan gagal dibuka", "Server belum memakai HTTPS. Ketik lengkap "
         "`http://13.212.201.121/login`; di Chrome matikan \"Selalu gunakan koneksi aman\" atau pakai jendela biasa."],
        ["Dashboard: \"Tidak bisa terhubung\"", "Backend mati atau alamat dashboard belum ada di `CORS_ORIGINS`."],
        ["AI tidak membaca / data kosong", "Kredensial AWS salah, kuota Bedrock habis, atau foto buram. Isi manual atau "
         "baca ulang; kirim foto sebagai File di Telegram."],
        ["PPh 23 tidak terpasang otomatis", "Imbalan jasa tidak cocok dengan PPN tercetak. Isi DPP sesuai invoice di "
         "bagian Pajak."],
        ["Tombol Ajukan tidak aktif", "Masih ada kendala wajib, uraian kosong, pajak belum dipilih, atau ada perubahan "
         "yang belum disimpan."],
        ["Port 8000/5173 sudah dipakai", "Matikan proses lama atau jalankan di port lain (`--port`)."],
        ["Bot Telegram tidak membalas", "Pastikan proses bot berjalan, `TELEGRAM_BOT_TOKEN` benar, dan akun sudah dihubungkan."],
    ], (58, 116), font_size=8.8)

    # 8 -------------------------------------------------------------------------------------------------------
    pdf.chapter("Glosarium")
    pdf.grid([
        ["Istilah", "Arti"],
        ["Bukti", "Satu invoice/struk dalam pengajuan; satu PDF bisa menjadi beberapa bukti"],
        ["DPP", "Dasar Pengenaan Pajak: nilai yang dikalikan tarif pajak"],
        ["Imbalan jasa", "Fee milik vendor (mis. Management Fee), bukan penggantian biaya yang diteruskan"],
        ["PPN", "Pajak Pertambahan Nilai; tidak dihitung ulang, voucher membayar total invoice"],
        ["PPh 21/23/4(2)/26", "Pajak penghasilan yang dipotong saat membayar vendor"],
        ["Request ID", "Nomor pengajuan, mis. REQ-20261026-10F9C0"],
        ["SoD", "Segregation of Duties: pengaju tidak boleh menyetujui pengajuannya sendiri"],
        ["Simulasi voucher", "Voucher bertanda SIMULASI sebelum disetujui reviewer"],
        ["Uraian transaksi", "Teks satu baris voucher untuk setiap invoice (mode Total saja)"],
    ], (40, 134))
    pdf.ln(4)
    pdf.set_font("body", "I", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, f"Dokumen ini dibuat otomatis dari docs/user-guide/build_user_guide.py pada "
                         f"{date.today().isoformat()}. Pertanyaan: hubungi Kelompok 11 MAIN Hackathon 2026.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"Selesai: {OUT.relative_to(ROOT)} ({pdf.pages_count} halaman)")


if __name__ == "__main__":
    build()
