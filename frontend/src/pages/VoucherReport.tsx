import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarRange, Download, FileText, Wallet } from "lucide-react";
import { api } from "../api";
import { Alert, Loading, StatusBadge, useApi } from "../components/ui";
import { rupiah, tanggal, waktu } from "../format";
import type { VoucherRow } from "../types";

type Period = "1" | "7" | "30" | "custom";
const PERIODS: { value: Period; label: string }[] = [
  { value: "1", label: "Hari ini" }, { value: "7", label: "7 hari" }, { value: "30", label: "30 hari" },
  { value: "custom", label: "Kustom" },
];

/** Tanggal hari ini di WIB (rekap mengikuti tanggal voucher terbit, WIB). */
function todayWib(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(new Date());
}

function shift(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Service Lead: rekap voucher yang terbit dalam 1, 7, 30 hari, atau periode kustom, dan unduh sebagai PDF. */
export function VoucherReport() {
  const today = todayWib();
  const [period, setPeriod] = useState<Period>("7");
  const [from, setFrom] = useState(shift(today, -6));
  const [to, setTo] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const range = period === "custom" ? { from, to } : { from: shift(today, -(Number(period) - 1)), to: today };
  const customInvalid = period === "custom" && (!from || !to || from > to);
  const rows = useApi(
    () => (customInvalid ? Promise.resolve([] as VoucherRow[])
      : api.get<VoucherRow[]>("/vouchers", { date_from: range.from, date_to: range.to })),
    [range.from, range.to, customInvalid],
  );

  const summary = useMemo(() => {
    const list = rows.data ?? [];
    const byClient = new Map<string, { count: number; total: number; pics: string[] }>();
    for (const r of list) {
      const g = byClient.get(r.client.name) ?? { count: 0, total: 0, pics: [] };
      g.count += 1;
      g.total += Number(r.total) || 0;
      if (r.pic_name && !g.pics.includes(r.pic_name)) g.pics.push(r.pic_name);
      byClient.set(r.client.name, g);
    }
    return {
      count: list.length,
      total: list.reduce((s, r) => s + (Number(r.total) || 0), 0),
      sent: list.filter((r) => r.status === "SENT_TO_CLIENT").length,
      clients: [...byClient.entries()].sort((a, b) => b[1].total - a[1].total),
    };
  }, [rows.data]);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ period, ...(period === "custom" ? { date_from: from, date_to: to } : {}) });
      const blob = await api.blob(`/vouchers/report?${qs}`);
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), {
        href: url, download: `rekap-voucher_${range.from.replaceAll("-", "")}-${range.to.replaceAll("-", "")}.pdf`,
      });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Rekap voucher</h1>
          <p>Voucher yang terbit dari semua perusahaan dalam periode tertentu (tanggal WIB). Unduh rekapnya sebagai PDF.</p>
        </div>
        <button className="btn primary" onClick={download} disabled={busy || customInvalid}>
          <Download /> {busy ? "Menyiapkan PDF…" : "Unduh rekap PDF"}
        </button>
      </div>

      <section className="card panel">
        <div className="report-filter">
          <div className="seg" role="group" aria-label="Periode">
            {PERIODS.map((p) => (
              <button key={p.value} aria-pressed={period === p.value} onClick={() => setPeriod(p.value)}>{p.label}</button>
            ))}
          </div>
          {period === "custom" ? (
            <div className="report-dates">
              <label htmlFor="r-from">Dari</label>
              <input id="r-from" className="input" type="date" value={from} max={to || today} onChange={(e) => setFrom(e.target.value)} />
              <label htmlFor="r-to">sampai</label>
              <input id="r-to" className="input" type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} />
            </div>
          ) : (
            <span className="muted"><CalendarRange size={14} style={{ verticalAlign: -2 }} />{" "}
              {range.from === range.to ? tanggal(range.to) : `${tanggal(range.from)} – ${tanggal(range.to)}`}</span>
          )}
        </div>
        {customInvalid && <Alert kind="warn">Pilih tanggal mulai dan tanggal akhir; tanggal mulai tidak boleh setelah tanggal akhir.</Alert>}
      </section>

      {(error || rows.error) && <Alert>{error ?? rows.error}</Alert>}

      <div className="report-stats">
        <div className="card stat"><div className="stat-top">Jumlah voucher <span className="stat-ic navy"><FileText /></span></div><b className="stat-value">{summary.count}</b></div>
        <div className="card stat"><div className="stat-top">Total nilai <span className="stat-ic navy"><Wallet /></span></div><b className="stat-value">{rupiah(summary.total)}</b></div>
        <div className="card stat"><div className="stat-top">Terkirim ke klien</div><b className="stat-value">{summary.sent}</b></div>
        <div className="card stat"><div className="stat-top">Belum diunduh klien</div><b className="stat-value">{summary.count - summary.sent}</b></div>
      </div>

      <section className="card panel">
        <div className="section-title">Rekap per perusahaan</div>
        {rows.loading && !rows.data ? <Loading /> : !summary.count ? (
          <p className="muted" style={{ margin: 0 }}>Tidak ada voucher yang terbit pada periode ini.</p>
        ) : (
          <div className="table-wrap">
            <table className="table compact">
              <thead><tr><th>Perusahaan</th><th className="right">Jumlah voucher</th><th className="right">Total nilai</th></tr></thead>
              <tbody>
                {summary.clients.map(([name, g]) => (
                  <tr key={name}><td>{name}{g.pics.length > 0 && <div className="muted" style={{ fontSize: 12 }}>PIC: {g.pics.join(", ")}</div>}</td><td className="right">{g.count}</td><td className="right mono">{rupiah(g.total)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {summary.count > 0 && (
        <section className="card panel">
          <div className="section-title">Daftar voucher ({summary.count})</div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>No. Voucher</th><th>Terbit</th><th>Perusahaan</th><th>Vendor</th><th className="right">Total</th><th>Disetujui oleh</th><th>Status</th></tr></thead>
              <tbody>
                {(rows.data ?? []).map((r) => (
                  <tr key={r.document_id}>
                    <td className="mono"><Link to={`/dokumen/${r.document_id}`}>{r.voucher_no}</Link></td>
                    <td>{waktu(r.generated_at)}</td>
                    <td>{r.client.name}{r.pic_name && <div className="muted" style={{ fontSize: 12 }}>PIC: {r.pic_name}</div>}</td>
                    <td>{r.vendor_name ?? "-"}</td>
                    <td className="right mono">{rupiah(r.total)}</td>
                    <td>{r.approved_by}</td>
                    <td><StatusBadge status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
