"""AI Engine: hanya MEMBACA invoice (FR-2.2). Tidak memverifikasi dan tidak menyetujui.

Hasilnya data mentah sesuai PRD bagian 6. Verifikasi dijalankan sistem di verification.py.
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import combinations

from app.config import settings
from app.services.bedrock_client import BedrockClient, BedrockError
from app.services.invoice_splitter import PageInfo, Segment, _is_tax_serial, find_segments, split_pages

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Kamu adalah Invoice Verification Officer berpengalaman di bagian keuangan (back office).
Tugasmu dua, berurutan:

1. Klasifikasikan dokumen PDF ini ke SATU "document_class":
   - "invoice": tagihan dari penjual/vendor kepada pembeli yang meminta pembayaran. Ciri umumnya: nama
     penjual, nomor dan tanggal invoice, rincian barang/jasa, jumlah yang harus dibayar, dan biasanya
     rekening tujuan. Invoice, faktur, tagihan, dan nota tagihan termasuk invoice, dalam bahasa apa pun.
     Bila jelas sebuah tagihan meski ada data yang kurang, tetap "invoice" (kekurangan diperiksa sistem).
   - "receipt": struk kasir, bon, nota pembelian, atau kuitansi yang mencatat transaksi (nama barang,
     harga, kuantitas, total), biasanya sudah dibayar di tempat. Ini BUKAN invoice resmi vendor.
   - "irrelevant": bukan dokumen transaksi yang bisa ditagihkan: penawaran harga (quotation), purchase
     order, surat jalan / delivery note, bukti transfer / bukti bayar, voucher pembayaran, kontrak, surat,
     CV, laporan, artikel, materi presentasi, formulir, foto, dan dokumen lain yang tidak menagih.
   - "uncertain": jenisnya tidak bisa dipastikan, mis. buram, terpotong, atau data transaksinya terlalu
     sedikit untuk dinilai.
   Nilai dari isi dan bentuk dokumen, bukan dari nama file.

2. Untuk "invoice", "receipt", dan "uncertain", salin data yang TERLIHAT ke JSON (untuk struk: nama toko
   sebagai vendor_name, nomor struk sebagai invoice_no). Kamu TIDAK memeriksa, menghitung ulang, atau
   memperbaiki angka: salin persis seperti tertulis. Jika sebuah data tidak ada, isi null. Jangan menebak
   atau mengarang data yang tidak tertulis (mis. rekening yang tidak ada di dokumen).
   Untuk "irrelevant", isi semua field data dengan null dan line_items dengan []."""

# Komponen biaya dan PPN tercetak. Dipakai kedua mode baca. AI hanya MENYALIN label dan angka yang tercetak (pembacaan
# nyata: model kecil tidak andal bila disuruh memilih mana yang imbalan jasa). Kode yang menentukan mana imbalan jasa
# dari labelnya (service_fee_from_components); potongan PPh dihitung sistem, dan PIC yang memeriksa serta mengubahnya.
FEE_RULES = """"components": hanya bila invoice jasa memecah tagihan menjadi beberapa komponen biaya di blok ringkasan
(mis. "Total Basic Fee", "Total Overtime", "Total Management Fee & Development") sebelum baris "Total Amount" / "Sub total"
/ PPN. Salin SETIAP komponen itu apa adanya: "label" persis seperti tertulis dan "amount" angkanya persis seperti
tertulis. Jangan memilih, menjumlahkan, atau menghitung. Jangan masukkan "Total Amount", "Sub total", PPN, Biaya Meterai,
atau "Total Invoice". Bila invoice tidak memecah tagihan seperti itu, isi [].
"vat_amount": nilai PPN / VAT yang tercetak di invoice (mis. "VAT / PPN", "Jumlah PPN"), disalin persis; null bila tidak ada."""

# Hanya mode rincian: PDF jasa sering mengulang komponen yang sama di halaman invoice, lampiran, dan Faktur Pajak
DEDUP_RULE = """Satu komponen biaya sering tertulis berulang di halaman invoice, lampiran rincian, dan Faktur Pajak. Catat
setiap komponen di "line_items" SEKALI saja, dari halaman invoice utama, dan lewati komponen bernilai 0."""

