/**
 * security-copilot content script — the in-page banner.
 *
 * Deliberately dependency-free (no imports, no React) so it can be bundled
 * as a small IIFE and injected on every page without pulling in the
 * extension's React bundle. Its only job is to render a floating banner
 * when background.ts's automatic quick-check flags the current page as
 * dangerous/suspicious — never for a safe result, per the user's request
 * that this be silent unless there's something to say.
 *
 * Renders inside a closed Shadow DOM so the page's own CSS can never break
 * (or be broken by) the banner, and talks back to background.ts by
 * message only — content scripts can't call chrome.tabs.* directly.
 */
(function securityCopilotContentScript() {
  type Label = "dangerous" | "suspicious";

  const HOST_ID = "security-copilot-banner-host";

  let shadow: ShadowRoot | null = null;
  let cardEl: HTMLDivElement | null = null;

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
      @keyframes sc-slide-in { from { opacity: 0; transform: translateX(16px); } to { opacity: 1; transform: translateX(0); } }
      .row { display: flex; align-items: flex-start; gap: 10px; }
      .icon { font-size: 20px; line-height: 1; flex-shrink: 0; }
      .title { font-weight: 700; font-size: 13px; letter-spacing: 0.02em; }
      .title.dangerous { color: #FB7185; }
      .title.suspicious { color: #FBBF24; }
      .sub { color: #94A3B8; font-size: 11px; margin-top: 2px; }
      .msg { margin-top: 8px; color: #C7D2E3; }
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
    `;
    shadow.appendChild(style);
    return shadow;
  }

  function labelIcon(label: Label): string {
    return label === "dangerous" ? "⛔" : "⚠️"; // ⛔ / ⚠️
  }

  function showBanner(url: string, label: Label, confidence: number): void {
    const root = ensureHost();
    hideBanner();

    const card = document.createElement("div");
    card.className = `card ${label}`;
    card.innerHTML = `
      <button class="close" aria-label="Dismiss">&times;</button>
      <div class="row">
        <span class="icon">${labelIcon(label)}</span>
        <div>
          <div class="title ${label}">${label === "dangerous" ? "Dangerous site" : "Suspicious site"}</div>
          <div class="sub">security-copilot &middot; ${Math.round(confidence * 100)}% confidence &middot; quick scan</div>
        </div>
      </div>
      <div class="msg">${
        label === "dangerous"
          ? "This page's URL matches known phishing patterns. Avoid entering any credentials."
          : "This page's URL looks unusual. Worth a closer look before you trust it."
      }</div>
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

    root.appendChild(card);
    cardEl = card;
  }

  function hideBanner(): void {
    if (cardEl) {
      cardEl.remove();
      cardEl = null;
    }
  }

  function updateFullReportButton(text: string, disabled: boolean): void {
    const btn = cardEl?.querySelector<HTMLButtonElement>(".full-report");
    if (!btn) return;
    btn.textContent = text;
    btn.disabled = disabled;
  }

  chrome.runtime.onMessage.addListener((message) => {
    switch (message?.type) {
      case "SHOW_BANNER":
        showBanner(message.url, message.label, message.confidence);
        break;
      case "HIDE_BANNER":
        hideBanner();
        break;
      case "FULL_CHECK_STARTED":
        updateFullReportButton("Investigating...", true);
        break;
      case "FULL_CHECK_DONE":
        updateFullReportButton("Opened in new tab", true);
        break;
      case "FULL_CHECK_FAILED":
        updateFullReportButton("Failed — retry", false);
        break;
      default:
        break;
    }
    return false;
  });
})();
