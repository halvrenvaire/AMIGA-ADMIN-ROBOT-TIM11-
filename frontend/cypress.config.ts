import { defineConfig } from "cypress";

// E2E berjalan terhadap frontend :5180 → backend :8001 dengan database *_test (lihat scripts/run_e2e.sh)
export default defineConfig({
  e2e: {
    baseUrl: "http://localhost:5180",
    defaultCommandTimeout: 10_000,
    viewportWidth: 1440,
    viewportHeight: 900,
    video: false,
    // Screenshot saat gagal bisa macet di Electron headless dan menutupi pesan error asli
    screenshotOnRunFailure: false,
    supportFile: "cypress/support/e2e.ts",
  },
});