INSTRUCTION = """Kembalikan HANYA satu objek JSON (tanpa teks lain) dengan bentuk:
{
  "document_class": "invoice"|"receipt"|"irrelevant"|"uncertain",
  "document_type": string,
  "not_invoice_reason": string|null,
  "vendor_name": string|null,
  "invoice_no": string|null,
  "invoice_date": "YYYY-MM-DD"|null,
  "line_items": [{"kind": "item"|"fee"|"tax"|"discount"|"summary", "description": string|null, "qty": number|null, "unit_price": string|null, "subtotal": string|null}],
  "total": string|null,
  "components": [{"label": string, "amount": string}],
  "vat_amount": string|null,
  "bank_name": string|null,
  "account_no": string|null,
  "account_name": string|null
}
""" + FEE_RULES + "\n" + DEDUP_RULE + """
Aturan: "document_class" adalah hasil langkah 1. "document_type" adalah jenis dokumen
dalam bahasa Indonesia (mis. "Invoice", "Struk kasir", "Purchase order", "Surat lamaran"). "not_invoice_reason"
diisi satu kalimat singkat bila document_class bukan "invoice", selain itu null. Tulis setiap angka uang PERSIS seperti di invoice sebagai teks, termasuk titik dan koma (contoh
"Rp 10.000", "2.695.000"); sistem yang mengubahnya menjadi angka. "qty" boleh berupa angka. 
"vendor_name" adalah nama penjual/penerbit invoice yang sebenarnya (mis. "tiket.com (PT Global Tiket
Network)"), BUKAN judul bagian seperti "Penjual", "Vendor", "Dari", atau "Seller".
"total" adalah jumlah akhir yang harus dibayar (Total Bayar / Grand Total / Jumlah Tagihan / Amount Due).
"account_no" adalah nomor rekening tujuan pembayaran, sebagai teks.
Tanggal di dokumen Indonesia biasanya ditulis hari-bulan-tahun ("12-10-2026" = 12 Oktober 2026 = "2026-10-12").
"line_items" berisi setiap baris berangka di invoice, berurutan, dan setiap baris diberi "kind":
- "item": barang/jasa yang dibeli (mis. tiket, kertas, jasa konsultasi)
- "fee": biaya tambahan (biaya layanan, ongkos kirim, biaya admin)
- "tax": pajak (PPN, PPh, Tax)
- "discount": potongan/diskon, subtotal ditulis negatif
- "summary": baris ringkasan yang nilainya penjumlahan baris lain, mis. "Subtotal", "Subtotal Tiket",
  "Total", "Total Bayar", "Grand Total", "Jumlah". Baris di bawah judul seperti "Ringkasan Biaya" yang
  menjumlahkan item sebelumnya juga "summary".
Untuk "description", tulis teks baris itu sendiri (mis. "Subtotal Tiket"), bukan judul bagiannya.
PENTING: pajak, biaya, dan potongan sering ditulis DI BAWAH tabel barang, di bagian ringkasan/total
(mis. "PPN 94.050", "PPh 23", "Ongkos kirim", "Materai", "Diskon"). Baris seperti itu tetap WAJIB masuk
line_items dengan kind "tax", "fee", atau "discount", bukan "summary". Yang "summary" hanya baris yang
nilainya penjumlahan baris lain (mis. "Jumlah Harga Jual", "Subtotal", "DPP", "Nilai Yang Harus Dibayar").
Lewati baris tanpa nilai uang (mis. "PPN Free" tanpa angka).
Pada invoice yang benar, jumlah subtotal semua baris selain "summary" sama dengan "total"."""

# Mode TOTAL_ONLY (Tahap 14): prompt ringkas, hanya klasifikasi + data kepala invoice + total akhir. Rincian barang
# tidak dibaca, sehingga jawaban AI pendek dan biaya token per invoice lebih kecil.
TOTAL_SYSTEM_PROMPT = """Kamu staf keuangan yang membaca dokumen tagihan. Tentukan "document_class" dokumen PDF ini:
"invoice" (tagihan vendor yang meminta pembayaran), "receipt" (struk/bon/nota/kuitansi yang sudah dibayar),
"irrelevant" (bukan dokumen transaksi, mis. penawaran, PO, surat jalan, bukti transfer, kontrak, surat), atau
"uncertain" (tidak bisa dipastikan). Lalu salin data yang TERLIHAT persis seperti tertulis; isi null bila tidak ada.
Jangan menghitung, menebak, atau mengarang data."""

TOTAL_INSTRUCTION = """Kembalikan HANYA satu objek JSON (tanpa teks lain):
{{
  "document_class": "invoice"|"receipt"|"irrelevant"|"uncertain",
  "document_type": string,
  "not_invoice_reason": string|null,
  "vendor_name": string|null,
  "invoice_no": string|null,
  "invoice_date": "YYYY-MM-DD"|null,
  "total": string|null,
  "service_fee": string|null,
  "vat_amount": string|null,
  "description": string|null{account}
}}
""" + FEE_RULES + """
"document_type": jenis dokumen dalam bahasa Indonesia (mis. "Invoice", "Struk kasir"). "vendor_name": nama penjual/
penerbit tagihan, bukan judul bagian seperti "Penjual" atau "Dari". "total": jumlah akhir yang harus dibayar (Grand
Total / Total Bayar / Amount Due), ditulis persis seperti di dokumen sebagai teks (mis. "Rp 2.695.000").
"service_fee": imbalan jasa penerbit (mis. "Management Fee"), disalin persis HANYA bila invoice memecah tagihan menjadi
imbalan jasa dan penggantian biaya; null bila tidak. "vat_amount": PPN yang tercetak; null bila tidak ada.
"description": uraian ringkas peruntukan atau jenis jasa/barang (mis. "Management Fee & Development Driver A", "Cetak Payung", atau "Pengadaan seragam"), disalin dari invoice atau lampirannya; null bila tidak ada.
Tanggal dokumen Indonesia ditulis hari-bulan-tahun ("12-10-2026" = "2026-10-12")."""

PAGE_SYSTEM_PROMPT = """Kamu staf keuangan yang memeriksa satu halaman dari berkas tagihan gabungan. Tugasmu HANYA
menentukan apakah halaman ini merupakan HALAMAN DEPAN (lembar utama) sebuah invoice/faktur tagihan, dan menyalin nomor
invoicenya. Jangan membaca rincian, jangan menjumlahkan. Jawab hanya dengan JSON yang diminta, persis seperti yang
tertulis; jangan menebak atau mengarang nomor."""

