/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#060d17',
        surface:  '#0b1120',
        surface2: '#101827',
        surface3: '#172030',
        border:   '#1e2d42',
        border2:  '#243347',
        text:     '#e2eaf4',
        muted:    '#6b7f99',
        dim:      '#3d5166',
        accent:   '#2563eb',
        'accent-hover': '#1d4ed8',
        'accent-dim':   '#1e3a5f',
        success:  '#16a34a',
        'success-dim':  '#14532d',
        danger:   '#dc2626',
        'danger-dim':   '#450a0a',
        warning:  '#d97706',
        'warning-dim':  '#451a03',
        removed:  '#ef4444',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
