/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser talks to the API through this proxy, so the backend needs no CORS change
// and the UI always calls the same-origin path `/api/v1`. Point it at another backend
// with ELIGICORE_API_URL (no trailing slash), e.g. ELIGICORE_API_URL=http://127.0.0.1:8001.
const apiTarget = process.env.ELIGICORE_API_URL ?? "http://127.0.0.1:8000";

const proxy = {
  "/api": { target: apiTarget, changeOrigin: false },
};

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
