/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: { colors: { ink: "#0b0e14", panel: "#131826", accent: "#ffd60a" } } },
  plugins: [],
};
