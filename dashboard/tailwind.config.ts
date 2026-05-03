import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ignis: {
          50: "#fff7ed", 100: "#ffedd5", 200: "#fed7aa",
          400: "#fb923c", 500: "#f97316", 600: "#ea580c",
          700: "#c2410c", 800: "#9a3412", 900: "#7c2d12",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