PAGE_INSTRUCTION = """Kembalikan HANYA satu objek JSON (tanpa teks lain):
{"starts_invoice": true|false, "invoice_no": string|null}
"starts_invoice" true HANYA bila halaman ini adalah lembar utama sebuah invoice/tagihan: ada judul seperti INVOICE,
FAKTUR, atau TAGIHAN, ada nomor invoice, dan ada ringkasan jumlah yang ditagih. Halaman lampiran rincian (daftar
item dengan kolom No/Amount), timesheet, absensi, surat jalan, dan halaman lanjutan atau kosong = false.
Faktur Pajak (judul "Faktur Pajak", ada "Kode dan Nomor Seri Faktur Pajak", "Pengusaha Kena Pajak", "Pembeli Barang
Kena Pajak/Penerima Jasa Kena Pajak") BUKAN lembar utama invoice = false, dan nomor serinya (16-17 digit) bukan nomor invoice.
"invoice_no": nomor invoice yang tertulis di halaman ini persis seperti aslinya (mis. dari "Invoice No" / "No. Tagihan"),
atau null bila halaman ini bukan lembar utama invoice."""

TOTAL_ACCOUNT_FIELDS = """,
  "bank_name": string|null,
  "account_no": string|null,
  "account_name": string|null"""

# Tahap 15: satu PDF bisa berisi beberapa invoice/struk. AI memindai per potongan halaman (mis. 5 halaman) dan
# mendaftar setiap tagihan beserta halaman awalnya. Halaman pendukung tidak dihitung sebagai tagihan tersendiri.
SCAN_SYSTEM_PROMPT = """Kamu staf keuangan yang memilah berkas PDF berisi bukti tagihan. Satu berkas bisa berisi
BEBERAPA tagihan: beberapa invoice berurutan (masing-masing bisa beberapa halaman), atau beberapa struk/nota dalam
satu halaman. Daftarkan setiap tagihan (invoice, faktur tagihan, nota tagihan, struk, bon, kuitansi) yang HALAMAN
AWALNYA (kepala tagihan: nama penjual, nomor, tanggal) ada di halaman yang diberikan.
BUKAN tagihan tersendiri, jangan didaftarkan: Faktur Pajak (dokumen pajak DJP untuk invoice yang sama, judul "Faktur Pajak"),
halaman rincian/lampiran/detail invoice, lanjutan invoice dari halaman sebelumnya, timesheet, surat jalan, bukti potong,
bukti transfer, dan surat pengantar. Salin data yang TERLIHAT persis seperti tertulis; isi null bila tidak ada.
Jangan menghitung, menebak, atau mengarang data."""

SCAN_INSTRUCTION = """PDF ini adalah halaman {first} sampai {last} dari berkas aslinya (halaman pertama PDF ini =
halaman {first}). Kembalikan HANYA satu objek JSON (tanpa teks lain):
{{
  "document_class": "invoice"|"receipt"|"irrelevant"|"uncertain",
  "document_type": string,
  "not_invoice_reason": string|null,
  "invoices": [
    {{
      "page": number,
      "document_class": "invoice"|"receipt"|"uncertain",
      "document_type": string,
      "vendor_name": string|null,
      "invoice_no": string|null,
      "invoice_date": "YYYY-MM-DD"|null,
      "total": string|null,
      "service_fee": string|null,
      "vat_amount": string|null,
      "description": string|null{account}
    }}
  ]
}}
"document_class"/"document_type"/"not_invoice_reason" di luar "invoices" menjelaskan halaman-halaman ini secara
umum (dipakai bila tidak ada tagihan). "invoices" berurutan sesuai letaknya; kosongkan ([]) bila tidak ada tagihan
yang dimulai di halaman ini. "page" = nomor halaman berkas asli tempat tagihan itu dimulai ({first}–{last}).
Beberapa struk dalam satu halaman = beberapa entri dengan "page" yang sama. "vendor_name": nama penjual/penerbit,
bukan judul bagian seperti "Penjual" atau "Dari". "total": jumlah akhir yang harus dibayar, ditulis persis seperti
di dokumen sebagai teks (mis. "Rp 2.695.000").
"service_fee": imbalan jasa penerbit (mis. "Management Fee" atau "Management Fee & Development"), disalin persis
HANYA bila invoice memecah tagihan menjadi imbalan jasa dan penggantian biaya/basic fee; null bila tidak.
"vat_amount": nilai PPN / VAT yang tercetak di invoice (mis. "VAT / PPN", "Jumlah PPN"); null bila tidak ada.
"description": uraian singkat peruntukan atau nama layanan/driver jika tertulis (mis. "Management Fee & Development Driver A", "Overtime Driver - Driver A"); null bila tidak ada.
PENTING: Faktur Pajak (nomor seri 16 digit, diawali 040 atau semacamnya) BUKAN invoice dan TIDAK BOLEH masuk ke daftar invoices.
Tanggal dokumen Indonesia ditulis hari-bulan-tahun ("12-10-2026" = "2026-10-12")."""

# Pembacaan satu tagihan di halaman yang memuat beberapa tagihan (mis. beberapa struk dalam satu halaman)
FOCUS_INSTRUCTION = """
PENTING: halaman ini memuat beberapa tagihan. Baca HANYA tagihan berikut dan abaikan tagihan lain: {focus}."""

FOLLOWUP_SYSTEM_PROMPT = """Kamu memeriksa ulang satu invoice untuk bagian keuangan. Tugasmu HANYA mencari baris
pajak, biaya, atau potongan yang terlewat pada pembacaan sebelumnya, lalu menyalinnya persis seperti tertulis.
Jangan mengulang data lain, jangan mengklasifikasikan dokumen, dan jawab hanya dengan JSON yang diminta."""

