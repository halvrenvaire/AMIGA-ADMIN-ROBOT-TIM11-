import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Alert, Loading, PdfFrame, StatusBadge, useApi } from "../components/ui";
import { rupiah, waktu } from "../format";
import type { DocumentDetail } from "../types";

/** Layar 04 — Pratinjau Voucher. Unduhan oleh PIC Klien → SENT_TO_CLIENT (FR-5.3). */
export function VoucherPage() {
  const { id = "" } = useParams();
  const { has } = useAuth();
  const doc = useApi(() => api.get<DocumentDetail>(`/documents/${id}`), [id]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const d = doc.data;

  if (doc.error) return <Alert>{doc.error}</Alert>;
  if (!d) return <Loading />;
  if (!d.voucher) return <Alert kind="info">Voucher belum tersedia. Voucher dibuat setelah Finance Reviewer menyetujui dokumen.</Alert>;

  const clientSide = has("PIC_KLIEN", "INTAKE_SUPPORT");

  async function download() {
    setError(null);
    try {
      const blob = await api.blob(`/documents/${id}/voucher?download=true`);
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: `${d!.voucher!.voucher_no.replaceAll("/", "-")}.pdf` });
      a.click();
      URL.revokeObjectURL(url);
      const before = d!.status;
      const next = await api.get<DocumentDetail>(`/documents/${id}`);
      doc.setData(next);
      setNotice(before !== next.status && next.status === "SENT_TO_CLIENT"
        ? "Voucher diunduh. Status menjadi SENT_TO_CLIENT. Teruskan voucher ke Client Approver sesuai prosedur klien."
        : "Voucher diunduh.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            Voucher <span className="mono" style={{ fontSize: 18 }}>{d.voucher.voucher_no}</span> <StatusBadge status={d.status} />
          </h1>
          <p>{d.request_id} · {d.client.name} · {d.vendor_name} · {rupiah(d.total)} · dibuat {waktu(d.voucher.generated_at)}</p>
        </div>
        <div className="actions">
          <Link className="btn" to={`/dokumen/${id}`}><ArrowLeft /> Dokumen</Link>
          <button className="btn primary" onClick={download}><Download /> Unduh voucher PDF</button>
        </div>
      </div>
      {notice && <Alert kind="ok">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      <Alert kind="warn">
        Periksa nomor voucher, vendor, rekening tujuan, dan total, serta pastikan teks <b>Batas Otorisasi</b> tercantum. Voucher
        bukan persetujuan pembayaran; keputusan bayar ada di Client Approver.
        {clientSide && d.status === "AMIGA_REVIEWED" && " Mengunduh voucher menandai dokumen sudah diserahkan ke klien."}
      </Alert>
      <section className="card pdf-pane" style={{ position: "static", height: "78vh" }}>
        <PdfFrame path={`/documents/${id}/voucher`} title={`Voucher ${d.voucher.voucher_no}`} />
      </section>
    </>
  );
}
