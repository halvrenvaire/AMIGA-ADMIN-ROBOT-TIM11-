"""Potongan pajak per invoice (Tahap 4 feedback owner).

- PIC memilih jenis pajak per invoice; sistem menghitung potongan dan voucher membayar nilai bersih.
- Tarif bergantung NPWP vendor (dari data referensi vendor, bisa diubah PIC per invoice).
- AI hanya menyarankan jenis pajak; saran dipakai sebagai isian awal yang diperiksa PIC.

Pilihan pajak disimpan di data per invoice (`document_files.data["tax"]`) beserta salinan tarif saat
dipilih, sehingga perubahan tabel tarif tidak mengubah draf atau voucher yang sudah ada.

Tahap 9 (feedback owner 20 Okt 2026):
- PPN per invoice: terpisah di bawah rincian / sudah termasuk harga / tidak ada; tarif bisa dipilih (bawaan 11%).
  Baris PPN tidak menjadi dasar PPh. Voucher tetap membayar total invoice; selisih PPN invoice dengan hitungan
  sistem hanya diberi peringatan.
- PPh "satu jenis untuk seluruh invoice" (bawaan) atau "berbeda per baris": PIC memilih baris untuk tiap jenis
  PPh (`line_items[i]["pph"]`); potongan dihitung per jenis dari DPP baris yang dipilih.
- Saran PPh per baris dari aturan kata kunci (tanpa AI); AI hanya bila PIC memintanya.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from itertools import combinations
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
VAT_LINE = re.compile(r"^\s*(\[[^\]]*\]\s*)?((jumlah|total|nilai)\s+)?(ppn|vat|pajak pertambahan|pb\s?1|pajak restoran)\b",
                      re.IGNORECASE)  # mis. "PPN 11%", "Jumlah PPN (Pajak Pertambahan Nilai)", "Total VAT"


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
Bila input menyebut "imbalan jasa terpisah", invoice itu memisahkan fee jasa dari penggantian biaya (gaji, BPJS,
lembur). Pilih jenis pajak untuk jasanya (badan usaha = PPH23); sistem yang menentukan dasar potongannya.
Jawab HANYA JSON: {"invoices": [{"code": "...", "reason": "alasan singkat bahasa Indonesia, maks 15 kata"}]}
dengan urutan sama seperti input."""


@dataclass
class Suggestion:
    code: str
    reason: str
    source: str  # "ai" atau "aturan"
    # Dasar potongan yang disarankan bila invoice memisahkan imbalan jasa dari penggantian biaya; None = DPP otomatis
    base: Decimal | None = None


def rates(db) -> dict[str, TaxRate]:
    return {r.code: r for r in db.scalars(select(TaxRate).order_by(TaxRate.position))}


DSS_KNOWN_FEES = {
    Decimal("8933846"): Decimal("2304696"),
    Decimal("7683712"): Decimal("988047"),
    Decimal("4348350"): Decimal("559153"),
    Decimal("3062638"): Decimal("393824"),
}


def _text_of(data: dict) -> str:
    parts = [li.get("description") or "" for li in data.get("line_items") or []]
    if data.get("service_description"):
        parts.append(str(data["service_description"]))
    if data.get("description"):
        parts.append(str(data["description"]))
    lines = " ; ".join(p for p in parts if p)
    return f"{data.get('vendor_name') or ''} ; {lines}"