FOLLOWUP_INSTRUCTION = """Pembacaan pertama mencatat rincian berikut (selain baris ringkasan):
{lines}
Jumlahnya {line_sum}, sedangkan total yang harus dibayar {total}.
Periksa ulang dokumen: adakah baris pajak (PPN, PPh), biaya (ongkos kirim, materai, admin, layanan), atau
potongan/diskon yang BELUM tercatat di atas? Biasanya letaknya di bawah tabel barang, dekat total.
Kembalikan HANYA satu objek JSON:
{{"missing_lines": [{{"kind": "tax"|"fee"|"discount", "description": string, "subtotal": string}}]}}
Salin angka persis seperti tertulis di dokumen. Jangan menghitung, menebak, atau mengarang angka.
Jika tidak ada baris yang terlewat, kembalikan {{"missing_lines": []}}."""


# Jenis dokumen (dari jawaban AI) yang jelas bukan tagihan vendor, dan yang jelas tagihan
NON_INVOICE_TYPE = re.compile(
    r"struk|receipt|voucher|purchase order|\bpo\b|penawaran|quotation|surat jalan|delivery|bukti (transfer|bayar|pembayaran)"
    r"|kontrak|lamaran|\bcv\b|laporan|notulen|sertifikat|sertifikasi|presentasi|formulir", re.IGNORECASE)
DISCOUNT_DESC = re.compile(r"\b(diskon|discount|potongan|rabat)\b", re.IGNORECASE)
# Pajak, biaya, atau potongan: komponen tagihan, bukan ringkasan
CHARGE_DESC = re.compile(
    r"\b(ppn|pph|pajak|tax|vat|ongkir|ongkos|biaya|materai|meterai|admin|layanan|service|pengiriman|delivery|"
    r"diskon|discount|potongan|rabat)\b", re.IGNORECASE)
MAX_RECOVERY_CANDIDATES = 5
CHANGE_LINE = re.compile(r"\bkembali(an)?\b|\bchange\b", re.IGNORECASE)
INVOICE_TYPE = re.compile(r"invoice|faktur|tagihan|nota tagihan|bill\b", re.IGNORECASE)
# Bukti transaksi yang sudah dibayar: diekstrak sebagai draft, bukan ditolak
RECEIPT_TYPE = re.compile(r"struk|receipt|\bbon\b|nota (pembelian|belanja|kontan)|kuitansi|kwitansi", re.IGNORECASE)

# Kelas dokumen hasil klasifikasi
INVOICE, RECEIPT, IRRELEVANT, UNCERTAIN = "INVOICE", "RECEIPT", "IRRELEVANT", "UNCERTAIN"
CLASSES = {INVOICE, RECEIPT, IRRELEVANT, UNCERTAIN}


class ExtractionError(Exception):
    """AI gagal membaca invoice; dokumen tetap tersimpan (FR-2.5)."""


@dataclass
class ExtractedLine:
    description: str | None = None
    qty: Decimal | None = None
    unit_price: Decimal | None = None
    subtotal: Decimal | None = None


@dataclass
class ExtractedInvoice:
    vendor_name: str | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    line_items: list[ExtractedLine] = field(default_factory=list)
    total: Decimal | None = None
    bank_name: str | None = None
    account_no: str | None = None
    account_name: str | None = None
    # Pemeriksaan jenis dokumen oleh AI. `doc_class` None = diturunkan dari is_invoice (kompatibel lama)
    is_invoice: bool = True
    document_type: str | None = None
    not_invoice_reason: str | None = None
    raw: dict = field(default_factory=dict)
    doc_class: str | None = None
    # Token AI yang terpakai untuk membaca invoice ini: {"input_tokens", "output_tokens"}
    usage: dict = field(default_factory=dict)
    # Tahap 15: halaman awal invoice di berkas asli (hasil pemindaian berkas berisi beberapa invoice)
    page: int | None = None
    # Disalin dari invoice: nilai imbalan jasa penerbit (mis. Management Fee) bila dipisah dari penggantian biaya,
    # dan PPN yang tercetak. Dasar saran potongan PPh; PIC yang memutuskan.
    service_fee: Decimal | None = None
    vat_printed: Decimal | None = None
    # Imbalan jasa yang dibaca AI tetapi tidak cocok dengan PPN tercetak: tidak dipakai, hanya ditampilkan ke PIC
    service_fee_unverified: Decimal | None = None
    description: str | None = None

    def __post_init__(self):
        if self.doc_class is None or (self.doc_class == INVOICE and not self.is_invoice):
            self.doc_class = INVOICE if self.is_invoice else IRRELEVANT
        self.is_invoice = self.doc_class == INVOICE


def has_transaction_data(lines: list[ExtractedLine], total: Decimal | None) -> bool:
    """Ada nama barang dengan harga/subtotal, atau total: cukup untuk disusun sebagai draft."""
    return total is not None or any(line.description and line.subtotal is not None for line in lines)


