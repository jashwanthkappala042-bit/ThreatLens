/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#070b12",
          900: "#0a101b",
          850: "#0d1522",
          800: "#111b2b",
          700: "#19263a",
          600: "#24344c",
        },
        lens: {
          300: "#7ee7e1",
          400: "#3dd6cf",
          500: "#19b8b0",
          600: "#0f958f",
        },
        signal: {
          safe: "#38d39f",
          cautious: "#f2b84b",
          danger: "#f1666d",
          unknown: "#9aa7bd",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 24px 60px -30px rgba(0,0,0,0.65)",
        glow: "0 0 0 1px rgba(61,214,207,0.25), 0 0 40px -12px rgba(61,214,207,0.45)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          "0%": { transform: "translateX(-120%)" },
          "100%": { transform: "translateX(220%)" },
        },
        pulseRing: {
          "0%": { transform: "scale(0.9)", opacity: "0.65" },
          "70%": { transform: "scale(1.12)", opacity: "0" },
          "100%": { transform: "scale(1.12)", opacity: "0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s ease-out both",
        sweep: "sweep 2.4s ease-in-out infinite",
        "pulse-ring": "pulseRing 2.4s cubic-bezier(0.4,0,0.6,1) infinite",
      },
    },
  },
  plugins: [],
};
