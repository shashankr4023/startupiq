import type { Config } from "tailwindcss";

// Palette drawn from the reference design: vivid electric blue + lime green
// accents on a light background, with white rounded cards ("tiles").
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: "#1b4dff",
          "blue-dark": "#1339cc",
          green: "#a3e635",
          "green-dark": "#84cc16",
        },
        ink: "#0f172a",
        muted: "#64748b",
        surface: "#f4f6fb",
      },
      borderRadius: {
        tile: "1.25rem",
      },
      boxShadow: {
        tile: "0 1px 3px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.05)",
      },
    },
  },
  plugins: [],
};

export default config;
