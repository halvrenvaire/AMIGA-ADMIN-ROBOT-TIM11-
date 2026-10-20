"""Isi jawaban Asisten yang interaktif: kartu dokumen dan data administrasi.

Kartu dokumen berisi tahapan progres, detail invoice, riwayat aktivitas, saran langkah berikutnya
sesuai peran penanya, dan tautan ke halaman terkait. Tautan hanya ke halaman yang memang boleh
dibuka peran tersebut. Data administrasi (pengguna, klien) hanya untuk System Admin.
"""
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AuditLog, Client, DocStatus, Document, Role, User, UserClientAssignment, UserRole, ValidationIssue,
)

MAX_CARDS = 5
HISTORY_ITEMS = 8

STATUS_LABEL = {
    DocStatus.QUEUED: "Antre", DocStatus.PROCESSING: "Diproses AI", DocStatus.READY_FOR_REVIEW: "Siap ditinjau",
    DocStatus.EXCEPTION: "Ada kendala", DocStatus.AMIGA_REVIEWED: "Disetujui", DocStatus.SENT_TO_CLIENT: "Diserahkan",
    DocStatus.CANCELLED: "Dibatalkan",
}
ACTION_LABEL = {
    "DOCUMENT_UPLOADED": "Invoice diunggah", "STATUS_CHANGED": "Status berubah", "EXTRACTED": "AI selesai membaca invoice",
    "FIXED_BY_PIC": "Diperbaiki PIC", "PIC_NOTE": "Catatan PIC", "REPROCESS_REQUESTED": "Diminta proses ulang",
    "CORRECTED_BY_REVIEWER": "Dikoreksi reviewer", "REVERIFIED": "Verifikasi ulang", "APPROVED": "Disetujui Finance Reviewer",
    "VOUCHER_CREATED": "Voucher dibuat", "VOUCHER_DOWNLOADED": "Voucher diunduh", "RETURNED_TO_PIC": "Dikembalikan ke PIC",
    "SOD_REJECTED": "Persetujuan ditolak (SoD)", "REVIEWER_REASSIGNED": "Reviewer dialihkan",
    "DUPLICATE_DISMISSED": "Ditandai bukan duplikat", "SIGNERS_CHANGED": "Penanda tangan diubah",
    "DOCUMENT_CANCELLED": "Pengajuan dibatalkan", "E_SIGNATURE_APPLIED": "Tanda tangan elektronik dibubuhkan",
    "CLASSIFICATION_DECIDED": "Klasifikasi diputuskan reviewer",
    "ACCOUNT_CONFIRMED_BY_REVIEWER": "Rekening dikonfirmasi reviewer",
    "TAX_AI_SUGGESTED": "Rekomendasi AI PPh per baris",
    "AI_UNAVAILABLE": "AI tidak membaca invoice; diisi manual", "WARNING_ACKNOWLEDGED": "Peringatan dikonfirmasi PIC",
}
ROLE_LABEL = {
    Role.PIC_KLIEN: "PIC Klien", Role.INTAKE_SUPPORT: "Intake Support", Role.FINANCE_REVIEWER: "Finance Reviewer",
    Role.SERVICE_LEAD: "Service Lead", Role.SYSTEM_ADMIN: "System Admin",
}
SUBMITTER_ROLES = {Role.PIC_KLIEN, Role.INTAKE_SUPPORT}


@dataclass
class DocCard:
    request_id: str
    href: str
    status: str
    status_label: str
    subtitle: str
    fields: list[list[str]]
    steps: list[dict]
    history: list[dict]
    links: list[dict]
    hint: str | None = None

    def as_text(self) -> str:
        lines = [f"Dokumen {self.request_id} ({self.status_label}) · {self.subtitle}"]
        lines += [f"  {k}: {v}" for k, v in self.fields]
        lines.append("  Tahapan: " + "; ".join(f"{s['label']}={s['state']}" + (f" ({s['detail']})" if s.get("detail") else "")
                                               for s in self.steps))
        lines.append("  Riwayat terbaru: " + "; ".join(f"{h['at']} {h['action']} oleh {h['actor']}" for h in self.history[:4]))
        if self.hint:
            lines.append(f"  Saran: {self.hint}")
        return "\n".join(lines)


def _rp(value) -> str:
    return f"Rp {value:,.0f}".replace(",", ".") if value is not None else "-"


def _fmt(dt) -> str:
    return dt.astimezone().strftime("%d-%m-%Y %H:%M") if dt else "-"


