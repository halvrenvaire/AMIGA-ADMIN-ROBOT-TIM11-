"""Bot Telegram AMIGA Robot Admin (@amiga_ro_bot).

Jalankan dari folder backend/, di terminal terpisah dari server API:
    .venv/bin/python -m bot.telegram_bot

Bot membaca pesan lewat long polling, lalu memanggil API AMIGA atas nama akun yang terhubung
(token login dibuat untuk akun itu di setiap permintaan). Jadi hak akses, isolasi klien, dan
Asisten AI sama persis dengan dashboard. Akun dihubungkan dengan kode sekali pakai dari dashboard;
password tidak pernah diketik di chat.

PIC Klien / Intake Support juga bisa mengunggah invoice PDF lewat bot (saluran "Telegram"). Bot
memakai endpoint unggah yang sama dengan dashboard, lalu mengabari hasil proses AI.
"""
import io
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from pypdf import PdfReader

from app.auth import create_access_token
from app.config import settings
from app.db import SessionLocal
from app.models import REQUEST_CATEGORIES, Role, User
from app.services import file_conversion, telegram_service

ACCEPTED_MIME = {"application/pdf", *file_conversion.IMAGE_TYPES.values()}
ACCEPTED_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".webp")

log = logging.getLogger("amiga.telegram")

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE = 4000  # batas Telegram 4096 karakter, sisakan ruang
STALE_SECONDS = 600  # pesan yang menumpuk lebih lama dari ini saat bot mati tidak dibalas
LOGIN_MAX_FAILURES = 5
LOGIN_BLOCK_SECONDS = 15 * 60
TELEGRAM_DOWNLOAD_MB = 20  # batas unduh file oleh bot di Telegram
DRAFT_TTL_SECONDS = 30 * 60
WATCH_SECONDS = 120  # lama bot memantau hasil proses AI setelah unggah
WATCH_INTERVAL = 3
# Kategori pengajuan sama dengan dashboard (feedback owner): tombol berurutan
CATEGORIES = REQUEST_CATEGORIES

COMMANDS = [
    ("login", "Masuk ke aplikasi AMIGA Robot Admin"),
    ("logout", "Keluar dari aplikasi"),
    ("reset", "Mulai percakapan baru"),
    ("terakhir", "Progress invoice terakhir saya"),
    ("kendala", "Progress invoice yang terkendala"),
    ("status", "Detail dokumen, contoh: /status REQ-20261015-ABC123"),
    ("bantuan", "Daftar perintah dan contoh pertanyaan"),
]

STATUS_LABEL = {
    "QUEUED": "Antre", "PROCESSING": "Diproses AI", "DRAFT": "Draf", "READY_FOR_REVIEW": "Siap ditinjau",
    "EXCEPTION": "Ada kendala", "AMIGA_REVIEWED": "Disetujui", "SENT_TO_CLIENT": "Diserahkan",
    "CANCELLED": "Dibatalkan",
}
STATUS_ICON = {
    "QUEUED": "⏳", "PROCESSING": "🤖", "DRAFT": "📝", "READY_FOR_REVIEW": "🔎", "EXCEPTION": "⚠️",
    "AMIGA_REVIEWED": "✅", "SENT_TO_CLIENT": "📨", "CANCELLED": "🚫",
}
ISSUE_LABEL = {
    "MISSING_EVIDENCE": "Data belum lengkap", "CALCULATION_DISCREPANCY": "Selisih hitungan",
    "POSSIBLE_DUPLICATE": "Kemungkinan duplikat", "EXTRACTION_FAILED": "AI gagal membaca",
    "RETURNED_BY_REVIEWER": "Dikembalikan reviewer", "VENDOR_MISMATCH": "Vendor/rekening berbeda",
    "NOT_AN_INVOICE": "Dokumen tidak relevan", "RECEIPT_NOT_INVOICE": "Struk/nota, bukan invoice resmi",
    "NEEDS_MANUAL_REVIEW": "Perlu pemeriksaan manual", "ACCOUNT_MISMATCH": "Rekening tidak cocok",
}
REQUEST_ID = re.compile(r"\bREQ-[A-Z0-9-]+\b", re.IGNORECASE)
SUBMITTER_ROLES = {Role.PIC_KLIEN, Role.INTAKE_SUPPORT}
IN_PROGRESS = {"QUEUED", "PROCESSING"}

