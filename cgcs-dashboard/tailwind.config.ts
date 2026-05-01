import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cgcs: {
          ink: "#0f172a",
          mute: "#475569",
          line: "#e2e8f0",
          accent: "#0369a1",
          good: "#16a34a",
          bad: "#dc2626",
        },
      },
    },
  },
  plugins: [],
};

export default config;