def _actor(label: str) -> str:
    # actor_label = "Nama <email>"; email tidak ditampilkan di jawaban Asisten
    return re.sub(r"\s*<[^>]*>$", "", label or "-")


def page_links(roles: set[Role]) -> list[dict]:
    """Halaman kerja utama sesuai peran, untuk tombol di bawah tabel."""
    links = []
    if roles & SUBMITTER_ROLES:
        links.append({"label": "Pengajuan Saya", "href": "/pengajuan"})
    if Role.FINANCE_REVIEWER in roles:
        links.append({"label": "Peninjauan Saya", "href": "/peninjauan"})
    if roles & {Role.FINANCE_REVIEWER, Role.SERVICE_LEAD}:
        links.append({"label": "Dashboard Antrean", "href": "/antrean"})
    return links


def _can_open_voucher(roles: set[Role]) -> bool:
    # Service Lead tidak membuka voucher (hanya rekap); peran lain yang punya akses dokumen boleh
    return bool(roles & {Role.PIC_KLIEN, Role.INTAKE_SUPPORT, Role.FINANCE_REVIEWER})


def _steps(doc: Document, times: dict[str, object]) -> list[dict]:
    st = doc.status
    read = doc.extraction is not None
    verified_ok = st in (DocStatus.READY_FOR_REVIEW, DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT)
    approved = st in (DocStatus.AMIGA_REVIEWED, DocStatus.SENT_TO_CLIENT)
    steps = [
        {"label": "Diunggah", "state": "done", "at": _fmt(times.get("uploaded") or doc.created_at)},
        {"label": "Dibaca AI", "at": _fmt(doc.extraction.extracted_at) if read else None,
         "state": "done" if read else "active" if st == DocStatus.PROCESSING else "todo"},
        {"label": "Verifikasi sistem", "at": _fmt(times.get("verified")) if times.get("verified") else None,
         "state": "done" if verified_ok else "bad" if st == DocStatus.EXCEPTION else "todo",
         "detail": "Ada kendala" if st == DocStatus.EXCEPTION else None},
        {"label": "Ditinjau reviewer", "at": _fmt(times.get("approved")) if approved else None,
         "state": "done" if approved else "active" if st == DocStatus.READY_FOR_REVIEW else "todo"},
        {"label": "Voucher terbit", "at": _fmt(doc.voucher.generated_at) if doc.voucher else None,
         "state": "done" if doc.voucher else "todo", "detail": doc.voucher.voucher_no if doc.voucher else None},
    ]
    if st == DocStatus.CANCELLED:
        for s in steps:
            if s["state"] in ("todo", "active"):
                s["state"] = "skip"
        steps.append({"label": "Dibatalkan", "state": "bad", "at": _fmt(times.get("cancelled"))})
    return steps


def _hint(doc: Document, user: User, reviewer: str | None, issues: list[str]) -> str | None:
    roles = user.roles
    st = doc.status
    if st == DocStatus.EXCEPTION and roles & SUBMITTER_ROLES:
        return f"Ada kendala yang perlu Anda perbaiki ({', '.join(issues) or '-'}). Buka detail dokumen untuk memperbaikinya."
    if st == DocStatus.EXCEPTION and Role.FINANCE_REVIEWER in roles:
        return f"Dokumen tertahan kendala ({', '.join(issues) or '-'}); menunggu perbaikan PIC atau proses ulang."
    if st == DocStatus.READY_FOR_REVIEW and doc.assigned_reviewer_id == user.id:
        return "Dokumen ini menunggu keputusan Anda. Buka detail dokumen untuk meninjau."
    if st == DocStatus.READY_FOR_REVIEW:
        return f"Lolos verifikasi, sedang menunggu ditinjau {reviewer or 'Finance Reviewer'}."
    if st in (DocStatus.QUEUED, DocStatus.PROCESSING):
        return "AI sedang membaca invoice; halaman detail diperbarui otomatis."
    if doc.voucher and _can_open_voucher(roles):
        return f"Voucher {doc.voucher.voucher_no} sudah terbit dan bisa dibuka atau diunduh."
    return None


