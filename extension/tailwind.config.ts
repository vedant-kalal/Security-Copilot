import type { Config } from "tailwindcss";

// "Night Watch" design tokens, now theme-aware: every colour is an
// `rgb(var(--c-*) / <alpha-value>)` reference so light/dark can be swapped
// by flipping `data-theme` on <html> (the CSS variables live in the popup /
// options index.css). The `<alpha-value>` form preserves Tailwind opacity
// modifiers like `bg-sentinel/15`.
const c = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ["./src/**/*.{ts,tsx}", "./*.html"],
  theme: {
    extend: {
      colors: {
        void: c("void"),
        panel: {
          DEFAULT: c("panel"),
          raised: c("panel-raised"),
          line: c("panel-line"),
          glass: c("panel-glass"),
        },
        sentinel: { DEFAULT: c("sentinel"), glow: c("sentinel-glow") },
        safe: c("safe"),
        threat: {
          low: c("threat-low"),
          medium: c("threat-medium"),
          high: c("threat-high"),
          critical: c("threat-critical"),
        },
        fog: {
          DEFAULT: c("fog"),
          dim: c("fog-dim"),
          faint: c("fog-faint"),
        },
        accent: { DEFAULT: c("accent"), deep: c("accent-deep"), light: c("accent-light") },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        "glow-sentinel": "0 0 12px rgb(var(--c-sentinel) / 0.25)",
        "glow-safe": "0 0 12px rgb(var(--c-safe) / 0.25)",
        "glow-critical": "0 0 12px rgb(var(--c-threat-critical) / 0.22)",
        "glow-medium": "0 0 12px rgb(var(--c-threat-medium) / 0.22)",
        "glow-accent": "0 0 16px rgb(var(--c-accent) / 0.30)",
        // Neutral card shadows differ per theme (soft grey on cream, deep on
        // dark) — driven by CSS variables set in index.css.
        "card": "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
      },
      animation: {
        "scan": "scan 2s ease-in-out infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
      },
      keyframes: {
        scan: {
          "0%": { backgroundPosition: "100% 0" },
          "100%": { backgroundPosition: "-100% 0" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
      },
      backdropBlur: {
        xs: "4px",
      },
    },
  },
  plugins: [],
} satisfies Config;
