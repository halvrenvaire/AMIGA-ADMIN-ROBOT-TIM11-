// Klien API: token login disimpan di localStorage, semua request lewat proxy /api (vite.config.ts)
const BASE = import.meta.env.VITE_API_URL ?? "/api";
const TOKEN_KEY = "amiga.token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value: string) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    // Error validasi FastAPI: [{loc, msg}]
    return detail.map((d: { loc?: string[]; msg?: string }) => `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg}`).join("; ");
  }
  return status >= 500 ? "Server sedang bermasalah. Coba lagi beberapa saat lagi." : `Permintaan gagal (${status}).`;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const t = token.get();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new ApiError(0, "Tidak bisa terhubung ke server. Pastikan backend berjalan di port 8000.");
  }
  if (res.status === 401 && t) onUnauthorized();
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detailMessage(body, res.status));
  }
  return res;
}

/** Isi respons JSON; 204 No Content menjadi undefined. */
const json = <T>(res: Response) => (res.status === 204 ? undefined : res.json()) as Promise<T>;

export const api = {
  get: async <T>(path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
    const qs = new URLSearchParams();
    Object.entries(params ?? {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== false) qs.set(k, String(v));
    });
    const query = qs.toString();
    return json<T>(await request(path + (query ? `?${query}` : "")));
  },
  post: async <T>(path: string, body?: unknown) =>
    json<T>(await request(path, {
      method: "POST",
      body: body instanceof FormData || body instanceof URLSearchParams ? body : JSON.stringify(body ?? {}),
    })),
  put: async <T>(path: string, body: unknown) =>
    json<T>(await request(path, { method: "PUT", body: JSON.stringify(body) })),
  patch: async <T>(path: string, body: unknown) =>
    json<T>(await request(path, { method: "PATCH", body: JSON.stringify(body) })),
  del: async <T>(path: string) => json<T>(await request(path, { method: "DELETE" })),
  blob: async (path: string) => (await request(path)).blob(),
};
