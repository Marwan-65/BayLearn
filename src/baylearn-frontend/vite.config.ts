import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/run": API_TARGET,
      "/health": API_TARGET,
      "/init": API_TARGET,
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
  },
});
