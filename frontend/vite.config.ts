import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/* diteruskan ke backend FastAPI, jadi frontend dan API satu origin saat development
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Gagal dengan jelas bila 5173 terpakai, jangan pindah diam-diam ke port lain (mis. port E2E)
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
