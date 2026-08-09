/**
 * security-copilot content script — the in-page banner.
 *
 * Deliberately dependency-free (no imports, no React) so it can be bundled
 * as a small IIFE and injected on every page without pulling in the
 * extension's React bundle. Its only job is to render a floating banner
 * or toast whenever background.ts's automatic quick-check finishes.
 *
 * Renders inside a closed Shadow DOM so the page's own CSS can never break
 * (or be broken by) the banner, and talks back to background.ts by
 * message only — content scripts can't call chrome.tabs.* directly.
 *
 * "safe" gets a distinct, minimal toast that clears itself after ~1.5s —
 * a brief confirmation, not an alert. "dangerous"/"suspicious" get the
 * full banner with actions, and NEVER auto-dismiss — the user asked
 * explicitly that those stay up until they click the close button.
 */
(function securityCopilotContentScript() {
  type Label = "dangerous" | "suspicious" | "safe";

  const HOST_ID = "security-copilot-banner-host";
  const SAFE_TOAST_MS = 1600;

  let shadow: ShadowRoot | null = null;
  let cardEl: HTMLDivElement | null = null;
  let safeDismissTimer: ReturnType<typeof setTimeout> | null = null;

  function ensureHost(): ShadowRoot {
    if (shadow) return shadow;
    const host = document.createElement("div");
    host.id = HOST_ID;
    host.style.all = "initial"; // isolate from page CSS at the host boundary too
    document.documentElement.appendChild(host);
    shadow = host.attachShadow({ mode: "closed" });

    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      .card {
        position: fixed;
        top: 16px;
        right: 16px;
        z-index: 2147483647;
        width: 320px;
        font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
        line-height: 1.5;
        color: #E2E8F0;
        background: #1A2235;
        border: 1px solid #2D3A52;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        padding: 14px 16px;
        animation: sc-slide-in 0.25s ease-out;
      }
      .card.dangerous { border-color: #FB7185; box-shadow: 0 8px 32px rgba(251,113,133,0.25); }
      .card.suspicious { border-color: #FBBF24; box-shadow: 0 8px 32px rgba(251,191,36,0.20); }
      .card.safe { border-color: #34D399; box-shadow: 0 8px 32px rgba(52,211,153,0.18); width: auto; max-width: 260px; padding: 10px 14px; animation: sc-slide-in 0.2s ease-out, sc-fade-out 0.35s ease-in 1.25s forwards; }
      @keyframes sc-slide-in { from { opacity: 0; transform: translateX(16px); } to { opacity: 1; transform: translateX(0); } }
      @keyframes sc-fade-out { from { opacity: 1; } to { opacity: 0; } }
      .row { display: flex; align-items: flex-start; gap: 10px; }
      .icon { font-size: 20px; line-height: 1; flex-shrink: 0; }
      .title { font-weight: 700; font-size: 13px; letter-spacing: 0.02em; }
      .title.dangerous { color: #FB7185; }
      .title.suspicious { color: #FBBF24; }
      .title.safe { color: #34D399; }
      .sub { color: #94A3B8; font-size: 11px; margin-top: 2px; }
      .msg { margin-top: 8px; color: #C7D2E3; }
      .progress {
        display: flex;
        align-items: center;
        gap: 7px;
        margin-top: 10px;
        padding: 7px 10px;
        border-radius: 8px;
        background: #161D2E;
        border: 1px solid #2D3A52;
        color: #94A3B8;
        font-size: 11.5px;
        line-height: 1.4;
      }
      .progress .spinner { margin-right: 0; flex-shrink: 0; }
      .actions { display: flex; gap: 8px; margin-top: 12px; }
      button {
        flex: 1;
        font-family: inherit;
        font-size: 12px;
        font-weight: 600;
        padding: 7px 10px;
        border-radius: 8px;
        cursor: pointer;
        border: 1px solid #2D3A52;
        background: #212B42;
        color: #E2E8F0;
        transition: background 0.15s ease, border-color 0.15s ease;
      }
      button.primary { background: #6366F1; border-color: #6366F1; color: white; }
      button:hover { filter: brightness(1.1); }
      button:disabled { opacity: 0.6; cursor: default; }
      .close {
        position: absolute; top: 10px; right: 12px;
        background: none; border: none; color: #64748B;
        font-size: 16px; padding: 0; width: auto; flex: none;
        line-height: 1;
      }
      .spinner {
        display: inline-block;
        width: 11px; height: 11px;
        margin-right: 6px;
        vertical-align: -1px;
        border: 2px solid rgba(255,255,255,0.35);
        border-top-color: #fff;
        border-radius: 50%;
        animation: sc-spin 0.7s linear infinite;
      }
      @keyframes sc-spin { to { transform: rotate(360deg); } }
    `;
    shadow.appendChild(style);
    return shadow;
  }

  function labelIcon(label: Label): string {
    if (label === "dangerous") return "⛔";
    if (label === "suspicious") return "⚠️";
    return "✅";
  }

  function labelTitle(label: Label): string {
    if (label === "dangerous") return "Dangerous site";
    if (label === "suspicious") return "Suspicious site";
    return "Looks safe";
  }

  function messageFor(label: "dangerous" | "suspicious", source: string): string {
    if (source === "blocklist") return "This URL matches a known-bad domain. Avoid entering any credentials.";
    if (source === "virustotal") {
      return label === "dangerous"
        ? "VirusTotal already has multiple security vendors flagging this domain as phishing/malicious."
        : "VirusTotal has at least one security vendor flagging this domain. Worth a closer look.";
    }
    if (source === "page_signal") {
      return "This page has a login form that submits your password to a different, unrelated domain — a strong sign of credential phishing. Do not enter your password.";
    }
    return label === "dangerous"
      ? "This page's URL matches known phishing patterns. Avoid entering any credentials."
      : "This page's URL looks unusual. Worth a closer look before you trust it.";
  }

  function showBanner(url: string, label: Label, confidence: number, source: string): void {
    const root = ensureHost();
    hideBanner();

    const card = document.createElement("div");
    card.className = `card ${label}`;

    if (label === "safe") {
      // Deliberately no close button, no actions — this is a brief
      // confirmation that clears itself, not something to interact with.
      card.innerHTML = `
        <div class="row">
          <span class="icon">${labelIcon(label)}</span>
          <div>
            <div class="title ${label}">${labelTitle(label)}</div>
            <div class="sub">security-copilot &middot; quick scan</div>
          </div>
        </div>
      `;
      root.appendChild(card);
      cardEl = card;
      safeDismissTimer = setTimeout(hideBanner, SAFE_TOAST_MS);
      return;
    }

    card.innerHTML = `
      <button class="close" aria-label="Dismiss">&times;</button>
      <div class="row">
        <span class="icon">${labelIcon(label)}</span>
        <div>
          <div class="title ${label}">${labelTitle(label)}</div>
          <div class="sub">security-copilot &middot; ${Math.round(confidence * 100)}% confidence &middot; quick scan</div>
        </div>
      </div>
      <div class="msg">${messageFor(label, source)}</div>
      <div class="progress" style="display:none;"></div>
      <div class="actions">
        <button class="full-report primary">Full report</button>
        <button class="dismiss">Dismiss</button>
      </div>
    `;

    card.querySelector(".close")?.addEventListener("click", hideBanner);
    card.querySelector(".dismiss")?.addEventListener("click", hideBanner);
    card.querySelector(".full-report")?.addEventListener("click", (e) => {
      const btn = e.currentTarget as HTMLButtonElement;
      btn.disabled = true;
      btn.textContent = "Investigating...";
      try {
        chrome.runtime.sendMessage({ type: "RUN_FULL_CHECK", url });
      } catch {
        // Extension context invalidated (e.g. mid-update) — nothing to recover.
      }
    });

    // No auto-dismiss timer here, intentionally: dangerous/suspicious
    // banners stay until the user clicks the close button.
    root.appendChild(card);
    cardEl = card;
  }

  function hideBanner(): void {
    if (safeDismissTimer !== null) {
      clearTimeout(safeDismissTimer);
      safeDismissTimer = null;
    }
    if (cardEl) {
      cardEl.remove();
      cardEl = null;
    }
  }

  function updateFullReportButton(text: string, disabled: boolean, spinner = false): void {
    const btn = cardEl?.querySelector<HTMLButtonElement>(".full-report");
    if (!btn) return;
    btn.innerHTML = spinner ? `<span class="spinner"></span>${text}` : text;
    btn.disabled = disabled;
  }

  // The live step narration (e.g. "Checking VirusTotal & domain
  // registration history...") gets its own row instead of living inside
  // the button — those labels are full sentences, and the button is a
  // small pill with no room to wrap them.
  function updateProgress(label: string | null): void {
    const el = cardEl?.querySelector<HTMLDivElement>(".progress");
    if (!el) return;
    if (label === null) {
      el.style.display = "none";
      el.innerHTML = "";
      return;
    }
    el.style.display = "flex";
    el.innerHTML = `<span class="spinner"></span><span>${label}</span>`;
  }

  chrome.runtime.onMessage.addListener((message) => {
    switch (message?.type) {
      case "SHOW_BANNER":
        showBanner(message.url, message.label, message.confidence, message.source);
        break;
      case "HIDE_BANNER":
        hideBanner();
        break;
      case "FULL_CHECK_STARTED":
        updateFullReportButton("Investigating...", true, true);
        updateProgress("Starting investigation...");
        break;
      case "FULL_CHECK_PROGRESS":
        updateProgress(message.label);
        break;
      case "FULL_CHECK_DONE":
        updateFullReportButton("✓ Opened in new tab", true);
        updateProgress(null);
        break;
      case "FULL_CHECK_FAILED":
        updateFullReportButton("Failed — retry", false);
        updateProgress(null);
        break;
      default:
        break;
    }
    return false;
  });

  // The one page-content signal this extension looks at: a password field
  // inside a form that posts somewhere other than this page's own site —
  // the classic shape of a credential-harvesting fake login page, and
  // something background.ts's /quick-check-url can't see from the URL
  // string alone. A password field by itself means nothing (nearly every
  // real login page has one) — only reported when paired with a foreign
  // submit target, and only that one fact is sent, never page content
  // itself.
  //
  // Static-DOM only: a form whose submission is fully handled by JS
  // (fetch()/XHR in a submit handler, no real `action` attribute) won't be
  // caught here. That's a missed detection, not a false positive, which is
  // the direction that matters — see routes_quick_check.py's docstring for
  // why false positives are treated as the costlier mistake throughout
  // this pipeline.
  function computePageSignals(): void {
    const passwordInputs = document.querySelectorAll<HTMLInputElement>('input[type="password"]');
    for (const input of passwordInputs) {
      const form = input.closest("form");
      if (!form) continue;

      const actionAttr = form.getAttribute("action");
      let resolved: URL;
      try {
        resolved = new URL(actionAttr || "", location.href);
      } catch {
        continue;
      }
      if (resolved.protocol !== "http:" && resolved.protocol !== "https:") continue;
      if (resolved.hostname === location.hostname) continue;

      try {
        chrome.runtime.sendMessage({
          type: "PAGE_SIGNALS",
          url: location.href,
          actionDomain: resolved.hostname,
        } satisfies { type: "PAGE_SIGNALS"; url: string; actionDomain: string });
      } catch {
        // Extension context invalidated (e.g. mid-update) — nothing to recover.
      }
      return; // one report is enough — background re-derives everything else itself
    }
  }

  computePageSignals();
})();
