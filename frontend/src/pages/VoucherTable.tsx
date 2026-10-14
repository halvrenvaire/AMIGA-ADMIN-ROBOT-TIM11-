import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Receipt } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, StatusBadge, useApi } from "../components/ui";
import { STATUS_LABEL, rupiah, tanggal, waktu } from "../format";
import type { Vendor, VoucherRow } from "../types";

type GroupBy = "none" | "client" | "vendor" | "status";
const GROUP_LABEL: Record<GroupBy, string> = { none: "Tanpa pengelompokan", client: "Perusahaan", vendor: "Vendor", status: "Status" };

const groupKey = (r: VoucherRow, by: GroupBy) =>
  by === "client" ? r.client.name : by === "vendor" ? r.vendor_name ?? "(vendor tidak terbaca)" : by === "status" ? STATUS_LABEL[r.status] : "";
const sum = (rows: VoucherRow[]) => rows.reduce((s, r) => s + Number(r.total ?? 0), 0);

/** Manajemen voucher pembayaran: filter dan kelompokkan per perusahaan, vendor, status. */
export function VoucherTable() {
  const { user, has } = useAuth();
  const [clientId, setClientId] = useState("");
  const [vendorId, setVendorId] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [groupBy, setGroupBy] = useState<GroupBy>("client");
  const canOpenPdf = has("PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER");

  const vendors = useApi(() => api.get<Vendor[]>("/vendors", { client_id: clientId, include_inactive: true }), [clientId]);
  const rows = useApi(() => api.get<VoucherRow[]>("/vouchers", {
    client_id: clientId, vendor_id: vendorId, status, date_from: from, date_to: to, q,
  }), [clientId, vendorId, status, from, to, q]);

  const groups = useMemo(() => {
    const data = rows.data ?? [];
    if (groupBy === "none") return [{ key: "", rows: data }];
    const map = new Map<string, VoucherRow[]>();
    data.forEach((r) => map.set(groupKey(r, groupBy), [...(map.get(groupKey(r, groupBy)) ?? []), r]));
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, rows]) => ({ key, rows }));
  }, [rows.data, groupBy]);

  function exportCsv() {
    const header = ["No Voucher", "Tanggal Voucher", "Request ID", "Perusahaan", "Vendor", "No Invoice", "Tgl Invoice", "Total", "Status", "Disetujui oleh"];
    const esc = (v: string | number | null) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = (rows.data ?? []).map((r) => [r.voucher_no, waktu(r.generated_at), r.request_id, r.client.name, r.vendor_name,
      r.invoice_no, r.invoice_date, r.total, STATUS_LABEL[r.status], r.approved_by].map(esc).join(","));
    const blob = new Blob(["﻿" + [header.map(esc).join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "voucher-amiga.csv" });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const total = sum(rows.data ?? []);
  const filtered = Boolean(clientId || vendorId || status || from || to || q);
  const colSpan = 8;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Voucher pembayaran</h1>
          <p>Semua voucher dari invoice yang terdaftar di sistem. Saring dan kelompokkan per perusahaan, vendor, atau status.</p>
        </div>
        <button className="btn" disabled={!rows.data?.length} onClick={exportCsv}><Download /> Unduh CSV</button>
      </div>

      <section className="card panel">
        <div className="filters">
          {(user?.clients.length ?? 0) > 1 && (
            <select className="input" value={clientId} onChange={(e) => { setClientId(e.target.value); setVendorId(""); }} aria-label="Perusahaan">
              <option value="">Semua perusahaan</option>
              {user?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <select className="input" value={vendorId} onChange={(e) => setVendorId(e.target.value)} aria-label="Vendor">
            <option value="">Semua vendor</option>
            {vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}{clientId ? "" : ` · ${v.client.name}`}</option>)}
          </select>
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">Semua status</option>
            <option value="AMIGA_REVIEWED">{STATUS_LABEL.AMIGA_REVIEWED} (belum diunduh klien)</option>
            <option value="SENT_TO_CLIENT">{STATUS_LABEL.SENT_TO_CLIENT} ke klien</option>
          </select>
          <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Dari tanggal" />
          <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Sampai tanggal" />
          <input className="input" placeholder="No voucher / Request ID / No invoice" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="toggle" style={{ marginLeft: "auto" }}>Kelompokkan
            <select className="input" style={{ minWidth: 0 }} value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)} aria-label="Kelompokkan">
              {(Object.keys(GROUP_LABEL) as GroupBy[]).map((g) => <option key={g} value={g}>{GROUP_LABEL[g]}</option>)}
            </select>
          </label>
          {filtered && <button className="btn ghost sm" onClick={() => { setClientId(""); setVendorId(""); setStatus(""); setFrom(""); setTo(""); setQ(""); }}>Hapus filter</button>}
        </div>

        {rows.error && <Alert>{rows.error}</Alert>}
        {rows.loading && !rows.data ? <Loading /> : !rows.data?.length ? (
          <div className="empty"><Receipt size={22} /><br />Belum ada voucher{filtered ? " yang cocok dengan filter" : ""}.</div>
        ) : (
          <div className="table-wrap">
            <table className="table docs">
              <thead>
                <tr>
                  <th>No voucher</th><th>Tanggal</th><th>Perusahaan</th><th>Vendor</th><th>No invoice</th>
                  <th className="right">Total</th><th>Status</th><th className="right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <Fragment key={g.key || "all"}>
                    {groupBy !== "none" && (
                      <tr className="group-row">
                        <td colSpan={5}><b>{g.key}</b> <span className="muted">· {g.rows.length} voucher</span></td>
                        <td className="right num"><b>{rupiah(sum(g.rows))}</b></td><td colSpan={2} />
                      </tr>
                    )}
                    {g.rows.map((r) => (
                      <tr key={r.document_id}>
                        <td><span className="mono">{r.voucher_no}</span><div className="muted mono" style={{ fontSize: 11.5 }}>{r.request_id}</div></td>
                        <td>{tanggal(r.generated_at)}</td>
                        <td className="wrap">{r.client.name}</td>
                        <td className="vendor">{r.vendor_name ?? <span className="muted">-</span>}</td>
                        <td>{r.invoice_no ?? "-"}</td>
                        <td className="right num">{rupiah(r.total)}</td>
                        <td><StatusBadge status={r.status} /></td>
                        <td className="right">
                          <Link className="btn sm" to={canOpenPdf ? `/dokumen/${r.document_id}/voucher` : `/dokumen/${r.document_id}`}>
                            {canOpenPdf ? "Pratinjau" : "Detail"}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
                <tr className="total-row">
                  <td colSpan={5}><b>Total {rows.data.length} voucher</b></td>
                  <td className="right num"><b>{rupiah(total)}</b></td><td colSpan={colSpan - 6} />
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
