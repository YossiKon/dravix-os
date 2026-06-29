/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deep instrument-panel charcoals
        void: "#070809",
        panel: "#0d0f11",
        "panel-2": "#121519",
        line: "#1d2228",
        "line-bright": "#2b333c",
        mute: "#5b6670",
        soft: "#8a96a1",
        ink: "#d7dee4",
        // Phosphor green primary, amber warn, cyan info, red fault
        phosphor: "#5dffa0",
        "phosphor-dim": "#2e7d54",
        amber: "#ffb454",
        cyan: "#5cc8ff",
        magenta: "#ff6ec7",
        fault: "#ff5a52",
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Space Mono"', "ui-monospace", "monospace"],
        display: ['"Chakra Petch"', "ui-sans-serif", "system-ui", "sans-serif"],
        body: ['"Sora"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(93,255,160,0.18), 0 0 24px -8px rgba(93,255,160,0.35)",
        panel:
          "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 -1px 0 0 rgba(0,0,0,0.4) inset, 0 18px 40px -24px rgba(0,0,0,0.9)",
      },
      keyframes: {
        "pulse-dot": {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.82)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          "0%": { opacity: "0", transform: "translateX(14px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
        "fade-up": "fade-up 0.4s ease both",
        "slide-in": "slide-in 0.28s cubic-bezier(0.2,0.8,0.2,1) both",
        sweep: "sweep 2.4s linear infinite",
      },
    },
  },
  plugins: [],
};
