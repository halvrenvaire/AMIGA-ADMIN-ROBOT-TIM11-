"""Asisten: pertanyaan bahasa sehari-hari menjadi query data (text-to-query).

Model AI TIDAK menulis SQL. Model hanya memilih satu jenis query dari katalog tetap dan mengisi
filternya (JSON). Server yang menjalankan query, selalu dibatasi ke klien yang boleh dibuka
pengguna, sehingga isolasi klien dan hak akses tetap dijaga di kode, bukan di prompt.
"""
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models import (
    AuditLog, Client, DocStatus, Document, DocumentFile, Extraction, Role, User, UserClientAssignment, UserRole,
    ValidationIssue, Voucher,
)

DONE = (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT, DocStatus.CANCELLED)
MAX_ROWS = 20
MAX_DETAIL = 5

STATUS_LABEL = {
    DocStatus.QUEUED: "Antre", DocStatus.PROCESSING: "Diproses AI", DocStatus.READY_FOR_REVIEW: "Siap ditinjau",
    DocStatus.EXCEPTION: "Ada kendala", DocStatus.AMIGA_REVIEWED: "Disetujui", DocStatus.SENT_TO_CLIENT: "Diserahkan",
    DocStatus.CANCELLED: "Dibatalkan",
}
ROLE_LABEL = {
    Role.PIC_KLIEN: "PIC Klien", Role.INTAKE_SUPPORT: "Intake Support", Role.FINANCE_REVIEWER: "Finance Reviewer",
}
GROUP_LABEL = {"status": "Status", "klien": "Klien", "vendor": "Vendor", "reviewer": "Reviewer", "pengaju": "Pengaju"}


class QueryPlan(BaseModel):
    """Rencana query yang dipilih model. Semua filter opsional."""
    query: Literal["progres_pengguna", "daftar_dokumen", "detail_dokumen", "ringkasan", "sop"]
    peran: Literal["PIC_KLIEN", "INTAKE_SUPPORT", "FINANCE_REVIEWER"] | None = None
    orang: str | None = Field(None, max_length=100)
    klien: str | None = Field(None, max_length=100)
    vendor: str | None = Field(None, max_length=100)
    status: list[DocStatus] | None = None
    tenggat: Literal["lewat", "dekat"] | None = None
    periode_hari: int | None = Field(None, ge=1, le=365)
    kelompok: Literal["status", "klien", "vendor", "reviewer", "pengaju"] | None = None
    request_ids: list[str] | None = Field(None, max_length=MAX_ROWS)


