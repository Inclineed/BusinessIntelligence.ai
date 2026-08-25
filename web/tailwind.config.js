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
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      colors: {
        // Asagi-Shu Palette
        asagi: {
          DEFAULT: "#6B9BB0",
          light: "#8EB8CB",
          dark: "#4D7689",
          dim: "rgba(107, 155, 176, 0.15)",
          glow: "rgba(107, 155, 176, 0.25)",
        },
        shu: {
          DEFAULT: "#D8453A",
          light: "#E56B62",
          dark: "#A63027",
          dim: "rgba(216, 69, 58, 0.15)",
          glow: "rgba(216, 69, 58, 0.25)",
        },
        gofun: {
          DEFAULT: "#F4EEE0",
          muted: "#D1C9B8",
          subtle: "#9E9788",
        },
        sumi: {
          DEFAULT: "#2B2B2B",
          dark: "#141414",
          surface: "#1C1C1C",
          card: "#222222",
          hover: "#2F2F2F",
          border: "#383838",
        },

        // Base structural surfaces
        background: "#141414",
        surface: {
          DEFAULT: "#1C1C1C",
          elevated: "#242424",
          hover: "#2C2C2C",
        },
        border: {
          DEFAULT: "#333333",
          subtle: "rgba(244, 238, 224, 0.08)",
          highlight: "rgba(244, 238, 224, 0.15)",
        },

        // Strict allowed accents: Asagi shades, Red/Shu shades, Green/Sage shades
        red: {
          300: '#E56B62',
          400: '#D8453A', // Shu
          500: '#A63027',
          600: '#7E2019',
        },
        emerald: {
          300: '#78AC91',
          400: '#4E8569', // Muted sage green
          500: '#386A4C',
          600: '#254A34',
        },
        sky: {
          300: '#8EB8CB',
          400: '#6B9BB0', // Asagi
          500: '#4D7689',
          600: '#375664',
        },
        amber: {
          300: '#8EB8CB', // Mapped to Asagi light to avoid unlisted colors
          400: '#6B9BB0',
          500: '#4D7689',
        },

        primary: {
          DEFAULT: "#6B9BB0",
          dim: "rgba(107, 155, 176, 0.15)",
          glow: "rgba(107, 155, 176, 0.25)",
        },
        destructive: {
          DEFAULT: "#D8453A",
          dim: "rgba(216, 69, 58, 0.15)",
          glow: "rgba(216, 69, 58, 0.25)",
        },
        muted: "#9E9788",
      },
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.6), inset 0 1px 0 0 rgba(244, 238, 224, 0.06)",
        "glass-elevated": "0 16px 48px -8px rgba(0, 0, 0, 0.8), inset 0 1px 0 0 rgba(244, 238, 224, 0.10)",
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.4)",
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      }
    },
  },
  plugins: [],
}
