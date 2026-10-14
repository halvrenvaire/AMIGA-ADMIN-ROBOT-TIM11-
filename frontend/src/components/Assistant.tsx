import { useEffect, useRef, useState, type FormEvent } from "react";
import { Bot, Database, Loader2, MessageCircle, RotateCcw, Send, X } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AskAgentResponse } from "../types";

interface Message {
  role: "user" | "bot";
  text: string;
  answerId?: number | null;
  usedData?: boolean;
  sources?: number;
  feedback?: 1 | -1;
}

const newSession = () => `web-${crypto.randomUUID()}`;

/** Tombol chat Asisten AI di semua layar, hanya untuk Finance Reviewer, Service Lead, System Admin. */
export function Assistant() {
  const { user, has } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState(newSession);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight); }, [messages, busy]);

  if (!has("FINANCE_REVIEWER", "SERVICE_LEAD", "SYSTEM_ADMIN")) return null;
  const adminOnly = user?.roles.length === 1 && user.roles[0] === "SYSTEM_ADMIN";
  const suggestions = adminOnly
    ? ["Apa itu Segregation of Duties?", "Siapa yang boleh mengelola akun?"]
    : ["Dokumen apa yang tenggatnya dekat?", "Apa arti MISSING_EVIDENCE?", "Beban reviewer siapa yang paling banyak?"];

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.post<AskAgentResponse>("/ask-agent", { question, session_id: session });
      setMessages((m) => [...m, {
        role: "bot", text: res.answer, answerId: res.answer_id, usedData: res.used_queue_data, sources: res.sources.length,
      }]);
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

  const submit = (e: FormEvent) => { e.preventDefault(); ask(input); };

  return (
    <>
      {open && (
        <section className="chat" aria-label="Asisten AMIGA">
          <div className="chat-head">
            <Bot size={18} color="var(--primary)" />
            <b>Asisten AMIGA</b>
            <button className="btn ghost sm" title="Percakapan baru" onClick={() => { setMessages([]); setSession(newSession()); }}>
              <RotateCcw />
            </button>
            <button className="btn ghost sm" onClick={() => setOpen(false)} aria-label="Tutup asisten"><X /></button>
          </div>
          <div className="chat-body" ref={bodyRef}>
            {messages.length === 0 && (
              <>
                <div className="msg bot">
                  Halo {user?.full_name.split(" ")[0]}! Saya menjawab dari SOP AMIGA
                  {adminOnly ? "." : " dan data antrean klien yang ditugaskan kepada Anda."}
                </div>
                <div className="suggest">{suggestions.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
              </>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.text}
                {m.role === "bot" && (m.usedData !== undefined) && (
                  <div className="msg-meta">
                    {m.usedData
                      ? <span><Database size={12} style={{ verticalAlign: "-2px" }} /> data antrean terkini</span>
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
          <form className="chat-form" onSubmit={submit}>
            <input className="input" value={input} onChange={(e) => setInput(e.target.value)}
                   placeholder="Tanya tentang SOP atau antrean…" aria-label="Pertanyaan" maxLength={2000} />
            <button className="btn primary" disabled={busy || !input.trim()} aria-label="Kirim"><Send /></button>
          </form>
        </section>
      )}
      <button className="fab" onClick={() => setOpen((o) => !o)}>
        {open ? <X size={18} /> : <MessageCircle size={18} />} Asisten
      </button>
    </>
  );
}
