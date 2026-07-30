/**
 * Light/dark theme, persisted in chrome.storage.local so it's shared
 * across the popup and options page and survives restarts. Dark is the
 * default; light is a cool-cream palette (see index.css).
 */
export type Theme = "dark" | "light";

const THEME_KEY = "theme";

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

export async function getTheme(): Promise<Theme> {
  const stored = await chrome.storage.local.get(THEME_KEY);
  return (stored[THEME_KEY] as Theme) === "light" ? "light" : "dark";
}

export async function setTheme(theme: Theme): Promise<void> {
  applyTheme(theme);
  await chrome.storage.local.set({ [THEME_KEY]: theme });
}

/** Apply the saved theme as early as possible (call before first render). */
export async function initTheme(): Promise<void> {
  applyTheme(await getTheme());
}
