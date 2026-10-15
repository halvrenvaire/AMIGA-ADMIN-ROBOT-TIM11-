import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bot, Database, Loader2, Maximize2, MessageCircle, RotateCcw, Send, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AskAgentResponse, AssistantMessage, DataTable } from "../types";

export interface Message {
  role: "user" | "bot";
  text: string;
  answerId?: number | null;
  usedData?: boolean;
  sources?: number;
  feedback?: 1 | -1;
  queryLabel?: string | null;
  tables?: DataTable[];
}

export const newSession = () => `web-${crypto.randomUUID()}`;

/** Siapa yang boleh memakai Asisten: Finance Reviewer, Service Lead, System Admin (System Admin: SOP saja). */
export function useAssistantAccess() {
  const { user, has } = useAuth();
  const allowed = has("FINANCE_REVIEWER", "SERVICE_LEAD", "SYSTEM_ADMIN");
  const adminOnly = user?.roles.length === 1 && user.roles[0] === "SYSTEM_ADMIN";
  return { allowed, adminOnly };
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
        queryLabel: res.query_label, tables: res.data_tables,
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
    })));
  }, []);

  return { messages, busy, session, ask, rate, reset, load };
}

export function suggestionsFor(adminOnly: boolean) {
  return adminOnly
    ? ["Apa itu Segregation of Duties?", "Siapa yang boleh mengelola akun?"]
    : ["Progres PIC Klien gimana?", "Progres Finance Reviewer minggu ini", "Invoice mana yang lewat tenggat?",
       "Apa arti MISSING_EVIDENCE?"];
}

/** Daftar pesan, termasuk sapaan + saran pertanyaan saat percakapan masih kosong. */
export function ChatThread({ chat, adminOnly, greeting }: {
  chat: ReturnType<typeof useAssistantChat>; adminOnly: boolean; greeting: ReactNode;
}) {
  const { messages, busy, ask, rate } = chat;
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight); }, [messages, busy]);

  return (
    <div className="chat-body" ref={bodyRef}>
      {messages.length === 0 && (
        <>
          <div className="msg bot">{greeting}</div>
          <div className="suggest">{suggestionsFor(adminOnly).map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
        </>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`msg ${m.role}${m.tables?.length ? " wide" : ""}`}>
          {m.role === "bot" ? <RichText text={m.text} /> : m.text}
          {m.tables?.map((t, j) => <ResultTable key={`${t.title}-${j}`} table={t} />)}
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

export function greetingText(name: string | undefined, adminOnly: boolean) {
  return (
    <>
      Halo {name?.split(" ")[0]}! Saya menjawab dari SOP AMIGA
      {adminOnly ? "." : ". Tanya juga soal data, mis. progres PIC, beban reviewer, atau invoice yang bermasalah; jawabannya diambil langsung dari sistem. Bisa lanjut bertanya, mis. \"tampilkan detail dokumen tersebut\"."}
    </>
  );
}

/** Tombol chat Asisten AI di semua layar (kecuali halaman Asisten itu sendiri). */
export function Assistant() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { allowed, adminOnly } = useAssistantAccess();
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
          <ChatThread chat={chat} adminOnly={adminOnly} greeting={greetingText(user?.full_name, adminOnly)} />
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

function ResultTable({ table }: { table: DataTable }) {
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
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
