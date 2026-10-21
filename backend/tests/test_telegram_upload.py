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
from tests.test_image_upload import image_bytes
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


def _choose(bot_and_tg, chat, category=0):
    """Pilih perusahaan (selalu ditanyakan) lalu kategori lewat tombol."""
    _, tg = bot_and_tg
    company = next(d for row in tg.buttons for _, d in row if d.startswith("up:c:"))
    _click(bot_and_tg, chat, company)
    return _click(bot_and_tg, chat, f"up:t:{category}")


def _documents():
    with db_module.SessionLocal() as db:
        return list(db.scalars(select(Document).options(selectinload(Document.files))
                               .where(Document.channel == "Telegram")))


def test_pic_uploads_invoice_and_gets_processing_result(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    # Pilihan perusahaan selalu ditampilkan, walau PIC Alpha hanya memegang satu perusahaan
    assert "Untuk perusahaan mana?" in _send_pdf(bot, chat, name="inv-maret.pdf")
    assert [label for row in bot[1].buttons for label, _ in row] == ["PT Klien Alpha"]
    _click(bot, chat, bot[1].buttons[0][0][1])
    assert "Kategori voucher?" in bot[1].last
    assert [label for row in bot[1].buttons for label, _ in row] == [
        "Voucher Pengeluaran Vendor", "Voucher Pengeluaran Reimburse", "Lainnya"]
    summary = _click(bot, chat, "up:t:0")
    assert "PT Klien Alpha" in summary and "Kategori: Voucher Pengeluaran Vendor" in summary and "Telegram" in summary

    _click(bot, chat, "up:send")
    sent = [text for _, text in bot[1].sent]
    assert "Terkirim ke AMIGA" in sent[-2] and "REQ-" in sent[-2]
    assert "selesai diproses: Draf" in sent[-1] and "PT Vendor Jaya" in sent[-1]
    assert "Saran pajak" in sent[-1] and "Bukti 1: Tanpa potongan" in sent[-1]
    [doc] = _documents()
    assert doc.status.value == "DRAFT"
    # Pajak belum dipilih: bot hanya menawarkan pilihan pajak (lalu kirim), bukan tombol kirim langsung
    assert [label for row in bot[1].buttons for label, _ in row] == ["✅ Pakai saran pajak & kirim", "Tanpa potongan & kirim"]
    reply = _click(bot, chat, f"tx:a:{doc.id}")
    assert "dikirim ke Finance Reviewer" in reply and "Dibayarkan" in reply

    [doc] = _documents()
    assert doc.status.value == "READY_FOR_REVIEW" and doc.original_filename == "inv-maret.pdf"
    assert doc.uploaded_by == _user("pic.alpha@amiga.test").id
    with db_module.SessionLocal() as db:
        note = db.scalar(select(AuditLog.note).where(AuditLog.document_id == doc.id,
                                                    AuditLog.action == "DOCUMENT_UPLOADED"))
    assert "via Telegram" in note


def test_exception_result_lists_issues(bot, extractor):  # noqa: F811
    extractor.result = invoice(invoice_date=None)
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _choose(bot, chat)
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
    _choose(bot, chat)
    _click(bot, chat, "up:send")
    [doc] = _documents()
    assert len(doc.files) == 2


def test_reimburse_category_is_sent(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    assert "Kategori: Voucher Pengeluaran Reimburse" in _choose(bot, chat, 1)
    _click(bot, chat, "up:send")
    [doc] = _documents()
    assert doc.request_type == "Voucher Pengeluaran Reimburse"


def test_cancel_sends_nothing(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _choose(bot, chat)
    assert "dibatalkan" in _click(bot, chat, "up:cancel")
    assert _documents() == []


def test_double_click_send_uploads_once(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    _send_pdf(bot, chat)
    _choose(bot, chat)
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
    assert "PDF atau foto" in _send_pdf(bot, chat, pdf=b"bukan pdf sama sekali")
    assert "PDF atau foto" in _send_pdf(bot, chat, pdf=b"PK\x03\x04", name="invoice.docx")


def test_photo_is_accepted_and_uploaded_with_original(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    bot_, tg = bot
    tg.files["foto1"] = image_bytes("JPEG")
    bot_.handle_update({"update_id": 6, "message": {"chat": {"id": chat, "type": "private"},
                                                    "photo": [{"file_id": "kecil"}, {"file_id": "foto1"}]}})
    assert "foto-invoice-" in tg.last and "dikompres Telegram" in tg.last
    assert "Untuk perusahaan mana?" in tg.last  # foto juga menampilkan pilihan perusahaan
    _choose(bot, chat)
    _click(bot, chat, "up:send")
    assert "selesai diproses: Draf" in tg.last
    [doc] = _documents()
    assert doc.files[0].source_format == "jpg" and doc.files[0].source_file_key


def test_image_sent_as_file_has_no_compression_tip(bot):
    chat = _link(bot, "pic.alpha@amiga.test")
    reply = _send_pdf(bot, chat, pdf=image_bytes("PNG"), name="scan.png")
    assert "scan.png (1 hal.)" in reply and "dikompres" not in reply


def test_unlinked_chat_cannot_upload(bot):
    chat = random.randint(10 ** 9, 10 ** 10)
    assert "belum terhubung" in _send_pdf(bot, chat)


def test_many_missing_fields_are_summarized_in_one_line():
    from bot.telegram_bot import format_issues
    fields = ["vendor_name", "invoice_no", "invoice_date", "total", "account_no"]
    doc = {"issues": [{"code": "MISSING_EVIDENCE", "field": f, "message": "x"} for f in fields]
           + [{"code": "NEEDS_MANUAL_REVIEW", "field": None, "message": "Foto buram."}]}
    lines = format_issues(doc)
    assert len(lines) == 2
    assert "5 data (nama vendor, nomor invoice, tanggal, total, nomor rekening)" in lines[0]
    assert "Foto buram." in lines[1]


def test_processing_result_shows_tax_deduction_and_net():
    from bot.telegram_bot import format_processing_result
    doc = {"id": "x", "request_id": "REQ-1", "status": "DRAFT", "vendor_name": "PT A", "total": "900000", "issues": [],
           "tax_summary": {"gross": "900000", "tax_total": "18000", "net": "882000",
                           "lines": [{"name": "PPh 23", "amount": "18000"}]}}
    text = format_processing_result(doc)
    assert "Potongan pajak (PPh 23)" in text and "882.000" in text
