import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, UserRound, X } from "lucide-react";
import { api } from "../api";
import type { Signatory } from "../types";

export const MAX_PENYETUJU = 5;

/** Kotak tanda tangan voucher. "Diajukan oleh" = PIC Klien pengaju (tetap); "Disetujui oleh" = satu kotak
 *  per pemberi persetujuan, urutannya sama dengan di voucher. Tanpa `initial`, satu kotak berisi default. */
export function SignerPicker({ clientId, clientName, submitter, initial, onChange, showSubmitter = true }: {
  clientId: string; clientName: string; submitter: string; initial?: string[]; showSubmitter?: boolean;
  onChange: (ids: string[], chosen: Signatory[]) => void;
}) {
  const [list, setList] = useState<Signatory[] | null>(null);
  const [rows, setRows] = useState<string[]>([]);

  useEffect(() => {
    if (!clientId) return;
    api.get<Signatory[]>("/signatories", { client_id: clientId }).then((items) => {
      setList(items);
      const fallback = items.find((s) => s.is_default) ?? items[0];
      const start = initial ?? (fallback ? [fallback.id] : []);
      setRows(start);
      onChange(start, start.map((id) => items.find((s) => s.id === id)!));
    }).catch(() => setList([]));
  }, [clientId]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (next: string[]) => {
    setRows(next);
    onChange(next, next.map((id) => list!.find((s) => s.id === id)!));
  };
  if (!list) return <p className="muted" style={{ margin: 0 }}>Memuat penanda tangan…</p>;

  const unused = list.filter((s) => !rows.includes(s.id));
  const canAdd = rows.length < MAX_PENYETUJU && unused.length > 0;

  return (
    <div className={`signer-picker${showSubmitter ? "" : " single"}`}>
      {showSubmitter && <fieldset>
        <legend>Diajukan oleh</legend>
        <div className="company-box">
          <UserRound />
          <div><b>{submitter}</b><small className="muted">{clientName}</small></div>
        </div>
      </fieldset>}
      <fieldset>
        <legend>Disetujui oleh <small className="muted">({rows.length}/{MAX_PENYETUJU} kotak)</small></legend>
        {!list.length && (
          <small className="muted">Belum ada pemberi persetujuan terdaftar. Satu kotak opsional dicetak kosong.</small>
        )}
        {rows.map((id, i) => (
          <div key={i} className="approver-row">
            <span className="approver-no">{i + 1}</span>
            <select className="input" aria-label={`Kotak disetujui oleh ${i + 1}`} value={id}
                    onChange={(e) => update(rows.map((r, j) => (j === i ? e.target.value : r)))}>
              {list.filter((s) => s.id === id || !rows.includes(s.id)).map((s) => (
                <option key={s.id} value={s.id}>{s.full_name} · {s.position}</option>
              ))}
            </select>
            <button type="button" className="btn ghost sm" aria-label={`Hapus kotak ${i + 1}`}
                    onClick={() => update(rows.filter((_, j) => j !== i))}><X /></button>
          </div>
        ))}
        {list.length > 0 && (
          <button type="button" className="btn sm" disabled={!canAdd} onClick={() => update([...rows, unused[0].id])}
                  style={{ alignSelf: "flex-start" }}>
            <Plus /> Tambah kotak tanda tangan
          </button>
        )}
        {list.length > 0 && !rows.length && <small className="muted">Tanpa kotak terisi: satu kotak opsional dicetak kosong.</small>}
      </fieldset>
      <small className="muted" style={{ gridColumn: "1 / -1" }}>
        Daftar pemberi persetujuan dikelola di <Link to="/referensi/penanda-tangan">Data Referensi → Penanda tangan</Link>.
      </small>
    </div>
  );
}