def document_cards(db: Session, doc_ids: list[uuid.UUID], user: User) -> list[DocCard]:
    """Kartu untuk dokumen (urutan dipertahankan). Pemanggil wajib sudah membatasi doc_ids ke klien penanya."""
    if not doc_ids:
        return []
    docs = {d.id: d for d in db.scalars(
        select(Document).where(Document.id.in_(doc_ids))
        .options(selectinload(Document.extraction), selectinload(Document.voucher), selectinload(Document.client)))}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(
        {d.assigned_reviewer_id for d in docs.values() if d.assigned_reviewer_id}
        | {d.uploaded_by for d in docs.values()}))).tuples().all())
    issues: dict[uuid.UUID, list[str]] = {}
    for doc_id, code in db.execute(select(ValidationIssue.document_id, ValidationIssue.code).where(
            ValidationIssue.document_id.in_(doc_ids), ValidationIssue.resolved.is_(False))):
        issues.setdefault(doc_id, []).append(code.value)
    logs: dict[uuid.UUID, list[AuditLog]] = {}
    for log in db.scalars(select(AuditLog).where(AuditLog.document_id.in_(doc_ids)).order_by(AuditLog.id)):
        logs.setdefault(log.document_id, []).append(log)

    cards = []
    for doc_id in doc_ids:
        doc = docs.get(doc_id)
        if doc is None:
            continue
        doc_logs = logs.get(doc_id, [])
        times = {}
        for log in doc_logs:
            if log.action == "DOCUMENT_UPLOADED" and "uploaded" not in times:
                times["uploaded"] = log.created_at
            elif log.action == "STATUS_CHANGED" and log.status_after in ("READY_FOR_REVIEW", "EXCEPTION"):
                times["verified"] = log.created_at
            elif log.action == "APPROVED":
                times["approved"] = log.created_at
            elif log.action == "DOCUMENT_CANCELLED":
                times["cancelled"] = log.created_at
        ex = doc.extraction
        reviewer = names.get(doc.assigned_reviewer_id)
        fields = [
            ["Klien", doc.client.name],
            ["Vendor", (ex.vendor_name if ex else None) or "-"],
            ["No. invoice", (ex.invoice_no if ex else None) or "-"],
            ["Total", _rp(ex.total if ex else None)],
            ["Rekening tujuan", " · ".join(x for x in (ex.bank_name, ex.account_no, ex.account_name) if x) if ex else "-"],
            ["Pengaju", names.get(doc.uploaded_by, "-")],
            ["Finance Reviewer", reviewer or "-"],
            ["Tenggat", doc.due_date.strftime("%d-%m-%Y") if doc.due_date else "-"],
            ["Kendala aktif", ", ".join(issues.get(doc_id, [])) or "-"],
        ]
        history = [{"at": _fmt(log.created_at), "action": ACTION_LABEL.get(log.action, log.action),
                    "actor": _actor(log.actor_label),
                    "note": (log.status_after and STATUS_LABEL.get(DocStatus(log.status_after))) or (log.note or "")[:120]}
                   for log in reversed(doc_logs[-HISTORY_ITEMS:])]
        href = f"/dokumen/{doc.id}"
        links = [{"label": "Buka detail dokumen", "href": href, "primary": True},
                 {"label": "Riwayat & audit", "href": f"{href}/riwayat"}]
        if doc.voucher and _can_open_voucher(user.roles):
            links.append({"label": f"Voucher {doc.voucher.voucher_no}", "href": f"{href}/voucher"})
        links += page_links(user.roles)
        cards.append(DocCard(
            request_id=doc.request_id, href=href, status=doc.status.value, status_label=STATUS_LABEL[doc.status],
            subtitle=" · ".join(x for x in (doc.client.name, ex.vendor_name if ex else None, _rp(ex.total) if ex and ex.total else None) if x),
            fields=fields, steps=_steps(doc, times), history=history, links=links,
            hint=_hint(doc, user, reviewer, issues.get(doc_id, [])),
        ))
    return cards


def recent_document_ids(db: Session, user: User, client_ids: set[uuid.UUID], limit: int) -> tuple[list[uuid.UUID], bool]:
    """Dokumen yang terakhir disentuh penanya (mengunggah, diwakili, memperbaiki, meninjau...), terbaru dulu.
    Bila penanya belum pernah menyentuh dokumen, dokumen terbaru di klien penanya (flag False)."""
    # ID audit selalu naik; lebih tegas daripada waktu (beberapa aksi bisa tercatat pada waktu yang sama)
    last = func.max(AuditLog.id)
    mine = db.execute(
        select(AuditLog.document_id, last)
        .join(Document, Document.id == AuditLog.document_id)
        .where(or_(AuditLog.actor_id == user.id, AuditLog.on_behalf_of == user.id),
               Document.client_id.in_(client_ids))
        .group_by(AuditLog.document_id).order_by(last.desc()).limit(limit)).all()
    if mine:
        return [row[0] for row in mine], True
    recent = db.scalars(select(Document.id).where(Document.client_id.in_(client_ids))
                        .order_by(Document.updated_at.desc()).limit(limit)).all()
    return list(recent), False


