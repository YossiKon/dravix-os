/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm ink — the robot's room at night
        bg: "#131110",
        card: "#1c1917",
        card2: "#26211d",
        line: "#312b25",
        "line-2": "#453c33",
        ink: "#f4eee3",
        soft: "#c9bfae",
        mute: "#8d8375",
        // The robot's own colours: teal face + amber "AI mode" LEDs
        teal: "#2ee6c8",
        "teal-dim": "#17705f",
        amber: "#ffc23d",
        red: "#ff6b5e",
        green: "#7ddf8f",
      },
      fontFamily: {
        display: ['"Secular One"', "Heebo", "sans-serif"],
        body: ["Heebo", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.03) inset, 0 14px 34px -22px rgba(0,0,0,0.9)",
        led: "0 0 18px 2px rgba(255,194,61,0.45)",
        "led-teal": "0 0 18px 2px rgba(46,230,200,0.35)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        breathe: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
      animation: {
        // "backwards" (not "both"): once the entrance finishes, no transform lingers on the
        // card — a lingering transform creates a stacking context that buries dropdowns
        // under the NEXT card in the page.
        rise: "rise 0.45s cubic-bezier(0.2,0.8,0.2,1) backwards",
        breathe: "breathe 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
