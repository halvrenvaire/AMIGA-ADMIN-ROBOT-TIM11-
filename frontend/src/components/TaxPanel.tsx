import { Fragment, useEffect, useMemo, useState } from "react";
import { Sparkles, Undo2, Wand2 } from "lucide-react";
import { api } from "../api";
import { plainNumber, rupiah } from "../format";
import type { DocumentDetail, FileData, LineSuggestion, TaxRate, TaxSummary, VatMode } from "../types";
import { Alert, useApi } from "./ui";

type Notice = { kind: "ok" | "info" | "error" | "warn"; text: string } | null;
type DocFile = DocumentDetail["files"][number];

/** Baris rincian seperti di editor draf; pph/vat/kind diatur di panel pajak. */
export interface TaxLine {
  description: string; subtotal: string;
  pph?: string | null; vat?: boolean | null; kind?: "item" | "vat" | null;
}

// Sama dengan backend (tax_service.VAT_LINE): hanya baris yang diawali kata pajak, mis. "PPN 11%",
// "Jumlah PPN (Pajak Pertambahan Nilai)", "Total VAT"
export const VAT_LINE = /^\s*(\[[^\]]*\]\s*)?((jumlah|total|nilai)\s+)?(ppn|vat|pajak pertambahan|pb\s?1|pajak restoran)\b/i;

export const isVatLine = (l: { description: string; kind?: "item" | "vat" | null }) =>
  l.kind ? l.kind === "vat" : VAT_LINE.test(l.description);

const pct = (v: string | number) => `${Number(v).toLocaleString("id-ID", { maximumFractionDigits: 3 })}%`;
const round2 = (n: number) => Math.round(n * 100) / 100;

const VAT_MODES: { value: VatMode; label: string }[] = [
  { value: "excluded", label: "Harga belum termasuk PPN (ditambahkan PPN)" },
  { value: "included", label: "Harga sudah termasuk PPN" },
  { value: "none", label: "Tidak ada PPN" },
];
const VAT_RATES = ["11", "12"];

interface Row { kind: "item" | "vat"; vat: boolean; pph: string }

/** DPP satu baris (sama dengan backend tax_service.line_dpp): harga sebelum PPN. */
function lineDpp(l: TaxLine, row: Row, vatMode: VatMode, rate: number): number {
  const sub = Number(l.subtotal) || 0;
  return vatMode === "included" && row.vat ? round2((sub * 100) / (100 + rate)) : sub;
}

/** DPP invoice tanpa rincian bila harga sudah termasuk PPN (sama dengan backend tax_service.total_dpp). */
const totalDpp = (total: number, rate: number) => Math.round((total * 100) / (100 + rate));

/** Format lama "PPN terpisah" dibaca sebagai "harga belum termasuk PPN" (sama dengan backend). */
const normalizeVatMode = (m: string | null | undefined): VatMode | null =>
  m === "separate" ? "excluded" : m === "excluded" || m === "included" || m === "none" ? m : null;

/** PPN dan hitungan sistem (sama dengan backend tax_service.vat_breakdown). `payable`: yang dibayar sebelum PPh bila
 *  PPN ditambahkan ke harga; tanpa `payable` = total invoice. */
function vatInfo(lines: TaxLine[], rows: Row[], total: string, vatMode: VatMode, rate: number, printed: number | null = null):
  { amount: number; computed: number; warning: string | null; payable?: number } {
  const items = lines.map((l, i) => ({ l, r: rows[i] })).filter(({ r }) => r && r.kind === "item");
  const itemSum = items.reduce((s, { l }) => s + (Number(l.subtotal) || 0), 0);
  const stated = lines.filter((_, i) => rows[i]?.kind === "vat").reduce((s, l) => s + (Number(l.subtotal) || 0), 0);
  const hasVatLine = rows.some((r) => r.kind === "vat");
  const taxed = items.filter(({ r }) => r.vat);
  if (vatMode === "excluded") {
    // Harga belum termasuk PPN: PPN = tarif x DPP, ditambahkan ke harga (tanpa rincian: DPP = total)
    const base = items.length ? taxed.reduce((s, { l, r }) => s + lineDpp(l, r, vatMode, rate), 0) : Number(total) || 0;
    const amount = Math.round((base * rate) / 100);
    const warning = items.length && total !== "" && Math.abs(itemSum + amount - Number(total)) > 100
      ? `Total invoice (${rupiah(Number(total))}) berbeda dengan harga + PPN hitungan sistem (${rupiah(itemSum + amount)}). Voucher membayar harga + PPN ${pct(rate)}; periksa tarif PPN dan baris yang kena PPN.`
      : null;
    return { amount, computed: amount, warning, payable: (items.length ? itemSum : Number(total) || 0) + amount };
  }
  if (!items.length && vatMode !== "none" && total !== "") {
    // Tanpa rincian, harga sudah termasuk PPN: total = DPP + PPN. PPN tercetak di invoice dipakai bila ada
    // (invoice jasa seperti DSS: PPN hanya atas imbalan jasa, jadi tarif x total akan salah)
    const amount = vatMode === "included" && printed != null ? printed : Number(total) - totalDpp(Number(total), rate);
    return { amount, computed: amount, warning: null as string | null };
  }
  if (vatMode === "included") {
    const amount = taxed.reduce((s, { l, r }) => s + (Number(l.subtotal) || 0) - lineDpp(l, r, vatMode, rate), 0);
    return { amount, computed: amount, warning: null as string | null };
  }
  return { amount: 0, computed: 0, warning: hasVatLine && stated ? "Ada baris PPN, tetapi PPN diatur \"Tidak ada PPN\". Periksa kembali pengaturan PPN." : null };
}

