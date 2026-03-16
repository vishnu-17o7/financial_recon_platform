import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://localhost:8000",
      "/ingestion": "http://localhost:8000",
      "/reconciliation": "http://localhost:8000"
    }
  },
  build: {
    outDir: "../app/ui",
    emptyOutDir: true
  }
});
