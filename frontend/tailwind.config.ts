import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        gem: {
          navy: "#0a192f",
          dark: "#0f172a",
          card: "#1e293b",
          border: "#334155",
          accent: "#2563eb",
          gold: "#f59e0b",
        },
      },
    },
  },
  plugins: [],
};
export default config;
