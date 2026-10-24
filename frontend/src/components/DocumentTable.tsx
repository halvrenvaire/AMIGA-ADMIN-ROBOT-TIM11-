import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { daysUntil, rupiah, tanggal, waktu } from "../format";
import type { DocumentSummary } from "../types";
import { StatusBadge } from "./ui";

function Due({ due, done }: { due: string | null; done: boolean }) {
  const days = daysUntil(due);
  if (days === null) return <span className="muted">-</span>;
  const note = done ? null : days < 0 ? <span className="chip bad">lewat {-days} hr</span>
    : days <= 2 ? <span className="chip warn">{days === 0 ? "hari ini" : `${days} hr lagi`}</span> : null;
  return <span className="num" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>{tanggal(due)} {note}</span>;
}

type SortKey = "request_id" | "client" | "vendor_name" | "total" | "status" | "due_date" | "updated_at" | "assigned_reviewer";

export function DocumentTable({ docs, showReviewer = true, action }: {
  docs: DocumentSummary[];
  showReviewer?: boolean;
  action?: (doc: DocumentSummary) => React.ReactNode;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("updated_at");
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(k);
      setSortAsc(k === "client" || k === "vendor_name" || k === "request_id" || k === "status");
    }
  }

  const sortedDocs = useMemo(() => {
    return [...docs].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "request_id":
          cmp = (a.request_id || "").localeCompare(b.request_id || "");
          break;
        case "client":
          cmp = (a.client?.name || "").localeCompare(b.client?.name || "");
          break;
        case "vendor_name":
          cmp = (a.vendor_name || "").localeCompare(b.vendor_name || "");
          break;
        case "total":
          cmp = (Number(a.total) || 0) - (Number(b.total) || 0);
          break;
        case "status":
          cmp = (a.status || "").localeCompare(b.status || "");
          break;
        case "due_date":
          cmp = (a.due_date || "").localeCompare(b.due_date || "");
          break;
        case "updated_at":
          cmp = new Date(a.updated_at || 0).getTime() - new Date(b.updated_at || 0).getTime();
          break;
        case "assigned_reviewer":
          cmp = (a.assigned_reviewer || "").localeCompare(b.assigned_reviewer || "");
          break;
      }
      return sortAsc ? cmp : -cmp;
    });
  }, [docs, sortKey, sortAsc]);

  if (!docs.length) return <div className="empty">Belum ada dokumen yang cocok.</div>;

  const header = (k: SortKey, label: string, right = false) => {
    const active = sortKey === k;
    return (
      <th
        className={right ? "right" : undefined}
        style={{ cursor: "pointer", userSelect: "none" }}
        onClick={() => toggleSort(k)}
        title={`Urutkan berdasarkan ${label}`}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, justifyContent: right ? "flex-end" : "flex-start" }}>
          {label}
          {active ? (
            sortAsc ? <ArrowUp size={13} style={{ opacity: 0.9 }} /> : <ArrowDown size={13} style={{ opacity: 0.9 }} />
          ) : (
            <ArrowUpDown size={12} style={{ opacity: 0.35 }} />
          )}
        </span>
      </th>
    );
  };

  return (
    <div className="table-wrap">
      <table className="table docs">
        <thead>
          <tr>
            {header("request_id", "Request ID")}
            {header("client", "Klien")}
            {header("vendor_name", "Vendor")}
            {header("total", "Total", true)}
            {header("status", "Status")}
            {header("due_date", "Tenggat")}
            {header("updated_at", "Terakhir Diubah")}
            {showReviewer && header("assigned_reviewer", "Reviewer")}
            <th className="right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {sortedDocs.map((d) => (
            <tr key={d.id}>
              <td><Link to={`/dokumen/${d.id}`} className="mono">{d.request_id}</Link></td>
              <td className="wrap">{d.client.name}</td>
              <td className="vendor">{d.vendor_name ?? <span className="muted">-</span>}</td>
              <td className="right num">{rupiah(d.total)}</td>
              <td><StatusBadge status={d.status} /></td>
              <td><Due due={d.due_date} done={d.status === "AMIGA_REVIEWED" || d.status === "SENT_TO_CLIENT"} /></td>
              <td>
                <span className="num" style={{ whiteSpace: "nowrap" }} title={waktu(d.updated_at)}>
                  {tanggal(d.updated_at)}
                </span>
              </td>
              {showReviewer && <td className="wrap">{d.assigned_reviewer ?? <span className="muted">-</span>}</td>}
              <td className="right">{action ? action(d) : <Link className="btn sm" to={`/dokumen/${d.id}`}>Buka</Link>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
