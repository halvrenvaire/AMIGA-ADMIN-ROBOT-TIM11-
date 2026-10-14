import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentSummary, ReviewerLoad } from "../types";
import { Alert, Loading, Modal } from "./ui";

/** Service Lead mengalihkan dokumen ke reviewer lain (FR-6.3). Status dokumen tidak berubah.
 *  Pilihan hanya reviewer yang sah dari server: klien dokumen, bukan pengunggah, bukan reviewer saat ini. */
export function ReassignModal({ doc, onClose, onDone }: {
  doc: DocumentSummary; onClose: () => void; onDone: () => void;
}) {
  const [options, setOptions] = useState<ReviewerLoad[] | null>(null);
  const [reviewerId, setReviewerId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<ReviewerLoad[]>(`/documents/${doc.id}/reviewer-options`)
      .then((list) => { setOptions(list); setReviewerId(list[0]?.id ?? ""); })
      .catch((e: Error) => { setOptions([]); setError(e.message); });
  }, [doc.id]);

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
      {options === null ? <Loading label="Memuat reviewer…" /> : options.length === 0 ? (
        <Alert kind="warn">Tidak ada reviewer lain yang bisa ditugaskan untuk klien dokumen ini.</Alert>
      ) : (
        <div className="field">
          <label htmlFor="rv">Reviewer baru</label>
          <select id="rv" className="input" value={reviewerId} onChange={(e) => setReviewerId(e.target.value)}>
            {options.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.pending} dokumen)</option>)}
          </select>
        </div>
      )}
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
