"""Potongan pajak per invoice (Tahap 4 feedback owner).

- PIC memilih jenis pajak per invoice; sistem menghitung potongan dan voucher membayar nilai bersih.
- Tarif bergantung NPWP vendor (dari data referensi vendor, bisa diubah PIC per invoice).
- AI hanya menyarankan jenis pajak; saran dipakai sebagai isian awal yang diperiksa PIC.

Pilihan pajak disimpan di data per invoice (`document_files.data["tax"]`) beserta salinan tarif saat
dipilih, sehingga perubahan tabel tarif tidak mengubah draf atau voucher yang sudah ada.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from app.models import TaxRate
from app.services.bedrock_client import BedrockError

log = logging.getLogger(__name__)

NONE = "NONE"
# Badan usaha (bukan orang pribadi): PPh 21 tidak berlaku, jasa badan dipotong PPh 23
ENTITY = re.compile(r"^\s*(pt|cv|ud|pd|fa|firma|koperasi|yayasan|perum|persero)\b\.?|\b(tbk|persero)\b", re.I)
# Baris PPN/pajak di rincian: tidak ikut DPP PPh dan tidak dicetak di voucher (feedback owner 20 Okt 2026:
# PPN tidak diperhitungkan lagi, yang dipakai total invoice). Hanya baris yang DIAWALI kata pajak, supaya
# barang seperti "Jasa servis (termasuk PPN)" tidak ikut tersembunyi. Awalan "[INV-001] " dari invoice gabungan
# dilewati.
VAT_LINE = re.compile(r"^\s*(\[[^\]]*\]\s*)?(ppn|vat|pajak pertambahan|pb\s?1|pajak restoran)\b", re.IGNORECASE)


def is_vat_line(description: str | None) -> bool:
    return bool(VAT_LINE.match(description or ""))

# Cadangan berbasis kata kunci bila AI tidak tersedia; urutan = prioritas
RULES: list[tuple[str, re.Pattern, str]] = [
    ("PPH26", re.compile(r"\b(ltd|inc|llc|pte|gmbh|corp(oration)?|luar negeri|overseas|usd|sgd)\b", re.I),
     "Vendor atau tagihan menunjukkan pihak luar negeri"),
    ("PPH4_2", re.compile(r"\b(sewa (gedung|ruang|ruangan|kantor|tanah|bangunan|gudang)|konstruksi|"
                          r"renovasi bangunan)\b", re.I),
     "Sewa tanah/bangunan atau jasa konstruksi"),
    ("PPH21", re.compile(r"\b(honor|honorarium|narasumber|pembicara|freelance|tenaga ahli perorangan)\b", re.I),
     "Honor atau jasa orang pribadi"),
    ("PPH23", re.compile(r"\b(jasa|konsultan|konsultasi|sewa|rental|perbaikan|servis|service|maintenance|"
                         r"pemeliharaan|kebersihan|keamanan|catering|katering|instalasi|pelatihan|training|"
                         r"desain|design|manajemen|pengiriman|ekspedisi)\b", re.I),
     "Tagihan jasa oleh badan usaha"),
]

SYSTEM_PROMPT = """Kamu staf pajak di bagian keuangan perusahaan Indonesia. Untuk setiap invoice, pilih SATU jenis
potongan PPh yang paling mungkin dipotong pemberi kerja saat membayar:
- NONE: pembelian barang, atau tagihan yang tidak dipotong PPh
- PPH23: jasa oleh badan usaha (PT/CV), sewa alat/kendaraan
- PPH21: honor/jasa orang pribadi (BUKAN untuk PT, CV, UD, koperasi, yayasan)
- PPH4_2: sewa tanah/bangunan, jasa konstruksi (final)
- PPH26: vendor luar negeri
Jawab HANYA JSON: {"invoices": [{"code": "...", "reason": "alasan singkat bahasa Indonesia, maks 15 kata"}]}
dengan urutan sama seperti input."""


@dataclass
class Suggestion:
    code: str
    reason: str
    source: str  # "ai" atau "aturan"


def rates(db) -> dict[str, TaxRate]:
    return {r.code: r for r in db.scalars(select(TaxRate).order_by(TaxRate.position))}


def _text_of(data: dict) -> str:
    lines = " ; ".join(li.get("description") or "" for li in data.get("line_items") or [])
    return f"{data.get('vendor_name') or ''} ; {lines}"


def suggest_by_rules(data: dict, reimburse: bool) -> Suggestion:
    if reimburse:
        return Suggestion(NONE, "Reimburse karyawan umumnya tidak dipotong PPh", "aturan")
    text = _text_of(data)
    for code, pattern, reason in RULES:
        if pattern.search(text):
            return Suggestion(code, reason, "aturan")
    return Suggestion(NONE, "Pembelian barang; umumnya tidak dipotong PPh", "aturan")


def suggest(bedrock, items: list[dict], reimburse: bool, valid: set[str]) -> list[Suggestion]:
    """Saran jenis pajak untuk tiap invoice. Memakai AI bila tersedia; bila gagal, aturan kata kunci."""
    fallback = [suggest_by_rules(d, reimburse) for d in items]
    if reimburse or bedrock is None or not items:
        return fallback
    listing = "\n".join(f"{i}. Vendor: {d.get('vendor_name') or '-'}; rincian: "
                        f"{'; '.join((li.get('description') or '-') for li in (d.get('line_items') or [])[:12])}"
                        for i, d in enumerate(items, start=1))
    try:
        text = bedrock.generate(SYSTEM_PROMPT, [{"role": "user", "content": listing}], max_tokens=400, temperature=0)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        answers = (json.loads(match.group(0)) if match else {}).get("invoices") or []
    except (BedrockError, json.JSONDecodeError, AttributeError) as e:
        log.info("Saran pajak AI gagal, memakai aturan: %s", e)
        return fallback
    result = []
    for i, (data, rule) in enumerate(zip(items, fallback)):
        answer = answers[i] if i < len(answers) and isinstance(answers[i], dict) else {}
        code = str(answer.get("code") or "").upper()
        reason = str(answer.get("reason") or "")[:200] or rule.reason
        if code == "PPH21" and ENTITY.search(data.get("vendor_name") or "") and "PPH23" in valid:
            # Pengaman: AI kadang memilih PPh 21 untuk jasa oleh badan usaha
            code, reason = "PPH23", "Jasa oleh badan usaha (PT/CV), bukan orang pribadi"
        result.append(Suggestion(code, reason, "ai") if code in valid else rule)
    return result


def default_base(data: dict) -> Decimal | None:
    """DPP awal: jumlah rincian tanpa baris PPN; bila tidak ada rincian, total invoice."""
    lines = [li for li in data.get("line_items") or [] if li.get("subtotal") not in (None, "")]
    base = sum((Decimal(str(li["subtotal"])) for li in lines if not is_vat_line(li.get("description"))),
               Decimal(0))
    if base > 0:
        return base
    return Decimal(str(data["total"])) if data.get("total") not in (None, "") else None


def amount(base: Decimal | None, rate: Decimal) -> Decimal:
    if not base or not rate:
        return Decimal(0)
    return (base * rate / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _num(value) -> str | None:
    if value is None:
        return None
    d = Decimal(str(value))
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d:f}"


def build(rate: TaxRate, npwp: bool, base: Decimal | None, base_auto: bool, data: dict,
          source: str = "pic") -> dict:
    """Pilihan pajak satu invoice, lengkap dengan salinan tarif dan nilai potongan."""
    if base_auto or base is None:
        base = default_base(data)
    pct = Decimal(rate.rate_npwp if npwp else rate.rate_no_npwp)
    return {"code": rate.code, "name": rate.name, "npwp": npwp, "rate": _num(pct), "base": _num(base),
            "base_auto": base_auto, "amount": _num(amount(base, pct)), "source": source}


def recompute(tax: dict | None, data: dict) -> dict | None:
    """Hitung ulang potongan setelah data invoice diedit (DPP otomatis mengikuti rincian baru)."""
    if not tax:
        return tax
    base = default_base(data) if tax.get("base_auto") else (Decimal(tax["base"]) if tax.get("base") else None)
    return {**tax, "base": _num(base), "amount": _num(amount(base, Decimal(tax.get("rate") or 0)))}


def label(tax: dict | None) -> str:
    if not tax or tax.get("code") == NONE:
        return "Tanpa potongan"
    npwp = "" if tax.get("npwp") else ", tanpa NPWP"
    return f"{tax['name']} {Decimal(tax['rate']).normalize():f}%{npwp} = {tax['amount']}"


@dataclass
class TaxLine:
    invoice_no: str | None
    name: str
    rate: Decimal
    npwp: bool
    base: Decimal
    amount: Decimal


@dataclass
class Summary:
    gross: Decimal | None
    tax_total: Decimal = Decimal(0)
    lines: list[TaxLine] = field(default_factory=list)

    @property
    def net(self) -> Decimal | None:
        return None if self.gross is None else self.gross - self.tax_total


def summary(doc) -> Summary:
    """Total tagihan, potongan pajak per invoice, dan nilai bersih yang dibayarkan voucher."""
    gross = doc.extraction.total if doc.extraction else None
    result = Summary(gross)
    for f in getattr(doc, "files", None) or []:
        tax = (f.data or {}).get("tax")
        if not tax or tax.get("code") == NONE or not tax.get("amount") or Decimal(tax["amount"]) == 0:
            continue
        line = TaxLine((f.data or {}).get("invoice_no"), tax["name"], Decimal(tax["rate"]), bool(tax.get("npwp")),
                       Decimal(tax.get("base") or 0), Decimal(tax["amount"]))
        result.lines.append(line)
        result.tax_total += line.amount
    return result
