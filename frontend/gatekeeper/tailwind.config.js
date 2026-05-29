/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'gk-bg': '#05050A',
        'gk-surface': '#0D0D1A',
        'gk-accent': '#00FFB2',
        'gk-danger': '#FF3366',
        'gk-gold': '#FFD166',
        'gk-primary': '#F0F0FF',
        'gk-muted': '#6B7280',
        'gk-border': 'rgba(0, 255, 178, 0.15)',
      },
      fontFamily: {
        syne: ['Syne', 'sans-serif'],
        dmmono: ['DM Mono', 'monospace'],
        space: ['Space Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}

