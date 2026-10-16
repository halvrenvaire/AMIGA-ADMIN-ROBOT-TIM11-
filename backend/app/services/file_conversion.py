"""Menerima invoice berupa PDF atau foto (JPG, PNG, WEBP).

Foto diubah menjadi PDF satu halaman di pintu masuk, supaya seluruh alur (batas halaman, layar
peninjauan, penggabungan voucher, ekstraksi AI) tetap memakai PDF. File asli disimpan terpisah
sebagai bukti. Jenis file dikenali dari isinya (magic bytes), bukan dari nama atau ekstensinya.
"""
import io
from dataclasses import dataclass

from PIL import Image, ImageOps

ACCEPTED_TEXT = "PDF atau foto (JPG, PNG, WEBP)"
# Foto kamera HP diperkecil supaya PDF tidak terlalu besar; teks invoice tetap terbaca AI
MAX_IMAGE_SIDE = 2500
A4_LONG_SIDE_INCH = 11.69

# format terdeteksi -> (ekstensi file asli, media type)
IMAGE_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class UnsupportedFile(ValueError):
    """Pesan untuk PIC: format tidak didukung atau file tidak bisa dibaca."""


@dataclass
class PreparedFile:
    pdf: bytes
    source_format: str | None = None  # "jpg" / "png" / "webp" bila dikonversi dari foto

    @property
    def converted(self) -> bool:
        return self.source_format is not None


def detect_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _image_to_pdf(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as opened:
        # Foto HP sering disimpan miring dengan penanda rotasi EXIF: putar sesuai tampilan aslinya
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        if image.mode not in ("RGB", "L"):
            # Latar transparan (PNG/WEBP) menjadi putih, bukan hitam
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
        out = io.BytesIO()
        # Sisi terpanjang setara A4, supaya ukuran halaman wajar di layar peninjauan
        image.save(out, "PDF", resolution=max(image.size) / A4_LONG_SIDE_INCH)
        return out.getvalue()


def to_pdf(data: bytes) -> PreparedFile:
    """PDF dikembalikan apa adanya; foto diubah menjadi PDF satu halaman."""
    if data.startswith(b"%PDF-"):
        return PreparedFile(pdf=data)
    kind = detect_image(data)
    if kind is None:
        raise UnsupportedFile(f"File harus berformat {ACCEPTED_TEXT}. "
                              "Simpan atau ekspor invoice ke salah satu format itu, lalu unggah ulang.")
    try:
        return PreparedFile(pdf=_image_to_pdf(data), source_format=kind)
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise UnsupportedFile("Foto rusak atau terlalu besar untuk dibaca. Foto ulang invoice, lalu unggah lagi.")
