"""Tanda tangan elektronik: spesimen digoreskan/diunggah, lalu ditempel di voucher saat terbit."""
import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.services.signature_service import normalize
from tests.test_documents import api, detail, extractor, tx, upload  # noqa: F401
from tests.test_reference import add_signatory, approve
from tests.test_review import audit


def signature_image(fmt="PNG", background=(255, 255, 255, 0), size=(400, 150)) -> str:
    img = Image.new("RGBA" if fmt == "PNG" else "RGB", size, background if fmt == "PNG" else (255, 255, 255))
    ImageDraw.Draw(img).line([(40, 110), (120, 30), (200, 100), (330, 40)], fill=(20, 30, 60), width=6)
    out = io.BytesIO()
    img.save(out, format=fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(out.getvalue()).decode()


def test_normalize_crops_and_makes_background_transparent():
    png = Image.open(io.BytesIO(normalize(signature_image("JPEG"))))
    assert png.format == "PNG" and png.mode == "RGBA"
    assert png.width < 400 and png.height < 150  # dipotong ke goresan
    assert png.getpixel((0, 0))[3] == 0 or png.getpixel((png.width - 1, 0))[3] == 0  # latar putih jadi transparan


@pytest.mark.parametrize("bad", [
    "bukan-base64!!!",
    "data:image/png;base64," + base64.b64encode(b"%PDF-1.4 bukan gambar").decode(),
])
def test_normalize_rejects_invalid_images(bad):
    with pytest.raises(HTTPException):
        normalize(bad)


def test_blank_canvas_is_rejected():
    blank = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    out = io.BytesIO()
    blank.save(out, format="PNG")
    with pytest.raises(HTTPException) as e:
        normalize(base64.b64encode(out.getvalue()).decode())
    assert "kosong" in e.value.detail


def test_pic_manages_approver_signature(tx):
    sig = add_signatory("PENYETUJU", "Budi Santoso", "Direktur")
    pic = api("pic.alpha@amiga.test")
    assert sig["signature_updated_at"] is None
    r = pic.put(f"/signatories/{sig['id']}/signature", json={"image": signature_image()})
    assert r.status_code == 200 and r.json()["signature_updated_at"]
    img = pic.get(f"/signatories/{sig['id']}/signature")
    assert img.headers["content-type"] == "image/png"

    assert api("intake@amiga.test").put(f"/signatories/{sig['id']}/signature",
                                        json={"image": signature_image()}).status_code == 403
    assert api("pic.beta@amiga.test").get(f"/signatories/{sig['id']}/signature").status_code == 403
    assert pic.delete(f"/signatories/{sig['id']}/signature").json()["signature_updated_at"] is None
    assert pic.get(f"/signatories/{sig['id']}/signature").status_code == 404


def test_only_pic_registers_own_signature(tx):
    assert api("reviewer1@amiga.test").put("/auth/me/signature", json={"image": signature_image()}).status_code == 403
    me = api("pic.alpha@amiga.test").put("/auth/me/signature", json={"image": signature_image()})
    assert me.status_code == 200 and me.json()["signature_updated_at"]


def _voucher_images(doc_id):
    pdf = PdfReader(io.BytesIO(api("pic.alpha@amiga.test").get(f"/documents/{doc_id}/voucher").content))
    page = pdf.pages[0]
    return len(page.images), page.extract_text()


def test_voucher_carries_registered_signatures(extractor):
    sig = add_signatory("PENYETUJU", "Budi Santoso", "Direktur")
    pic = api("pic.alpha@amiga.test")
    pic.put("/auth/me/signature", json={"image": signature_image()})
    pic.put(f"/signatories/{sig['id']}/signature", json={"image": signature_image("JPEG")})

    doc = detail(upload().json()["id"])
    approve(doc)
    images, text = _voucher_images(doc["id"])
    assert images == 2  # 2 tanda tangan (klien belum punya logo: kop berisi nama klien)
    # Catatan "Tanda tangan elektronik pada N kotak" tidak dicetak lagi (feedback owner); tiap kotak tetap bertanggal
    assert "Tanda tangan elektronik pada" not in text and "Ditandatangani:" in text
    [log] = audit(doc["id"], "E_SIGNATURE_APPLIED")
    assert "Rina (PIC Alpha)" in log.new_value and "Budi Santoso" in log.new_value


def test_voucher_without_signatures_keeps_wet_signature_boxes(extractor):
    add_signatory("PENYETUJU", "Budi Santoso", "Direktur")
    doc = detail(upload().json()["id"])
    approve(doc)
    images, text = _voucher_images(doc["id"])
    assert images == 0  # tanpa logo klien dan tanpa tanda tangan
    assert "Tanda tangan elektronik" not in text and "Tanggal:" in text
