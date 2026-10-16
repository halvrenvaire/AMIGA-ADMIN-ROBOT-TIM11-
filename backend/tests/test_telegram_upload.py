"""Unggah invoice lewat bot Telegram (saluran "Telegram").

Bot memakai endpoint unggah yang sama dengan dashboard, dengan AI tiruan dan transaksi database
yang di-rollback (fixture `tx` / `extractor` dari test_documents).
"""
import random

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import db as db_module
from app.config import settings
from app.models import AuditLog, Document
from app.services import telegram_service
from bot.telegram_bot import AmigaAPI, AmigaBot
from tests.test_documents import DrainingClient, extractor, invoice, make_pdf, tx  # noqa: F401  (fixture)
from tests.test_telegram import FakeTelegram, _user
from app.main import app


@pytest.fixture
def bot(extractor, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "telegram_bot_token", "token-test")
    tg = FakeTelegram()
    # session_factory dibaca sekarang, setelah fixture `tx` mengganti SessionLocal ke transaksi test
    return AmigaBot(tg, AmigaAPI(client=DrainingClient(app)), session_factory=db_module.SessionLocal,
                    watch_in_background=False), tg


def _link(bot_and_tg, email: str) -> int:
    bot, tg = bot_and_tg
    chat = random.randint(10 ** 9, 10 ** 10)
    with db_module.SessionLocal() as db:
        code, _ = telegram_service.create_link_code(db, db.merge(_user(email)))
    bot.handle_update({"update_id": 1, "message": {"chat": {"id": chat, "type": "private"}, "text": f"/login {code}"}})
    assert "Terhubung" in tg.last
    return chat


def _send_pdf(bot_and_tg, chat, pdf=None, name="invoice.pdf", group=None):
    bot, tg = bot_and_tg
    file_id = f"f{random.randint(0, 10 ** 9)}"
    tg.files[file_id] = pdf if pdf is not None else make_pdf()
    message = {"chat": {"id": chat, "type": "private"},
               "document": {"file_id": file_id, "file_name": name, "mime_type": "application/pdf", "file_size": 1000}}
    if group:
        message["media_group_id"] = group
    count = len(tg.sent)
    bot.handle_update({"update_id": 2, "message": message})
    return tg.last if len(tg.sent) > count else None


def _click(bot_and_tg, chat, data):
    bot, tg = bot_and_tg
    assert data in [d for row in tg.buttons for _, d in row], f"tombol {data} tidak ada: {tg.buttons}"
    bot.handle_update({"update_id": 3, "callback_query": {
        "id": "cb", "data": data, "message": {"message_id": 10, "chat": {"id": chat, "type": "private"}}}})
    return tg.last


def _documents():
    with db_module.SessionLocal() as db:
        return list(db.scalars(select(Document).options(selectinload(Document.files))
                               .where(Document.channel == "Telegram")))


def test_pic_uploads_invoice_and_gets_processing_result(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    # PIC Alpha hanya ditugaskan ke satu perusahaan: langsung ditanya jenis permintaan
    assert "Jenis permintaan?" in _send_pdf(bot, chat, name="inv-maret.pdf")
    summary = _click(bot, chat, "up:t:default")
    assert "PT Klien Alpha" in summary and "Pembayaran vendor" in summary and "Telegram" in summary

    _click(bot, chat, "up:send")
    sent = [text for _, text in bot[1].sent]
    assert "Terkirim ke AMIGA" in sent[-2] and "REQ-" in sent[-2]
    assert "selesai diproses: Siap ditinjau" in sent[-1] and "PT Vendor Jaya" in sent[-1]

    [doc] = _documents()
    assert doc.status.value == "READY_FOR_REVIEW" and doc.original_filename == "inv-maret.pdf"
    assert doc.uploaded_by == _user("pic.alpha@amiga.test").id
    with db_module.SessionLocal() as db:
        note = db.scalar(select(AuditLog.note).where(AuditLog.document_id == doc.id,
                                                    AuditLog.action == "DOCUMENT_UPLOADED"))
    assert "via Telegram" in note


def test_exception_result_lists_issues(bot, extractor):  # noqa: F811
    extractor.result = invoice(account_no=None)
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _click(bot, chat, "up:t:default")
    _click(bot, chat, "up:send")
    result = bot[1].last
    assert "Ada kendala" in result and "Data belum lengkap" in result


def test_several_pdfs_sent_at_once_become_one_voucher(bot, extractor):  # noqa: F811
    extractor.result = [invoice(invoice_no="INV-A"), invoice(invoice_no="INV-B")]
    chat = _link(bot, "pic.alpha@amiga.test")
    assert _send_pdf(bot, chat, name="a.pdf", group="album1") is None  # dibalas sekali, setelah semua file masuk
    assert _send_pdf(bot, chat, name="b.pdf", group="album1") is None
    bot[0].flush_prompts()
    assert "2 file invoice" in bot[1].last and "a.pdf" in bot[1].last and "b.pdf" in bot[1].last
    _click(bot, chat, "up:t:default")
    _click(bot, chat, "up:send")
    [doc] = _documents()
    assert len(doc.files) == 2


def test_custom_request_type(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    assert "Ketik jenis permintaan" in _click(bot, chat, "up:t:custom")
    bot[0].handle_update({"update_id": 4, "message": {"chat": {"id": chat, "type": "private"},
                                                      "text": "Reimburse perjalanan dinas"}})
    assert "Jenis permintaan: Reimburse perjalanan dinas" in bot[1].last


def test_cancel_sends_nothing(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _click(bot, chat, "up:t:default")
    assert "dibatalkan" in _click(bot, chat, "up:cancel")
    assert _documents() == []


def test_double_click_send_uploads_once(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _click(bot, chat, "up:t:default")
    bot_, tg = bot
    tg.buttons_before = tg.buttons
    _click(bot, chat, "up:send")
    tg.buttons = tg.buttons_before  # klik ulang tombol yang sama
    assert "sudah tidak aktif" in _click(bot, chat, "up:send")
    assert len(_documents()) == 1


def test_only_submitters_can_upload(bot):
    chat = _link(bot, "reviewer1@amiga.test")
    assert "Hanya PIC Klien dan Intake Support" in _send_pdf(bot, chat)


def test_invalid_files_are_rejected(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    assert "maksimal" in _send_pdf(bot, chat, pdf=make_pdf(pages=settings.max_pdf_pages + 1)).lower()
    assert "bukan PDF" in _send_pdf(bot, chat, pdf=b"bukan pdf sama sekali")
    bot[0].handle_update({"update_id": 5, "message": {"chat": {"id": chat, "type": "private"},
                                                      "photo": [{"file_id": "x"}]}})
    assert "sebagai file PDF" in bot[1].last


def test_unlinked_chat_cannot_upload(bot):
    chat = random.randint(10 ** 9, 10 ** 10)
    assert "belum terhubung" in _send_pdf(bot, chat)
