"""Bot Telegram: kode sekali pakai, endpoint Pengaturan akun, dan percakapan bot.

Bot diuji dengan Telegram tiruan, tetapi API AMIGA sungguhan (TestClient), jadi hak akses
dan isolasi klien yang berlaku sama dengan dashboard.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Client, DocStatus, Document, TelegramLink, TelegramLinkCode, User
from app.services import telegram_service
from bot.telegram_bot import AmigaAPI, AmigaBot, LOGIN_MAX_FAILURES, format_assistant, split_message
from tests.auth_helpers import auth_header
from tests.test_ask import client  # noqa: F401  (fixture: Asisten palsu + akun reviewer1)

SEED_EMAILS = ["pic.alpha@amiga.test", "pic.beta@amiga.test", "reviewer1@amiga.test", "admin@amiga.test"]


def _user(email: str) -> User:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


def _clean_telegram():
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.email.in_(SEED_EMAILS))))
        db.execute(delete(TelegramLink).where(TelegramLink.user_id.in_(ids)))
        db.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id.in_(ids)))
        db.commit()


@pytest.fixture(autouse=True)
def clean_telegram(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "token-test")
    _clean_telegram()
    yield
    _clean_telegram()


def _code_for(email: str) -> str:
    with SessionLocal() as db:
        code, _ = telegram_service.create_link_code(db, db.merge(_user(email)))
        return code


def _chat_id() -> int:
    return random.randint(10 ** 9, 10 ** 10)


# --- Layanan kode sekali pakai ---

def test_code_links_chat_and_is_single_use():
    code, chat = _code_for("pic.alpha@amiga.test"), _chat_id()
    with SessionLocal() as db:
        user = telegram_service.redeem_code(db, chat, "rina_tg", code)
        assert user.email == "pic.alpha@amiga.test"
        link = telegram_service.get_link_for_chat(db, chat)
        assert link.telegram_username == "rina_tg" and link.session_id.startswith("tg-")
        assert telegram_service.redeem_code(db, _chat_id(), None, code) is None  # sudah dipakai
        assert db.scalar(select(AuditLog).where(AuditLog.action == "TELEGRAM_LINKED",
                                                AuditLog.actor_id == user.id)) is not None


def test_expired_and_wrong_codes_are_rejected():
    code = _code_for("pic.alpha@amiga.test")
    with SessionLocal() as db:
        assert telegram_service.redeem_code(db, _chat_id(), None, "000000" if code != "000000" else "111111") is None
        db.execute(TelegramLinkCode.__table__.update().values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
        assert telegram_service.redeem_code(db, _chat_id(), None, code) is None


def test_new_code_cancels_previous_code():
    old = _code_for("pic.alpha@amiga.test")
    new = _code_for("pic.alpha@amiga.test")
    with SessionLocal() as db:
        assert telegram_service.redeem_code(db, _chat_id(), None, old) is None
        assert telegram_service.redeem_code(db, _chat_id(), None, new) is not None


def test_relinking_moves_account_to_new_chat():
    first, second = _chat_id(), _chat_id()
    with SessionLocal() as db:
        telegram_service.redeem_code(db, first, None, _code_for("pic.alpha@amiga.test"))
        telegram_service.redeem_code(db, second, None, _code_for("pic.alpha@amiga.test"))
        assert telegram_service.get_link_for_chat(db, first) is None
        assert telegram_service.get_link_for_chat(db, second).user.email == "pic.alpha@amiga.test"


def test_code_normalization():
    assert telegram_service.normalize_code(" 123 456 ") == "123456"
    assert telegram_service.normalize_code("12345") is None


# --- Endpoint Pengaturan akun ---

def test_settings_endpoints():
    api = TestClient(app, headers=auth_header("pic.alpha@amiga.test"))
    assert api.get("/auth/me/telegram").json()["linked"] is False
    assert api.delete("/auth/me/telegram").status_code == 404

    body = api.post("/auth/me/telegram/link-code").json()
    assert len(body["code"]) == 6 and body["code"].isdigit()
    assert body["deep_link"] == f"https://t.me/{settings.telegram_bot_username}?start={body['code']}"

    with SessionLocal() as db:
        telegram_service.redeem_code(db, _chat_id(), "rina_tg", body["code"])
    status = api.get("/auth/me/telegram").json()
    assert status["linked"] is True and status["telegram_username"] == "rina_tg"
    assert api.delete("/auth/me/telegram").status_code == 204
    assert api.get("/auth/me/telegram").json()["linked"] is False


def test_link_code_requires_login_and_configured_bot(monkeypatch):
    assert TestClient(app).post("/auth/me/telegram/link-code").status_code == 401
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    api = TestClient(app, headers=auth_header("pic.alpha@amiga.test"))
    assert api.post("/auth/me/telegram/link-code").status_code == 503


# --- Percakapan bot ---

class FakeTelegram:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.buttons: list = []  # tombol pada pesan terakhir
        self.files: dict[str, bytes] = {}
        self.documents: list[tuple[int, str, bytes]] = []

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, text))
        self.buttons = buttons or []

    def typing(self, chat_id):
        pass

    def answer_callback(self, callback_id):
        pass

    def send_document(self, chat_id, filename, content, caption=""):
        self.documents.append((chat_id, filename, content))

    def clear_buttons(self, chat_id, message_id):
        pass

    def download(self, file_id):
        return self.files[file_id]

    @property
    def last(self) -> str:
        return self.sent[-1][1]


@pytest.fixture
def bot(client):  # noqa: F811  (`client` memasang Asisten palsu di app.state)
    tg = FakeTelegram()
    return AmigaBot(tg, AmigaAPI(client=TestClient(app))), tg


def _send(bot_and_tg, chat_id, text, chat_type="private"):
    bot, tg = bot_and_tg
    bot.handle_update({"update_id": 1, "message": {
        "chat": {"id": chat_id, "type": chat_type}, "from": {"username": "tester"}, "text": text}})
    return tg.last


def _linked_chat(bot_and_tg, email) -> int:
    chat = _chat_id()
    assert "Terhubung sebagai" in _send(bot_and_tg, chat, f"/login {_code_for(email)}")
    return chat


def test_unlinked_chat_gets_login_instructions(bot):
    chat = _chat_id()
    assert "belum terhubung" in _send(bot, chat, "/start")
    assert "Hubungkan Telegram" in _send(bot, chat, "halo, invoice saya gimana?")
    assert "/login" in _send(bot, chat, "/terakhir")
    assert "/status" in _send(bot, chat, "/bantuan")


def test_deep_link_start_with_code_links_account(bot):
    chat = _chat_id()
    reply = _send(bot, chat, f"/start {_code_for('pic.alpha@amiga.test')}")
    assert "Terhubung sebagai Rina (PIC Alpha)" in reply


def test_wrong_codes_are_rate_limited(bot):
    chat = _chat_id()
    for _ in range(LOGIN_MAX_FAILURES):
        assert "tidak valid" in _send(bot, chat, "/login 999999")
    # Kode benar pun ditolak selama diblokir
    assert "Terlalu banyak" in _send(bot, chat, f"/login {_code_for('pic.alpha@amiga.test')}")


def test_group_chat_is_refused(bot):
    reply = _send(bot, -_chat_id(), f"/login {_code_for('pic.alpha@amiga.test')}", chat_type="group")
    assert "chat pribadi" in reply
    with SessionLocal() as db:
        assert telegram_service.get_link_for_user(db, _user("pic.alpha@amiga.test")) is None


def test_commands_use_api_with_account_permissions(bot):
    chat = _linked_chat(bot, "pic.alpha@amiga.test")
    assert _send(bot, chat, "/terakhir")  # daftar atau "Belum ada invoice", tanpa error
    assert "kendala" in _send(bot, chat, "/kendala").lower()
    assert "Tulis Request ID" in _send(bot, chat, "/status")
    assert "tidak ditemukan" in _send(bot, chat, "/status REQ-19990101-TIDAKADA")
    assert "tidak dikenal" in _send(bot, chat, "/apaini")


@pytest.fixture
def beta_document():
    """Dokumen milik PT Klien Beta, dibuat langsung di database test."""
    request_id = f"REQ-TGTEST-{random.randint(10 ** 5, 10 ** 6)}"
    with SessionLocal() as db:
        beta = db.scalar(select(Client).where(Client.name == "PT Klien Beta"))
        doc = Document(request_id=request_id, client_id=beta.id, uploaded_by=_user("pic.beta@amiga.test").id,
                       status=DocStatus.EXCEPTION, file_key="tg-test.pdf", original_filename="tg-test.pdf",
                       page_count=1)
        db.add(doc)
        db.commit()
        doc_id = doc.id
    yield request_id
    with SessionLocal() as db:
        db.execute(delete(Document).where(Document.id == doc_id))
        db.commit()


def test_status_respects_client_isolation(bot, beta_document):
    """Dokumen klien Beta tidak bisa dibuka oleh PIC Alpha lewat bot, sama seperti di dashboard."""
    alpha = _linked_chat(bot, "pic.alpha@amiga.test")
    assert "tidak ditemukan" in _send(bot, alpha, f"/status {beta_document}")
    assert beta_document not in _send(bot, alpha, "/kendala")

    beta = _linked_chat(bot, "pic.beta@amiga.test")
    detail = _send(bot, beta, f"/status {beta_document.lower()}")
    assert beta_document in detail and "Ada kendala" in detail
    assert beta_document in _send(bot, beta, "/kendala")


def test_free_text_goes_to_assistant_and_reset_starts_new_session(bot):
    chat = _linked_chat(bot, "reviewer1@amiga.test")
    assert "jawaban untuk: Apa itu QUEUED?" in _send(bot, chat, "Apa itu QUEUED?")
    with SessionLocal() as db:
        before = telegram_service.get_link_for_chat(db, chat).session_id
    assert "Percakapan baru" in _send(bot, chat, "/reset")
    with SessionLocal() as db:
        assert telegram_service.get_link_for_chat(db, chat).session_id != before


def test_system_admin_has_no_invoice_access(bot):
    chat = _linked_chat(bot, "admin@amiga.test")
    assert "tidak memiliki akses ke data invoice" in _send(bot, chat, "/terakhir")


def test_logout_unlinks(bot):
    chat = _linked_chat(bot, "pic.alpha@amiga.test")
    assert "sudah keluar" in _send(bot, chat, "/logout")
    assert "belum terhubung" in _send(bot, chat, "/terakhir")


def test_deactivated_account_loses_bot_access(bot):
    chat = _linked_chat(bot, "pic.beta@amiga.test")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "pic.beta@amiga.test"))
        user.is_active = False
        db.commit()
    try:
        assert "belum terhubung" in _send(bot, chat, "/terakhir")
    finally:
        with SessionLocal() as db:
            db.scalar(select(User).where(User.email == "pic.beta@amiga.test")).is_active = True
            db.commit()


# --- Format pesan ---

def test_format_assistant_renders_tables_cards_and_strips_markdown():
    text = format_assistant({
        "answer": "**Ringkasan**: ada 2 dokumen.",
        "data_tables": [{"title": "Progres", "columns": ["A", "B"], "rows": [["REQ-1", "Antre"]] * 12}],
        "cards": [{"request_id": "REQ-1", "status": "EXCEPTION", "status_label": "Ada kendala",
                   "subtitle": "Vendor X", "hint": "Lengkapi rekening", "href": "/dokumen/abc"}],
    })
    assert text.startswith("Ringkasan: ada 2 dokumen.")
    assert "📊 Progres" in text and "dan 2 baris lainnya" in text
    assert f"{settings.frontend_url}/dokumen/abc" in text and "💡 Lengkapi rekening" in text


def test_long_messages_are_split():
    parts = split_message("baris\n" * 2000, limit=4000)
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
