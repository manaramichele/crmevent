module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: { tiffany: { DEFAULT: "#0ABAB5", hover: "#09A8A3", light: "#E6F8F7", fg: "#0F4C45" }, ink: "#0F172A" },
      fontFamily: { display: ["'Plus Jakarta Sans'", "sans-serif"], sans: ["Inter", "sans-serif"] },
    },
  },
  plugins: [],
};
