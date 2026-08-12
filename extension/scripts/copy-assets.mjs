/**
 * Post-build step:
 *   1. Flatten Vite's nested HTML output (dist/src/popup/index.html,
 *      dist/src/options/index.html, dist/src/blocked/index.html) to
 *      dist/popup.html, dist/options.html, dist/blocked.html — matching
 *      the paths manifest.json/background.ts's chrome.runtime.getURL()
 *      calls expect. This is safe because Vite emits root-absolute asset
 *      URLs ("/assets/popup.js"), which resolve correctly under
 *      chrome-extension://<id>/... regardless of which folder the HTML
 *      file itself lives in.
 *   2. Copy manifest.json and icons/ into dist/ so the folder is a
 *      complete, loadable unpacked extension.
 */
import { cpSync, existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const distDir = join(root, "dist");

if (!existsSync(distDir)) {
  mkdirSync(distDir, { recursive: true });
}

const relocations = [
  [join(distDir, "src", "popup", "index.html"), join(distDir, "popup.html")],
  [join(distDir, "src", "options", "index.html"), join(distDir, "options.html")],
  [join(distDir, "src", "blocked", "index.html"), join(distDir, "blocked.html")],
];

for (const [from, to] of relocations) {
  if (existsSync(from)) {
    renameSync(from, to);
  }
}

const nestedSrcDir = join(distDir, "src");
if (existsSync(nestedSrcDir)) {
  rmSync(nestedSrcDir, { recursive: true, force: true });
}

cpSync(join(root, "manifest.json"), join(distDir, "manifest.json"));
cpSync(join(root, "public", "icons"), join(distDir, "icons"), { recursive: true });

console.log("Flattened popup/options/blocked HTML and copied manifest.json + icons/ into dist/");

