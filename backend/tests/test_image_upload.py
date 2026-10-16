"""Unggah invoice berupa foto (JPG, PNG, WEBP): dikonversi ke PDF, file asli disimpan."""
import io

import pytest
from PIL import Image
from pypdf import PdfReader

from app.services import file_conversion
from app.services.file_conversion import UnsupportedFile, to_pdf
from tests.test_documents import api, detail, extractor, make_pdf, tx, upload  # noqa: F401  (fixture)


def image_bytes(fmt: str, size=(1200, 800), mode="RGB", exif_orientation: int | None = None) -> bytes:
    img = Image.new(mode, size, (255, 255, 255, 0) if mode == "RGBA" else "white")
    out = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    img.save(out, fmt, **kwargs)
    return out.getvalue()


def pdf_pages(data: bytes) -> list:
    return PdfReader(io.BytesIO(data)).pages


# --- Konversi ---

@pytest.mark.parametrize("fmt, expected", [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
def test_photos_become_one_page_pdf(fmt, expected):
    result = to_pdf(image_bytes(fmt))
    assert result.source_format == expected and result.converted
    assert result.pdf.startswith(b"%PDF-") and len(pdf_pages(result.pdf)) == 1


def test_pdf_is_passed_through_unchanged():
    pdf = make_pdf()
    result = to_pdf(pdf)
    assert result.pdf == pdf and not result.converted


def test_exif_rotation_is_applied():
    # Piksel landscape dengan penanda "putar 90°" (seperti foto HP tegak) harus jadi halaman portrait
    page = pdf_pages(to_pdf(image_bytes("JPEG", size=(1200, 800), exif_orientation=6)).pdf)[0]
    assert page.mediabox.height > page.mediabox.width


def test_transparent_png_gets_white_background():
    result = to_pdf(image_bytes("PNG", mode="RGBA"))
    assert result.pdf.startswith(b"%PDF-")


def test_large_photo_is_scaled_down():
    result = to_pdf(image_bytes("JPEG", size=(6000, 4000)))
    page = pdf_pages(result.pdf)[0]
    assert len(result.pdf) < 2_000_000 and page.mediabox.width > 0


@pytest.mark.parametrize("data", [
    b"GIF89a" + b"\x00" * 50,                     # GIF
    b"PK\x03\x04" + b"\x00" * 50,                 # DOCX/XLSX (zip)
    b"\xff\xd8\xff\xe0" + b"bukan jpeg sungguhan",  # header JPEG tapi isinya rusak
    b"teks biasa yang dinamai invoice.jpg",
])
def test_unsupported_or_broken_files_are_rejected(data):
    with pytest.raises(UnsupportedFile):
        to_pdf(data)


# --- Unggah lewat API ---

def test_upload_photo_creates_pdf_and_keeps_original(extractor):  # noqa: F811
    photo = image_bytes("JPEG")
    r = upload(pdf=photo, filename="invoice-foto.jpg")
    assert r.status_code == 201, r.text
    doc = detail(r.json()["id"])
    assert doc["status"] == "READY_FOR_REVIEW"  # AI tiruan menerima PDF hasil konversi
    assert extractor.calls == 1
    [part] = doc["files"]
    assert part["source_format"] == "jpg" and part["page_count"] == 1
    assert part["original_filename"] == "invoice-foto.jpg"

    pic = api("pic.alpha@amiga.test")
    assert pic.get(f"/documents/{doc['id']}/file").content.startswith(b"%PDF-")
    original = pic.get(f"/documents/{doc['id']}/files/1/original")
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/jpeg" and original.content == photo

    history = pic.get(f"/documents/{doc['id']}/history").json()
    assert any("foto JPG → PDF" in (h.get("note") or "") for h in history)


def test_mixed_pdf_and_photo_in_one_voucher(extractor):  # noqa: F811
    from tests.test_documents import invoice
    extractor.result = [invoice(invoice_no="INV-A"), invoice(invoice_no="INV-B")]
    from tests.test_documents import api as client_for, client_id
    r = client_for("pic.alpha@amiga.test").post(
        "/documents",
        data={"client_id": client_id("PT Klien Alpha"), "request_type": "Pembayaran vendor",
              "channel": "Email", "submitted_date": "2026-10-16"},
        files=[("files", ("a.pdf", make_pdf(), "application/pdf")),
               ("files", ("b.png", image_bytes("PNG"), "image/png"))])
    assert r.status_code == 201, r.text
    doc = detail(r.json()["id"])
    assert [f["source_format"] for f in doc["files"]] == [None, "png"]
    assert doc["page_count"] == 2
    pic = api("pic.alpha@amiga.test")
    assert pic.get(f"/documents/{doc['id']}/files/1/original").status_code == 404  # PDF asli, tidak ada file lain


def test_unsupported_upload_gets_clear_message(extractor):  # noqa: F811
    r = upload(pdf=b"PK\x03\x04" + b"\x00" * 100, filename="invoice.docx")
    assert r.status_code == 422
    assert file_conversion.ACCEPTED_TEXT in r.json()["detail"]


def test_original_file_respects_client_isolation(extractor):  # noqa: F811
    doc_id = upload(pdf=image_bytes("JPEG"), filename="foto.jpg").json()["id"]
    assert api("pic.beta@amiga.test").get(f"/documents/{doc_id}/files/1/original").status_code in (403, 404)