# --- Data administrasi (System Admin) ---

@dataclass
class AdminTable:
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str | None = None
    links: list[dict] = field(default_factory=list)
    row_links: list[str | None] = field(default_factory=list)


def users_overview(db: Session, peran: str | None, klien: str | None, orang: str | None,
                   aktif: bool | None) -> list[AdminTable]:
    users = db.scalars(select(User).options(selectinload(User.role_links)).order_by(User.full_name)).all()
    assigned: dict[uuid.UUID, list[str]] = {}
    for uid, name in db.execute(select(UserClientAssignment.user_id, Client.name)
                                .join(Client, Client.id == UserClientAssignment.client_id).order_by(Client.name)):
        assigned.setdefault(uid, []).append(name)

    recap = []
    for role in Role:
        with_role = [u for u in users if role in u.roles]
        recap.append([ROLE_LABEL[role], str(sum(u.is_active for u in with_role)), str(sum(not u.is_active for u in with_role))])
    active = sum(u.is_active for u in users)
    tables = [AdminTable(title="Rekap pengguna per peran", columns=["Peran", "Aktif", "Nonaktif"], rows=recap,
                         note=f"{len(users)} akun ({active} aktif); satu akun bisa punya beberapa peran",
                         links=[{"label": "Pengguna & Peran", "href": "/admin/pengguna"}])]

    shown = users
    if peran:
        shown = [u for u in shown if Role(peran) in u.roles]
    if klien:
        shown = [u for u in shown if any(klien.lower() in c.lower() for c in assigned.get(u.id, []))]
    if orang:
        shown = [u for u in shown if orang.lower() in u.full_name.lower() or orang.lower() in u.email.lower()]
    if aktif is not None:
        shown = [u for u in shown if u.is_active == aktif]
    if peran or klien or orang or aktif is not None:
        tables.append(AdminTable(
            title="Daftar pengguna", columns=["Nama", "Email", "Peran", "Klien", "Status"],
            rows=[[u.full_name, u.email, ", ".join(ROLE_LABEL[r] for r in sorted(u.roles, key=lambda r: r.value)),
                   ", ".join(assigned.get(u.id, [])) or "-", "Aktif" if u.is_active else "Nonaktif"] for u in shown[:20]],
            note=f"{len(shown)} pengguna cocok" + (", 20 ditampilkan" if len(shown) > 20 else ""),
            links=[{"label": "Kelola di Pengguna & Peran", "href": "/admin/pengguna"}]))
    return tables


def clients_overview(db: Session, klien: str | None, tanpa_pic: bool) -> list[AdminTable]:
    people: dict[uuid.UUID, dict[Role, list[str]]] = {}
    for cid, name, role in db.execute(
            select(UserClientAssignment.client_id, User.full_name, UserRole.role)
            .join(User, User.id == UserClientAssignment.user_id).join(UserRole, UserRole.user_id == User.id)
            .where(User.is_active.is_(True), UserRole.role.in_(SUBMITTER_ROLES)).order_by(User.full_name)):
        people.setdefault(cid, {}).setdefault(role, []).append(name)
    stmt = select(Client).order_by(Client.name)
    if klien:
        stmt = stmt.where(Client.name.ilike(f"%{klien.strip()}%"))
    rows = []
    for c in db.scalars(stmt):
        pics = people.get(c.id, {}).get(Role.PIC_KLIEN, [])
        if tanpa_pic and pics:
            continue
        rows.append([c.name, ", ".join(pics) or "Belum ada PIC",
                     ", ".join(people.get(c.id, {}).get(Role.INTAKE_SUPPORT, [])) or "-", _fmt(c.created_at)[:10]])
    return [AdminTable(title="Klien tanpa PIC" if tanpa_pic else "Klien", columns=["Klien", "PIC Klien", "Intake Support", "Terdaftar"],
                       rows=rows, note=f"{len(rows)} klien", links=[{"label": "Kelola Klien", "href": "/admin/klien"},
                                                                     {"label": "Tugaskan PIC", "href": "/admin/pengguna"}])]
