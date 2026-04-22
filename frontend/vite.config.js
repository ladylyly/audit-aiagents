import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy all /api/* calls to the local Flask API server
      "/api": {
        target: "http://localhost:7002",
        changeOrigin: true,
      },
    },
  },
});
