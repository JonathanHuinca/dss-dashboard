/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'uct-blue-primary':   '#002B49',
        'uct-blue-secondary': '#003865',
        'uct-gold':           '#C59B27',
        'uct-gold-light':     '#E0B648',
        'uct-bg-main':        '#F8FAFC',
        'uct-card-bg':        '#FFFFFF',
        'uct-text-primary':   '#0F172A',
        'uct-text-muted':     '#64748B',
        'uct-danger':         '#DC2626',
        'uct-warning':        '#D97706',
        'uct-success':        '#16A34A',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
