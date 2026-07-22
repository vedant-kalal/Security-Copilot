import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Main build pass: popup + options (React, multi-page) and the
// background service worker (ES module — MV3 supports "type": "module"
// service workers). The content script is built separately (see
// vite.content.config.ts) because content scripts must ship as a
// classic IIFE script for maximum browser compatibility.
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
        background: path.resolve(__dirname, "src/background/index.ts"),
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/chunk-[hash].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
