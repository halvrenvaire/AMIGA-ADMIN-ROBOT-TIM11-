import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, token } from "./api";
import type { Me, Role } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => void;
  has: (...roles: Role[]) => boolean;
  /** Perbarui data pengguna (dan token, mis. setelah ganti password) tanpa login ulang. */
  updateSession: (user: Me, newToken?: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(Boolean(token.get()));

  const logout = useCallback(() => {
    token.clear();
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!token.get()) return;
    api.get<Me>("/auth/me").then(setUser).catch(logout).finally(() => setLoading(false));
  }, [logout]);

  const login = async (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    const res = await api.post<{ access_token: string; user: Me }>("/auth/login", form);
    token.set(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const has = (...roles: Role[]) => Boolean(user?.roles.some((r) => roles.includes(r)));

  const updateSession = (next: Me, newToken?: string) => {
    if (newToken) token.set(newToken);
    setUser(next);
  };

  return <AuthContext.Provider value={{ user, loading, login, logout, has, updateSession }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus dipakai di dalam AuthProvider");
  return ctx;
}

/** Halaman awal sesuai peran utama. */
export function homePath(roles: Role[]): string {
  if (roles.some((r) => r !== "SYSTEM_ADMIN")) return "/dashboard";
  if (roles.includes("SYSTEM_ADMIN")) return "/admin/pengguna";
  return "/login";
}
