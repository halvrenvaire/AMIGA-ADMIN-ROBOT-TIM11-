import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, StatusBadge, useApi } from "../components/ui";
import { ISSUE_LABEL, STATUS_ORDER, rupiah } from "../format";
import type { DashboardMetrics, DocStatus } from "../types";

const PERIODS = [7, 30, 90];
// Warna seri grafik dari brand amiga: teal (masuk), teal tua (disetujui), merah muda (bermasalah)
const SERIES = [
  { key: "received", label: "Invoice masuk", color: "#4497A1" },
  { key: "approved", label: "Voucher terbit", color: "#1D5B63" },
  { key: "exception", label: "Bermasalah", color: "#E65C97" },
] as const;

const shortDate = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short" });
const compactRp = (v: number) =>
  v >= 1e9 ? `Rp ${(v / 1e9).toFixed(1).replace(".", ",")} M` : v >= 1e6 ? `Rp ${(v / 1e6).toFixed(1).replace(".", ",")} jt` : rupiah(v);
const pct = (num: number, den: number) => (den ? `${Math.round((num / den) * 100)}%` : "–");

function Delta({ now, prev, goodWhenUp = true }: { now: number; prev: number; goodWhenUp?: boolean }) {
  if (!prev && !now) return <span className="muted">tidak ada data periode lalu</span>;
  if (!prev) return <span className="chip ok">baru</span>;
  const change = Math.round(((now - prev) / prev) * 100);
  const Icon = change > 0 ? ArrowUpRight : change < 0 ? ArrowDownRight : Minus;
  const good = change === 0 ? null : (change > 0) === goodWhenUp;
  return (
    <span className={`chip ${good === null ? "gray" : good ? "ok" : "warn"}`} style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
      <Icon size={12} />{change > 0 ? "+" : ""}{change}%
    </span>
  );
}

