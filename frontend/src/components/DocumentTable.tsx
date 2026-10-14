import { Link } from "react-router-dom";
import { daysUntil, rupiah, tanggal } from "../format";
import type { DocumentSummary } from "../types";
import { StatusBadge } from "./ui";

function Due({ due, done }: { due: string | null; done: boolean }) {
  const days = daysUntil(due);
  if (days === null) return <span className="muted">-</span>;
  const note = done ? null : days < 0 ? <span className="chip bad">lewat {-days} hr</span>
    : days <= 2 ? <span className="chip warn">{days === 0 ? "hari ini" : `${days} hr lagi`}</span> : null;
  return <span className="num" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>{tanggal(due)} {note}</span>;
}

export function DocumentTable({ docs, showReviewer = true, action }: {
  docs: DocumentSummary[];
  showReviewer?: boolean;
  action?: (doc: DocumentSummary) => React.ReactNode;
}) {
  if (!docs.length) return <div className="empty">Belum ada dokumen yang cocok.</div>;
  return (
    <div className="table-wrap">
      <table className="table docs">
        <thead>
          <tr>
            <th>Request ID</th><th>Klien</th><th>Vendor</th><th className="right">Total</th>
            <th>Status</th><th>Tenggat</th>{showReviewer && <th>Reviewer</th>}<th className="right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td><Link to={`/dokumen/${d.id}`} className="mono">{d.request_id}</Link></td>
              <td>{d.client.name}</td>
              <td className="vendor">{d.vendor_name ?? <span className="muted">-</span>}</td>
              <td className="right num">{rupiah(d.total)}</td>
              <td><StatusBadge status={d.status} /></td>
              <td><Due due={d.due_date} done={d.status === "AMIGA_REVIEWED" || d.status === "SENT_TO_CLIENT"} /></td>
              {showReviewer && <td>{d.assigned_reviewer ?? <span className="muted">-</span>}</td>}
              <td className="right">{action ? action(d) : <Link className="btn sm" to={`/dokumen/${d.id}`}>Buka</Link>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