function initialRows(data: FileData | null | undefined, lines: TaxLine[], lineMode: boolean): Row[] {
  const suggestions = data?.line_suggestions ?? [];
  return lines.map((l, i) => {
    const kind = isVatLine(l) ? "vat" : "item";
    // Belum ada pilihan per baris: saran sistem (tanpa AI) menjadi pilihan awal, tetap perlu diterapkan PIC
    const pph = l.pph ?? (lineMode ? "" : suggestions[i]?.code ?? "");
    return { kind, vat: l.vat !== false, pph: pph === "NONE" ? "" : pph };
  });
}

/** Pajak per invoice: pengaturan PPN dan potongan PPh (satu jenis untuk seluruh invoice, atau per baris).
 *  PIC memilih; sistem dan AI hanya menyarankan; tarif PPh sesuai NPWP vendor. */
export function TaxPanel({ doc, file, lines, total, disabled, onDirty, onChange, onNotice }: {
  doc: DocumentDetail; file: DocFile; lines: TaxLine[]; total: string; disabled: boolean;
  onDirty: (d: boolean) => void; onChange: (d: DocumentDetail, n?: Notice) => void; onNotice: (n: Notice) => void;
}) {
  const rates = useApi(() => api.get<TaxRate[]>("/tax-rates"), []);
  const current = file.data?.tax ?? null;
  const suggestion = file.data?.tax_suggestion ?? null;
  const suggestions = file.data?.line_suggestions ?? [];
  const known = file.data?.npwp_known;
  const currentMode = current?.mode ?? "invoice";
  // Belum dipilih: saran menjadi pilihan awal di formulir, tetapi baru berlaku setelah PIC menerapkannya
  const [mode, setMode] = useState<"invoice" | "line">(currentMode);
  const [code, setCode] = useState(current && currentMode === "invoice" ? current.code : suggestion?.code ?? "NONE");
  const [npwp, setNpwp] = useState(current?.npwp ?? known !== false);
  const [manual, setManual] = useState(current && currentMode === "invoice" ? !current.base_auto : false);
  const [base, setBase] = useState(current && currentMode === "invoice" && !current.base_auto ? plainNumber(current.base ?? null) : "");
  // Hitung pajak otomatis (bawaan). Dimatikan: DPP, PPN, dan potongan PPh diisi sendiri oleh PIC
  const [calc, setCalc] = useState(current?.calc !== false);
  const [vatAmount, setVatAmount] = useState(current?.calc === false ? plainNumber(current.vat?.amount ?? null) : "");
  const [cutAmount, setCutAmount] = useState(current?.calc === false ? plainNumber(current.amount ?? null) : "");
  // Pengaturan baris yang tersimpan di server (panel nonaktif selama data invoice belum disimpan, jadi barisnya sama)
  const saved = useMemo<TaxLine[]>(() => (file.data?.line_items ?? []).map((l) => ({
    description: l.description ?? "", subtotal: l.subtotal ?? "", pph: l.pph, vat: l.vat, kind: l.kind,
  })), [file.data]);
  const initialVat = current?.vat;
  // Sama dengan backend: tanpa pengaturan, "belum termasuk PPN" bila ada baris PPN, selain itu "tidak ada"
  // Belum ada pilihan pajak: saran PPN dari pembacaan invoice (PPN tercetak = total sudah termasuk PPN)
  const defaultVatMode: VatMode = saved.some(isVatLine) ? "excluded" : suggestion?.vat?.mode ?? "none";
  const [vatMode, setVatMode] = useState<VatMode>(normalizeVatMode(initialVat?.mode) ?? defaultVatMode);
  const [vatRate, setVatRate] = useState(initialVat ? plainNumber(initialVat.rate) : "11");
  const [vatShow, setVatShow] = useState(initialVat?.show ?? false);
  const startRows = useMemo(() => initialRows(file.data, saved, currentMode === "line"), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [rows, setRows] = useState<Row[]>(startRows);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkCode, setBulkCode] = useState("PPH23");
  const [showLines, setShowLines] = useState(false);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // Rincian di editor berubah jumlahnya (baris ditambah/dihapus): sesuaikan pengaturan baris
  useEffect(() => {
    if (rows.length !== lines.length) setRows(initialRows(file.data, lines.length === saved.length ? saved : lines, mode === "line"));
  }, [lines.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = (rates.data ?? []).filter((r) => r.is_active || r.code === code);
  const pphList = list.filter((r) => r.code !== "NONE");
  const rateOf = (c: string) => {
    const r = list.find((x) => x.code === c);
    return r ? Number(npwp ? r.rate_npwp : r.rate_no_npwp) : 0;
  };
  const vatPct = Number(vatRate) || 11;
  const itemIdx = rows.map((r, i) => (r.kind === "item" ? i : -1)).filter((i) => i >= 0);
  const dpp = (i: number) => lineDpp(lines[i], rows[i], vatMode, vatPct);
  const dppTotal = itemIdx.reduce((s, i) => s + dpp(i), 0);
  const printedVat = file.data?.vat_printed ? Number(file.data.vat_printed) : null;
  const vat = vatInfo(lines, rows, total, vatMode, vatPct, printedVat);
  const gross = total === "" ? null : Number(total);
  // Dibayarkan sebelum PPh: harga + PPN bila PPN ditambahkan, selain itu total invoice
  const payable = gross == null ? null : calc ? vat.payable ?? gross
    : vatMode === "excluded" ? gross + (Number(vatAmount) || 0) : gross;

  // Mode satu jenis: DPP otomatis = jumlah DPP baris barang/jasa; tanpa rincian = total dikurangi PPN di dalamnya
  const autoBase = dppTotal > 0 ? dppTotal : gross == null ? null : itemIdx.length || vatMode !== "included" ? gross
    : printedVat != null ? gross - printedVat : totalDpp(gross, vatPct);
  const invoiceBase = manual || !calc ? (base === "" ? null : Number(base)) : autoBase;
  const invoiceCut = !calc ? (code === "NONE" ? 0 : Number(cutAmount) || 0)
    : invoiceBase && rateOf(code) ? Math.round((invoiceBase * rateOf(code)) / 100) : 0;
  // Mode per baris: potongan dikelompokkan per jenis PPh
  const groups = useMemo(() => {
    const byCode = new Map<string, { code: string; lines: number[]; base: number }>();
    itemIdx.forEach((i) => {
      const c = rows[i].pph;
      if (!c) return;
      const g = byCode.get(c) ?? { code: c, lines: [], base: 0 };
      g.lines.push(i); g.base += dpp(i);
      byCode.set(c, g);
    });
    return [...byCode.values()].map((g) => ({ ...g, rate: rateOf(g.code), amount: Math.round((g.base * rateOf(g.code)) / 100) }));
  }, [rows, lines, vatMode, vatPct, npwp, rates.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const cut = mode === "line" ? groups.reduce((s, g) => s + g.amount, 0) : invoiceCut;
  const distinctSuggestions = new Set(itemIdx.map((i) => suggestions[i]?.code ?? "NONE"));

  const body = () => ({
    mode, code: mode === "invoice" ? code : "NONE", npwp,
    base: mode === "invoice" && (manual || !calc) && base !== "" ? base : null,
    ...(!calc && { calc: false, vat_amount: vatMode !== "none" && vatAmount !== "" ? vatAmount : null,
                   amount: code !== "NONE" && cutAmount !== "" ? cutAmount : null }),
    lines: rows.map((r, i) => ({
      index: i, vat: r.vat, pph: mode === "line" && r.kind === "item" ? r.pph || null : undefined,
      // Jenis baris hanya dikirim bila berbeda dengan tebakan sistem atau pernah dikoreksi PIC
      kind: saved[i]?.kind || (r.kind === "vat") !== VAT_LINE.test(lines[i].description) ? r.kind : undefined,
    })),
    vat: { mode: vatMode, rate: String(vatPct), show: vatShow },
  });
  const savedBody = useMemo(() => JSON.stringify(current ? bodyFrom(current, saved, startRows) : null), [current, saved, startRows]);
  const dirty = Boolean(current) && JSON.stringify(body()) !== savedBody;
  useEffect(() => { onDirty(dirty); }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onDirty(false), []); // eslint-disable-line react-hooks/exhaustive-deps

  function bodyFrom(t: NonNullable<typeof current>, ls: TaxLine[], rs: Row[]) {
    const m = t.mode ?? "invoice";
    const manualCalc = t.calc === false;
    return {
      mode: m, code: m === "invoice" ? t.code : "NONE", npwp: t.npwp,
      base: m === "invoice" && !t.base_auto && t.base != null ? plainNumber(t.base) : null,
      ...(manualCalc && { calc: false, vat_amount: t.vat?.mode !== "none" && t.vat?.amount != null ? plainNumber(t.vat.amount) : null,
                          amount: t.code !== "NONE" && t.amount != null ? plainNumber(t.amount) : null }),
      lines: rs.map((r, i) => ({
        index: i, vat: r.vat, pph: m === "line" && r.kind === "item" ? ls[i].pph || null : undefined,
        kind: ls[i].kind || (r.kind === "vat") !== VAT_LINE.test(ls[i].description) ? r.kind : undefined,
      })),
      vat: { mode: t.vat?.mode ?? defaultVatMode, rate: String(Number(t.vat?.rate ?? 11)), show: t.vat?.show ?? false },
    };
  }

  function reset() {
    setMode(currentMode); setRows(startRows); setSelected(new Set());
    if (current) {
      setCode(currentMode === "invoice" ? current.code : "NONE"); setNpwp(current.npwp);
      setCalc(current.calc !== false);
      setVatAmount(current.calc === false ? plainNumber(current.vat?.amount ?? null) : "");
      setCutAmount(current.calc === false ? plainNumber(current.amount ?? null) : "");
      setManual(currentMode === "invoice" ? !current.base_auto : false);
      setBase(currentMode === "invoice" && !current.base_auto ? plainNumber(current.base ?? null) : "");
      if (current.vat) { setVatMode(current.vat.mode); setVatRate(plainNumber(current.vat.rate)); setVatShow(current.vat.show); }
    }
  }

  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, n) => (n === i ? { ...r, ...patch } : r)));
  const toggle = (i: number) => setSelected((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const allSelected = itemIdx.length > 0 && itemIdx.every((i) => selected.has(i));

  function applyBulk(c: string) {
    setRows((rs) => rs.map((r, i) => (selected.has(i) && r.kind === "item" ? { ...r, pph: c } : r)));
    setSelected(new Set());
  }

  function fillFromSuggestions(list: (LineSuggestion | null)[]) {
    setRows((rs) => rs.map((r, i) => (r.kind === "item" ? { ...r, pph: list[i]?.code && list[i]!.code !== "NONE" ? list[i]!.code : "" } : r)));
  }

  async function askAi() {
    setAiBusy(true); setAiError(null);
    try {
      const next = await api.post<DocumentDetail>(`/documents/${doc.id}/files/${file.position}/tax/ai-suggest`);
      const fresh = next.files.find((f) => f.position === file.position)?.data?.line_suggestions ?? [];
      fillFromSuggestions(fresh);
      onChange(next, { kind: "info", text: "Rekomendasi AI sudah diisikan ke pilihan PPh per baris. Periksa, lalu klik \"Terapkan pajak\"." });
    } catch (e) {
      setAiError((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  }

  async function apply() {
    setBusy(true);
    try {
      const next = await api.put<DocumentDetail>(`/documents/${doc.id}/files/${file.position}/tax`, body());
      onChange(next, { kind: "ok", text: `Pajak bukti ${file.position} diterapkan. Cek pratinjau voucher sebelum diajukan.` });
    } catch (e) {
      onNotice({ kind: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const off = disabled || busy;
  const codeName = (c: string) => list.find((r) => r.code === c)?.name ?? c;
  const lineTable = lines.length > 0 && (mode === "line" || showLines);

  return (
    <div className="tax-panel">
      <div className="section-title">Pajak</div>
      {!current && (
        <Alert kind="warn">Pajak bukti {file.position} <b>belum dipilih</b>. Periksa pengaturan di bawah, lalu klik
          &quot;Terapkan pajak&quot; (termasuk bila tanpa potongan).</Alert>
      )}
      <label className="toggle">
        <input type="checkbox" checked={calc} disabled={off}
               onChange={(e) => {
                 setCalc(e.target.checked);
                 if (!e.target.checked) {
                   // Mulai dari hitungan sistem, lalu PIC menyesuaikan dengan angka di invoice
                   setMode("invoice");
                   setBase(autoBase != null ? String(autoBase) : "");
                   setVatAmount(vatMode !== "none" ? String(Math.round(vat.amount)) : "");
                   setCutAmount(String(invoiceCut));
                 }
               }} />
        <span>Hitung pajak otomatis <span className="muted">· matikan bila ingin mengisi DPP, PPN, dan potongan PPh sendiri sesuai invoice</span></span>
      </label>

      <div className="tax-sub">
        <b>PPN</b>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="vat-mode">Perlakuan PPN</label>
            <select id="vat-mode" className="input" value={vatMode} disabled={off} onChange={(e) => setVatMode(e.target.value as VatMode)}>
              {VAT_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <small>{vatMode === "included" ? "Umum di struk ritel: DPP dihitung mundur dari harga." : vatMode === "excluded"
              ? `Harga = DPP; PPN ditambahkan (mis. 200.000 + ${pct(vatPct)} = ${rupiah(Math.round(200000 * (1 + vatPct / 100)))}). Baris PPN di invoice tidak dihitung sebagai barang.`
              : "Vendor bukan PKP atau tagihan tanpa PPN."}</small>
          </div>
          {vatMode !== "none" && (
            <div className="field">
              <label htmlFor="vat-rate">Tarif PPN</label>
              <div style={{ display: "flex", gap: 8 }}>
                <select id="vat-rate" className="input" disabled={off} value={VAT_RATES.includes(vatRate) ? vatRate : "other"}
                        onChange={(e) => setVatRate(e.target.value === "other" ? "" : e.target.value)}>
                  {VAT_RATES.map((r) => <option key={r} value={r}>{r}%</option>)}
                  <option value="other">Lainnya</option>
                </select>
                {!VAT_RATES.includes(vatRate) && (
                  <input className="input num" type="number" min="0.01" max="100" step="0.01" placeholder="%" aria-label="Tarif PPN lainnya"
                         style={{ width: 90 }} disabled={off} value={vatRate} onChange={(e) => setVatRate(e.target.value)} />
                )}
              </div>
              {calc ? (
                <small>{vatMode === "excluded" ? "PPN ditambahkan" : "PPN pada tagihan ini"}: <b className="num">{rupiah(vat.amount)}</b></small>
              ) : (
                <input className="input num" type="number" min="0" placeholder="Nilai PPN di invoice" aria-label="Nilai PPN (manual)"
                       style={{ marginTop: 6 }} disabled={off} value={vatAmount} onChange={(e) => setVatAmount(e.target.value)} />
              )}
            </div>
          )}
        </div>
        {calc && vat.warning && <small className="tax-warn">{vat.warning}</small>}
        {vatMode !== "none" && (
          <label className="toggle">
            <input type="checkbox" checked={vatShow} disabled={off} onChange={(e) => setVatShow(e.target.checked)} />
            <span>Tampilkan rincian PPN pada voucher <span className="muted">· bila tidak dicentang, PPN sudah termasuk dalam nilai tiap barang dan total</span></span>
          </label>
        )}
      </div>

      <div className="tax-sub">
        <b>Potongan PPh</b>
        <div className="seg" role="radiogroup" aria-label="Penerapan PPh">
          <button type="button" role="radio" aria-checked={mode === "invoice"} className={mode === "invoice" ? "active" : ""} disabled={off}
                  onClick={() => setMode("invoice")}>Satu jenis untuk seluruh invoice</button>
          <button type="button" role="radio" aria-checked={mode === "line"} className={mode === "line" ? "active" : ""} disabled={off || !lines.length || !calc}
                  title={!lines.length ? "Hanya untuk mode rincian barang/jasa" : !calc ? "Hanya saat pajak dihitung otomatis" : undefined}
                  onClick={() => setMode("line")}>Berbeda per baris</button>
        </div>
        {mode === "invoice" && distinctSuggestions.size > 1 && (
          <p className="tax-hint tax-switch">
            Saran sistem berbeda antarbaris (mis. barang dan jasa). Potongan PPh sebaiknya dipilih per baris.{" "}
            <button type="button" className="btn sm" disabled={off} onClick={() => setMode("line")}>Gunakan PPh per baris</button>
          </p>
        )}
        {mode === "invoice" && suggestion && (
          <p className="tax-hint">
            <span className="chip gray">{suggestion.source === "ai" ? "Saran AI" : "Saran sistem"}</span>{" "}
            <b>{suggestion.name}</b> · {suggestion.reason}. Keputusan tetap di Anda.
          </p>
        )}
        {suggestion?.vat && (
          <p className="tax-hint">
            <span className="chip gray">Saran PPN</span> Harga sudah termasuk PPN · {suggestion.vat.reason}.
          </p>
        )}
        {mode === "invoice" && file.data?.service_fee_unverified && (
          <Alert kind="warn">Invoice ini memisahkan imbalan jasa dari penggantian biaya. AI membaca imbalan jasa{" "}
            {rupiah(Number(file.data.service_fee_unverified))}, tetapi angka itu tidak cocok dengan PPN yang tercetak, jadi tidak
            dipakai. Isi DPP potongan PPh 23 manual dengan nilai imbalan jasa (mis. Management Fee) sesuai invoice.</Alert>
        )}
        {mode === "invoice" && (file.data?.service_fee || file.data?.vat_printed) && (
          <p className="tax-hint">
            Angka pajak yang tercetak di invoice (disalin AI, cocokkan dengan dokumen):
            {file.data?.service_fee && <> imbalan jasa <b>{rupiah(Number(file.data.service_fee))}</b></>}
            {file.data?.service_fee && file.data?.vat_printed && " ·"}
            {file.data?.vat_printed && <> PPN <b>{rupiah(Number(file.data.vat_printed))}</b></>}.
          </p>
        )}
        {mode === "invoice" && file.data?.service_fee && (
          <p className="tax-hint">
            DPP PPh 23 = <b>imbalan jasa vendor</b> (bagian tagihan yang dikenai PPN, mis. Management Fee), bukan total
            invoice. Penggantian biaya yang diteruskan (gaji/Basic Fee, BPJS, lembur driver) tidak dipotong PPh 23.
          </p>
        )}

        <div className="grid-2">
          {mode === "invoice" && (
            <div className="field">
              <label htmlFor="tax-code">Jenis pajak</label>
              <select id="tax-code" className="input" value={code} disabled={off} onChange={(e) => setCode(e.target.value)}>
                {list.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
              </select>
              {list.find((r) => r.code === code)?.description && <small>{list.find((r) => r.code === code)!.description}</small>}
            </div>
          )}
          <div className="field">
            <label htmlFor="tax-npwp">NPWP vendor</label>
            <select id="tax-npwp" className="input" value={npwp ? "1" : "0"} disabled={off || (mode === "invoice" && code === "NONE")}
                    onChange={(e) => setNpwp(e.target.value === "1")}>
              <option value="1">Punya NPWP</option>
              <option value="0">Tidak punya NPWP</option>
            </select>
            <small>{known == null ? "Vendor belum terdaftar di data referensi; pastikan NPWP-nya."
              : known ? "Sesuai data referensi vendor (ada NPWP)." : "Data referensi vendor: tanpa NPWP."}</small>
          </div>
        </div>

        {mode === "invoice" && code !== "NONE" && (
          <div className="grid-2">
            <div className="field">
              <label htmlFor="tax-base">Dasar pengenaan pajak (DPP)</label>
              <input id="tax-base" className="input num" type="number" disabled={off || (calc && !manual)}
                     value={manual || !calc ? base : autoBase ?? ""} onChange={(e) => setBase(e.target.value)} />
              {calc && (
                <label className="toggle" style={{ marginTop: 4 }}>
                  <input type="checkbox" checked={!manual} disabled={off}
                         onChange={(e) => { setManual(!e.target.checked); setBase(autoBase != null ? String(autoBase) : ""); }} />
                  <span>{itemIdx.length ? "Otomatis dari rincian (tanpa PPN)" : "Otomatis dari total (tanpa PPN)"}</span>
                </label>
              )}
            </div>
            <div className="field">
              <label htmlFor="tax-cut">Potongan</label>
              {calc ? (
                <div className="tax-calc num">
                  {pct(rateOf(code))} × {rupiah(invoiceBase)} = <b>{rupiah(invoiceCut)}</b>
                  {payable != null && <div className="muted">Dibayarkan untuk bukti ini: <b>{rupiah(payable - invoiceCut)}</b></div>}
                </div>
              ) : (
                <>
                  <input id="tax-cut" className="input num" type="number" min="0" disabled={off} value={cutAmount}
                         onChange={(e) => setCutAmount(e.target.value)} />
                  <small>Tarif acuan {pct(rateOf(code))}{payable != null && <> · dibayarkan untuk bukti ini: <b>{rupiah(payable - invoiceCut)}</b></>}</small>
                </>
              )}
              {list.find((r) => r.code === code)?.needs_confirmation && <small className="tax-warn">Tarif awal memakai aturan umum; perlu dikonfirmasi konsultan pajak.</small>}
            </div>
          </div>
        )}

        {mode === "line" && (
          <div className="tax-ai">
            <div>
              <b><Wand2 size={14} /> Saran sistem sudah diisikan</b>
              <small>Sistem menebak jenis PPh dari uraian tiap baris (tanpa AI). Butuh analisis lebih lanjut? Minta rekomendasi AI; hasilnya tetap perlu Anda periksa sebelum diterapkan.</small>
            </div>
            <div className="actions">
              <button type="button" className="btn sm" disabled={off} onClick={() => fillFromSuggestions(suggestions)}>Pakai saran sistem</button>
              <button type="button" className="btn sm primary" disabled={off || aiBusy} onClick={askAi}>
                <Sparkles /> {aiBusy ? "AI sedang menganalisis…" : "Minta rekomendasi AI untuk PPh per baris"}
              </button>
            </div>
            {aiError && <Alert kind="warn">{aiError}</Alert>}
          </div>
        )}
      </div>

      {lines.length > 0 && mode === "invoice" && (
        <button type="button" className="btn ghost sm" style={{ alignSelf: "flex-start" }} onClick={() => setShowLines(!showLines)}>
          {showLines ? "Sembunyikan pengaturan per baris" : `Atur PPN per baris (${lines.length} baris)`}
        </button>
      )}

      {lineTable && (
        <>
          {mode === "line" && (
            <div className="tax-bulk">
              <label className="toggle">
                <input type="checkbox" checked={allSelected} disabled={off}
                       onChange={() => setSelected(allSelected ? new Set() : new Set(itemIdx))} />
                <span>Pilih semua</span>
              </label>
              <span className="muted">{selected.size} baris dipilih</span>
              <select className="input" style={{ width: "auto" }} aria-label="Jenis PPh untuk baris terpilih" value={bulkCode}
                      disabled={off} onChange={(e) => setBulkCode(e.target.value)}>
                {pphList.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
              </select>
              <button type="button" className="btn sm" disabled={off || !selected.size} onClick={() => applyBulk(bulkCode)}>Terapkan ke baris terpilih</button>
              <button type="button" className="btn ghost sm" disabled={off || !selected.size} onClick={() => applyBulk("")}>Jadikan tanpa potongan</button>
            </div>
          )}
          <div style={{ overflowX: "auto" }}>
            <table className="table compact tax-lines">
              <thead>
                <tr>
                  {mode === "line" && <th aria-label="Pilih" />}
                  <th>#</th><th>Uraian</th><th className="right">DPP</th>
                  {vatMode !== "none" && <th title="Baris kena PPN">PPN</th>}
                  {mode === "line" && <th>PPh</th>}
                </tr>
              </thead>
              <tbody>
                {lines.map((l, i) => {
                  const r = rows[i];
                  if (!r) return null;
                  const s = suggestions[i];
                  const item = r.kind === "item";
                  return (
                    <tr key={i} className={!item ? "muted" : selected.has(i) ? "selected" : ""}>
                      {mode === "line" && (
                        <td>{item && <input type="checkbox" aria-label={`Pilih baris ${i + 1}`} checked={selected.has(i)}
                                            disabled={off} onChange={() => toggle(i)} />}</td>
                      )}
                      <td>{i + 1}</td>
                      <td>
                        <div className="tax-line-desc">{l.description || "-"}</div>
                        <div className="tax-line-meta">
                          {!item && <span className="chip gray">Baris PPN</span>}
                          {mode === "line" && item && s && (
                            <span className={`chip ${s.source === "ai" ? "" : "gray"}`} title={s.reason}>
                              Saran {s.source === "ai" ? "AI" : "sistem"}: {s.code === "NONE" ? "tanpa potongan" : codeName(s.code)}
                            </span>
                          )}
                          <button type="button" className="link-btn" disabled={off}
                                  onClick={() => {
                                    setRow(i, { kind: item ? "vat" : "item", pph: "" });
                                    if (item && vatMode === "none") setVatMode("excluded");  // baris PPN berarti PPN ditambahkan ke harga
                                  }}>
                            {item ? "Tandai sebagai baris PPN" : "Bukan baris PPN"}
                          </button>
                        </div>
                      </td>
                      <td className="right num nowrap">{item ? rupiah(dpp(i)) : rupiah(l.subtotal || null)}</td>
                      {vatMode !== "none" && (
                        <td>{item && <input type="checkbox" aria-label={`Baris ${i + 1} kena PPN`} title="Kena PPN" checked={r.vat}
                                            disabled={off} onChange={(e) => setRow(i, { vat: e.target.checked })} />}</td>
                      )}
                      {mode === "line" && (
                        <td>{item && (
                          <select className="input sm" aria-label={`PPh baris ${i + 1}`} value={r.pph} disabled={off}
                                  onChange={(e) => setRow(i, { pph: e.target.value })}>
                            <option value="">Tanpa potongan</option>
                            {pphList.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
                          </select>
                        )}</td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {mode === "line" && (
        <div className="tax-calc num">
          {groups.length === 0 ? <span className="muted">Belum ada baris yang dipotong PPh.</span> : groups.map((g) => (
            <div key={g.code}>{codeName(g.code)} {pct(g.rate)} × {rupiah(g.base)} ({g.lines.length} baris) = <b>{rupiah(g.amount)}</b></div>
          ))}
          {payable != null && <div className="muted">Total potongan <b>{rupiah(cut)}</b> · dibayarkan untuk bukti ini: <b>{rupiah(payable - cut)}</b></div>}
        </div>
      )}

      {(dirty || !current) && (
        <div className="actions" style={{ justifyContent: "flex-end" }}>
          {dirty && current && <button className="btn" disabled={busy} onClick={reset}><Undo2 /> Batalkan</button>}
          <button className="btn primary" disabled={off || (mode === "invoice" && (manual || !calc) && base === "" && code !== "NONE")
                    || (vatMode !== "none" && !(Number(vatRate) > 0)) || (!calc && code !== "NONE" && cutAmount === "")}
                  onClick={apply}>Terapkan pajak</button>
        </div>
      )}
    </div>
  );
}

/** Total tagihan, PPN, potongan pajak per invoice (per jenis bila per baris), dan nilai bersih yang dibayarkan. */
export function TaxSummaryBox({ summary, multi }: { summary: TaxSummary; multi: boolean }) {
  const vat = summary.vat ?? [];
  const warnings = vat.filter((v) => v.warning);
  return (
    <>
      {warnings.map((v, i) => <Alert key={i} kind="warn">{multi && v.invoice_no ? `${v.invoice_no}: ` : ""}{v.warning}</Alert>)}
      {!summary.lines.length ? (
        <p className="muted" style={{ margin: 0 }}>Tanpa potongan PPh. Voucher membayar <b className="num">{rupiah(summary.net)}</b>
          {vat.some((v) => v.mode !== "none") && <> (termasuk PPN)</>}.</p>
      ) : (
        <dl className="meta tax-summary">
          <dt>Jumlah tagihan</dt><dd className="num">{rupiah(summary.gross)}</dd>
          {vat.filter((v) => v.mode !== "none").map((v, i) => (
            <Fragment key={`v${i}`}>
              <dt className="muted">PPN {pct(v.rate)}{multi && v.invoice_no ? ` · ${v.invoice_no}` : ""}</dt>
              <dd className="num muted">{rupiah(v.amount)} <span>{v.mode === "excluded" ? "ditambahkan ke harga" : "termasuk dalam tagihan"}{v.show ? " · dirinci di voucher" : ""}</span></dd>
            </Fragment>
          ))}
          {summary.lines.map((t, i) => (
            <Fragment key={i}>
              <dt>Potongan {t.name} {pct(t.rate)}{t.npwp ? "" : " (tanpa NPWP)"}{multi && t.invoice_no ? ` · ${t.invoice_no}` : ""}</dt>
              <dd className="num">−{rupiah(t.amount)} <span className="muted">dari DPP {rupiah(t.base)}{t.detail ? ` · ${t.detail}` : ""}</span></dd>
            </Fragment>
          ))}
          <dt><b>Dibayarkan</b></dt><dd className="num"><b>{rupiah(summary.net)}</b></dd>
        </dl>
      )}
    </>
  );
}