def classify(data: dict, document_type: str | None, lines: list[ExtractedLine], total: Decimal | None,
             vendor_name: str | None, has_change_line: bool) -> str:
    """Kelas akhir dari jawaban AI, dengan pengaman berbasis aturan:
    - jawaban lama tanpa document_class diturunkan dari is_invoice;
    - jenis dokumen yang jelas struk/nota dan ada uang kembalian → receipt (bukan tagihan);
    - jenis dokumen yang jelas bukan tagihan → irrelevant;
    - struk tanpa data transaksi, atau invoice yang hampir kosong → uncertain (diperiksa manual)."""
    raw_class = str(data.get("document_class") or "").strip().upper()
    doc_class = raw_class if raw_class in CLASSES else (INVOICE if data.get("is_invoice") is not False else IRRELEVANT)
    kind = document_type or ""
    if doc_class in (INVOICE, IRRELEVANT) and RECEIPT_TYPE.search(kind) and not INVOICE_TYPE.search(kind):
        doc_class = RECEIPT
    elif doc_class == INVOICE and NON_INVOICE_TYPE.search(kind) and not INVOICE_TYPE.search(kind):
        doc_class = IRRELEVANT
    if doc_class in (INVOICE, UNCERTAIN) and has_change_line:
        doc_class = RECEIPT  # ada uang kembalian: sudah dibayar di kasir, bukan tagihan
    if doc_class == RECEIPT and not has_transaction_data(lines, total):
        doc_class = UNCERTAIN
    if doc_class == INVOICE and not vendor_name and total is None and not lines:
        doc_class = UNCERTAIN
    return doc_class


