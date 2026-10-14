import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Signatory } from "../types";

const MAX_PENYETUJU = 3;

/** Pilih penanda tangan voucher: satu "Diajukan oleh" dan paling banyak tiga "Disetujui oleh".
 *  Bila `initial` tidak diberikan, penanda tangan default klien yang terpilih. */
export function SignerPicker({ clientId, initial, onChange }: {
  clientId: string; initial?: string[]; onChange: (ids: string[]) => void;
}) {
  const [list, setList] = useState<Signatory[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (!clientId) return;
    api.get<Signatory[]>("/signatories", { client_id: clientId }).then((items) => {
      setList(items);
      const start = initial ?? items.filter((s) => s.is_default).map((s) => s.id);
      setSelected(start);
      onChange(start);
    }).catch(() => setList([]));
  }, [clientId]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (next: string[]) => { setSelected(next); onChange(next); };
  if (!list) return <p className="muted" style={{ margin: 0 }}>Memuat penanda tangan…</p>;

  const pengaju = list.filter((s) => s.kind === "PENGAJU");
  const penyetuju = list.filter((s) => s.kind === "PENYETUJU");
  const chosenApprovers = selected.filter((id) => penyetuju.some((p) => p.id === id));

  return (
    <div className="signer-picker">
      <fieldset>
        <legend>Diajukan oleh</legend>
        {!pengaju.length && <small className="muted">Belum terdaftar. Kotak dicetak kosong.</small>}
        {pengaju.map((s) => (
          <label key={s.id} className="toggle">
            <input type="radio" name="pengaju" checked={selected.includes(s.id)}
                   onChange={() => update([...selected.filter((id) => !pengaju.some((p) => p.id === id)), s.id])} />
            {s.full_name} <span className="muted">· {s.position}</span>
          </label>
        ))}
        {pengaju.length > 0 && (
          <label className="toggle">
            <input type="radio" name="pengaju" checked={!pengaju.some((p) => selected.includes(p.id))}
                   onChange={() => update(selected.filter((id) => !pengaju.some((p) => p.id === id)))} />
            <span className="muted">Kosongkan (isi manual)</span>
          </label>
        )}
      </fieldset>
      <fieldset>
        <legend>Disetujui oleh <small className="muted">(maks. {MAX_PENYETUJU})</small></legend>
        {!penyetuju.length && <small className="muted">Belum terdaftar. Kotak opsional dicetak kosong.</small>}
        {penyetuju.map((s) => {
          const on = selected.includes(s.id);
          return (
            <label key={s.id} className="toggle">
              <input type="checkbox" checked={on} disabled={!on && chosenApprovers.length >= MAX_PENYETUJU}
                     onChange={() => update(on ? selected.filter((id) => id !== s.id) : [...selected, s.id])} />
              {s.full_name} <span className="muted">· {s.position}</span>
            </label>
          );
        })}
      </fieldset>
      <small className="muted" style={{ gridColumn: "1 / -1" }}>
        Daftar penanda tangan dikelola di <Link to="/referensi/penanda-tangan">Data Referensi → Penanda tangan</Link>.
      </small>
    </div>
  );
}
