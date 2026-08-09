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
      <div class="actions" style="margin-top: 8px;">
        <button class="report-page" style="background: transparent; border-color: #64748B; color: #94A3B8; text-align: left;" title="Report this phishing page to Google Safe Browsing">
          <span style="display: block; font-size: 11px; margin-bottom: 2px;">Help protect others:</span>
          Report to Google Safe Browsing <span style="float: right;">↗</span>
        </button>
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
    card.querySelector(".report-page")?.addEventListener("click", (e) => {
      const btn = e.currentTarget as HTMLButtonElement;
      btn.disabled = true;
      btn.innerHTML = "Opening report form...";
      try {
        chrome.runtime.sendMessage({ type: "REPORT_PHISHING", url, reason: "Flagged by security-copilot: " + messageFor(label, source) });
      } catch {
        // Extension context invalidated
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

  function checkAndAutoFillSafeBrowsing(): void {
    if (!location.hostname.includes("safebrowsing.google.com")) return;
    const params = new URLSearchParams(location.search);
    const urlToReport = params.get("url");
    if (!urlToReport) return;
    const reason = params.get("reason") || "Flagged as a deceptive site attempting to trick users into sharing sensitive information. Please investigate for potential phishing activity.";

    const triggerEvents = (element: HTMLElement | null) => {
      if (!element) return;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      element.dispatchEvent(new Event("blur", { bubbles: true }));
    };

    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

    const showModal = () => {
      const modalOverlay = document.createElement("div");
      modalOverlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.5); z-index: 999998; backdrop-filter: blur(2px);
        display: flex; align-items: center; justify-content: center;
      `;
      const modalContent = document.createElement("div");
      modalContent.style.cssText = `
        background: #1e293b; color: #f8fafc; padding: 24px 32px; border-radius: 12px;
        font-family: -apple-system, sans-serif; max-width: 420px; text-align: center;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3); z-index: 999999;
        border: 1px solid #334155;
      `;
      modalContent.innerHTML = `
        <div style="font-size: 32px; margin-bottom: 12px;">✅</div>
        <h2 style="margin: 0 0 12px; font-size: 18px; font-weight: 600;">Form auto-filled!</h2>
        <p style="margin: 0 0 24px; color: #94a3b8; font-size: 14px; line-height: 1.5;">
          We've filled out the report details for you. However, Google's <strong>security reCAPTCHA</strong> prevents us from submitting it automatically.<br><br>
          Please complete the CAPTCHA check below and manually click <strong>Submit Report</strong>.
        </p>
        <button id="sc-modal-dismiss" style="
          background: #6366f1; color: white; border: none; padding: 10px 24px;
          border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px;
          transition: opacity 0.2s;
        ">Got it, let me submit</button>
      `;
      modalOverlay.appendChild(modalContent);
      document.body.appendChild(modalOverlay);

      modalContent.querySelector("#sc-modal-dismiss")?.addEventListener("click", () => {
        modalOverlay.remove();
      });
    };

    let highlightBox: HTMLDivElement | null = null;
    const highlightElement = (element: HTMLElement | null) => {
      if (!element) {
        if (highlightBox) { highlightBox.remove(); highlightBox = null; }
        return;
      }
      if (!highlightBox) {
        highlightBox = document.createElement("div");
        highlightBox.style.cssText = `
          position: fixed;
          border: 3px solid #6366f1;
          border-radius: 6px;
          box-shadow: 0 0 16px rgba(99, 102, 241, 0.6);
          pointer-events: none;
          z-index: 999997;
          transition: all 0.3s ease;
          background: rgba(99, 102, 241, 0.1);
        `;
        document.body.appendChild(highlightBox);
      }
      const targetForRect = element.closest('mat-form-field') || element;
      const rect = targetForRect.getBoundingClientRect();
      const padding = 8;
      highlightBox.style.top = (rect.top - padding) + "px";
      highlightBox.style.left = (rect.left - padding) + "px";
      highlightBox.style.width = (rect.width + padding * 2) + "px";
      highlightBox.style.height = (rect.height + padding * 2) + "px";
    };

    const runAutoFill = async () => {
      // Wait for URL input to be available
      let urlInput = null;
      for (let i = 0; i < 20; i++) {
        urlInput = document.querySelector<HTMLInputElement>('input[formcontrolname="url"]') || document.querySelector<HTMLInputElement>("#mat-input-0");
        if (urlInput) break;
        await sleep(250);
      }
      if (!urlInput) return;

      await sleep(1000); // Initial human-like pause
      highlightElement(urlInput);
      await sleep(500);

      urlInput.value = "";
      for (let i = 0; i < urlToReport.length; i++) {
        urlInput.value += urlToReport[i];
        triggerEvents(urlInput);
        await sleep(30 + Math.random() * 40);
      }

      await sleep(800);
      const threatTypeSelect = document.querySelector<HTMLElement>('mat-select[formcontrolname="threatType"]') || document.querySelector<HTMLElement>("#mat-select-1");
      if (threatTypeSelect) {
        highlightElement(threatTypeSelect);
        await sleep(400);
        threatTypeSelect.click();
        await sleep(1000); // Wait for dropdown animation
        
        const options = document.querySelectorAll<HTMLElement>("mat-option");
        const seOption = Array.from(options).find((opt) => opt.textContent?.includes("Social Engineering"));
        if (seOption) seOption.click();

        await sleep(800);
        const threatCategorySelect = document.querySelector<HTMLElement>('mat-select[formcontrolname="threatCategory"]') || document.querySelector<HTMLElement>("#mat-select-2");
        if (threatCategorySelect) {
          highlightElement(threatCategorySelect);
          await sleep(400);
          threatCategorySelect.click();
          await sleep(1000);
          
          const visibleOptions = Array.from(document.querySelectorAll<HTMLElement>("mat-option")).filter(opt => opt.offsetParent !== null);
          let targetOption = visibleOptions.find((opt) => opt.textContent?.toLowerCase().includes("other"));
          if (!targetOption) {
            targetOption = visibleOptions.find((opt) => opt.textContent?.toLowerCase().includes("none")) || visibleOptions[1] || visibleOptions[0];
          }
          
          if (targetOption) targetOption.click();
        }
      }

      await sleep(800);
      const details = document.querySelector<HTMLTextAreaElement>("textarea");
      if (details) {
        highlightElement(details);
        await sleep(400);
        details.value = "";
        // Human-paced typing
        for (let i = 0; i < reason.length; i++) {
          details.value += reason[i];
          triggerEvents(details);
          await sleep(30 + Math.random() * 40); // 30-70ms per character
        }
      }

      highlightElement(null);
      await sleep(1000);
      showModal();
    };

    void runAutoFill();
  }

  computePageSignals();
  checkAndAutoFillSafeBrowsing();
})();
