/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1600px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Dedicated financial intelligence palette
        canvas: "#090D14",
        surface: {
          DEFAULT: "#0F1622",
          raised: "#161F2E",
          hover: "#1E2A3C",
          accent: "#121A28",
        },
        hairline: {
          DEFAULT: "#1E2B3E",
          subtle: "#162030",
          bright: "#2A3D58",
        },
        semantic: {
          critical: "#F05252",
          "critical-bg": "#2A1417",
          "critical-border": "#5E1E24",
          positive: "#31C48D",
          "positive-bg": "#10281F",
          "positive-border": "#1A523C",
          warning: "#FACA15",
          "warning-bg": "#2E2410",
          "warning-border": "#5E4A14",
          neutral: "#3F83F8",
          "neutral-bg": "#12233F",
          "neutral-border": "#1D3B6B",
          cognitive: "#9061F9",
          "cognitive-bg": "#251842",
          "cognitive-border": "#472B7A",
          simulated: "#9CA3AF",
          "simulated-bg": "#1F242C",
          "simulated-border": "#374151",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "SF Mono", "ui-monospace", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.45)",
        hero: "0 10px 40px -4px rgba(0, 0, 0, 0.6)",
        glow: "0 0 15px rgba(63, 131, 248, 0.35)",
        "glow-positive": "0 0 15px rgba(49, 196, 141, 0.35)",
        "glow-critical": "0 0 15px rgba(240, 82, 82, 0.35)",
      },
    },
  },
  plugins: [],
}
