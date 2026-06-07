/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // base surfaces (deeper than before, layered for glass)
        ink: "#070a10",
        base: "#0a0e16",
        panel: "#111725",
        surface: "#141b2b",
        edge: "#222c40",
        // brand + semantic accents
        accent: "#22d3a8", // mint — primary / live
        iris: "#7c8cff", // violet — AI
        amber: "#f5b343", // warn
        danger: "#fb6a78", // alert
      },
      fontFamily: {
        display: [
          '"Helvetica Neue"',
          "Helvetica",
          "Arial",
          "system-ui",
          "sans-serif",
        ],
      },
      boxShadow: {
        glass: "inset 0 1px 0 0 rgba(255,255,255,0.06), 0 20px 50px -20px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(34,211,168,0.25), 0 0 28px -6px rgba(34,211,168,0.45)",
        "glow-iris": "0 0 0 1px rgba(124,140,255,0.25), 0 0 28px -6px rgba(124,140,255,0.45)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgba(34,211,168,0.55)" },
          "70%": { boxShadow: "0 0 0 7px rgba(34,211,168,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(34,211,168,0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-3px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.22,1,0.36,1) both",
        "fade-in": "fade-in 0.6s ease both",
        "pulse-ring": "pulse-ring 2s ease-out infinite",
        shimmer: "shimmer 2.5s linear infinite",
        float: "float 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
