import { useState } from "react";
import { Cpu } from "lucide-react";
import { api } from "../api";
import { rupiah } from "../format";
import { Alert, Loading, useApi } from "./ui";

interface ModeUsage {
  documents: number; invoices: number; input_tokens: number; output_tokens: number;
  cost_usd: number; cost_idr: number; per_invoice_idr: number | null;
}
interface AiUsage {
  period_days: number; modes: { TOTAL_ONLY: ModeUsage; ITEMIZED: ModeUsage };
  total_usd: number; total_idr: number; price_input_per_1k_usd: number; price_output_per_1k_usd: number; usd_to_idr: number;
}

const MODE_LABEL = { TOTAL_ONLY: "Total saja", ITEMIZED: "Rincian barang/jasa" } as const;
const tokens = (n: number) => n.toLocaleString("id-ID");

/** Estimasi biaya AI pembaca invoice per mode baca (khusus System Admin dan Service Lead). Angka berupa perkiraan
 *  dari token yang tercatat per pengajuan dikali harga per 1.000 token di pengaturan server. */
export function AiCostCard({ initialDays = 30 }: { initialDays?: number }) {
  const [days, setDays] = useState(initialDays);
  const usage = useApi(() => api.get<AiUsage>("/dashboard/ai-usage", { days }), [days]);
  const u = usage.data;
  const saving = u && u.modes.TOTAL_ONLY.per_invoice_idr != null && u.modes.ITEMIZED.per_invoice_idr
    ? Math.round((1 - u.modes.TOTAL_ONLY.per_invoice_idr / u.modes.ITEMIZED.per_invoice_idr) * 100) : null;
  return (
    <section className="card panel ai-cost">
      <div className="panel-head">
        <div><h2><Cpu size={16} /> Estimasi biaya AI</h2><p>Per mode baca, pengajuan {days} hari terakhir. Hanya terlihat oleh Admin dan Service Lead.</p></div>
        <div className="seg" role="group" aria-label="Periode biaya AI">
          {[7, 30, 90].map((p) => <button key={p} aria-pressed={days === p} onClick={() => setDays(p)}>{p} hari</button>)}
        </div>
      </div>
      {usage.error && <Alert>{usage.error}</Alert>}
      {!u ? !usage.error && <Loading /> : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="table compact">
              <thead><tr><th>Mode</th><th className="right">Pengajuan</th><th className="right">Invoice</th><th className="right">Token (masuk / keluar)</th>
                <th className="right">Biaya</th><th className="right">Per invoice</th></tr></thead>
              <tbody>
                {(["TOTAL_ONLY", "ITEMIZED"] as const).map((m) => {
                  const r = u.modes[m];
                  return (
                    <tr key={m}>
                      <td>{MODE_LABEL[m]}</td>
                      <td className="right num">{r.documents}</td>
                      <td className="right num">{r.invoices}</td>
                      <td className="right num">{tokens(r.input_tokens)} / {tokens(r.output_tokens)}</td>
                      <td className="right num">{rupiah(r.cost_idr)} <small className="muted">${r.cost_usd.toFixed(4)}</small></td>
                      <td className="right num">{r.per_invoice_idr == null ? "–" : rupiah(r.per_invoice_idr)}</td>
                    </tr>
                  );
                })}
                <tr className="total-row">
                  <td colSpan={4}><b>Total</b></td>
                  <td className="right num"><b>{rupiah(u.total_idr)}</b> <small className="muted">${u.total_usd.toFixed(4)}</small></td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
          <small className="muted">
            {saving != null && saving > 0 && <>Mode total saja sekitar <b>{saving}% lebih hemat</b> per invoice. </>}
            Perkiraan: ${u.price_input_per_1k_usd} per 1.000 token masuk, ${u.price_output_per_1k_usd} per 1.000 token keluar,
            kurs Rp {u.usd_to_idr.toLocaleString("id-ID")}/USD. Pengajuan sebelum fitur ini tidak tercatat.
          </small>
        </>
      )}
    </section>
  );
}
