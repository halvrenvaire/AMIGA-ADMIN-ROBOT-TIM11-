import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Upload as UploadIcon } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { DocumentTable } from "../components/DocumentTable";
import { Alert, Loading, useApi } from "../components/ui";
import { STATUS_LABEL, STATUS_ORDER } from "../format";
import type { DocStatus, DocumentSummary } from "../types";

function useDocs(params: Record<string, string | boolean | undefined>, deps: unknown[]) {
  return useApi(() => api.get<DocumentSummary[]>("/documents", params), deps);
}

function ListCard({ title, note, state, children, showReviewer, action }: {
  title: string; note: string; state: ReturnType<typeof useDocs>; children?: React.ReactNode;
  showReviewer?: boolean; action?: (d: DocumentSummary) => React.ReactNode;
}) {
  return (
    <section className="card panel">
      <div className="panel-head"><div><h2>{title}</h2><p>{note}</p></div></div>
      {children}
      {state.error && <Alert>{state.error}</Alert>}
      {state.loading && !state.data ? <Loading /> : <DocumentTable docs={state.data ?? []} showReviewer={showReviewer} action={action} />}
    </section>
  );
}

/** Pengajuan Saya — status, kode & alasan EXCEPTION (Layar 02, PIC Klien / Intake Support). */
export function Submissions() {
  const [params] = useSearchParams();
  const [status, setStatus] = useState<DocStatus | "">((params.get("status") as DocStatus | null) ?? "");
  const docs = useDocs({ status }, [status]);
  const all = useDocs({}, []);
  const exceptions = all.data?.filter((d) => d.status === "EXCEPTION").length ?? 0;
  return (
    <>
      <div className="page-head">
        <div><h1>Pengajuan saya</h1><p>Semua invoice klien Anda beserta statusnya.</p></div>
        <Link className="btn primary" to="/unggah"><UploadIcon /> Unggah invoice</Link>
      </div>
      {exceptions > 0 && (
        <Alert kind="warn">
          <span>{exceptions} dokumen <b>ada kendala</b> dan menunggu perbaikan Anda.{" "}
            <button className="btn sm" onClick={() => setStatus("EXCEPTION")}>Tampilkan</button></span>
        </Alert>
      )}
      <ListCard title="Daftar pengajuan" note="Terbaru di atas" state={docs} showReviewer={false}>
        <div className="filters">
          <button className={`btn sm ${status === "" ? "primary" : ""}`} onClick={() => setStatus("")}>Semua</button>
          {STATUS_ORDER.map((s) => (
            <button key={s} className={`btn sm ${status === s ? "primary" : ""}`} onClick={() => setStatus(s)}>{STATUS_LABEL[s]}</button>
          ))}
        </div>
      </ListCard>
    </>
  );
}

/** Peninjauan Saya — dokumen READY_FOR_REVIEW yang ditugaskan ke reviewer ini. */
export function MyReviews() {
  const { user } = useAuth();
  const docs = useDocs({ status: "READY_FOR_REVIEW", reviewer_id: user?.id, sort: "tenggat" }, [user?.id]);
  return (
    <>
      <div className="page-head">
        <div><h1>Peninjauan saya</h1><p>Dahulukan dokumen dengan tenggat terdekat (SOP 7.4).</p></div>
      </div>
      <ListCard title="Siap ditinjau" note="Ditugaskan kepada Anda" state={docs} showReviewer={false}
                action={(d) => <Link className="btn sm primary" to={`/dokumen/${d.id}`}>Tinjau</Link>} />
    </>
  );
}

/** Riwayat & Audit (Layar 05): pilih dokumen untuk melihat jejak auditnya. */
export function Histories() {
  const docs = useDocs({}, []);
  return (
    <>
      <div className="page-head">
        <div><h1>Riwayat & jejak audit</h1><p>Setiap aksi, perubahan nilai, pengembalian, penolakan SoD, dan pengalihan tercatat permanen.</p></div>
      </div>
      <ListCard title="Dokumen" note="Pilih dokumen untuk melihat kronologinya" state={docs}
                action={(d) => <Link className="btn sm" to={`/dokumen/${d.id}/riwayat`}>Riwayat</Link>} />
    </>
  );
}

/** Hasil pencarian dari kolom cari di top bar. */
export function SearchResults() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const docs = useDocs({ q }, [q]);
  return (
    <ListCard title={`Hasil pencarian "${q}"`} note="Request ID atau nama vendor, hanya klien yang ditugaskan" state={docs} />
  );
}