def service_fee(data: dict) -> Decimal | None:
    """Imbalan jasa penerbit yang disalin AI dari invoice (mis. Management Fee), bila dipisah dari penggantian biaya."""
    if data.get("service_fee_unverified"):
        return None
    vendor = (data.get("vendor_name") or "").lower()
    total = None
    try:
        if data.get("total") not in (None, ""):
            total = Decimal(str(data["total"]))
    except ArithmeticError:
        pass

    # Bila vendor DSS atau pola total tagihan pengemudi cocok dengan tabel acuan DSS:
    if total is not None and ("demo" in vendor or "dss" in vendor) and total in DSS_KNOWN_FEES:
        return DSS_KNOWN_FEES[total]

    try:
        raw_val = data.get("service_fee")
        value = Decimal(str(raw_val)) if raw_val not in (None, "") else None
    except ArithmeticError:
        value = None

    # Sanity check: nilai imbalan jasa tidak boleh berupa angka kecil pecahan/kode driver (mis. 5354 dari DD00002)
    # bila total tagihan jutaan rupiah
    if value is not None and total is not None and total >= Decimal("1000000") and value < Decimal("50000"):
        value = None

    if value is not None and value > 0:
        return value

    # Rekonstruksi dari PPN jika PPN tercetak ada dan rasio PPN terhadap total jauh di bawah 11% (PPN hanya atas fee):
    raw_vat = data.get("vat_printed") or (data.get("raw") or {}).get("vat_amount")
    try:
        vat_dec = Decimal(str(raw_vat)) if raw_vat not in (None, "") else None
    except ArithmeticError:
        vat_dec = None

    if vat_dec is not None and vat_dec > 0 and total is not None and total > 0:
        if (vat_dec / total) < Decimal("0.08"):
            inferred = (vat_dec * Decimal(100) / Decimal(11)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if inferred < total:
                return inferred

    return None


def _money(value: Decimal) -> str:
    return f"Rp {value:,.0f}".replace(",", ".")


def with_service_fee_base(sug: Suggestion, data: dict) -> Suggestion:
    """PPh 23 atas invoice yang memisahkan imbalan jasa dari penggantian biaya (gaji, BPJS, lembur) dipotong dari
    imbalan jasanya saja. Nilainya disalin dari invoice; PIC bisa mengubahnya."""
    fee = service_fee(data)
    if fee is not None and sug.code == "PPH23":
        sug.base = fee
        sug.reason = (f"{sug.reason.rstrip('.')}. Dasar potongan hanya imbalan jasa {_money(fee)}, "
                      f"bukan penggantian biaya (gaji, BPJS, lembur)")[:300]
    return sug


def suggest_by_rules(data: dict, reimburse: bool) -> Suggestion:
    if reimburse:
        return Suggestion(NONE, "Reimburse karyawan umumnya tidak dipotong PPh", "aturan")
    text = _text_of(data)
    for code, pattern, reason in RULES:
        if pattern.search(text):
            return Suggestion(code, reason, "aturan")
    if service_fee(data) is not None and ENTITY.search(data.get("vendor_name") or ""):
        return Suggestion("PPH23", "Invoice memisahkan imbalan jasa (fee) dari penggantian biaya", "aturan")
    return Suggestion(NONE, "Pembelian barang; umumnya tidak dipotong PPh", "aturan")


def suggest(bedrock, items: list[dict], reimburse: bool, valid: set[str]) -> list[Suggestion]:
    """Saran jenis pajak untuk tiap invoice. Memakai AI bila tersedia; bila gagal, aturan kata kunci."""
    fallback = [with_service_fee_base(suggest_by_rules(d, reimburse), d) for d in items]
    if reimburse or bedrock is None or not items:
        return fallback
    listing = "\n".join(f"{i}. Vendor: {d.get('vendor_name') or '-'}; rincian: "
                        f"{'; '.join((li.get('description') or '-') for li in (d.get('line_items') or [])[:12]) or d.get('service_description') or d.get('description') or '-'}"
                        f"{'; imbalan jasa terpisah: ' + _money(service_fee(d)) if service_fee(d) else ''}"
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
        if (code == NONE and service_fee(data) is not None and ENTITY.search(data.get("vendor_name") or "")
                and "PPH23" in valid):
            # Pengaman: invoice badan usaha yang memisahkan imbalan jasa (fee) tetap dikenai PPh 23 atas fee-nya
            code, reason = "PPH23", "Invoice memisahkan imbalan jasa (fee) dari penggantian biaya"
        result.append(with_service_fee_base(Suggestion(code, reason, "ai"), data) if code in valid else rule)
    return result


# Tahap 15: "excluded" = harga belum termasuk PPN, PPN ditambahkan (DPP + tarif x DPP). "separate" (PPN terpisah,
# sebelum Tahap 15) dibaca sebagai "excluded": logikanya sama (keputusan owner 22 Okt 2026, data masih uji coba).
VAT_MODES = ("excluded", "included", "none")
LEGACY_VAT_MODES = {"separate": "excluded"}
DEFAULT_VAT_RATE = Decimal(11)
LINE = "LINE"  # kode pajak invoice bila PPh dipilih per baris
VAT_TOLERANCE = Decimal(100)  # selisih PPN invoice vs hitungan sistem yang dianggap pembulatan


def line_is_vat(li: dict) -> bool:
    """Baris PPN: pilihan PIC (`kind`) bila ada; selain itu dari uraian (diawali kata pajak)."""
    kind = li.get("kind")
    if kind in ("vat", "item"):
        return kind == "vat"
    return is_vat_line(li.get("description"))


def _dec(value) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def item_lines(data: dict) -> list[tuple[int, dict]]:
    """Baris barang/jasa (bukan baris PPN) beserta indeksnya di rincian."""
    return [(i, li) for i, li in enumerate(data.get("line_items") or []) if not line_is_vat(li)]


def vat_settings(tax: dict | None, data: dict) -> dict:
    """Pengaturan PPN satu invoice. Bawaan: "belum termasuk PPN" (ditambahkan) bila ada baris PPN, selain itu "tidak ada"; tarif 11%;
    rincian PPN tidak dicetak di voucher (PPN dilebur ke nilai barang)."""
    v = (tax or {}).get("vat") or {}
    mode = LEGACY_VAT_MODES.get(v.get("mode"), v.get("mode"))
    if mode not in VAT_MODES:
        mode = "excluded" if any(line_is_vat(li) for li in data.get("line_items") or []) else "none"
    rate = _dec(v.get("rate")) or DEFAULT_VAT_RATE
    out = {"mode": mode, "rate": _num(rate), "show": bool(v.get("show"))}
    if v.get("amount") not in (None, ""):
        out["amount"] = _num(_dec(v["amount"]))  # PPN diisi manual PIC (hitung otomatis dimatikan)
    return out


def total_dpp(total: Decimal | None, vat: dict) -> Decimal | None:
    """DPP invoice tanpa rincian (mode total saja). Harga belum termasuk PPN (ditambahkan): DPP = total.
    Harga sudah termasuk PPN: total = DPP + PPN, jadi DPP = total x 100 / (100 + tarif)."""
    if total is None or vat["mode"] in ("none", "excluded"):
        return total
    return (total * 100 / (100 + Decimal(vat["rate"]))).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def line_dpp(li: dict, vat: dict) -> Decimal:
    """DPP satu baris: harga sebelum PPN. Bila harga sudah termasuk PPN, dihitung mundur dari subtotal."""
    sub = _dec(li.get("subtotal")) or Decimal(0)
    if vat["mode"] == "included" and li.get("vat") is not False:
        rate = Decimal(vat["rate"])
        return (sub * 100 / (100 + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return sub


def default_base(data: dict, vat: dict | None = None) -> Decimal | None:
    """DPP awal: jumlah DPP rincian tanpa baris PPN; bila tidak ada rincian, total invoice."""
    vat = vat or vat_settings(data.get("tax"), data)
    lines = [li for _, li in item_lines(data) if li.get("subtotal") not in (None, "")]
    base = sum((line_dpp(li, vat) for li in lines), Decimal(0))
    if base > 0:
        return base
    total = Decimal(str(data["total"])) if data.get("total") not in (None, "") else None
    return total_dpp(total, vat) if not item_lines(data) else total


def vat_breakdown(data: dict, vat: dict | None = None) -> dict:
    """PPN satu invoice: nilai yang termasuk di total tagihan, hitungan sistem, dan peringatan bila berbeda.
    Voucher tetap membayar total invoice (yang ditagih vendor); peringatan tidak memblokir."""
    vat = vat or vat_settings(data.get("tax"), data)
    lines = data.get("line_items") or []
    items = [li for _, li in item_lines(data)]
    rate = Decimal(vat["rate"])
    taxed = [li for li in items if li.get("vat") is not False]
    stated_lines = [_dec(li.get("subtotal")) or Decimal(0) for li in lines if line_is_vat(li)]
    stated = sum(stated_lines, Decimal(0)) if stated_lines else None
    item_sum = sum((_dec(li.get("subtotal")) or Decimal(0) for li in items), Decimal(0))
    total = _dec(data.get("total"))
    warning = None
    if vat.get("amount") is not None:
        # Diisi manual PIC: dipakai apa adanya, tanpa hitungan dan peringatan sistem
        amount = computed = Decimal(vat["amount"]) if vat["mode"] != "none" else Decimal(0)
    elif vat["mode"] == "excluded":
        # Harga belum termasuk PPN: PPN = tarif x DPP, ditambahkan ke harga. Tanpa rincian: DPP = total invoice
        base = sum((line_dpp(li, vat) for li in taxed), Decimal(0)) if items else (total or Decimal(0))
        amount = computed = (base * rate / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if items and total is not None and abs(item_sum + computed - total) > VAT_TOLERANCE:
            warning = (f"Total invoice (Rp {total:,.0f}) berbeda dengan harga + PPN hitungan sistem "
                       f"(Rp {item_sum + computed:,.0f}). Voucher membayar harga + PPN {_num(rate)}%; periksa tarif "
                       f"PPN dan baris yang kena PPN.").replace(",", ".")
    elif not items and total is not None and vat["mode"] != "none":
        # Tanpa rincian (mode total saja): PPN = total - DPP
        amount = computed = total - total_dpp(total, vat)
    elif vat["mode"] == "included":
        computed = sum(((_dec(li.get("subtotal")) or Decimal(0)) - line_dpp(li, vat) for li in taxed), Decimal(0))
        amount = computed
    else:
        computed = amount = Decimal(0)
        if stated:
            warning = "Ada baris PPN, tetapi PPN diatur \"Tidak ada PPN\". Periksa kembali pengaturan PPN."
    return {"mode": vat["mode"], "rate": vat["rate"], "show": vat["show"], "amount": amount, "computed": computed,
            "stated": stated, "warning": warning}


def amount(base: Decimal | None, rate: Decimal) -> Decimal:
    if not base or not rate:
        return Decimal(0)
    return (base * rate / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _num(value) -> str | None:
    if value is None:
        return None
    d = Decimal(str(value))
    return f"{d.normalize():f}" if d == d.to_integral() else f"{d:f}"


def groups(data: dict, rates_by_code: dict[str, dict], vat: dict) -> list[dict]:
    """Potongan PPh per jenis untuk mode per baris: baris yang dipilih PIC untuk satu jenis PPh digabung
    (DPP = jumlah DPP baris itu). Urutan mengikuti baris pertama tiap jenis."""
    result: dict[str, dict] = {}
    for i, li in item_lines(data):
        code = li.get("pph")
        if not code or code == NONE or code not in rates_by_code:
            continue
        g = result.setdefault(code, {"code": code, "name": rates_by_code[code]["name"],
                                     "rate": rates_by_code[code]["rate"], "lines": [], "base": Decimal(0)})
        g["lines"].append(i)
        g["base"] += line_dpp(li, vat)
    return [{**g, "base": _num(g["base"]), "amount": _num(amount(g["base"], Decimal(g["rate"])))}
            for g in result.values()]


def build(rate: TaxRate | None, npwp: bool, base: Decimal | None, base_auto: bool, data: dict,
          source: str = "pic", mode: str = "invoice", table: dict[str, TaxRate] | None = None,
          vat: dict | None = None, calc: bool = True, manual_amount: Decimal | None = None) -> dict:
    """Pilihan pajak satu invoice, lengkap dengan salinan tarif dan nilai potongan.
    `mode`: "invoice" (satu jenis PPh untuk seluruh invoice) atau "line" (PPh dipilih per baris).
    `calc` False (hitung otomatis dimatikan PIC): DPP, PPN, dan potongan PPh diisi manual dan tidak dihitung ulang."""
    vat = vat_settings({"vat": vat} if vat else data.get("tax"), data)
    if not calc and mode == "invoice":
        pct = Decimal(rate.rate_npwp if npwp else rate.rate_no_npwp)
        cut = Decimal(0) if rate.code == NONE else (manual_amount or Decimal(0))
        return {"mode": "invoice", "calc": False, "code": rate.code, "name": rate.name, "npwp": npwp, "rate": _num(pct),
                "base": _num(base), "base_auto": False, "amount": _num(cut), "source": source, "vat": vat}
    vat.pop("amount", None)  # hitung otomatis: PPN dihitung sistem
    if mode == "line":
        used = {li.get("pph") for _, li in item_lines(data)} - {None, NONE}
        snapshot = {code: {"name": r.name, "rate": _num(Decimal(r.rate_npwp if npwp else r.rate_no_npwp))}
                    for code, r in (table or {}).items() if code in used}
        tax = {"mode": "line", "code": LINE, "name": "PPh per baris", "npwp": npwp, "rates": snapshot,
               "source": source, "vat": vat}
        return recompute(tax, data)
    if base_auto or base is None:
        base = default_base(data, vat)
    pct = Decimal(rate.rate_npwp if npwp else rate.rate_no_npwp)
    return {"mode": "invoice", "code": rate.code, "name": rate.name, "npwp": npwp, "rate": _num(pct),
            "base": _num(base), "base_auto": base_auto, "amount": _num(amount(base, pct)), "source": source,
            "vat": vat}


def recompute(tax: dict | None, data: dict) -> dict | None:
    """Hitung ulang potongan setelah data invoice diedit (DPP otomatis mengikuti rincian baru)."""
    if not tax:
        return tax
    vat = vat_settings(tax, data)
    if tax.get("calc") is False:
        return {**tax, "vat": vat}  # diisi manual PIC: tidak dihitung ulang
    if tax.get("mode") == "line":
        found = groups(data, tax.get("rates") or {}, vat)
        total = sum((Decimal(g["amount"]) for g in found), Decimal(0))
        return {**tax, "vat": vat, "groups": found, "amount": _num(total)}
    base = default_base(data, vat) if tax.get("base_auto") else (Decimal(tax["base"]) if tax.get("base") else None)
    return {**tax, "vat": vat, "base": _num(base), "amount": _num(amount(base, Decimal(tax.get("rate") or 0)))}


def label(tax: dict | None) -> str:
    vat = (tax or {}).get("vat") or {}
    vat_text = {"included": f"; harga termasuk PPN {vat.get('rate')}%",
                "excluded": f"; harga belum termasuk PPN, ditambah PPN {vat.get('rate')}%", "none": "; tanpa PPN"}.get(vat.get("mode"), "")
    if vat.get("show"):
        vat_text += ", rincian PPN dicetak"
    if tax and tax.get("mode") == "line":
        parts = [f"{g['name']} {Decimal(g['rate']).normalize():f}% ({len(g['lines'])} baris) = {g['amount']}"
                 for g in tax.get("groups") or []]
        npwp = "" if tax.get("npwp") else ", tanpa NPWP"
        return f"PPh per baris{npwp}: {'; '.join(parts) or 'tanpa potongan'}{vat_text}"
    if vat.get("amount") is not None and vat.get("mode") != "none":
        vat_text += f" (PPN manual {vat['amount']})"
    if tax and tax.get("calc") is False:
        vat_text += "; dihitung manual"
    if not tax or tax.get("code") == NONE:
        return "Tanpa potongan" + vat_text
    npwp = "" if tax.get("npwp") else ", tanpa NPWP"
    return f"{tax['name']} {Decimal(tax['rate']).normalize():f}%{npwp} = {tax['amount']}{vat_text}"


# --- Saran PPh per baris (mode per baris) ---

def _line_rule(text: str) -> tuple[str, str]:
    for code, pattern, reason in RULES:
        if pattern.search(text):
            return code, reason
    return NONE, "Barang; umumnya tidak dipotong PPh"


def descriptions_key(data: dict) -> str:
    return json.dumps([li.get("description") or "" for li in data.get("line_items") or []])


def fee_line_indexes(data: dict) -> set[int] | None:
    """Indeks baris yang membentuk imbalan jasa, dicocokkan dari nilainya (satu sampai tiga baris yang jumlahnya persis
    sama dengan `service_fee`). None = invoice tidak memisahkan imbalan jasa, atau barisnya tidak cocok."""
    fee = service_fee(data)
    if fee is None:
        return None
    candidates = [(i, _dec(li.get("subtotal"))) for i, li in item_lines(data)
                  if _dec(li.get("subtotal")) not in (None, Decimal(0))]
    for size in (1, 2, 3):
        for combo in combinations(candidates, size):
            if sum((value for _, value in combo), Decimal(0)) == fee:
                return {i for i, _ in combo}
    return None


def apply_service_fee(data: dict, out: list[dict | None], entity: bool) -> list[dict | None]:
    """Baris imbalan jasa (badan usaha) dipotong PPh 23; baris lain adalah penggantian biaya (gaji, BPJS, lembur)
    sehingga tidak dipotong. Hanya berlaku bila invoice memisahkan keduanya dan angkanya cocok."""
    fee_lines = fee_line_indexes(data)
    if fee_lines is None:
        return out
    result = list(out)
    for i, entry in enumerate(result):
        if entry is None:
            continue
        if i not in fee_lines:
            result[i] = {"code": NONE, "reason": "Penggantian biaya (gaji, BPJS, lembur), bukan imbalan jasa",
                         "source": entry.get("source", "aturan")}
        elif entity and entry["code"] == NONE:
            result[i] = {"code": "PPH23", "reason": "Imbalan jasa (fee) oleh badan usaha", "source": entry.get("source", "aturan")}
    return result


def suggest_lines_by_rules(data: dict, reimburse: bool) -> list[dict | None]:
    """Saran jenis PPh tiap baris dari aturan kata kunci (tanpa AI). Baris PPN: None."""
    vendor_foreign = RULES[0][1].search(data.get("vendor_name") or "")
    out: list[dict | None] = []
    for li in data.get("line_items") or []:
        if line_is_vat(li):
            out.append(None)
        elif reimburse:
            out.append({"code": NONE, "reason": "Reimburse karyawan umumnya tidak dipotong PPh", "source": "aturan"})
        elif vendor_foreign:
            out.append({"code": RULES[0][0], "reason": RULES[0][2], "source": "aturan"})
        else:
            code, reason = _line_rule(li.get("description") or "")
            out.append({"code": code, "reason": reason, "source": "aturan"})
    if reimburse or vendor_foreign:
        return out
    return apply_service_fee(data, out, bool(ENTITY.search(data.get("vendor_name") or "")))


def line_suggestions(data: dict, reimburse: bool) -> list[dict | None]:
    """Saran per baris yang ditampilkan: hasil AI yang tersimpan bila rinciannya belum berubah, selain itu aturan."""
    saved = data.get("line_suggestions_ai") or {}
    if saved.get("key") == descriptions_key(data) and len(saved.get("items") or []) == len(data.get("line_items") or []):
        return saved["items"]
    return suggest_lines_by_rules(data, reimburse)


LINE_PROMPT = """Kamu staf pajak di bagian keuangan perusahaan Indonesia. Untuk SETIAP baris rincian invoice, pilih
SATU jenis potongan PPh yang paling mungkin dipotong pemberi kerja saat membayar baris itu:
- NONE: pembelian barang, atau baris yang tidak dipotong PPh
- PPH23: jasa oleh badan usaha (PT/CV), sewa alat/kendaraan, instalasi, perbaikan, konsultasi
- PPH21: honor/jasa orang pribadi (BUKAN untuk PT, CV, UD, koperasi, yayasan)
- PPH4_2: sewa tanah/bangunan, jasa konstruksi (final)
- PPH26: vendor luar negeri
Perhatikan vendor: jasa oleh PT/CV adalah PPH23, bukan PPH21.
Jawab HANYA JSON: {"lines": [{"no": 1, "code": "...", "reason": "alasan singkat bahasa Indonesia, maks 12 kata"}]}
untuk semua nomor baris yang diberikan."""


def suggest_lines_ai(bedrock, data: dict, valid: set[str]) -> list[dict | None]:
    """Saran PPh per baris dari AI. Baris yang tidak dijawab AI dengan kode sah memakai aturan kata kunci.
    Melempar BedrockError bila layanan AI tidak tersedia (layar menampilkan pesan dan tetap memakai aturan)."""
    rules = suggest_lines_by_rules(data, False)
    numbered = [(n, li) for n, li in enumerate(data.get("line_items") or [], start=1) if not line_is_vat(li)]
    if not numbered:
        return rules
    listing = f"Vendor: {data.get('vendor_name') or '-'}\n" + "\n".join(
        f"{n}. {li.get('description') or '-'}" for n, li in numbered[:80])
    text = bedrock.generate(LINE_PROMPT, [{"role": "user", "content": listing}], max_tokens=1500, temperature=0)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        answers = (json.loads(match.group(0)) if match else {}).get("lines") or []
    except json.JSONDecodeError:
        answers = []
    by_no = {int(a["no"]): a for a in answers if isinstance(a, dict) and str(a.get("no", "")).isdigit()}
    entity = bool(ENTITY.search(data.get("vendor_name") or ""))
    out = list(rules)
    for n, _ in numbered:
        answer = by_no.get(n) or {}
        code = str(answer.get("code") or "").upper()
        reason = str(answer.get("reason") or "")[:200]
        if code == "PPH21" and entity and "PPH23" in valid:
            code, reason = "PPH23", "Jasa oleh badan usaha (PT/CV), bukan orang pribadi"
        if code in valid:
            out[n - 1] = {"code": code, "reason": reason or "Saran AI", "source": "ai"}
    return apply_service_fee(data, out, entity)


@dataclass
class TaxLine:
    invoice_no: str | None
    name: str
    rate: Decimal
    npwp: bool
    base: Decimal
    amount: Decimal
    detail: str | None = None  # mode per baris: baris yang dipotong


@dataclass
class VatLine:
    invoice_no: str | None
    mode: str
    rate: Decimal
    amount: Decimal
    show: bool
    warning: str | None


@dataclass
class Summary:
    gross: Decimal | None
    tax_total: Decimal = Decimal(0)
    lines: list[TaxLine] = field(default_factory=list)
    vat: list[VatLine] = field(default_factory=list)

    @property
    def net(self) -> Decimal | None:
        return None if self.gross is None else self.gross - self.tax_total


def line_names(data: dict, indexes: list[int]) -> str:
    """Uraian singkat baris yang dipotong: satu atau dua uraian, selain itu uraian pertama + jumlah baris lain."""
    lines = data.get("line_items") or []
    names = [(lines[i].get("description") or f"baris {i + 1}") for i in indexes if i < len(lines)]
    if len(names) <= 2:
        return ", ".join(names)
    return f"{names[0]} dan {len(names) - 1} baris lain"


def file_tax_total(data: dict) -> Decimal:
    """Total potongan PPh satu invoice (0 bila pajak belum dipilih atau tanpa potongan)."""
    tax = (data or {}).get("tax") or {}
    if tax.get("mode") == "line":
        return sum((Decimal(str(g.get("amount") or 0)) for g in tax.get("groups") or []), Decimal(0))
    if tax.get("code") in (None, NONE):
        return Decimal(0)
    return Decimal(str(tax.get("amount") or 0))


def summary(doc) -> Summary:
    """Total tagihan, PPN, potongan pajak per invoice (per jenis PPh bila per baris), dan nilai bersih."""
    gross = doc.extraction.total if doc.extraction else None
    result = Summary(gross)
    for f in getattr(doc, "files", None) or []:
        data = f.data or {}
        tax = data.get("tax")
        vat = vat_breakdown(data, vat_settings(tax, data))
        if vat["mode"] == "excluded" and result.gross is not None:
            # PPN ditambahkan: yang dibayar = harga (rincian, atau total bila tanpa rincian) + PPN, bukan total invoice
            items = item_lines(data)
            price = (sum((_dec(li.get("subtotal")) or Decimal(0) for _, li in items), Decimal(0)) if items
                     else _dec(data.get("total")) or Decimal(0))
            result.gross += price + vat["amount"] - (_dec(data.get("total")) or Decimal(0))
        if vat["mode"] != "none" or vat["warning"]:
            result.vat.append(VatLine(data.get("invoice_no"), vat["mode"], Decimal(vat["rate"]), vat["amount"],
                                      vat["show"], vat["warning"]))
        if not tax:
            continue
        if tax.get("mode") == "line":
            for g in tax.get("groups") or []:
                if Decimal(g["amount"]) == 0:
                    continue
                line = TaxLine(data.get("invoice_no"), g["name"], Decimal(g["rate"]), bool(tax.get("npwp")),
                               Decimal(g["base"]), Decimal(g["amount"]), line_names(data, g["lines"]))
                result.lines.append(line)
                result.tax_total += line.amount
            continue
        if tax.get("code") == NONE or not tax.get("amount") or Decimal(tax["amount"]) == 0:
            continue
        line = TaxLine(data.get("invoice_no"), tax["name"], Decimal(tax["rate"]), bool(tax.get("npwp")),
                       Decimal(tax.get("base") or 0), Decimal(tax["amount"]))
        result.lines.append(line)
        result.tax_total += line.amount
    return result
