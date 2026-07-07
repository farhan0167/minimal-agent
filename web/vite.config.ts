import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The App serves its routes under /api natively, so no rewrite —
    // dev mode forwards the prefix as-is to a running `app.serve()`.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
      },
    },
  },
});