HELP_TEXT = (
    "Perintah yang tersedia:\n"
    + "\n".join(f"/{c} - {d}" for c, d in COMMANDS)
    + "\n\nUnggah invoice (PIC Klien / Intake Support): kirim file PDF atau foto invoice "
    "(JPG, PNG, WEBP) ke chat ini, boleh beberapa file untuk satu voucher.\n"
    "\nAtau tanya langsung dengan kalimat biasa, misalnya:\n"
    "• Apa yang harus dilakukan kalau kena MISSING_EVIDENCE?\n"
    "• Berapa target waktu pembuatan voucher?\n"
    "• Dokumen saya yang tenggatnya minggu ini apa saja?"
)

# Tombol inline: [[(label, callback_data), ...], ...]
Buttons = list[list[tuple[str, str]]]


@dataclass
class Reply:
    text: str
    buttons: Buttons | None = None


def login_instructions() -> str:
    return (
        "Akun Telegram ini belum terhubung ke AMIGA Robot Admin.\n\n"
        "Cara menghubungkan:\n"
        f"1. Login ke dashboard AMIGA ({settings.frontend_url}).\n"
        "2. Buka Pengaturan akun → Hubungkan Telegram → Buat kode.\n"
        "3. Kirim ke sini: /login <kode 6 digit>\n\n"
        "Kode berlaku beberapa menit dan hanya bisa dipakai sekali. "
        "Jangan pernah mengirim password Anda di chat."
    )


class BackendError(Exception):
    """API AMIGA menolak atau tidak bisa dihubungi; pesannya aman ditampilkan ke pengguna."""


# --- Format pesan ---

