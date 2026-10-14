import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "../api";
import { Alert, Loading, useApi } from "../components/ui";
import { FIELD_LABEL, STATUS_LABEL, waktu } from "../format";
import type { AuditItem, DocStatus, DocumentDetail } from "../types";

const ACTION: Record<string, [string, "" | "ok" | "warn" | "bad"]> = {
  DOCUMENT_UPLOADED: ["Invoice diunggah", ""],
  STATUS_CHANGED: ["Status berubah", ""],
  EXTRACTED: ["AI selesai membaca invoice", ""],
  FIXED_BY_PIC: ["Diperbaiki PIC", "warn"],
  PIC_NOTE: ["Catatan PIC", ""],
  REPROCESS_REQUESTED: ["Diminta proses ulang", "warn"],
  CORRECTED_BY_REVIEWER: ["Dikoreksi reviewer", "warn"],
  REVERIFIED: ["Verifikasi ulang menemukan kendala", "warn"],
  APPROVED: ["Disetujui Finance Reviewer", "ok"],
  VOUCHER_CREATED: ["Voucher dibuat", "ok"],
  VOUCHER_DOWNLOADED: ["Voucher diunduh", "ok"],
  RETURNED_TO_PIC: ["Dikembalikan ke PIC", "bad"],
  SOD_REJECTED: ["Persetujuan ditolak (Segregation of Duties)", "bad"],
  REVIEWER_REASSIGNED: ["Reviewer dialihkan", "warn"],
  DUPLICATE_DISMISSED: ["Ditandai bukan duplikat", "warn"],
};

const statusText = (s: string | null) => (s ? STATUS_LABEL[s as DocStatus] ?? s : "");

/** Layar 05 — Riwayat & Jejak Audit (lihat saja). */
export function HistoryPage() {
  const { id = "" } = useParams();
  const doc = useApi(() => api.get<DocumentDetail>(`/documents/${id}`).catch(() => null), [id]);
  const log = useApi(() => api.get<AuditItem[]>(`/documents/${id}/history`), [id]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Riwayat dokumen {doc.data && <span className="mono" style={{ fontSize: 18 }}>{doc.data.request_id}</span>}</h1>
          <p>Catatan permanen: tidak bisa diubah atau dihapus oleh siapa pun, termasuk System Admin.</p>
        </div>
        {doc.data && <Link className="btn" to={`/dokumen/${id}`}><ArrowLeft /> Dokumen</Link>}
      </div>
      {log.error && <Alert>{log.error}</Alert>}
      {log.loading && !log.data ? <Loading /> : (
        <section className="card panel">
          <ol className="timeline">
            {(log.data ?? []).map((a) => {
              const [label, tone] = ACTION[a.action] ?? [a.action, ""];
              const change = a.field !== null || a.old_value !== null || a.new_value !== null;
              return (
                <li key={a.id}>
                  <span className="tl-time">{waktu(a.created_at)}</span>
                  <span className={`tl-dot ${tone}`} />
                  <div className="tl-body">
                    <b>{label}</b>
                    {a.status_after && a.action === "STATUS_CHANGED" && <> → <span className={`badge ${a.status_after}`}>{statusText(a.status_after)}</span></>}
                    <div className="muted" style={{ fontSize: 12.5 }}>{a.actor_label}</div>
                    {change && (
                      <div className="tl-change">
                        {a.field && <span className="chip gray">{FIELD_LABEL[a.field] ?? a.field}</span>}
                        {a.old_value !== null && <del>{a.old_value}</del>}
                        {a.old_value !== null && a.new_value !== null && "→"}
                        {a.new_value !== null && <ins>{a.new_value}</ins>}
                      </div>
                    )}
                    {a.note && <div style={{ fontSize: 12.5, marginTop: 2 }}>{a.note}</div>}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </>
  );
}
