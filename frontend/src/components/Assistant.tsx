import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity, AlertTriangle, ArrowUp, ArrowUpRight, BookOpen, Check, ChevronDown, Database, Lightbulb, Maximize2, Receipt,
  RotateCcw, Sparkles, ThumbsDown, ThumbsUp, Users, X, type LucideIcon,
} from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import { StatusBadge } from "./ui";
import type { AskAgentResponse, AssistantLink, AssistantMessage, DataTable, DocCard } from "../types";

export interface Message {
  role: "user" | "bot";
  text: string;
  answerId?: number | null;
  usedData?: boolean;
  sources?: number;
  feedback?: 1 | -1;
  queryLabel?: string | null;
  tables?: DataTable[];
  cards?: DocCard[];
}

function genUUID(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const newSession = () => `web-${genUUID()}`;

/** Asisten untuk semua peran. Data dibatasi server: PIC Klien / Intake Support hanya klien yang ditugaskan,
 *  Finance Reviewer / Service Lead semua klien, System Admin hanya SOP. */
export function useAssistantAccess() {
  const { user, has } = useAuth();
  const allowed = Boolean(user);
  const adminOnly = user?.roles.length === 1 && user.roles[0] === "SYSTEM_ADMIN";
  const submitter = !has("FINANCE_REVIEWER", "SERVICE_LEAD") && has("PIC_KLIEN", "INTAKE_SUPPORT");
  return { allowed, adminOnly, submitter };
}

/** State percakapan Asisten, dipakai widget mengambang dan halaman Asisten layar penuh. */
export function useAssistantChat(onAnswered?: () => void) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState(newSession);

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await api.post<AskAgentResponse>("/ask-agent", { question, session_id: session });
      setMessages((m) => [...m, {
        role: "bot", text: res.answer, answerId: res.answer_id, usedData: res.used_queue_data, sources: res.sources.length,
        queryLabel: res.query_label, tables: res.data_tables, cards: res.cards,
      }]);
      onAnswered?.();
    } catch (e) {
      setMessages((m) => [...m, { role: "bot", text: `⚠ ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function rate(index: number, helpful: boolean) {
    const msg = messages[index];
    if (!msg.answerId) return;
    await api.post("/ask-agent/feedback", { answer_id: msg.answerId, helpful }).catch(() => undefined);
    setMessages((m) => m.map((x, i) => (i === index ? { ...x, feedback: helpful ? 1 : -1 } : x)));
  }

  const reset = useCallback(() => { setMessages([]); setSession(newSession()); }, []);

  /** Buka percakapan lama dari riwayat (tabel data ikut ditampilkan ulang). */
  const load = useCallback(async (id: string) => {
    const rows = await api.get<AssistantMessage[]>(`/ask-agent/sessions/${encodeURIComponent(id)}`);
    setSession(id);
    setMessages(rows.map((r) => (r.role === "user" ? { role: "user", text: r.content } : {
      role: "bot", text: r.content, usedData: Boolean(r.query_label) || undefined, queryLabel: r.query_label, tables: r.data_tables,
      cards: r.cards,
    })));
  }, []);

  return { messages, busy, session, ask, rate, reset, load };
}

export function suggestionsFor(adminOnly: boolean, submitter = false) {
  if (adminOnly) {
    return ["Ada berapa user di sistem?", "Klien mana yang belum punya PIC?", "Akun mana yang nonaktif?",
            "Apa itu Segregation of Duties?"];
  }
  if (submitter) {
    return ["Progres invoice yang terakhir saya update", "Invoice mana yang ada kendala?",
            "Berapa voucher yang sudah disetujui?", "Apa arti MISSING_EVIDENCE?"];
  }
  return ["Dokumen yang terakhir saya tangani", "Progres Finance Reviewer minggu ini", "Invoice mana yang lewat tenggat?",
          "Apa arti MISSING_EVIDENCE?"];
}

/** Ikon untuk saran pertanyaan, ditebak dari kata kuncinya. */
function suggestionIcon(text: string): LucideIcon {
  if (/kendala|tenggat|lewat/i.test(text)) return AlertTriangle;
  if (/voucher/i.test(text)) return Receipt;
  if (/^apa (arti|itu)/i.test(text)) return BookOpen;
  if (/user|akun|klien|PIC\b/i.test(text)) return Users;
  return Activity;
}

/** Avatar Asisten (ikon kilau di lingkaran bergradien). */
export function ChatAvatar({ size = "sm" }: { size?: "sm" | "lg" }) {
  return <span className={`chat-avatar ${size}`} aria-hidden="true"><Sparkles /></span>;
}

/** Sapaan singkat + kartu saran pertanyaan saat percakapan masih kosong. */
function ChatWelcome({ name, adminOnly, submitter, onAsk }: {
  name?: string; adminOnly: boolean; submitter: boolean; onAsk: (q: string) => void;
}) {
  const scope = adminOnly
    ? "Tanya soal SOP AMIGA, akun pengguna, peran, dan klien."
    : submitter
      ? "Tanya soal SOP, progres pengajuan, invoice yang ada kendala, atau voucher perusahaan Anda."
      : "Tanya soal SOP, progres tim, beban reviewer, atau invoice yang bermasalah.";
  return (
    <div className="chat-welcome">
      <ChatAvatar size="lg" />
      <h3>Halo, {name?.split(" ")[0] ?? "Anda"} 👋</h3>
      <p>{scope}</p>
      <p className="chat-welcome-note">Jawaban diambil langsung dari sistem sesuai hak akses Anda, dan bisa diklik untuk membuka halaman terkait.</p>
      <div className="suggest">
        {suggestionsFor(adminOnly, submitter).map((q) => {
          const Icon = suggestionIcon(q);
          return (
            <button key={q} type="button" onClick={() => onAsk(q)}>
              <span className="suggest-ic"><Icon /></span>
              <span className="suggest-text">{q}</span>
              <ArrowUpRight className="suggest-go" />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Daftar pesan, termasuk sapaan + saran pertanyaan saat percakapan masih kosong. */
export function ChatThread({ chat, adminOnly, name, onNavigate }: {
  chat: ReturnType<typeof useAssistantChat>; adminOnly: boolean; name?: string; onNavigate?: () => void;
}) {
  const { messages, busy, ask, rate } = chat;
  const { submitter } = useAssistantAccess();
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" }); }, [messages, busy]);

  return (
    <div className="chat-body" ref={bodyRef} aria-live="polite">
      {messages.length === 0 && <ChatWelcome name={name} adminOnly={adminOnly} submitter={submitter} onAsk={ask} />}
      {messages.map((m, i) => {
        const wide = m.tables?.length || m.cards?.length ? " wide" : "";
        return (
          <div key={i} className={`msg-row ${m.role}${wide}`}>
            {m.role === "bot" && <ChatAvatar />}
            <div className={`msg ${m.role}${wide}`}>
              {m.role === "bot" ? <RichText text={m.text} /> : m.text}
              {m.cards?.map((c) => <DocCardView key={c.request_id} card={c} onNavigate={onNavigate} />)}
              {m.tables?.map((t, j) => <ResultTable key={`${t.title}-${j}`} table={t} onNavigate={onNavigate} />)}
              {m.role === "bot" && (m.usedData !== undefined) && (
                <div className="msg-meta">
                  {m.usedData
                    ? <span className="msg-source" title={m.queryLabel ?? undefined}><Database /> {m.queryLabel ?? "data antrean terkini"}</span>
                    : <span className="msg-source"><BookOpen /> {m.sources} kutipan SOP</span>}
                  {m.answerId && (
                    <span className="msg-rate">
                      <button type="button" aria-pressed={m.feedback === 1} onClick={() => rate(i, true)} title="Membantu" aria-label="Jawaban membantu"><ThumbsUp /></button>
                      <button type="button" aria-pressed={m.feedback === -1} onClick={() => rate(i, false)} title="Tidak membantu" aria-label="Jawaban tidak membantu"><ThumbsDown /></button>
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
      {busy && (
        <div className="msg-row bot">
          <ChatAvatar />
          <div className="msg bot typing" role="status" aria-label="Asisten sedang menyiapkan jawaban"><i /><i /><i /></div>
        </div>
      )}
    </div>
  );
}

/** Kolom pertanyaan. Enter mengirim, Shift+Enter baris baru. */
export function ChatInput({ chat, autoFocus }: { chat: ReturnType<typeof useAssistantChat>; autoFocus?: boolean }) {
  const [input, setInput] = useState("");
  const send = () => { if (input.trim() && !chat.busy) { chat.ask(input); setInput(""); } };
  const submit = (e: FormEvent) => { e.preventDefault(); send(); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
  };
  return (
    <form className="chat-form" onSubmit={submit}>
      <div className="chat-compose">
        <textarea rows={1} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey}
                  autoFocus={autoFocus} placeholder="Tulis pertanyaan tentang SOP atau data…"
                  aria-label="Pertanyaan" maxLength={2000} />
        <button className="chat-send" disabled={chat.busy || !input.trim()} aria-label="Kirim"><ArrowUp /></button>
      </div>
      <div className="chat-hint">
        <span><kbd>Enter</kbd> kirim · <kbd>Shift</kbd>+<kbd>Enter</kbd> baris baru</span>
        <span>AI bisa keliru, cek dokumen asli</span>
      </div>
    </form>
  );
}

/** Header Asisten: avatar, nama, status, dan tombol aksi. */
export function ChatHeader({ subtitle, children }: { subtitle: string; children?: ReactNode }) {
  return (
    <div className="chat-head">
      <ChatAvatar />
      <div className="chat-title">
        <b>Asisten AMIGA</b>
        <span><i className="chat-online" aria-hidden="true" />{subtitle}</span>
      </div>
      {children && <div className="chat-actions">{children}</div>}
    </div>
  );
}

export function scopeText(adminOnly: boolean, submitter: boolean) {
  return adminOnly ? "Menjawab dari SOP AMIGA"
    : submitter ? "SOP + data perusahaan Anda"
    : "SOP + data semua perusahaan";
}

/** Tombol chat Asisten AI di semua layar (kecuali halaman Asisten itu sendiri). */
export function Assistant() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { allowed, adminOnly, submitter } = useAssistantAccess();
  const [open, setOpen] = useState(false);
  const chat = useAssistantChat();

  if (!allowed || pathname.startsWith("/asisten")) return null;
  const fullUrl = chat.messages.length ? `/asisten?s=${encodeURIComponent(chat.session)}` : "/asisten";

  return (
    <>
      {open && (
        <section className="chat" aria-label="Asisten AMIGA">
          <ChatHeader subtitle={scopeText(adminOnly, submitter)}>
            <Link className="chat-icon-btn" to={fullUrl} title="Buka layar penuh" aria-label="Buka layar penuh"
                  onClick={() => setOpen(false)}><Maximize2 /></Link>
            <button type="button" className="chat-icon-btn" title="Percakapan baru" aria-label="Percakapan baru"
                    onClick={chat.reset}><RotateCcw /></button>
            <button type="button" className="chat-icon-btn" onClick={() => setOpen(false)} aria-label="Tutup asisten"><X /></button>
          </ChatHeader>
          <ChatThread chat={chat} adminOnly={adminOnly} name={user?.full_name} onNavigate={() => setOpen(false)} />
          <ChatInput chat={chat} autoFocus />
        </section>
      )}
      <button className={`fab${open ? " open" : ""}`} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <X size={18} /> : <Sparkles size={18} />} {open ? "Tutup" : "Tanya Asisten"}
      </button>
    </>
  );
}

/** Tebal (**teks**) dan baris daftar ("- ") dari jawaban model, tanpa memasukkan HTML mentah. */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i, all) => {
        const bullet = /^\s*[-*•]\s+/.test(line);
        const body = line.replace(/^\s*[-*•]\s+/, "").replace(/^#{1,4}\s+/, "");
        const parts = body.split(/\*\*(.+?)\*\*/g).map((p, j) => (j % 2 ? <b key={j}>{p}</b> : <Fragment key={j}>{p}</Fragment>));
        return (
          <Fragment key={i}>
            {bullet ? <span className="msg-bullet">{parts}</span> : parts}
            {i < all.length - 1 && !bullet && "\n"}
          </Fragment>
        );
      })}
    </>
  );
}

/** Hanya tautan internal aplikasi (diawali "/"), supaya isi data tidak bisa membuat tautan keluar. */
const internal = (href: string | null | undefined): href is string => Boolean(href && href.startsWith("/") && !href.startsWith("//"));

function LinkRow({ links, onNavigate }: { links?: AssistantLink[]; onNavigate?: () => void }) {
  const safe = (links ?? []).filter((l) => internal(l.href));
  if (!safe.length) return null;
  return (
    <div className="chat-links">
      {safe.map((l) => (
        <Link key={l.href + l.label} to={l.href} className={`chat-link${l.primary ? " primary" : ""}`} onClick={onNavigate}>
          {l.label} <ArrowUpRight size={13} />
        </Link>
      ))}
    </div>
  );
}

/** Kartu dokumen: status, tahapan progres, detail, riwayat, saran langkah berikutnya, dan tautan. */
function DocCardView({ card, onNavigate }: { card: DocCard; onNavigate?: () => void }) {
  const [showHistory, setShowHistory] = useState(false);
  return (
    <div className="doc-card">
      <div className="doc-card-head">
        {internal(card.href)
          ? <Link to={card.href} className="mono doc-card-id" onClick={onNavigate}>{card.request_id}</Link>
          : <b className="mono">{card.request_id}</b>}
        <StatusBadge status={card.status} />
      </div>
      <div className="doc-card-sub">{card.subtitle}</div>
      <ol className="doc-steps">
        {card.steps.map((s) => (
          <li key={s.label} className={s.state} title={[s.at, s.detail].filter(Boolean).join(" · ")}>
            <span>{s.state === "done" ? <Check size={11} /> : s.state === "bad" ? <X size={11} /> : null}</span>
            <b>{s.label}</b>
            <small>{s.detail ?? s.at ?? ""}</small>
          </li>
        ))}
      </ol>
      {card.hint && <div className={`doc-card-hint${card.status === "EXCEPTION" ? " warn" : ""}`}><Lightbulb size={14} /> {card.hint}</div>}
      <dl className="chat-record">
        {card.fields.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
      </dl>
      {card.history.length > 0 && (
        <div className="doc-history">
          <button type="button" onClick={() => setShowHistory((v) => !v)} aria-expanded={showHistory}>
            <ChevronDown size={14} style={{ transform: showHistory ? "rotate(180deg)" : undefined }} />
            Riwayat aktivitas ({card.history.length} terbaru)
          </button>
          {showHistory && (
            <ul>
              {card.history.map((h, i) => (
                <li key={i}><small>{h.at}</small><span><b>{h.action}</b> · {h.actor}{h.note && <> · {h.note}</>}</span></li>
              ))}
            </ul>
          )}
        </div>
      )}
      <LinkRow links={card.links} onNavigate={onNavigate} />
    </div>
  );
}

function ResultTable({ table, onNavigate }: { table: DataTable; onNavigate?: () => void }) {
  const record = table.columns.length === 2 && table.columns[0] === "Kolom";
  return (
    <div className="chat-table">
      <div className="chat-table-head"><b>{table.title}</b>{table.note && <span>{table.note}</span>}</div>
      {table.rows.length === 0 ? <div className="muted" style={{ padding: "6px 8px" }}>Tidak ada data yang cocok.</div> : record ? (
        <dl className="chat-record">
          {table.rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
        </dl>
      ) : (
        <div className="chat-table-scroll">
          <table>
            <thead><tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => {
              const href = table.row_links?.[i];
              return (
                <tr key={i}>{r.map((v, j) => (
                  <td key={j}>{j === 0 && internal(href) ? <Link to={href} onClick={onNavigate}>{v}</Link> : v}</td>
                ))}</tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
      <LinkRow links={table.links} onNavigate={onNavigate} />
    </div>
  );
}