def plain(text: str) -> str:
    """Pesan dikirim sebagai teks biasa: buang penanda markdown dari jawaban model."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text.strip()


def rupiah(value) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "-"
    return "Rp " + f"{number:,.0f}".replace(",", ".")


def doc_url(document_id: str) -> str:
    return f"{settings.frontend_url}/dokumen/{document_id}"


def format_doc_line(doc: dict) -> str:
    status = doc.get("status", "")
    parts = [doc.get("vendor_name") or "Vendor belum terbaca", doc.get("client", {}).get("name") or "-"]
    if doc.get("total") is not None:
        parts.append(rupiah(doc["total"]))
    line = f"{STATUS_ICON.get(status, '•')} {doc['request_id']} — {STATUS_LABEL.get(status, status)}\n   " + " · ".join(parts)
    if doc.get("due_date") and status not in ("AMIGA_REVIEWED", "SENT_TO_CLIENT", "CANCELLED"):
        line += f"\n   Tenggat: {doc['due_date']}"
    return line


MISSING_FIELD = {
    "vendor_name": "nama vendor", "invoice_no": "nomor invoice", "invoice_date": "tanggal", "total": "total",
    "bank_name": "nama bank", "account_no": "nomor rekening", "account_name": "nama penerima", "line_items": "rincian",
}


def format_issues(doc: dict) -> list[str]:
    issues = doc.get("issues") or []
    missing = [i for i in issues if i["code"] == "MISSING_EVIDENCE"]
    if len(missing) < 4:
        return [f"• {ISSUE_LABEL.get(i['code'], i['code'])}: {i['message']}" for i in issues]
    # Banyak data kosong sekaligus biasanya berarti fotonya tidak terbaca: cukup satu baris ringkas
    fields = ", ".join(MISSING_FIELD.get(i.get("field"), i.get("field") or "-") for i in missing)
    lines = [f"• {ISSUE_LABEL['MISSING_EVIDENCE']}: AI tidak menemukan {len(missing)} data ({fields}). "
             "Biasanya karena foto buram, terpotong, atau terkompres. Kirim ulang sebagai File (📎 → File), "
             "atau lengkapi datanya di dashboard."]
    return lines + [f"• {ISSUE_LABEL.get(i['code'], i['code'])}: {i['message']}" for i in issues if i not in missing]


def format_doc_detail(doc: dict) -> str:
    status = doc.get("status", "")
    extraction = doc.get("extraction") or {}
    lines = [
        f"{STATUS_ICON.get(status, '•')} {doc['request_id']}",
        f"Status: {STATUS_LABEL.get(status, status)}",
        f"Perusahaan: {doc.get('client', {}).get('name') or '-'}",
        f"Vendor: {doc.get('vendor_name') or extraction.get('vendor_name') or '-'}",
        f"No. invoice: {extraction.get('invoice_no') or '-'}",
        f"Total: {rupiah(doc['total']) if doc.get('total') is not None else '-'}",
        f"Diunggah oleh: {doc.get('uploaded_by') or '-'}",
        f"Reviewer: {doc.get('assigned_reviewer') or '-'}",
    ]
    if doc.get("due_date"):
        lines.append(f"Tenggat: {doc['due_date']}")
    if doc.get("voucher"):
        lines.append(f"Voucher: {doc['voucher'].get('voucher_no', '-')}")
    issues = format_issues(doc)
    if issues:
        lines += ["\nKendala:", *issues]
    lines.append(f"\nBuka di dashboard: {doc_url(doc['id'])}")
    return "\n".join(lines)


def format_processing_result(doc: dict) -> str:
    """Pesan setelah AI selesai membaca invoice yang diunggah lewat bot."""
    status = doc.get("status", "")
    head = f"{STATUS_ICON.get(status, '•')} {doc['request_id']} selesai diproses: {STATUS_LABEL.get(status, status)}"
    lines = [head]
    if doc.get("vendor_name") or doc.get("total") is not None:
        lines.append(f"Vendor: {doc.get('vendor_name') or '-'} · Total: "
                     f"{rupiah(doc['total']) if doc.get('total') is not None else '-'}")
    if status == "READY_FOR_REVIEW":
        lines.append(f"Invoice lolos verifikasi dan menunggu Finance Reviewer ({doc.get('assigned_reviewer') or '-'}).")
    taxes = doc.get("tax_summary") or {}
    if taxes.get("lines"):
        names = ", ".join(sorted({t["name"] for t in taxes["lines"]}))
        lines.append(f"Potongan pajak ({names}): {rupiah(taxes['tax_total'])} · Dibayarkan: {rupiah(taxes['net'])}")
    if status == "DRAFT":
        lines.append("Draf siap. Periksa data dan pajak per invoice serta simulasi voucher di dashboard, lalu kirim ke "
                     "Finance Reviewer (bisa juga lewat tombol di bawah).")
    issues = format_issues(doc)
    if issues:
        lines += ["\nKendala yang perlu Anda tindak lanjuti:", *issues,
                  "\nPerbaiki datanya lewat dashboard."]
    lines.append(f"Buka di dashboard: {doc_url(doc['id'])}")
    return "\n".join(lines)


def format_assistant(body: dict) -> str:
    parts = [plain(body.get("answer") or "")]
    for table in (body.get("data_tables") or [])[:2]:
        rows = table.get("rows") or []
        block = [f"\n📊 {table.get('title', 'Data')}"]
        block += ["• " + " · ".join(str(c) for c in row) for row in rows[:10]]
        if len(rows) > 10:
            block.append(f"…dan {len(rows) - 10} baris lainnya (lihat di dashboard).")
        parts.append("\n".join(block))
    for card in (body.get("cards") or [])[:5]:
        status = card.get("status", "")
        block = f"\n{STATUS_ICON.get(status, '📄')} {card['request_id']} — {card.get('status_label') or status}"
        if card.get("subtitle"):
            block += f"\n{card['subtitle']}"
        if card.get("hint"):
            block += f"\n💡 {card['hint']}"
        if card.get("href"):
            block += f"\n{settings.frontend_url}{card['href']}"
        parts.append(block)
    return "\n".join(p for p in parts if p).strip() or "Maaf, Asisten tidak memberikan jawaban."


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks + ([text] if text else [])


def count_pdf_pages(data: bytes) -> int | None:
    """Jumlah halaman, atau None bila bukan PDF yang bisa dibaca."""
    if not data.startswith(b"%PDF-"):
        return None
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None


# --- Klien API ---

class TelegramAPI:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.base = f"{TELEGRAM_API}/bot{token}"
        self.file_base = f"{TELEGRAM_API}/file/bot{token}"
        self.client = client or httpx.Client(timeout=45)
        # Pemantau hasil proses berjalan di thread lain dan juga mengirim pesan
        self.lock = threading.Lock()

    def call(self, method: str, **params) -> dict | list | bool:
        try:
            with self.lock:
                r = self.client.post(f"{self.base}/{method}", json=params)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            # Pesan error httpx memuat URL yang berisi token: jangan dicatat
            raise RuntimeError(f"Telegram {method} gagal ({type(e).__name__})") from None
        if not body.get("ok"):
            raise RuntimeError(f"Telegram {method} ditolak: {body.get('description')}")
        return body["result"]

    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict]:
        return self.call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message", "callback_query"])

    def send_message(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None:
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            params = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
            if buttons and i == len(chunks) - 1:
                params["reply_markup"] = {"inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in row] for row in buttons]}
            self.call("sendMessage", **params)

    def answer_callback(self, callback_id: str) -> None:
        try:
            self.call("answerCallbackQuery", callback_query_id=callback_id)
        except RuntimeError:
            pass

    def clear_buttons(self, chat_id: int, message_id: int) -> None:
        """Hapus tombol dari pesan yang sudah dijawab, supaya tidak diklik dua kali."""
        try:
            self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                      reply_markup={"inline_keyboard": []})
        except RuntimeError:
            pass

    def download(self, file_id: str) -> bytes:
        path = self.call("getFile", file_id=file_id)["file_path"]
        try:
            with self.lock:
                r = self.client.get(f"{self.file_base}/{path}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"Unduh file Telegram gagal ({type(e).__name__})") from None
        return r.content

    def typing(self, chat_id: int) -> None:
        try:
            self.call("sendChatAction", chat_id=chat_id, action="typing")
        except RuntimeError:
            pass  # hanya indikator, tidak penting bila gagal

    def set_commands(self) -> None:
        self.call("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])


class AmigaAPI:
    """Memanggil API AMIGA atas nama pengguna yang terhubung."""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(base_url=settings.bot_api_base_url, timeout=120)

    def request(self, user: User, method: str, path: str, **kwargs):
        headers = {"Authorization": f"Bearer {create_access_token(user)}"}
        try:
            r = self.client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise BackendError("Server AMIGA sedang tidak bisa dihubungi. Coba lagi beberapa saat lagi.") from None
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            if not isinstance(detail, str):
                detail = "Server AMIGA sedang bermasalah. Coba lagi beberapa saat lagi." if r.status_code >= 500 \
                    else f"Permintaan ditolak ({r.status_code})."
            raise BackendError(detail)
        return r.json()


# --- Bot ---

@dataclass
class LoginGuard:
    """Batasi tebakan kode: setelah 5 kali salah, chat diblokir 15 menit."""
    failures: dict[int, list[float]] = field(default_factory=dict)

    def blocked(self, chat_id: int) -> bool:
        now = time.time()
        recent = [t for t in self.failures.get(chat_id, []) if now - t < LOGIN_BLOCK_SECONDS]
        self.failures[chat_id] = recent
        return len(recent) >= LOGIN_MAX_FAILURES

    def fail(self, chat_id: int) -> None:
        self.failures.setdefault(chat_id, []).append(time.time())

    def reset(self, chat_id: int) -> None:
        self.failures.pop(chat_id, None)


@dataclass
class UploadDraft:
    """Pengajuan invoice yang sedang disusun di chat. Disimpan di memori bot (hilang bila bot restart)."""
    user_id: object
    files: list[tuple[str, bytes, int, str]] = field(default_factory=list)  # (nama, isi, halaman, media type)
    compressed_photo: bool = False  # ada foto yang dikompres Telegram (dikirim sebagai "Foto")
    client_options: list[dict] = field(default_factory=list)
    client: dict | None = None
    request_type: str | None = None  # kategori pengajuan
    # File dari satu kiriman sekaligus (album) belum dibalas; ringkasan dikirim oleh flush_prompts()
    prompt_pending: bool = False
    updated: float = field(default_factory=time.time)

    def expired(self) -> bool:
        return time.time() - self.updated > DRAFT_TTL_SECONDS


class AmigaBot:
    def __init__(self, telegram: TelegramAPI, amiga: AmigaAPI, session_factory=SessionLocal,
                 watch_in_background: bool = True):
        self.tg = telegram
        self.amiga = amiga
        self.session_factory = session_factory
        self.guard = LoginGuard()
        self.drafts: dict[int, UploadDraft] = {}
        self.watch_in_background = watch_in_background

    # -- penerimaan update --

    def handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            callback = update["callback_query"]
            chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
            if chat_id is None:  # pesan bertombol sudah terlalu lama / dihapus
                self.tg.answer_callback(callback["id"])
                return
            self._safe(chat_id, self._handle_callback, callback)
            return
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = (message.get("text") or "").strip()
        if not chat or not (text or message.get("document") or message.get("photo")):
            return
        chat_id = chat["id"]
        if chat.get("type") != "private":
            # Data invoice tidak boleh tampil di grup
            if text.startswith("/") or message.get("document"):
                self.tg.send_message(chat_id, "Demi keamanan data, bot AMIGA hanya bisa dipakai lewat chat pribadi.")
            return
        username = (message.get("from") or {}).get("username")
        if message.get("document") or message.get("photo"):
            self._safe(chat_id, self._handle_file, chat_id, message)
        else:
            self._safe(chat_id, self.reply, chat_id, username, text)

    def _safe(self, chat_id: int, handler, *args) -> None:
        try:
            result = handler(*args)
        except BackendError as e:
            result = f"⚠️ {e}"
        except Exception:
            log.exception("Gagal memproses pesan")
            result = "⚠️ Terjadi kesalahan saat memproses pesan. Coba lagi beberapa saat lagi."
        if isinstance(result, Reply):
            self.tg.send_message(chat_id, result.text, result.buttons)
        elif result:
            self.tg.send_message(chat_id, result)

    # -- pesan teks dan perintah --

    def reply(self, chat_id: int, username: str | None, text: str) -> str | Reply:
        command, _, args = text.partition(" ")
        command = command.split("@")[0].lower() if command.startswith("/") else None
        args = args.strip()

        with self.session_factory() as db:
            if command in ("/login", "/start") and args:
                return self._login(db, chat_id, username, args)
            if command == "/bantuan":
                return HELP_TEXT
            link = telegram_service.get_link_for_chat(db, chat_id)
            if command == "/start":
                if link is None:
                    return "Halo! Saya AMIGA RoBot AI Assistant.\n\n" + login_instructions()
                return f"Halo, {link.user.full_name}! Akun Anda sudah terhubung.\n\n{HELP_TEXT}"
            if command == "/login":
                if link is not None:
                    return f"Telegram ini sudah terhubung sebagai {link.user.full_name} ({link.user.email})."
                return login_instructions()
            if link is None:
                self.drafts.pop(chat_id, None)
                return login_instructions()

            user = link.user
            if command == "/logout":
                self.drafts.pop(chat_id, None)
                telegram_service.unlink(db, link, via="bot Telegram")
                return "Anda sudah keluar. Kirim /login <kode> untuk menghubungkan lagi."
            if command == "/reset":
                self.drafts.pop(chat_id, None)
                telegram_service.reset_session(db, link)
                return "Percakapan baru dimulai. Silakan bertanya."
            if command == "/terakhir":
                return self._latest(user)
            if command == "/kendala":
                return self._problems(user)
            if command == "/status":
                return self._status(user, args)
            if command is not None:
                return f"Perintah {command} tidak dikenal.\n\n{HELP_TEXT}"
            session_id = link.session_id

        self.tg.typing(chat_id)
        body = self.amiga.request(user, "POST", "/ask-agent", json={"question": text[:2000], "session_id": session_id})
        return format_assistant(body)

    def _login(self, db, chat_id: int, username: str | None, args: str) -> str:
        if self.guard.blocked(chat_id):
            return "Terlalu banyak kode yang salah. Coba lagi 15 menit lagi."
        code = telegram_service.normalize_code(args)
        user = telegram_service.redeem_code(db, chat_id, username, code) if code else None
        if user is None:
            self.guard.fail(chat_id)
            return ("Kode tidak valid, sudah dipakai, atau kedaluwarsa. "
                    "Buat kode baru di dashboard: Pengaturan akun → Hubungkan Telegram.")
        self.guard.reset(chat_id)
        self.drafts.pop(chat_id, None)
        return (f"✅ Terhubung sebagai {user.full_name} ({user.email}).\n\n"
                "Kode tadi sudah tidak berlaku lagi. Hapus pesan berisi kode dari chat ini bila mau.\n\n"
                + HELP_TEXT)

    def _documents(self, user: User, **params) -> list[dict]:
        if not user.roles - {Role.SYSTEM_ADMIN}:
            raise BackendError("Akun System Admin tidak memiliki akses ke data invoice. "
                               "Silakan bertanya soal SOP atau akun pengguna.")
        return self.amiga.request(user, "GET", "/documents", params=params)

    def _latest(self, user: User) -> str:
        params = {"sort": "terbaru"}
        # Reviewer murni: dokumen yang ditugaskan kepadanya. Pengaju dan Service Lead: semua yang boleh dilihat.
        if Role.FINANCE_REVIEWER in user.roles and not user.roles & SUBMITTER_ROLES:
            params["reviewer_id"] = str(user.id)
        docs = self._documents(user, **params)[:5]
        if not docs:
            return "Belum ada invoice untuk ditampilkan."
        return "Progress invoice terakhir:\n\n" + "\n\n".join(format_doc_line(d) for d in docs) \
            + "\n\nDetail: /status <Request ID>"

    def _problems(self, user: User) -> str:
        docs = self._documents(user, problem="true", sort="tenggat")
        if not docs:
            return "✅ Tidak ada invoice yang terkendala saat ini."
        lines = [format_doc_line(d) for d in docs[:10]]
        more = f"\n\n…dan {len(docs) - 10} lainnya di dashboard." if len(docs) > 10 else ""
        return f"Invoice terkendala ({len(docs)}):\n\n" + "\n\n".join(lines) + more \
            + "\n\nLihat alasannya: /status <Request ID>"

    def _status(self, user: User, args: str) -> str:
        match = REQUEST_ID.search(args)
        if not match:
            return "Tulis Request ID-nya, contoh: /status REQ-20261015-ABC123"
        request_id = match.group(0).upper()
        found = [d for d in self._documents(user, q=request_id) if d["request_id"].upper() == request_id]
        if not found:
            return f"Dokumen {request_id} tidak ditemukan, atau bukan milik perusahaan yang ditugaskan kepada Anda."
        detail = self.amiga.request(user, "GET", f"/documents/{found[0]['id']}")
        return format_doc_detail(detail)

    # -- unggah invoice --

    def _draft(self, chat_id: int, user: User) -> UploadDraft | None:
        draft = self.drafts.get(chat_id)
        if draft and (draft.expired() or draft.user_id != user.id):
            self.drafts.pop(chat_id, None)
            return None
        return draft

    def _handle_file(self, chat_id: int, message: dict) -> str | Reply | None:
        with self.session_factory() as db:
            link = telegram_service.get_link_for_chat(db, chat_id)
            if link is None:
                return login_instructions()
            user = link.user
        if not user.roles & SUBMITTER_ROLES:
            return "Hanya PIC Klien dan Intake Support yang bisa mengunggah invoice."
        document = message.get("document")
        photo = (message.get("photo") or [None])[-1]  # ukuran terbesar ada di akhir daftar
        if document:
            name = document.get("file_name") or "invoice.pdf"
            file_id, size = document["file_id"], document.get("file_size") or 0
            mime = document.get("mime_type") or ""
            if not (mime in ACCEPTED_MIME or name.lower().endswith(ACCEPTED_EXT)):
                return f"{name}: kirim invoice sebagai {file_conversion.ACCEPTED_TEXT}."
        elif photo:
            name = f"foto-invoice-{int(time.time())}.jpg"
            file_id, size = photo["file_id"], photo.get("file_size") or 0
        else:
            return f"Kirim invoice sebagai {file_conversion.ACCEPTED_TEXT}."
        limit_mb = min(settings.max_upload_mb, TELEGRAM_DOWNLOAD_MB)
        if size > limit_mb * 1024 * 1024:
            return f"{name}: ukuran file melebihi {limit_mb} MB."

        draft = self._draft(chat_id, user)
        if draft is None:
            draft = self.drafts[chat_id] = UploadDraft(user_id=user.id)
        # Batas akhir per kategori dicek server saat dikirim (Reimburse 20, lainnya 10)
        if len(draft.files) >= settings.max_reimburse_files:
            return f"Maksimal {settings.max_reimburse_files} file bukti per pengajuan."

        data = self.tg.download(file_id)
        # Diperiksa dengan aturan yang sama dengan server: foto diubah menjadi PDF untuk menghitung halaman
        try:
            prepared = file_conversion.to_pdf(data)
        except file_conversion.UnsupportedFile as e:
            return f"{name}: {e}"
        pages = count_pdf_pages(prepared.pdf)
        if pages is None:
            return f"{name}: file PDF rusak atau tidak bisa dibaca."
        if pages > settings.max_pdf_pages:
            return f"{name}: berisi {pages} halaman. Maksimal {settings.max_pdf_pages} halaman per file."
        media_type = file_conversion.IMAGE_TYPES[prepared.source_format] if prepared.converted else "application/pdf"
        if photo and not document:
            draft.compressed_photo = True
        draft.files.append((name[:300], data, pages, media_type))
        draft.updated = time.time()

        # Beberapa file yang dikirim sekaligus datang sebagai pesan terpisah: balas sekali saja,
        # setelah semua file dari kiriman itu diproses (lihat flush_prompts)
        if message.get("media_group_id"):
            draft.prompt_pending = True
            return None
        draft.prompt_pending = False
        return self._draft_prompt(user, draft)

    def flush_prompts(self) -> None:
        """Kirim ringkasan untuk draft yang menerima beberapa file sekaligus."""
        for chat_id, draft in list(self.drafts.items()):
            if not draft.prompt_pending:
                continue
            draft.prompt_pending = False
            with self.session_factory() as db:
                link = telegram_service.get_link_for_chat(db, chat_id)
                user = link.user if link else None
            if user is not None:
                self._safe(chat_id, self._draft_prompt, user, draft)

    def _draft_prompt(self, user: User, draft: UploadDraft) -> Reply:
        """Langkah berikutnya: pilih perusahaan → jenis permintaan → ringkasan + konfirmasi."""
        if draft.client is None:
            if not draft.client_options:
                me = self.amiga.request(user, "GET", "/auth/me")
                draft.client_options = me.get("upload_clients") or []
            if not draft.client_options:
                raise BackendError("Akun Anda belum ditugaskan ke perusahaan mana pun. Hubungi System Admin.")
            # Pilihan perusahaan selalu ditampilkan, juga bila PIC hanya memegang satu perusahaan,
            # supaya PIC sadar voucher ini atas nama perusahaan mana (feedback owner)
            return Reply(f"{self._file_list(draft)}\n\nUntuk perusahaan mana?",
                         [[(c["name"], f"up:c:{c['id']}")] for c in draft.client_options])
        if draft.request_type is None:
            return Reply(f"{self._file_list(draft)}\n\nKategori voucher?",
                         [[(name, f"up:t:{i}")] for i, name in enumerate(CATEGORIES)])
        return Reply(
            "Ringkasan pengajuan:\n"
            f"{self._file_list(draft)}\n"
            f"• Perusahaan: {draft.client['name']}\n"
            f"• Kategori: {draft.request_type}\n"
            f"• Saluran: Telegram · Tanggal pengajuan: {date.today().isoformat()}\n\n"
            "Mau menambah invoice lain ke voucher yang sama? Kirim file atau fotonya sekarang.",
            [[("✅ Kirim ke AMIGA", "up:send")], [("❌ Batal", "up:cancel")]],
        )

    @staticmethod
    def _file_list(draft: UploadDraft) -> str:
        files = "\n".join(f"  {i}. {name} ({pages} hal.)" for i, (name, _, pages, _) in enumerate(draft.files, 1))
        tip = ("\n💡 Foto yang dikirim sebagai \"Foto\" dikompres Telegram. Untuk hasil baca AI terbaik, "
               "kirim sebagai File (📎 → File).") if draft.compressed_photo else ""
        return f"📎 {len(draft.files)} file invoice:\n{files}{tip}"

    def _handle_callback(self, callback: dict) -> str | Reply | None:
        self.tg.answer_callback(callback["id"])
        message = callback.get("message") or {}
        chat_id = message["chat"]["id"]
        self.tg.clear_buttons(chat_id, message.get("message_id"))
        data = callback.get("data") or ""
        with self.session_factory() as db:
            link = telegram_service.get_link_for_chat(db, chat_id)
            if link is None:
                return login_instructions()
            user = link.user
        if data.startswith("sub:"):
            sent = self.amiga.request(user, "POST", f"/documents/{data[4:]}/submit")
            return (f"📤 {sent['request_id']} dikirim ke Finance Reviewer ({sent.get('assigned_reviewer') or '-'}).\n"
                    f"Status: {STATUS_LABEL.get(sent['status'], sent['status'])}")
        draft = self._draft(chat_id, user)
        if draft is None:
            return "Pengajuan ini sudah tidak aktif. Kirim ulang file PDF invoice untuk memulai."

        if data == "up:cancel":
            self.drafts.pop(chat_id, None)
            return "❌ Pengajuan dibatalkan. File tidak dikirim ke AMIGA."
        if data.startswith("up:c:"):
            chosen = next((c for c in draft.client_options if c["id"] == data[5:]), None)
            if chosen is None:
                return "Perusahaan tidak valid. Pilih dari tombol yang tersedia."
            draft.client = chosen
        elif data.startswith("up:t:"):
            index = data[5:]
            if not index.isdigit() or int(index) >= len(CATEGORIES):
                return "Kategori tidak valid. Pilih dari tombol yang tersedia."
            draft.request_type = CATEGORIES[int(index)]
        elif data == "up:send":
            if draft.client is None or draft.request_type is None:
                return self._draft_prompt(user, draft)
            # Keluarkan dulu dari daftar draft supaya klik ganda tidak mengunggah dua kali
            self.drafts.pop(chat_id, None)
            return self._submit(chat_id, user, draft)
        draft.updated = time.time()
        return self._draft_prompt(user, draft)

    def _submit(self, chat_id: int, user: User, draft: UploadDraft) -> None:
        self.tg.typing(chat_id)
        doc = self.amiga.request(
            user, "POST", "/documents",
            data={"client_id": draft.client["id"], "request_type": draft.request_type,
                  "channel": "Telegram", "submitted_date": date.today().isoformat()},
            files=[("files", (name, content, media_type)) for name, content, _, media_type in draft.files],
        )
        self.tg.send_message(chat_id, (
            f"✅ Terkirim ke AMIGA!\nRequest ID: {doc['request_id']}\nStatus: {STATUS_LABEL['QUEUED']}\n\n"
            "AI sedang membaca invoice. Saya kabari hasilnya sebentar lagi.\n"
            f"Dashboard: {doc_url(doc['id'])}"))
        self._start_watch(chat_id, user.id, doc["id"])
        return None

    def _start_watch(self, chat_id: int, user_id, document_id: str) -> None:
        if self.watch_in_background:
            threading.Thread(target=self.watch_document, args=(chat_id, user_id, document_id), daemon=True).start()
        else:
            self.watch_document(chat_id, user_id, document_id, interval=0)

    def watch_document(self, chat_id: int, user_id, document_id: str,
                       timeout: float = WATCH_SECONDS, interval: float = WATCH_INTERVAL) -> None:
        """Pantau dokumen sampai AI selesai, lalu kirim hasilnya ke chat."""
        deadline = time.time() + timeout
        detail = None
        try:
            while True:
                with self.session_factory() as db:
                    user = db.get(User, user_id)
                    if user is None or not user.is_active:
                        return
                    detail = self.amiga.request(user, "GET", f"/documents/{document_id}")
                if detail["status"] not in IN_PROGRESS or time.time() >= deadline:
                    break
                time.sleep(interval)
            buttons = None
            if detail["status"] in IN_PROGRESS:
                text = (f"⏳ {detail['request_id']} masih diproses. Cek lagi nanti dengan "
                        f"/status {detail['request_id']}")
            else:
                text = format_processing_result(detail)
                if detail["status"] == "DRAFT":
                    buttons = [[("📤 Kirim ke reviewer", f"sub:{detail['id']}")]]
            self.tg.send_message(chat_id, text, buttons)
        except Exception:
            log.exception("Gagal memantau hasil proses dokumen")


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx mencatat URL lengkap di level INFO, dan URL Telegram berisi token bot
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN belum diisi di backend/.env")

    telegram = TelegramAPI(settings.telegram_bot_token)
    bot = AmigaBot(telegram, AmigaAPI())
    me = telegram.call("getMe")
    telegram.set_commands()
    log.info("Bot @%s berjalan. API AMIGA: %s. Tekan Ctrl+C untuk berhenti.", me["username"], settings.bot_api_base_url)

    offset = None
    while True:
        try:
            updates = telegram.get_updates(offset)
        except RuntimeError as e:
            log.warning("%s; mencoba lagi dalam 5 detik", e)
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            sent_at = (update.get("message") or (update.get("callback_query") or {}).get("message") or {}).get("date", 0)
            if "message" in update and time.time() - sent_at > STALE_SECONDS:
                log.info("Lewati pesan lama (update %s)", update["update_id"])
                continue
            bot.handle_update(update)
        bot.flush_prompts()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
