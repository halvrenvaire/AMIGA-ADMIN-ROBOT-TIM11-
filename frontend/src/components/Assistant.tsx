import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowUpRight, Bot, Check, ChevronDown, Database, Lightbulb, Loader2, Maximize2, MessageCircle, RotateCcw, Send, X } from "lucide-react";
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

export const newSession = () => `web-${crypto.randomUUID()}`;

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

/** Daftar pesan, termasuk sapaan + saran pertanyaan saat percakapan masih kosong. */
export function ChatThread({ chat, adminOnly, greeting, onNavigate }: {
  chat: ReturnType<typeof useAssistantChat>; adminOnly: boolean; greeting: ReactNode; onNavigate?: () => void;
}) {
  const { messages, busy, ask, rate } = chat;
  const { submitter } = useAssistantAccess();
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight); }, [messages, busy]);

  return (
    <div className="chat-body" ref={bodyRef}>
      {messages.length === 0 && (
        <>
          <div className="msg bot">{greeting}</div>
          <div className="suggest">{suggestionsFor(adminOnly, submitter).map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
        </>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`msg ${m.role}${m.tables?.length || m.cards?.length ? " wide" : ""}`}>
          {m.role === "bot" ? <RichText text={m.text} /> : m.text}
          {m.cards?.map((c) => <DocCardView key={c.request_id} card={c} onNavigate={onNavigate} />)}
          {m.tables?.map((t, j) => <ResultTable key={`${t.title}-${j}`} table={t} onNavigate={onNavigate} />)}
          {m.role === "bot" && (m.usedData !== undefined) && (
            <div className="msg-meta">
              {m.usedData
                ? <span title={m.queryLabel ?? undefined}>
                    <Database size={12} style={{ verticalAlign: "-2px" }} /> {m.queryLabel ?? "data antrean terkini"}
                  </span>
                : <span>{m.sources} kutipan SOP</span>}
              {m.answerId && (
                <>
                  <button aria-pressed={m.feedback === 1} onClick={() => rate(i, true)} title="Membantu">👍</button>
                  <button aria-pressed={m.feedback === -1} onClick={() => rate(i, false)} title="Tidak membantu">👎</button>
                </>
              )}
            </div>
          )}
        </div>
      ))}
      {busy && <div className="msg bot"><Loader2 className="spin" size={14} /> Menyiapkan jawaban…</div>}
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
      <textarea className="input" rows={1} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey}
                autoFocus={autoFocus} placeholder="Tanya tentang SOP atau data… (Enter kirim, Shift+Enter baris baru)"
                aria-label="Pertanyaan" maxLength={2000} />
      <button className="btn primary" disabled={chat.busy || !input.trim()} aria-label="Kirim"><Send /></button>
    </form>
  );
}

export function greetingText(name: string | undefined, adminOnly: boolean, submitter = false) {
  const data = submitter
    ? "Tanya juga soal pengajuan perusahaan Anda, mis. progres, invoice yang ada kendala, atau voucher yang sudah terbit"
    : "Tanya juga soal data, mis. progres PIC, beban reviewer, atau invoice yang bermasalah";
  return (
    <>
      Halo {name?.split(" ")[0]}! Saya asisten pribadi akun Anda. Saya menjawab dari SOP AMIGA
      {adminOnly
        ? " dan data administrasi: akun pengguna, peran, dan klien. Hasilnya bisa diklik untuk membuka halaman terkait."
        : `. ${data}; jawabannya diambil langsung dari sistem dan bisa diklik untuk membuka halaman terkait. Bisa lanjut bertanya, mis. "tampilkan detail dokumen tersebut".`}
    </>
  );
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
          <div className="chat-head">
            <Bot size={18} color="var(--primary)" />
            <b>Asisten AMIGA</b>
            <Link className="btn ghost sm" to={fullUrl} title="Buka layar penuh" aria-label="Buka layar penuh"
                  onClick={() => setOpen(false)}><Maximize2 /></Link>
            <button className="btn ghost sm" title="Percakapan baru" onClick={chat.reset}><RotateCcw /></button>
            <button className="btn ghost sm" onClick={() => setOpen(false)} aria-label="Tutup asisten"><X /></button>
          </div>
          <ChatThread chat={chat} adminOnly={adminOnly} greeting={greetingText(user?.full_name, adminOnly, submitter)}
                      onNavigate={() => setOpen(false)} />
          <ChatInput chat={chat} autoFocus />
        </section>
      )}
      <button className="fab" onClick={() => setOpen((o) => !o)}>
        {open ? <X size={18} /> : <MessageCircle size={18} />} Asisten
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
