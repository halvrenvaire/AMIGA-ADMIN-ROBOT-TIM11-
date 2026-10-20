import { useEffect, useState, type ReactNode } from "react";
import { ArrowDownCircle } from "lucide-react";

/** fix = perlu diisi/diperbaiki PIC (oranye), block = menghalangi pengiriman (merah), ok = lengkap, info = informasi. */
export type SectionState = "fix" | "block" | "ok" | "info";
export interface NavSection { id: string; label: string; state: SectionState; note?: string }

const anchorId = (id: string) => `sec-${id}`;

/** Gulir ke bagian, sorot sebentar, dan bila bagian itu perlu diisi, arahkan kursor ke kolom pertama yang
 *  ditandai atau masih kosong. */
export function jumpTo(id: string, focus = true) {
  const el = document.getElementById(anchorId(id));
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.remove("sec-flash");
  void el.offsetWidth; // mulai ulang animasi sorotan
  el.classList.add("sec-flash");
  if (!focus) return;
  const inputs = [...el.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input.input:not(:disabled), select.input:not(:disabled)")];
  const target = inputs.find((i) => i.classList.contains("flag")) ?? inputs.find((i) => i instanceof HTMLInputElement && i.value === "");
  if (target) setTimeout(() => target.focus({ preventScroll: true }), 450);
}

/** Bagian yang sedang terlihat di layar (bagian teratas yang melewati garis bawah topbar). */
function useScrollSpy(ids: string[]) {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);
  const key = ids.join("|");
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(anchorId(id))).filter((e): e is HTMLElement => Boolean(e));
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const visible = new Map<string, number>();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        const id = e.target.id.slice(4);
        if (e.isIntersecting) visible.set(id, e.boundingClientRect.top); else visible.delete(id);
      });
      const first = ids.find((id) => visible.has(id));
      if (first) setActive(first);
    }, { rootMargin: "-80px 0px -55% 0px" });
    els.forEach((e) => observer.observe(e));
    return () => observer.disconnect();
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}

/** Navigasi cepat panel kanan layar tinjau: daftar bagian dengan warna status. Oranye = perlu diisi/diperbaiki. */
export function SectionNav({ sections }: { sections: NavSection[] }) {
  const active = useScrollSpy(sections.map((s) => s.id));
  const todo = sections.filter((s) => s.state === "fix" || s.state === "block");
  const next = () => {
    if (!todo.length) return;
    const from = sections.findIndex((s) => s.id === active);
    const after = todo.find((s) => sections.indexOf(s) > from) ?? todo[0];
    jumpTo(after.id);
  };
  return (
    <nav className="sec-nav" aria-label="Navigasi bagian">
      <div className="sec-nav-head">
        <b>Navigasi cepat</b>
        <small>{todo.length ? `${todo.length} bagian perlu diisi/diperbaiki` : "Semua bagian lengkap"}</small>
      </div>
      <ol>
        {sections.map((s) => (
          <li key={s.id}>
            <button type="button" className={`sec-item ${s.state} ${active === s.id ? "active" : ""}`}
                    aria-current={active === s.id ? "location" : undefined}
                    onClick={() => jumpTo(s.id, s.state === "fix" || s.state === "block")}>
              <i aria-hidden="true" />
              <span>{s.label}{s.note && <small>{s.note}</small>}</span>
            </button>
          </li>
        ))}
      </ol>
      {todo.length > 0 && (
        <button type="button" className="btn sm sec-next" onClick={next}><ArrowDownCircle /> Perbaikan berikutnya</button>
      )}
      <div className="sec-legend" aria-hidden="true">
        <span><i className="fix" /> perlu diisi</span><span><i className="block" /> menghalangi kirim</span><span><i className="ok" /> lengkap</span>
      </div>
    </nav>
  );
}

/** Pembungkus bagian yang bisa dituju dari navigasi cepat. */
export function Anchor({ id, children }: { id: string; children: ReactNode }) {
  return <div id={anchorId(id)} className="sec-anchor">{children}</div>;
}