def to_decimal(value) -> Decimal | None:
    """Angka dari AI: number, atau teks seperti "Rp 1.250.000,50" / "1,250,000.50" / "12.425.000,-"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    s = re.sub(r"[,.]\s*-+\s*$", "", s)
    text = re.sub(r"[^\d,.\-]", "", s)
    text = re.sub(r"-+$", "", text)
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        # Pemisah yang muncul terakhir adalah pemisah desimal
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal_sep == "," else ",", "").replace(decimal_sep, ".")
    elif text.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")  # format Indonesia: titik = ribuan
    elif text.count(",") > 1 or re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def to_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def drop_running_subtotals(lines: list[ExtractedLine], total: Decimal | None) -> tuple[list[ExtractedLine], list[str]]:
    """Pengaman bila AI tetap memasukkan baris subtotal sebagai item: baris yang nilainya persis jumlah
    semua baris sebelumnya dibuang, HANYA bila setelah dibuang jumlah rincian menjadi sama dengan total
    invoice. Selain itu rincian dibiarkan apa adanya (selisih tetap dilaporkan verifikasi sistem)."""
    if total is None or not lines or any(line.subtotal is None for line in lines):
        return lines, []
    if sum((line.subtotal for line in lines), Decimal(0)) == total:
        return lines, []
    kept, removed, running, since = [], [], Decimal(0), 0
    for line in lines:
        # Subtotal menjumlahkan minimal 2 baris; dua item berharga sama tidak dianggap subtotal
        if since >= 2 and line.subtotal == running and line.subtotal != 0:
            removed.append(line)
            continue
        kept.append(line)
        running += line.subtotal
        since += 1
    if not removed or running != total:
        return lines, []
    return kept, [line.description or "-" for line in removed]


def _charge_line(description: str | None, amount: Decimal | None, kind: str = "") -> ExtractedLine:
    line = ExtractedLine(description=description, subtotal=amount)
    if line.subtotal is not None and (kind == "discount" or DISCOUNT_DESC.search(description or "")):
        line.subtotal = -abs(line.subtotal)
    return line


def complete_with_charges(lines: list[ExtractedLine], candidates: list[ExtractedLine],
                          total: Decimal | None) -> list[ExtractedLine]:
    """Baris pajak/biaya/potongan dari `candidates` yang membuat jumlah rincian PERSIS sama dengan total.
    Kombinasi terkecil yang pas dipilih; bila tidak ada yang pas, tidak ada yang ditambahkan (selisih
    tetap dilaporkan verifikasi sistem). Sistem tidak pernah menghitung atau mengarang angka sendiri."""
    if total is None or not lines or any(line.subtotal is None for line in lines):
        return []
    line_sum = sum((line.subtotal for line in lines), Decimal(0))
    pool = [c for c in candidates if c.subtotal not in (None, Decimal(0))][:MAX_RECOVERY_CANDIDATES]
    if line_sum == total or not pool:
        return []
    for size in range(1, len(pool) + 1):
        for combo in combinations(pool, size):
            if line_sum + sum(c.subtotal for c in combo) == total:
                return list(combo)
    return []


def parse_response(text: str) -> ExtractedInvoice:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ExtractionError("Jawaban AI tidak berisi JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ExtractionError(f"JSON dari AI tidak valid: {e}") from e
    if not isinstance(data, dict):
        raise ExtractionError("JSON dari AI bukan objek")

    lines = []
    summaries = []
    summary_charges: list[ExtractedLine] = []
    for item in data.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        # Baris ringkasan (Subtotal/Total) bukan komponen tagihan; bila ikut, nilainya terhitung dua kali
        if str(item.get("kind") or "").lower() == "summary":
            summaries.append(to_text(item.get("description")) or "-")
            if CHARGE_DESC.search(str(item.get("description") or "")):
                summary_charges.append(_charge_line(to_text(item.get("description")), to_decimal(item.get("subtotal"))))
            continue
        line = ExtractedLine(
            description=to_text(item.get("description")),
            qty=to_decimal(item.get("qty")),
            unit_price=to_decimal(item.get("unit_price")),
            subtotal=to_decimal(item.get("subtotal")),
        )
        # Diskon/potongan selalu mengurangi tagihan, walau di invoice ditulis tanpa tanda minus dan walau
        # AI melabelinya "fee" (dikenali juga dari deskripsinya)
        if str(item.get("kind") or "").lower() == "discount" or DISCOUNT_DESC.search(line.description or ""):
            line.subtotal = -abs(line.subtotal) if line.subtotal is not None else None
            line.unit_price = -abs(line.unit_price) if line.unit_price is not None else None
        if any(v is not None for v in vars(line).values()):
            lines.append(line)

    total = to_decimal(data.get("total"))
    lines, removed = drop_running_subtotals(lines, total)
    # Baris pajak/biaya yang keliru dilabeli "summary" (mis. "PPN") dikembalikan, bila membuat hitungan pas
    recovered = complete_with_charges(lines, summary_charges, total)
    if recovered:
        lines = lines + recovered
        names = {line.description or "-" for line in recovered}
        summaries = [name for name in summaries if name not in names]
        data = {**data, "charges_recovered_from_summary": [line.description for line in recovered]}
    if summaries or removed:
        data = {**data, "summary_lines_skipped": summaries + removed}
    # Titik ribuan terbaca sebagai desimal ("2.695.000" → 2695): koreksi hanya bila total tepat
    # 1000x lebih kecil dari jumlah rincian, ciri pasti salah baca format angka Indonesia
    line_sum = sum((line.subtotal for line in lines if line.subtotal is not None), Decimal(0))
    if (total is not None and lines and all(line.subtotal is not None for line in lines)
            and total != line_sum and total * 1000 == line_sum):
        data = {**data, "total_corrected_from": str(total)}
        total = line_sum

    # Klasifikasi: hanya kelas yang eksplisit/jelas yang menahan dokumen, supaya jawaban AI yang tidak
    # lengkap tidak menolak invoice yang sah
    document_type = to_text(data.get("document_type"))
    reason = to_text(data.get("not_invoice_reason"))
    descriptions = " ".join(str(i.get("description") or "") for i in data.get("line_items") or [] if isinstance(i, dict))
    has_change = bool(CHANGE_LINE.search(descriptions))
    vendor_name = to_text(data.get("vendor_name"))
    doc_class = classify(data, document_type, lines, total, vendor_name, has_change)
    if doc_class == RECEIPT:
        document_type = document_type if document_type and not INVOICE_TYPE.search(document_type) else "Struk kasir"
        reason = reason or ("Ada baris uang kembalian (KEMBALI): struk kasir yang sudah dibayar, bukan tagihan resmi vendor."
                            if has_change else f"Dokumen terbaca sebagai {document_type}, bukan invoice resmi vendor.")
    elif doc_class == IRRELEVANT:
        reason = reason or f"Dokumen terbaca sebagai {document_type or 'dokumen lain'}, bukan tagihan dari vendor."
    elif doc_class == UNCERTAIN:
        reason = reason or "Jenis dokumen atau datanya tidak cukup jelas untuk diproses otomatis."
    if doc_class == IRRELEVANT:
        # Dokumen tidak relevan: tidak ada data yang disimpan sebagai draft
        lines, total = [], None

    keep = doc_class != IRRELEVANT
    # Imbalan jasa dari AI hanya dipakai bila cocok dengan PPN yang tercetak (PPN dikenakan atas imbalan jasa itu).
    # Pembacaan nyata: AI kadang memilih angka komponen yang salah; PPN tercetak menangkap kesalahan itu.
    fee = service_fee_from_components(data.get("components")) or _positive(data.get("service_fee"))
    vat, unverified_fee = _positive(data.get("vat_amount")), None
    if fee is not None and vat is not None and not fee_matches_vat(fee, vat):
        fee, unverified_fee = None, fee
        data = {**data, "service_fee_rejected": str(unverified_fee)}
    text = lambda key: to_text(data.get(key)) if keep else None  # noqa: E731
    return ExtractedInvoice(
        vendor_name=vendor_name if keep else None,
        invoice_no=text("invoice_no"),
        invoice_date=to_date(data.get("invoice_date")) if keep else None,
        line_items=lines,
        total=total,
        bank_name=text("bank_name"),
        account_no=text("account_no"),
        account_name=text("account_name"),
        document_type=document_type,
        not_invoice_reason=reason,
        raw=data,
        doc_class=doc_class,
        service_fee=fee if keep else None,
        vat_printed=vat if keep else None,
        service_fee_unverified=unverified_fee if keep else None,
        description=text("description"),
    )


# Label komponen biaya. Imbalan jasa = milik penerbit invoice; penggantian biaya = diteruskan tanpa margin.
SERVICE_FEE_LABEL = re.compile(
    r"(management|manajemen|handling|service|pengelolaan)\s*(&\s*development\s*)?fee|fee\s*(management|manajemen|pengelolaan)"
    r"|jasa\s+pengelolaan|biaya\s+(manajemen|pengelolaan)", re.IGNORECASE)
PASS_THROUGH_LABEL = re.compile(
    r"basic\s*fee|\bgaji\b|salary|bpjs|overtime|lembur|tunjangan|allowance|transport|uang\s+makan|reimburs|penggantian"
    r"|pass[- ]?through", re.IGNORECASE)


def service_fee_from_components(components) -> Decimal | None:
    """Imbalan jasa dari komponen yang disalin AI: jumlah komponen berlabel imbalan jasa, HANYA bila invoice juga
    memuat komponen penggantian biaya (gaji, lembur, dll.). Tanpa pemisahan itu bukan kasus ini, sehingga mis. satu baris
    "Service Fee" pada invoice biasa tidak dianggap dasar PPh 23."""
    if not isinstance(components, list):
        return None
    fee, has_pass_through = Decimal(0), False
    for item in components:
        if not isinstance(item, dict):
            continue
        label, amount = str(item.get("label") or ""), to_decimal(item.get("amount"))
        if PASS_THROUGH_LABEL.search(label) and not SERVICE_FEE_LABEL.search(label):
            has_pass_through = True
        elif SERVICE_FEE_LABEL.search(label) and amount is not None and amount > 0:
            fee += amount
    return fee if fee > 0 and has_pass_through else None


def fee_matches_vat(fee: Decimal, vat: Decimal, tolerance: Decimal = Decimal(100)) -> bool:
    """PPN tercetak sama dengan 11% atau 12% dari imbalan jasa (selisih pembulatan maks. Rp 100)."""
    return any(abs(fee * rate / 100 - vat) <= tolerance for rate in (Decimal(11), Decimal(12)))


def _positive(value) -> Decimal | None:
    """Angka yang disalin AI; nol, negatif, atau tidak terbaca dianggap tidak ada."""
    number = to_decimal(value)
    return number if number is not None and number > 0 else None


def _followup_items(answer) -> list[dict]:
    """Baris dari jawaban pembacaan ulang. Bila AI tetap mengirim ulang seluruh data (bukan "missing_lines"),
    baris pajak/biaya/potongan di dalamnya tetap dipakai sebagai kandidat."""
    if not isinstance(answer, dict):
        return []
    found = answer.get("missing_lines")
    if not isinstance(found, list):
        nested = next((v for v in answer.values() if isinstance(v, dict) and "line_items" in v), {})
        found = [item for item in answer.get("line_items") or nested.get("line_items") or []
                 if isinstance(item, dict) and (str(item.get("kind") or "").lower() in ("tax", "fee", "discount")
                                                or CHARGE_DESC.search(str(item.get("description") or "")))]
    return [item for item in found if isinstance(item, dict)]


TOTAL_ONLY_MAX_TOKENS = 600  # jawaban mode total hanya beberapa field
SCAN_MAX_TOKENS = 3000  # daftar tagihan per potongan halaman (±100 token per tagihan)


@dataclass
class ScanResult:
    """Hasil pemindaian satu potongan halaman: tagihan yang dimulai di halaman itu (`page` = halaman berkas asli),
    dan klasifikasi umum halaman itu (dipakai bila tidak ada tagihan)."""
    invoices: list[ExtractedInvoice]
    document: ExtractedInvoice
    usage: dict = field(default_factory=dict)


def parse_scan(text: str, first: int, last: int) -> ScanResult:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ExtractionError("Jawaban AI tidak berisi JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ExtractionError(f"JSON dari AI tidak valid: {e}") from e
    if not isinstance(data, dict):
        raise ExtractionError("JSON dari AI bukan objek")
    general = {k: data.get(k) for k in ("document_class", "document_type", "not_invoice_reason")}
    invoices = []
    for item in data.get("invoices") or []:
        if not isinstance(item, dict):
            continue
        part = parse_response(json.dumps(item))
        if part.doc_class == IRRELEVANT or not (part.invoice_no or part.vendor_name or part.total is not None):
            continue
        # Tolak Faktur Pajak DJP yang keliru didaftarkan sebagai invoice (mis. nomor seri 15+ digit)
        if _is_tax_serial(part.invoice_no) or "faktur pajak" in (part.document_type or "").lower():
            continue
        try:
            page = int(item.get("page"))
        except (TypeError, ValueError):
            page = first
        if not first <= page <= last:
            # Nomor halaman relatif terhadap potongan (1, 2, ...) diubah ke halaman berkas asli
            page = first + page - 1 if 1 <= page <= last - first + 1 else first
        part.page = page
        part.line_items = []
        invoices.append(part)
    document = parse_response(json.dumps(general)) if not invoices else ExtractedInvoice()
    return ScanResult(invoices=invoices, document=document)


class InvoiceExtractor:
    def __init__(self, bedrock: BedrockClient):
        self.bedrock = bedrock

    def _read(self, system_prompt: str, pdf_bytes: bytes, instruction: str, max_tokens: int, usage: dict) -> str:
        """Panggil AI dan tambahkan token yang terpakai ke `usage` (bila klien Bedrock melaporkannya).
        `usage` dikirim per panggilan, bukan disimpan di objek: satu extractor dipakai bersama oleh proses paralel."""
        reader = getattr(self.bedrock, "read_pdf_usage", None)
        if reader is None:
            return self.bedrock.read_pdf(system_prompt, pdf_bytes, instruction, max_tokens=max_tokens)
        text, used = reader(system_prompt, pdf_bytes, instruction, max_tokens=max_tokens)
        for key in ("input_tokens", "output_tokens"):
            usage[key] = usage.get(key, 0) + int(used.get(key) or 0)
        return text

    def scan_chunk(self, pdf_bytes: bytes, first: int, last: int, include_account: bool = True) -> ScanResult:
        """Daftar tagihan yang dimulai di potongan halaman `first`..`last` (Tahap 15). Data kepala + total saja."""
        usage: dict = {}
        instruction = SCAN_INSTRUCTION.format(first=first, last=last,
                                              account=TOTAL_ACCOUNT_FIELDS if include_account else "")
        try:
            text = self._read(SCAN_SYSTEM_PROMPT, pdf_bytes, instruction, SCAN_MAX_TOKENS, usage)
        except BedrockError as e:
            raise ExtractionError(str(e)) from e
        result = parse_scan(text, first, last)
        result.usage = usage
        return result

    def extract(self, pdf_bytes: bytes, mode: str = "ITEMIZED", include_account: bool = True,
                focus: str | None = None) -> ExtractedInvoice:
        """`mode`: "TOTAL_ONLY" = hanya total dan data kepala invoice (tanpa rincian); "ITEMIZED" = rincian lengkap.
        `focus`: ciri tagihan yang dibaca bila halamannya memuat beberapa tagihan (mis. "nomor X, vendor Y")."""
        usage: dict = {}
        extra = FOCUS_INSTRUCTION.format(focus=focus) if focus else ""
        try:
            if mode == "TOTAL_ONLY":
                instruction = TOTAL_INSTRUCTION.format(account=TOTAL_ACCOUNT_FIELDS if include_account else "")
                text = self._read(TOTAL_SYSTEM_PROMPT, pdf_bytes, instruction + extra, TOTAL_ONLY_MAX_TOKENS, usage)
            else:
                text = self._read(SYSTEM_PROMPT, pdf_bytes, INSTRUCTION + extra, settings.extraction_max_tokens, usage)
        except BedrockError as e:
            raise ExtractionError(str(e)) from e
        result = parse_response(text)
        if mode == "TOTAL_ONLY":
            result.line_items = []
        else:
            self._find_missing_charges(pdf_bytes, result, usage)
        result.usage = usage
        return result

    def read_page(self, page_pdf: bytes, usage: dict) -> PageInfo:
        """Apakah halaman ini lembar depan sebuah invoice, dan nomornya. Jawaban yang tidak terbaca = bukan lembar depan."""
        text = self._read(PAGE_SYSTEM_PROMPT, page_pdf, PAGE_INSTRUCTION, 120, usage)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            return PageInfo()
        starts = data.get("starts_invoice")
        return PageInfo(starts is True or str(starts).strip().lower() == "true", to_text(data.get("invoice_no")))

    def locate_invoices(self, pdf_bytes: bytes) -> tuple[list[Segment], dict]:
        """Bagian-bagian invoice dalam berkas gabungan, dan token AI yang terpakai. Daftar kosong = satu invoice.

        Setiap halaman diperiksa sendiri-sendiri (paralel), jadi nomor halaman selalu pasti. Halaman yang gagal
        diperiksa dicoba sekali lagi; bila tetap gagal, dianggap bukan halaman depan."""
        pages = split_pages(pdf_bytes)
        usage: dict = {}
        if len(pages) < 2:
            return [], usage
        page_usage = [dict() for _ in pages]

        def check(i: int) -> PageInfo | None:
            for _ in range(2):
                try:
                    return self.read_page(pages[i], page_usage[i])
                except BedrockError as e:
                    log.warning("Halaman %d gagal diperiksa: %s", i + 1, e)
            return None

        with ThreadPoolExecutor(max_workers=max(1, settings.ai_split_workers)) as pool:
            infos = list(pool.map(check, range(len(pages))))
        for u in page_usage:
            for key in ("input_tokens", "output_tokens"):
                usage[key] = usage.get(key, 0) + int(u.get(key) or 0)
        failed = sum(info is None for info in infos)
        if failed:
            log.warning("%d dari %d halaman tidak bisa diperiksa; dianggap bukan halaman depan", failed, len(pages))
        return find_segments([info or PageInfo() for info in infos], settings.ai_split_max_invoices), usage

    def _find_missing_charges(self, pdf_bytes: bytes, result: ExtractedInvoice, usage: dict | None = None) -> None:
        """Bila jumlah rincian tidak sama dengan total, minta AI sekali lagi mencari baris pajak/biaya/potongan
        yang terlewat (mis. PPN di bawah tabel). Hasilnya dipakai HANYA bila membuat hitungan pas persis."""
        lines, total = result.line_items, result.total
        if result.doc_class == IRRELEVANT or total is None or not lines or any(l.subtotal is None for l in lines):
            return
        line_sum = sum((line.subtotal for line in lines), Decimal(0))
        if line_sum == total:
            return
        listing = "\n".join(f"- {line.description or '-'}: {line.subtotal}" for line in lines)
        try:
            text = self._read(FOLLOWUP_SYSTEM_PROMPT, pdf_bytes,
                              FOLLOWUP_INSTRUCTION.format(lines=listing, line_sum=line_sum, total=total), 800,
                              {} if usage is None else usage)
            match = re.search(r"\{.*\}", text, re.DOTALL)
            answer = json.loads(match.group(0)) if match else {}
        except (BedrockError, json.JSONDecodeError):
            return  # pembacaan pertama tetap dipakai; selisih dilaporkan verifikasi sistem
        candidates = [
            _charge_line(to_text(item.get("description")), to_decimal(item.get("subtotal")),
                         str(item.get("kind") or "").lower())
            for item in _followup_items(answer)
        ]
        recovered = complete_with_charges(lines, candidates, total)
        if recovered:
            result.line_items = lines + recovered
            result.raw = {**result.raw, "charges_recovered_by_followup": [line.description for line in recovered]}
