import path from "node:path";
import { defineConfig } from "vite";

// Separate build pass for the content script: bundled as a single
// dependency-free IIFE (no ES module imports/exports at the top level)
// so it works as a classic injected script on every supported Chrome
// version, independent of the main ESM build in vite.config.ts.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: false,
    lib: {
      entry: path.resolve(__dirname, "src/content/index.ts"),
      name: "SecurityCopilotContentScript",
      formats: ["iife"],
      fileName: () => "assets/content.js",
    },
    rollupOptions: {
      output: {
        extend: true,
      },
    },
  },
});