PLANNER_PROMPT = """Kamu menerjemahkan pertanyaan pengguna AMIGA Robot Admin menjadi rencana query JSON.
Balas HANYA satu objek JSON, tanpa penjelasan.

Jenis query:
- "progres_pengguna": progres/kinerja/beban per ORANG. Pengaju (PIC Klien, Intake Support): jumlah
  pengajuan per status. Finance Reviewer: menunggu review, lewat tenggat, disetujui, dikembalikan.
  Pakai "peran" bila pengguna menyebut satu peran.
- "daftar_dokumen": daftar dokumen/invoice tertentu (mis. yang bermasalah, yang lewat tenggat, milik vendor X).
- "detail_dokumen": rincian lengkap dokumen (invoice, rekening, kendala, voucher, pengaju, reviewer). Pakai
  "request_ids" bila Request ID-nya diketahui, atau filter yang sama dengan daftar dokumen.
- "ringkasan": jumlah dan total nilai dokumen dikelompokkan per "kelompok"
  (status | klien | vendor | reviewer | pengaju). Untuk "progres secara umum" pakai kelompok "status".
- "sop": pertanyaan tentang prosedur, aturan, definisi, atau hal lain yang tidak butuh data.

Filter opsional: "peran" (PIC_KLIEN | INTAKE_SUPPORT | FINANCE_REVIEWER), "orang" (nama), "klien" (nama
perusahaan), "vendor", "tenggat" ("lewat" | "dekat"), "periode_hari" (angka; "minggu ini" = 7, "bulan ini" = 30),
"status" (daftar kode status, tulis PERSIS kodenya):
  QUEUED = antre, baru diunggah; PROCESSING = sedang dibaca AI;
  READY_FOR_REVIEW = menunggu review / siap ditinjau reviewer; EXCEPTION = ada kendala / bermasalah;
  AMIGA_REVIEWED = disetujui, voucher sudah terbit; SENT_TO_CLIENT = diserahkan ke klien; CANCELLED = dibatalkan.
  "Sedang berjalan" / "belum selesai" = QUEUED, PROCESSING, READY_FOR_REVIEW, EXCEPTION.
  "Selesai" / "sudah disetujui" = AMIGA_REVIEWED, SENT_TO_CLIENT.
Pertanyaan "berapa ..." dengan status tertentu pakai "daftar_dokumen" (jumlahnya ikut ditampilkan).
"request_ids" (daftar Request ID, mis. ["REQ-20261015-7F2A1C"]).
Jangan isi filter yang tidak disebut pengguna.

Pertanyaan lanjutan ("tampilkan detailnya", "yang tadi", "dokumen tersebut", "kalau reviewer?") merujuk ke
jawaban sebelumnya. Jawaban berbasis data di riwayat percakapan diakhiri "[Rencana query jawaban ini: ...]" dan
"[Data yang ditampilkan]". Salin filter dari rencana itu, atau ambil Request ID dari data itu.

Contoh:
"progres PIC gimana?" -> {{"query": "progres_pengguna", "peran": "PIC_KLIEN"}}
"siapa reviewer yang paling banyak kerjaan?" -> {{"query": "progres_pengguna", "peran": "FINANCE_REVIEWER"}}
"progres Rina minggu ini" -> {{"query": "progres_pengguna", "orang": "Rina", "periode_hari": 7}}
"invoice mana yang bermasalah di PT Klien Alpha?" -> {{"query": "daftar_dokumen", "status": ["EXCEPTION"], "klien": "PT Klien Alpha"}}
"dokumen yang lewat tenggat" -> {{"query": "daftar_dokumen", "tenggat": "lewat"}}
"sekarang progresnya gimana?" -> {{"query": "ringkasan", "kelompok": "status"}}
"berapa voucher yang sudah disetujui?" -> {{"query": "daftar_dokumen", "status": ["AMIGA_REVIEWED", "SENT_TO_CLIENT"]}}
"ada berapa invoice yang nunggu review?" -> {{"query": "daftar_dokumen", "status": ["READY_FOR_REVIEW"]}}
"total tagihan per vendor bulan ini" -> {{"query": "ringkasan", "kelompok": "vendor", "periode_hari": 30}}
"detail REQ-20261015-7F2A1C" -> {{"query": "detail_dokumen", "request_ids": ["REQ-20261015-7F2A1C"]}}
(setelah daftar dokumen lewat tenggat) "tampilkan detail dokumen tersebut" -> {{"query": "detail_dokumen", "tenggat": "lewat"}}
"apa itu MISSING_EVIDENCE?" -> {{"query": "sop"}}

Hari ini: {today}."""


def planner_prompt() -> str:
    return PLANNER_PROMPT.format(today=date.today().isoformat())


# Model kadang menulis status dengan bahasa sehari-hari; dipetakan ke kode status
STATUS_ALIASES = {
    **{s.value.lower(): s for s in DocStatus},
    **{label.lower(): s for s, label in STATUS_LABEL.items()},
    "antre": DocStatus.QUEUED, "antri": DocStatus.QUEUED, "diproses": DocStatus.PROCESSING,
    "menunggu review": DocStatus.READY_FOR_REVIEW, "siap direview": DocStatus.READY_FOR_REVIEW,
    "bermasalah": DocStatus.EXCEPTION, "kendala": DocStatus.EXCEPTION, "selesai": DocStatus.AMIGA_REVIEWED,
    "terkirim": DocStatus.SENT_TO_CLIENT, "batal": DocStatus.CANCELLED,
}


def _statuses(value) -> list[DocStatus]:
    values = value if isinstance(value, list) else [value]
    found = [STATUS_ALIASES.get(str(v).strip().lower().replace("_", " ")) or STATUS_ALIASES.get(str(v).strip().lower())
             for v in values]
    return list(dict.fromkeys(s for s in found if s))


