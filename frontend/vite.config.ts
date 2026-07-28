import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Dev only: the Vite server forwards API calls to FastAPI.
      // In production, FastAPI serves the built frontend itself, so no proxy exists.
      "/api": "http://127.0.0.1:8000",
    },
  },
})