/** Dashboard metrik utama (permintaan owner): status, tren, kecepatan, kualitas, nilai pembayaran. */
export function Metrics() {
  const { user, has } = useAuth();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [clientId, setClientId] = useState("");
  const m = useApi(() => api.get<DashboardMetrics>("/dashboard/metrics", { days, client_id: clientId }), [days, clientId]);
  const d = m.data;
  const internal = has("SERVICE_LEAD", "FINANCE_REVIEWER");
  const openStatus = (s: DocStatus) => navigate(internal ? `/antrean?status=${s}` : `/pengajuan?status=${s}`);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>Kinerja back office invoice-to-voucher{d ? `, ${shortDate.format(new Date(d.start))} – ${shortDate.format(new Date(d.end))}` : ""}.</p>
        </div>
        <div className="actions">
          {(user?.clients.length ?? 0) > 1 && (
            <select className="input" style={{ width: "auto" }} value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Klien">
              <option value="">Semua klien</option>
              {user?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <div className="seg" role="group" aria-label="Periode">
            {PERIODS.map((p) => (
              <button key={p} aria-pressed={days === p} onClick={() => setDays(p)}>{p} hari</button>
            ))}
          </div>
        </div>
      </div>

      {m.error && <Alert>{m.error}</Alert>}
      {!d ? <Loading /> : (
        <>
          <section className="kpi-status" aria-label="Dokumen per status">
            {STATUS_ORDER.map((s) => (
              <button key={s} className="card kpi-mini" onClick={() => openStatus(s)}>
                <StatusBadge status={s} />
                <b className="num">{d.status_counts[s]}</b>
              </button>
            ))}
          </section>

          <section className="stats">
            <div className="card stat">
              <div className="stat-top">Invoice masuk</div>
              <div className="stat-val">{d.received}</div>
              <div className="stat-foot"><Delta now={d.received} prev={d.received_prev} /> vs {days} hari sebelumnya</div>
            </div>
            <div className="card stat">
              <div className="stat-top">Voucher terbit</div>
              <div className="stat-val">{d.approved}</div>
              <div className="stat-foot"><Delta now={d.approved} prev={d.approved_prev} /> vs {days} hari sebelumnya</div>
            </div>
            <div className="card stat">
              <div className="stat-top">Nilai pembayaran</div>
              <div className="stat-val">{compactRp(Number(d.total_value))}</div>
              <div className="stat-foot"><Delta now={Number(d.total_value)} prev={Number(d.total_value_prev)} /> total voucher terbit</div>
            </div>
            <div className="card stat">
              <div className="stat-top">Lolos verifikasi pertama</div>
              <div className="stat-val">{pct(d.first_pass, d.first_pass_total)}</div>
              <div className="stat-foot">{d.first_pass} dari {d.first_pass_total} dokumen tanpa kendala</div>
            </div>
          </section>

          <section className="card panel">
            <div className="panel-head">
              <div><h2>Tren harian</h2><p>Invoice masuk, voucher terbit, dan dokumen yang pertama kali bermasalah per hari (WIB)</p></div>
            </div>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <LineChart data={d.trend} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="#ecf1f3" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(v) => shortDate.format(new Date(v))} tick={{ fontSize: 12, fill: "#84959b" }}
                         tickLine={false} axisLine={{ stroke: "#dfe6e9" }} minTickGap={24} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "#84959b" }} tickLine={false} axisLine={false} />
                  <Tooltip labelFormatter={(v) => shortDate.format(new Date(String(v)))}
                           contentStyle={{ borderRadius: 10, border: "1px solid #dfe6e9", fontSize: 13 }} />
                  <Legend iconType="plainline" wrapperStyle={{ fontSize: 13 }} />
                  {SERIES.map((s) => (
                    <Line key={s.key} type="linear" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2}
                          dot={days <= 7 ? { r: 2.5 } : false} activeDot={{ r: 5 }} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <div className="grid-3 metric-panels">
            <section className="card panel">
              <div className="panel-head"><div><h2>Kecepatan proses</h2><p>Dokumen yang vouchernya terbit dalam periode</p></div></div>
              <dl className="metric-list">
                <dt>Unggah → voucher terbit</dt>
                <dd>{d.avg_hours_to_voucher == null ? "–" : d.avg_hours_to_voucher < 1
                  ? `${Math.round(d.avg_hours_to_voucher * 60)} menit` : `${d.avg_hours_to_voucher.toFixed(1).replace(".", ",")} jam`}</dd>
                <dt>Waktu baca AI</dt>
                <dd>{d.avg_extraction_seconds == null ? "–" : `${d.avg_extraction_seconds.toFixed(1).replace(".", ",")} detik`}
                  <small className="muted"> target ≤ 15</small></dd>
                <dt>Selesai sebelum tenggat</dt>
                <dd>{pct(d.sla_on_time, d.sla_total)} <small className="muted">{d.sla_on_time}/{d.sla_total} bertenggat</small></dd>
              </dl>
            </section>

            <section className="card panel">
              <div className="panel-head"><div><h2>Kualitas & kendala</h2><p>Kendala yang ditemukan sistem dalam periode</p></div></div>
              <dl className="metric-list">
                <dt>Dikoreksi reviewer</dt>
                <dd>{pct(d.corrected_docs, d.reviewed_docs)} <small className="muted">{d.corrected_docs}/{d.reviewed_docs} voucher</small></dd>
              </dl>
              <BarList items={d.top_issues.map((i) => ({ label: ISSUE_LABEL[i.code], value: i.count, text: String(i.count) }))}
                       empty="Belum ada kendala dalam periode ini." color="#E65C97" />
            </section>

            <section className="card panel">
              <div className="panel-head"><div><h2>Nilai pembayaran</h2><p>Per klien dan 5 vendor terbesar</p></div></div>
              <BarList items={d.value_by_client.map((c) => ({ label: c.client, value: Number(c.value), text: compactRp(Number(c.value)) }))}
                       empty="Belum ada voucher terbit." color="#4497A1" />
              <div className="section-title" style={{ marginTop: 4 }}>Vendor terbesar</div>
              <BarList items={d.top_vendors.map((v) => ({ label: v.vendor, value: Number(v.value), text: compactRp(Number(v.value)) }))}
                       empty="–" color="#1D5B63" />
            </section>
          </div>
        </>
      )}
    </>
  );
}

function BarList({ items, empty, color }: { items: { label: string; value: number; text: string }[]; empty: string; color: string }) {
  if (!items.length) return <p className="muted" style={{ margin: 0 }}>{empty}</p>;
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <div className="load">
      {items.map((i) => (
        <div key={i.label} className="load-row">
          <span style={{ overflowWrap: "anywhere" }}>{i.label}</span>
          <b className="num">{i.text}</b>
          <div className="load-bar"><i style={{ width: `${(i.value / max) * 100}%`, background: color }} /></div>
        </div>
      ))}
    </div>
  );
}
