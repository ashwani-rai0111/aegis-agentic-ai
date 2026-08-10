import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07131a",
          900: "#0b1c26",
          800: "#123041",
          700: "#1a4258",
        },
        mist: {
          50: "#f3f7f8",
          100: "#e4eef1",
          300: "#9bb6c0",
          400: "#7a9aa6",
        },
        signal: {
          amber: "#e8a23a",
          mint: "#3ecf9a",
          rose: "#e35d6a",
          sky: "#4db0d1",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      backgroundImage: {
        "ops-grid":
          "linear-gradient(rgba(77,176,209,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(77,176,209,0.06) 1px, transparent 1px)",
        "ops-glow":
          "radial-gradient(ellipse 80% 50% at 20% -10%, rgba(232,162,58,0.18), transparent 55%), radial-gradient(ellipse 60% 40% at 90% 0%, rgba(77,176,209,0.16), transparent 50%)",
      },
      backgroundSize: {
        grid: "48px 48px",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s ease-out both",
        pulseSoft: "pulseSoft 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
