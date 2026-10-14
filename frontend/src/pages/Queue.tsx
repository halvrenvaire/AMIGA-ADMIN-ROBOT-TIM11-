import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CalendarClock, ClipboardCheck, Clock } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { DocumentTable } from "../components/DocumentTable";
import { ReassignModal } from "../components/ReassignModal";
import { Alert, Loading, useApi } from "../components/ui";
import { STATUS_LABEL, STATUS_ORDER } from "../format";
import type { DashboardSummary, DocStatus, DocumentSummary } from "../types";

/** Layar 01 — Dashboard Antrean (Service Lead, Finance Reviewer). */
export function Queue() {
  const { user, has } = useAuth();
  const [status, setStatus] = useState<DocStatus | "">("");
  const [clientId, setClientId] = useState("");
  const [reviewerId, setReviewerId] = useState("");
  const [problem, setProblem] = useState(false);
  const [dueSoon, setDueSoon] = useState(false);
  const [q, setQ] = useState("");
  const [reassign, setReassign] = useState<DocumentSummary | null>(null);

  const summary = useApi(() => api.get<DashboardSummary>("/dashboard/summary"), []);
  const docs = useApi(
    () => api.get<DocumentSummary[]>("/documents", {
      status, client_id: clientId, reviewer_id: reviewerId, problem, q,
      due_within_days: dueSoon ? summary.data?.due_soon_days ?? 2 : undefined, sort: "tenggat",
    }),
    [status, clientId, reviewerId, problem, dueSoon, q],
  );
  const isLead = has("SERVICE_LEAD");
  const s = summary.data;
  const maxLoad = Math.max(1, ...(s?.reviewers.map((r) => r.pending) ?? [1]), (s?.overload_threshold ?? 0) + 1);
  const refresh = () => { summary.reload(); docs.reload(); };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Selamat datang, {user?.full_name.split(" ")[0]}</h1>
          <p>Pantau antrean invoice klien, tenggat, dan beban reviewer dalam satu tempat.</p>
        </div>
      </div>

      {summary.error && <Alert>{summary.error}</Alert>}
      {s && (
        <section className="stats" aria-label="Ringkasan antrean">
          <Stat icon={ClipboardCheck} tone="navy" label="Siap ditinjau" value={s.counts.READY_FOR_REVIEW}
                foot="menunggu keputusan reviewer" onClick={() => { setStatus("READY_FOR_REVIEW"); setProblem(false); }} />
          <Stat icon={AlertTriangle} tone="amber" label="Dokumen bermasalah" value={s.problem}
                foot="status EXCEPTION" onClick={() => { setProblem(true); setStatus(""); }} />
          <Stat icon={CalendarClock} tone="teal" label={`Tenggat ≤ ${s.due_soon_days} hari`} value={s.due_soon}
                foot="belum selesai" onClick={() => setDueSoon(true)} />
          <Stat icon={Clock} tone="red" label="Lewat tenggat" value={s.overdue} foot="perlu segera ditangani" />
        </section>
      )}

      <div className="row-2">
        <section className="card panel">
          <div className="panel-head">
            <div><h2>Antrean dokumen</h2><p>Diurutkan dari tenggat terdekat</p></div>
          </div>
          {s && (
            <div className="card status-strip" style={{ boxShadow: "none" }} role="group" aria-label="Saring status">
              {STATUS_ORDER.map((st) => (
                <button key={st} aria-pressed={status === st} onClick={() => setStatus(status === st ? "" : st)}>
                  <span className="muted" style={{ fontSize: 12 }}>{STATUS_LABEL[st]}</span>
                  <b>{s.counts[st]}</b>
                </button>
              ))}
            </div>
          )}
          <div className="filters">
            <select className="input" value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Klien">
              <option value="">Semua klien</option>
              {user?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="input" value={reviewerId} onChange={(e) => setReviewerId(e.target.value)} aria-label="Reviewer">
              <option value="">Semua reviewer</option>
              {s?.reviewers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            <input className="input" placeholder="Request ID / vendor" value={q} onChange={(e) => setQ(e.target.value)} />
            <label className="toggle"><input type="checkbox" checked={problem} onChange={(e) => setProblem(e.target.checked)} /> Bermasalah</label>
            <label className="toggle"><input type="checkbox" checked={dueSoon} onChange={(e) => setDueSoon(e.target.checked)} /> Tenggat dekat</label>
            {(status || clientId || reviewerId || problem || dueSoon || q) && (
              <button className="btn ghost sm" onClick={() => { setStatus(""); setClientId(""); setReviewerId(""); setProblem(false); setDueSoon(false); setQ(""); }}>
                Hapus filter
              </button>
            )}
          </div>
          {docs.error && <Alert>{docs.error}</Alert>}
          {docs.loading && !docs.data ? <Loading /> : (
            <DocumentTable docs={docs.data ?? []} action={isLead ? (d) => (
              <span className="actions" style={{ justifyContent: "flex-end" }}>
                {d.status === "READY_FOR_REVIEW" && <button className="btn sm" onClick={() => setReassign(d)}>Alihkan</button>}
                <Link className="btn sm" to={`/dokumen/${d.id}`}>Buka</Link>
              </span>
            ) : undefined} />
          )}
        </section>

        <section className="card panel" aria-labelledby="load-h">
          <div className="panel-head">
            <div><h2 id="load-h">Beban reviewer</h2><p>Dokumen siap ditinjau per reviewer</p></div>
          </div>
          {s && (
            <div className="load">
              {s.reviewers.map((r) => (
                <div key={r.id} className="load-row">
                  <span>{r.name} {r.overloaded && <span className="chip bad">berlebih</span>}</span>
                  <b className="num">{r.pending}</b>
                  <div className="load-bar"><i className={r.overloaded ? "over" : ""} style={{ width: `${(r.pending / maxLoad) * 100}%` }} /></div>
                </div>
              ))}
              <small className="muted">
                Ditandai berlebih bila lebih dari {s.overload_threshold} dokumen.
                {isLead ? " Gunakan tombol Alihkan di antrean untuk memeratakan beban." : ""}
              </small>
            </div>
          )}
        </section>
      </div>

      {reassign && s && (
        <ReassignModal doc={reassign} reviewers={s.reviewers} onClose={() => setReassign(null)}
                       onDone={() => { setReassign(null); refresh(); }} />
      )}
    </>
  );
}

function Stat({ icon: Icon, tone, label, value, foot, onClick }: {
  icon: typeof Clock; tone: string; label: string; value: number; foot: string; onClick?: () => void;
}) {
  return (
    <div className="card stat" onClick={onClick} style={onClick ? { cursor: "pointer" } : undefined}>
      <div className="stat-top">{label}<span className={`stat-ic ${tone}`}><Icon /></span></div>
      <div className="stat-val">{value}</div>
      <div className="stat-foot">{foot}</div>
    </div>
  );
}
