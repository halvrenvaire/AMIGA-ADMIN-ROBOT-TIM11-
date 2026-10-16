import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MessageSquarePlus, Trash2 } from "lucide-react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  ChatHeader, ChatInput, ChatThread, scopeText, useAssistantAccess, useAssistantChat,
} from "../components/Assistant";
import { Alert, useApi } from "../components/ui";
import { waktu } from "../format";
import type { AssistantSession } from "../types";

/** Asisten AI layar penuh: riwayat percakapan di kiri, percakapan aktif di kanan. */
export function AssistantPage() {
  const { user } = useAuth();
  const { adminOnly, submitter } = useAssistantAccess();
  const [params, setParams] = useSearchParams();
  const sessions = useApi(() => api.get<AssistantSession[]>("/ask-agent/sessions"), []);
  const chat = useAssistantChat(() => sessions.reload());
  const [error, setError] = useState<string | null>(null);
  const active = params.get("s");

  // Percakapan dari URL (mis. dibuka dari widget mengambang atau dari riwayat)
  useEffect(() => {
    if (!active || active === chat.session) return;
    setError(null);
    chat.load(active).catch(() => { setParams({}, { replace: true }); chat.reset(); });
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pertanyaan pertama di percakapan baru: catat sesinya di URL supaya bisa dimuat ulang
  useEffect(() => {
    if (chat.messages.length && active !== chat.session) setParams({ s: chat.session }, { replace: true });
  }, [chat.messages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  function startNew() { chat.reset(); setParams({}); }

  async function remove(s: AssistantSession) {
    setError(null);
    try {
      await api.del(`/ask-agent/sessions/${encodeURIComponent(s.session_id)}`);
      if (s.session_id === chat.session) startNew();
      sessions.reload();
    } catch (e) { setError((e as Error).message); }
  }

  const list = sessions.data ?? [];
  return (
    <div className="assistant-page">
      <aside className="card assistant-history" aria-label="Riwayat percakapan">
        <button className="btn primary" onClick={startNew}><MessageSquarePlus /> Percakapan baru</button>
        <div className="nav-label" style={{ padding: "4px 4px 0" }}>Riwayat</div>
        {list.length === 0 && <p className="muted" style={{ fontSize: 12.5, margin: 0, padding: "0 4px" }}>Belum ada percakapan.</p>}
        <ul>
          {list.map((s) => (
            <li key={s.session_id} className={s.session_id === chat.session ? "on" : undefined}>
              <button className="assistant-history-item" onClick={() => setParams({ s: s.session_id })} title={s.title}>
                <span>{s.title}</span>
                <small>{waktu(s.last_activity)}</small>
              </button>
              <button className="btn ghost sm icon-btn" aria-label={`Hapus percakapan ${s.title}`} title="Hapus percakapan"
                      onClick={() => remove(s)}><Trash2 /></button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="card assistant-main" aria-label="Asisten AMIGA">
        <ChatHeader subtitle={scopeText(adminOnly, submitter)} />
        {(error || sessions.error) && <div style={{ padding: "10px 14px 0" }}><Alert>{error ?? sessions.error}</Alert></div>}
        <ChatThread chat={chat} adminOnly={adminOnly} name={user?.full_name} />
        <ChatInput chat={chat} autoFocus />
      </section>
    </div>
  );
}
