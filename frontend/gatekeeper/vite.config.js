import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Proxy API requests to backend
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  // Handle client-side routing for SPA
  build: {
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
});
