# SentinelAI Browser Extension

Chrome Manifest V3 extension: the telemetry source for SentinelAI (architecture doc section 7). It does **not**
run any AI models itself — it collects events and renders the popup; the backend performs all intelligence.

## What it does

- **Background service worker** (`src/background/`) — watches top-level navigations and submits each URL to
  `POST /phishing/check`; watches downloads and reports them as events; relays form-submission signals from the
  content script; sends a periodic device heartbeat.
- **Content script** (`src/content/`) — a small, dependency-free script that detects password-field form
  submissions and messages the background worker (never talks to the backend directly).
- **Popup** (`src/popup/`) — shows the current tab's risk verdict with **View Details / Report / Continue /
  Leave Site** actions when a threat is detected, or a calm "No threats detected" state otherwise.
- **Options page** (`src/options/`) — sign in / create an account, and configure the backend API URL.

## Setup

```bash
cd extension
cp .env.example .env   # documents the default API URL; the real setting lives in the Options page at runtime
npm install
npm run build
```

This produces a complete unpacked extension in `extension/dist/`.

## Load into Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode** (top right).
3. Click **Load unpacked** and select `extension/dist/`.
4. Click the SentinelAI icon in the toolbar, then **New here? Create an account in Settings** (or sign in if
   you've already run `python scripts/seed_db.py`, using `demo@sentinelai.io` / `SentinelDemo123!`).
5. By default the extension talks to `http://localhost:8000/api/v1` — change this on the Options page if your
   backend runs elsewhere.

## Development

```bash
npm run dev        # rebuilds on file changes; reload the unpacked extension in chrome://extensions after each change
npm run typecheck  # strict TypeScript check, no build
```

## Build architecture

Two separate Vite build passes (see `vite.config.ts` / `vite.content.config.ts`):

1. **Main pass** — popup + options (React, multi-page) and the background service worker, all as ES modules
   (MV3 supports `"type": "module"` service workers).
2. **Content-script pass** — bundled separately as a dependency-free IIFE for maximum browser compatibility,
   since content scripts are injected as classic scripts.

`scripts/copy-assets.mjs` flattens Vite's nested HTML output to `popup.html` / `options.html` at the root of
`dist/` (matching `manifest.json`) and copies in `manifest.json` + icons.
