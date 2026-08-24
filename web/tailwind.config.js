/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      colors: {
        background: "#0A0A0A", // neutral-950
        surface: {
          DEFAULT: "#171717", // neutral-900
          hover: "#262626", // neutral-800
        },
        border: {
          DEFAULT: "#262626", // neutral-800
          subtle: "rgba(255,255,255,0.05)",
        },
        primary: {
          DEFAULT: "#22c55e", // emerald-500
          dim: "rgba(34, 197, 94, 0.15)",
        },
        destructive: {
          DEFAULT: "#ef4444", // red-500
          dim: "rgba(239, 68, 68, 0.15)",
        },
        muted: "#a3a3a3", // neutral-400
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.2)",
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      }
    },
  },
  plugins: [],
}
