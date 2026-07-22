import type { Config } from "tailwindcss";

// Condensed version of the dashboard's "Night Watch" tokens, scoped to
// the extension's small popup/options surfaces.
export default {
  content: ["./src/**/*.{ts,tsx}", "./*.html"],
  theme: {
    extend: {
      colors: {
        void: "#0A0F1C",
        panel: { DEFAULT: "#121B2E", raised: "#182642", line: "#22314F" },
        sentinel: { DEFAULT: "#2DD4BF", glow: "#5EEAD4" },
        threat: { low: "#5B8DEF", medium: "#F5A623", high: "#F0653E", critical: "#EF4444" },
        fog: { DEFAULT: "#C7D2E3", dim: "#8394B4", faint: "#4C5A78" },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
