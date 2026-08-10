import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f6f4ef",
        ink: "#111111",
        accent: "#0f766e",
      },
    },
  },
  plugins: [],
};

export default config;
