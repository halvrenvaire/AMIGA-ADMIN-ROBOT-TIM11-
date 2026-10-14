import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

export type ThemeMode = "light" | "dark" | "system";
type Resolved = "light" | "dark";

const KEY = "amiga.theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

const resolve = (mode: ThemeMode): Resolved => (mode === "system" ? (media().matches ? "dark" : "light") : mode);

const ThemeContext = createContext<{ mode: ThemeMode; resolved: Resolved; setMode: (m: ThemeMode) => void } | null>(null);

/** Tema terang/gelap/ikut sistem. Atribut data-theme di <html> dipasang lebih awal oleh index.html. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [resolved, setResolved] = useState<Resolved>(() => resolve(readMode()));

  useEffect(() => {
    const apply = () => {
      const r = resolve(mode);
      setResolved(r);
      document.documentElement.dataset.theme = r;
    };
    apply();
    if (mode !== "system") return;
    const mq = media();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [mode]);

  const setMode = (m: ThemeMode) => {
    try {
      if (m === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, m);
    } catch {
      /* penyimpanan browser tidak tersedia: tema tetap berlaku sampai halaman dimuat ulang */
    }
    setModeState(m);
  };

  return <ThemeContext.Provider value={{ mode, resolved, setMode }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme harus dipakai di dalam ThemeProvider");
  return ctx;
}

const NEXT: Record<ThemeMode, ThemeMode> = { light: "dark", dark: "system", system: "light" };
const LABEL: Record<ThemeMode, string> = { light: "Tema terang", dark: "Tema gelap", system: "Ikut sistem" };

/** Tombol ganti tema: terang → gelap → ikut sistem. */
export function ThemeToggle({ className = "btn ghost sm" }: { className?: string }) {
  const { mode, setMode } = useTheme();
  const Icon = mode === "light" ? Sun : mode === "dark" ? Moon : Monitor;
  return (
    <button type="button" className={className} onClick={() => setMode(NEXT[mode])}
            title={`${LABEL[mode]} (klik untuk ${LABEL[NEXT[mode]].toLowerCase()})`} aria-label={`Ganti tema, sekarang ${LABEL[mode].toLowerCase()}`}>
      <Icon />
    </button>
  );
}
