import type { Config } from "tailwindcss";

// "Night Watch" design tokens — softened cybersecurity palette with
// glassmorphism glow effects and premium depth.  Scoped to the
// extension's popup/options surfaces.
export default {
  content: ["./src/**/*.{ts,tsx}", "./*.html"],
  theme: {
    extend: {
      colors: {
        void: "#111827",
        panel: {
          DEFAULT: "#1A2235",
          raised: "#212B42",
          line: "#2D3A52",
          glass: "rgba(26,34,53,0.5)",
        },
        sentinel: { DEFAULT: "#2DD4BF", glow: "#5EEAD4" },
        safe: "#34D399",
        threat: {
          low: "#5B8DEF",
          medium: "#FBBF24",
          high: "#F0653E",
          critical: "#FB7185",
        },
        fog: {
          DEFAULT: "#E2E8F0",
          dim: "#94A3B8",
          faint: "#64748B",
        },
        accent: { DEFAULT: "#818CF8", deep: "#6366f1", light: "#A5B4FC" },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      boxShadow: {
        "glow-sentinel": "0 0 12px rgba(45,212,191,0.25)",
        "glow-safe": "0 0 12px rgba(52,211,153,0.25)",
        "glow-critical": "0 0 12px rgba(251,113,133,0.22)",
        "glow-medium": "0 0 12px rgba(251,191,36,0.22)",
        "glow-accent": "0 0 16px rgba(129,140,248,0.30)",
        "card": "0 4px 24px rgba(0,0,0,0.15), 0 1px 0 rgba(255,255,255,0.04) inset",
        "card-hover": "0 8px 32px rgba(0,0,0,0.22), 0 1px 0 rgba(255,255,255,0.04) inset",
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
          "0%, 100%": { opacity: "0.5" },
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
