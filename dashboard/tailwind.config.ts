import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

// SentinelAI design tokens — "Night Watch" system.
// A watchtower/radar visual language for a security copilot: a deep-navy
// operations-room base with a teal "all-clear / scanning" signal color and
// an amber -> red severity ramp for threats. See docs/DEVELOPER_GUIDE.md
// ("Design System") for the full rationale.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: {
          DEFAULT: "#0A0F1C",
          soft: "#0D1420",
        },
        panel: {
          DEFAULT: "#121B2E",
          raised: "#182642",
          line: "#22314F",
        },
        sentinel: {
          DEFAULT: "#2DD4BF",
          dim: "#1F9C8C",
          glow: "#5EEAD4",
        },
        threat: {
          low: "#5B8DEF",
          medium: "#F5A623",
          high: "#F0653E",
          critical: "#EF4444",
        },
        fog: {
          DEFAULT: "#C7D2E3",
          dim: "#8394B4",
          faint: "#4C5A78",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      borderRadius: {
        lg: "0.75rem",
        md: "0.5rem",
        sm: "0.375rem",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 24px -4px rgba(45, 212, 191, 0.35)",
      },
      keyframes: {
        "radar-sweep": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.6" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "radar-sweep": "radar-sweep 4s linear infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-up": "fade-up 0.4s ease-out",
      },
    },
  },
  plugins: [tailwindcssAnimate],
} satisfies Config;
