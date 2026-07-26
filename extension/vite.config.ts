import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Popup + options (React, multi-page). There is no background service
// worker or content script — every check is triggered on-demand from
// the popup, which talks to the backend directly (see src/lib/api.ts)
// and reads the active tab via chrome.scripting (see src/popup/Popup.tsx).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: path.resolve(__dirname, "src/popup/index.html"),
        options: path.resolve(__dirname, "src/options/index.html"),
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/chunk-[hash].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
