import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api vers le backend FastAPI en développement — évite les soucis
// de CORS et reflète la topologie de production (Nginx en frontal).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // 127.0.0.1 explicite (pas "localhost") : évite l'échec de proxy
        // quand Node résout "localhost" en ::1 alors qu'uvicorn n'écoute
        // qu'en IPv4.
        target: "http://127.0.0.1:9000",
        changeOrigin: true,
      },
    },
  },
});
