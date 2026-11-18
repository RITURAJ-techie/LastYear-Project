/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--page)",
        surface: "var(--surface-1)",
        surface2: "var(--surface-2)",
        ink: "var(--text-primary)",
        ink2: "var(--text-secondary)",
        muted: "var(--text-muted)",
        line: "var(--border)",
        accent: "var(--accent)",
        accentsoft: "var(--accent-soft)",
        good: "var(--status-good)",
        warn: "var(--status-warning)",
        serious: "var(--status-serious)",
        critical: "var(--status-critical)",
      },
      fontFamily: { sans: ['system-ui', '-apple-system', '"Segoe UI"', "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};
