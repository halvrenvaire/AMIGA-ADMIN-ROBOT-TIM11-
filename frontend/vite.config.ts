import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/* diteruskan ke backend FastAPI, jadi frontend dan API satu origin saat development
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
