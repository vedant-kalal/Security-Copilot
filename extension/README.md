# security-copilot browser extension

Chrome Manifest V3 extension for the security-copilot agent (`backend/`). It does **not** run any AI models or
sandboxing itself — it's a thin, on-demand trigger: click the toolbar icon, click a button, get a verdict. The
backend performs all the investigation (headless browser, WHOIS/VirusTotal, an LLM, web search).

There is no auth and nothing runs automatically in the background — see `backend/README.md`'s POC scope for why
(no DB beyond SQLite, no auth, terminal-first). Every check is a deliberate click.

## What it does

- **Popup** (`src/popup/`) — two buttons on the current tab: **Check this URL** (`POST /check-links`) and
  **Check page text** (grabs `document.body.innerText` via `chrome.scripting`, then `POST /check-email`). Shows
  the verdict (label, confidence, reason, mitigation, and — if the agent suspected brand impersonation — links to
  the real site), badges the tab icon (red `!` for dangerous, orange `!` for suspicious), and links out to the
  full report in the backend's UI.
- **Options page** (`src/options/`) — the one setting: the backend's base URL (defaults to
  `http://127.0.0.1:8010`, matching `backend/README.md`).

There is no background service worker and no content script injected into every page — `chrome.scripting`
(triggered from the popup, covered by the `activeTab` permission granted when you click the toolbar icon) reads
the active tab's text on demand instead.

## Setup

```bash
cd extension
npm install
npm run build
```

This produces a complete unpacked extension in `extension/dist/`.

## Load into Chrome

1. Make sure the backend is running first (`cd backend && uvicorn api.app:app --port 8010` — see
   `backend/README.md`).
2. Open `chrome://extensions`.
3. Enable **Developer mode** (top right).
4. Click **Load unpacked** and select `extension/dist/`.
5. Click the security-copilot icon in the toolbar on any `http(s)://` page and use **Check this URL** or
   **Check page text**.
6. If your backend isn't on `http://127.0.0.1:8010`, open the extension's **Settings** (gear icon in the popup,
   or right-click the toolbar icon → Options) and change the URL.

## Development

```bash
npm run dev        # rebuilds on file changes; reload the unpacked extension in chrome://extensions after each change
npm run typecheck  # strict TypeScript check, no build
```

## Build architecture

One Vite build pass (`vite.config.ts`) compiles the popup and options pages (React, multi-page) as ES modules.
`scripts/copy-assets.mjs` flattens Vite's nested HTML output to `popup.html` / `options.html` at the root of
`dist/` (matching `manifest.json`) and copies in `manifest.json` + icons.