def parse_plan(text: str) -> QueryPlan | None:
    """Ambil objek JSON pertama dari jawaban model. Filter yang tidak valid dibuang (bukan seluruh rencana);
    None bila jenis query-nya sendiri tidak bisa dipakai."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if "status" in data:
        data["status"] = _statuses(data["status"])
    data = {k: v for k, v in data.items() if k in QueryPlan.model_fields and v not in (None, "", [])}
    for _ in range(len(data)):
        try:
            return QueryPlan.model_validate(data)
        except ValidationError as e:
            bad = {err["loc"][0] for err in e.errors() if err["loc"]}
            if not bad or "query" in bad:
                return None
            data = {k: v for k, v in data.items() if k not in bad}
    return None


@dataclass
class DataTable:
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str | None = None


@dataclass
class QueryResult:
    label: str
    plan: QueryPlan
    tables: list[DataTable] = field(default_factory=list)

    def to_data(self) -> dict:
        """Disimpan di riwayat percakapan: untuk menampilkan ulang tabel dan untuk pertanyaan lanjutan."""
        return {"label": self.label, "plan": self.plan.model_dump(exclude_none=True, mode="json"),
                "tables": [vars(t) for t in self.tables], "text": self.as_text()}

    def as_text(self) -> str:
        parts = [f"Interpretasi query: {self.label}"]
        for t in self.tables:
            parts.append(f"\n{t.title}" + (f" ({t.note})" if t.note else ""))
            parts.append(" | ".join(t.columns))
            parts += [" | ".join(r) for r in t.rows] or ["(tidak ada data)"]
        return "\n".join(parts)


def _rp(value) -> str:
    return f"Rp {value:,.0f}".replace(",", ".") if value is not None else "-"


def _like(text: str) -> str:
    return f"%{text.strip()}%"


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _filtered_clients(db: Session, client_ids: set[uuid.UUID], plan: QueryPlan) -> set[uuid.UUID]:
    if not plan.klien:
        return client_ids
    found = db.scalars(select(Client.id).where(Client.id.in_(client_ids), Client.name.ilike(_like(plan.klien))))
    return set(found)


def _doc_filters(plan: QueryPlan, client_ids: set[uuid.UUID], today: date) -> list:
    """Filter dokumen bersama. Selalu diawali batas klien yang boleh dibuka pengguna."""
    conds = [Document.client_id.in_(client_ids)]
    if plan.vendor:
        conds.append(Extraction.vendor_name.ilike(_like(plan.vendor)))
    if plan.status:
        conds.append(Document.status.in_(plan.status))
    if plan.tenggat == "lewat":
        conds += [Document.status.not_in(DONE), Document.due_date < today]
    elif plan.tenggat == "dekat":
        conds += [Document.status.not_in(DONE),
                  Document.due_date.between(today, today + timedelta(days=settings.due_soon_days))]
    if plan.periode_hari:
        conds.append(Document.created_at >= _since(plan.periode_hari))
    if plan.request_ids:
        conds.append(func.upper(Document.request_id).in_([r.strip().upper() for r in plan.request_ids]))
    return conds


def describe(plan: QueryPlan) -> str:
    what = {
        "progres_pengguna": "Progres per " + (ROLE_LABEL[Role(plan.peran)] if plan.peran else "pengguna"),
        "daftar_dokumen": "Daftar dokumen",
        "detail_dokumen": "Detail dokumen",
        "ringkasan": f"Ringkasan per {GROUP_LABEL[plan.kelompok or 'status'].lower()}",
    }[plan.query]
    bits = []
    if plan.orang:
        bits.append(f"nama mengandung \"{plan.orang}\"")
    if plan.klien:
        bits.append(f"klien \"{plan.klien}\"")
    if plan.vendor:
        bits.append(f"vendor \"{plan.vendor}\"")
    if plan.status:
        bits.append("status " + ", ".join(STATUS_LABEL[s] for s in plan.status))
    if plan.tenggat:
        bits.append("lewat tenggat" if plan.tenggat == "lewat" else f"tenggat ≤ {settings.due_soon_days} hari")
    if plan.periode_hari:
        bits.append(f"{plan.periode_hari} hari terakhir")
    if plan.request_ids:
        bits.append(", ".join(plan.request_ids))
    return what + (f" · {'; '.join(bits)}" if bits else "")


def run(db: Session, plan: QueryPlan, client_ids: set[uuid.UUID], today: date | None = None) -> QueryResult:
    today = today or date.today()
    clients = _filtered_clients(db, client_ids, plan)
    result = QueryResult(label=describe(plan), plan=plan)
    if plan.query == "progres_pengguna":
        if plan.peran in (None, "PIC_KLIEN", "INTAKE_SUPPORT"):
            result.tables.append(_submitter_progress(db, plan, clients, today))
        if plan.peran in (None, "FINANCE_REVIEWER"):
            result.tables.append(_reviewer_progress(db, plan, clients, today))
    elif plan.query == "daftar_dokumen":
        result.tables.append(_document_list(db, plan, clients, today))
    elif plan.query == "detail_dokumen":
        result.tables += _document_details(db, plan, clients, today)
    elif plan.query == "ringkasan":
        result.tables.append(_summary(db, plan, clients, today))
    return result


def _users_with_roles(db: Session, roles: list[Role], name: str | None) -> list[tuple[uuid.UUID, str, set[Role]]]:
    stmt = (select(User.id, User.full_name, UserRole.role)
            .join(UserRole, UserRole.user_id == User.id)
            .where(User.is_active.is_(True), UserRole.role.in_(roles))
            .order_by(User.full_name))
    if name:
        stmt = stmt.where(User.full_name.ilike(_like(name)))
    users: dict[uuid.UUID, tuple[str, set[Role]]] = {}
    for uid, full_name, role in db.execute(stmt):
        users.setdefault(uid, (full_name, set()))[1].add(role)
    return [(uid, n, r) for uid, (n, r) in users.items()]


def _submitter_progress(db: Session, plan: QueryPlan, clients: set[uuid.UUID], today: date) -> DataTable:
    roles = [Role(plan.peran)] if plan.peran else [Role.PIC_KLIEN, Role.INTAKE_SUPPORT]
    users = _users_with_roles(db, roles, plan.orang)
    buckets = {
        "Diproses AI": (DocStatus.QUEUED, DocStatus.PROCESSING),
        "Siap ditinjau": (DocStatus.READY_FOR_REVIEW,),
        "Ada kendala": (DocStatus.EXCEPTION,),
        "Selesai": (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT),
        "Dibatalkan": (DocStatus.CANCELLED,),
    }
    counts = {
        uid: rest for uid, *rest in db.execute(
            select(Document.uploaded_by, func.count(),
                   *[func.count().filter(Document.status.in_(s)) for s in buckets.values()])
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .where(*_doc_filters(plan, clients, today), Document.uploaded_by.in_([u[0] for u in users]))
            .group_by(Document.uploaded_by))
    }
    # Pengaju tanpa pengajuan tetap tampil bila ditugaskan ke klien dalam cakupan (progresnya 0)
    assigned = set(db.scalars(select(UserClientAssignment.user_id).where(UserClientAssignment.client_id.in_(clients))))
    rows = []
    for uid, name, user_roles in users:
        if uid not in counts and uid not in assigned:
            continue
        total, *per_bucket = counts.get(uid, [0] * (len(buckets) + 1))
        rows.append([name, " + ".join(ROLE_LABEL[r] for r in sorted(user_roles, key=lambda r: r.value)),
                     str(total), *map(str, per_bucket)])
    rows.sort(key=lambda r: -int(r[2]))
    return DataTable(title="Progres pengaju", columns=["Nama", "Peran", "Total", *buckets], rows=rows[:MAX_ROWS],
                     note=_period_note(plan))


def _reviewer_progress(db: Session, plan: QueryPlan, clients: set[uuid.UUID], today: date) -> DataTable:
    users = _users_with_roles(db, [Role.FINANCE_REVIEWER], plan.orang)
    ids = [u[0] for u in users]
    open_docs = dict(db.execute(
        select(Document.assigned_reviewer_id, func.count())
        .outerjoin(Extraction, Extraction.document_id == Document.id)
        .where(*_doc_filters(plan, clients, today), Document.assigned_reviewer_id.in_(ids),
               Document.status == DocStatus.READY_FOR_REVIEW)
        .group_by(Document.assigned_reviewer_id)).tuples().all())
    late = dict(db.execute(
        select(Document.assigned_reviewer_id, func.count())
        .where(Document.client_id.in_(clients), Document.assigned_reviewer_id.in_(ids),
               Document.status.not_in(DONE), Document.due_date < today)
        .group_by(Document.assigned_reviewer_id)).tuples().all())
    # Keputusan reviewer diambil dari jejak audit, dibatasi klien dalam cakupan
    days = plan.periode_hari or 30
    actions = ("APPROVED", "RETURNED_TO_PIC", "CORRECTED_BY_REVIEWER")
    decided: dict[uuid.UUID, dict[str, int]] = {}
    for actor, action, n in db.execute(
        select(AuditLog.actor_id, AuditLog.action, func.count())
        .join(Document, Document.id == AuditLog.document_id)
        .where(AuditLog.actor_id.in_(ids), AuditLog.action.in_(actions), Document.client_id.in_(clients),
               AuditLog.created_at >= _since(days))
        .group_by(AuditLog.actor_id, AuditLog.action)):
        decided.setdefault(actor, {})[action] = n

    rows = []
    for uid, name, _ in users:
        pending = open_docs.get(uid, 0)
        d = decided.get(uid, {})
        load = f"{pending} (berlebih)" if pending > settings.reviewer_overload_threshold else str(pending)
        rows.append([name, load, str(late.get(uid, 0)), str(d.get("APPROVED", 0)),
                     str(d.get("RETURNED_TO_PIC", 0)), str(d.get("CORRECTED_BY_REVIEWER", 0))])
    rows.sort(key=lambda r: -int(r[1].split()[0]))
    return DataTable(
        title="Progres Finance Reviewer",
        columns=["Nama", "Menunggu review", "Lewat tenggat", "Disetujui", "Dikembalikan", "Dikoreksi"],
        rows=rows[:MAX_ROWS],
        note=f"keputusan {days} hari terakhir; berlebih bila > {settings.reviewer_overload_threshold}",
    )


def _period_note(plan: QueryPlan) -> str | None:
    return f"pengajuan {plan.periode_hari} hari terakhir" if plan.periode_hari else "semua waktu"


def _document_list(db: Session, plan: QueryPlan, clients: set[uuid.UUID], today: date) -> DataTable:
    uploader, reviewer = aliased(User), aliased(User)
    conds = _doc_filters(plan, clients, today)
    if plan.orang:
        conds.append(or_(uploader.full_name.ilike(_like(plan.orang)), reviewer.full_name.ilike(_like(plan.orang))))
    base = (select(Document.request_id, Client.name, Extraction.vendor_name, Document.status, Extraction.total,
                   Document.due_date, uploader.full_name, reviewer.full_name)
            .join(Client, Client.id == Document.client_id)
            .join(uploader, uploader.id == Document.uploaded_by)
            .outerjoin(reviewer, reviewer.id == Document.assigned_reviewer_id)
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .where(and_(*conds)))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Document.due_date.is_(None), Document.due_date, Document.created_at.desc())
                      .limit(MAX_ROWS)).all()
    return DataTable(
        title="Dokumen",
        columns=["Request ID", "Klien", "Vendor", "Status", "Total", "Tenggat", "Pengaju", "Reviewer"],
        rows=[[rid, client, vendor or "-", STATUS_LABEL[st], _rp(amount), due.isoformat() if due else "-",
               up, rev or "-"] for rid, client, vendor, st, amount, due, up, rev in rows],
        note=f"{total} dokumen" + (f", {MAX_ROWS} ditampilkan" if total > MAX_ROWS else ""),
    )


def _summary(db: Session, plan: QueryPlan, clients: set[uuid.UUID], today: date) -> DataTable:
    uploader, reviewer = aliased(User), aliased(User)
    group = plan.kelompok or "status"
    key = {
        "status": Document.status, "klien": Client.name, "vendor": Extraction.vendor_name,
        "reviewer": reviewer.full_name, "pengaju": uploader.full_name,
    }[group]
    conds = _doc_filters(plan, clients, today)
    if plan.orang:
        conds.append(or_(uploader.full_name.ilike(_like(plan.orang)), reviewer.full_name.ilike(_like(plan.orang))))
    rows = db.execute(
        select(key, func.count(), func.sum(Extraction.total))
        .select_from(Document)
        .join(Client, Client.id == Document.client_id)
        .join(uploader, uploader.id == Document.uploaded_by)
        .outerjoin(reviewer, reviewer.id == Document.assigned_reviewer_id)
        .outerjoin(Extraction, Extraction.document_id == Document.id)
        .where(and_(*conds)).group_by(key).order_by(func.count().desc()).limit(MAX_ROWS)).all()

    def label(v):
        if v is None:
            return "(belum ada)"
        return STATUS_LABEL[v] if isinstance(v, DocStatus) else str(v)

    return DataTable(title=f"Ringkasan per {GROUP_LABEL[group].lower()}",
                     columns=[GROUP_LABEL[group], "Jumlah dokumen", "Total nilai"],
                     rows=[[label(k), str(n), _rp(s)] for k, n, s in rows], note=_period_note(plan))


def _document_details(db: Session, plan: QueryPlan, clients: set[uuid.UUID], today: date) -> list[DataTable]:
    """Rincian per dokumen (maks. MAX_DETAIL), satu tabel Kolom/Nilai per dokumen."""
    uploader, reviewer = aliased(User), aliased(User)
    conds = _doc_filters(plan, clients, today)
    if plan.orang:
        conds.append(or_(uploader.full_name.ilike(_like(plan.orang)), reviewer.full_name.ilike(_like(plan.orang))))
    base = (select(Document, Client.name, Extraction, uploader.full_name, reviewer.full_name, Voucher.voucher_no)
            .join(Client, Client.id == Document.client_id)
            .join(uploader, uploader.id == Document.uploaded_by)
            .outerjoin(reviewer, reviewer.id == Document.assigned_reviewer_id)
            .outerjoin(Extraction, Extraction.document_id == Document.id)
            .outerjoin(Voucher, Voucher.document_id == Document.id)
            .where(and_(*conds)))
    total = db.scalar(select(func.count()).select_from(base.with_only_columns(Document.id).subquery()))
    rows = db.execute(base.order_by(Document.due_date.is_(None), Document.due_date, Document.created_at.desc())
                      .limit(MAX_DETAIL)).all()
    if not rows:
        return [DataTable(title="Detail dokumen", columns=["Kolom", "Nilai"], rows=[], note="0 dokumen")]

    ids = [doc.id for doc, *_ in rows]
    issues: dict[uuid.UUID, list[str]] = {}
    for doc_id, code, message in db.execute(
            select(ValidationIssue.document_id, ValidationIssue.code, ValidationIssue.message)
            .where(ValidationIssue.document_id.in_(ids), ValidationIssue.resolved.is_(False))):
        issues.setdefault(doc_id, []).append(f"{code.value}: {message}")
    files = dict(db.execute(select(DocumentFile.document_id, func.count())
                            .where(DocumentFile.document_id.in_(ids)).group_by(DocumentFile.document_id)).tuples().all())
    approved = dict(db.execute(
        select(AuditLog.document_id, User.full_name)
        .join(User, User.id == AuditLog.actor_id)
        .where(AuditLog.document_id.in_(ids), AuditLog.action == "APPROVED")
        .order_by(AuditLog.id)).tuples().all())

    tables = []
    for doc, client, ext, up, rev, voucher_no in rows:
        fields = [
            ("Status", STATUS_LABEL[doc.status]),
            ("Klien", client),
            ("Vendor", (ext.vendor_name if ext else None) or "-"),
            ("No. invoice", (ext.invoice_no if ext else None) or "-"),
            ("Tanggal invoice", ext.invoice_date.isoformat() if ext and ext.invoice_date else "-"),
            ("Total", _rp(ext.total if ext else None)),
            ("Rekening tujuan", " · ".join(x for x in (ext.bank_name, ext.account_no, ext.account_name) if x)
             if ext and (ext.bank_name or ext.account_no) else "-"),
            ("Jenis permintaan", doc.request_type or "-"),
            ("Saluran", doc.channel or "-"),
            ("Jumlah file", str(files.get(doc.id, 1))),
            ("Pengaju", up),
            ("Reviewer", rev or "-"),
            ("Disetujui oleh", approved.get(doc.id, "-")),
            ("Tanggal pengajuan", doc.submitted_date.isoformat() if doc.submitted_date else "-"),
            ("Tenggat", doc.due_date.isoformat() if doc.due_date else "-"),
            ("Kendala aktif", "; ".join(issues.get(doc.id, [])) or "-"),
            ("No. voucher", voucher_no or "-"),
            ("Terakhir diperbarui", doc.updated_at.astimezone().strftime("%Y-%m-%d %H:%M") if doc.updated_at else "-"),
        ]
        tables.append(DataTable(title=doc.request_id, columns=["Kolom", "Nilai"], rows=[[k, v] for k, v in fields]))
    if total > MAX_DETAIL:
        tables[0].note = f"{total} dokumen cocok, {MAX_DETAIL} pertama ditampilkan"
    return tables
