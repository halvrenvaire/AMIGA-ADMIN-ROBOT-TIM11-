import { useState } from "react";
import { api } from "../api";
import type { DocumentSummary, ReviewerLoad } from "../types";
import { Alert, Modal } from "./ui";

/** Service Lead mengalihkan dokumen ke reviewer lain (FR-6.3). Status dokumen tidak berubah. */
export function ReassignModal({ doc, reviewers, onClose, onDone }: {
  doc: DocumentSummary; reviewers: ReviewerLoad[]; onClose: () => void; onDone: () => void;
}) {
  const options = reviewers.filter((r) => r.name !== doc.assigned_reviewer);
  const [reviewerId, setReviewerId] = useState(options[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/documents/${doc.id}/reassign`, { reviewer_id: reviewerId, reason: reason || null });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Alihkan ${doc.request_id}`} onClose={onClose}>
      <p className="muted" style={{ margin: 0 }}>
        Reviewer saat ini: <b>{doc.assigned_reviewer ?? "belum ada"}</b>. Status dokumen tidak berubah, dan pengalihan
        tercatat di jejak audit.
      </p>
      {error && <Alert>{error}</Alert>}
      <div className="field">
        <label htmlFor="rv">Reviewer baru</label>
        <select id="rv" className="input" value={reviewerId} onChange={(e) => setReviewerId(e.target.value)}>
          {options.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.pending} dokumen)</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="reason">Alasan (opsional)</label>
        <input id="reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)}
               placeholder="mis. Dewi cuti hingga Jumat" />
      </div>
      <div className="actions" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Batal</button>
        <button className="btn primary" disabled={!reviewerId || busy} onClick={submit}>Alihkan</button>
      </div>
    </Modal>
  );
}
