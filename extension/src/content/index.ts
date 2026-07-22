/**
 * SentinelAI content script.
 *
 * Deliberately dependency-free (no imports) so it can be bundled as a
 * small, dependency-free IIFE and injected on every page without
 * pulling in the extension's React/auth bundle. Its only job is to
 * detect when the user submits a form containing a password field —
 * a precursor to the "credential_form_on_suspicious_site" correlation
 * signal — and relay that fact to the background service worker, which
 * holds the auth token and talks to the backend.
 *
 * All actual intelligence (is this domain phishing? should this be an
 * incident?) happens server-side, per architecture doc section 7:
 * "The extension is NOT an AI model."
 */
(function sentinelAIContentScript() {
  function hasPasswordField(form: HTMLFormElement): boolean {
    return form.querySelector('input[type="password"]') !== null;
  }

  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (!hasPasswordField(form)) return;

      try {
        chrome.runtime.sendMessage({
          type: "FORM_SUBMISSION",
          url: window.location.href,
          hasPasswordField: true,
        });
      } catch {
        // The extension context may be invalidated (e.g. during an
        // update); silently ignore rather than throwing on the page.
      }
    },
    { capture: true }
  );
})();
