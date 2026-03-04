/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        /* ── Static primary palette (fallback / Tailwind IntelliSense) ── */
        primary: {
          50:  '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },

        /* ── Theme-aware tokens (CSS variable backed) ─────────────────
           Usage:  bg-bd-card  text-bd-fg  border-bd-border  etc.
           ──────────────────────────────────────────────────────────── */
        bd: {
          /* Backgrounds */
          bg:         'var(--bd-bg)',
          'bg-mid':   'var(--bd-bg-mid)',
          card:       'var(--bd-bg-card)',
          'card-alt': 'var(--bd-bg-card-alt)',
          overlay:    'var(--bd-bg-overlay)',
          'overlay-md': 'var(--bd-bg-overlay-md)',
          'overlay-lg': 'var(--bd-bg-overlay-lg)',
          surface:    'var(--bd-bg-surface)',
          'surface-2':'var(--bd-bg-surface-2)',

          /* Borders */
          border:       'var(--bd-border)',
          'border-soft':'var(--bd-border-soft)',
          'border-strong':'var(--bd-border-strong)',

          /* Foreground / text */
          fg:       'var(--bd-fg)',
          muted:    'var(--bd-fg-muted)',
          subtle:   'var(--bd-fg-subtle)',
          ghost:    'var(--bd-fg-ghost)',

          /* Primary */
          primary:     'var(--bd-primary)',
          'primary-alt':'var(--bd-primary-alt)',
          'primary-dim':'var(--bd-primary-dim)',
          'primary-fg': 'var(--bd-primary-fg)',

          /* Accents */
          accent1: 'var(--bd-accent-1)',
          accent2: 'var(--bd-accent-2)',
          accent3: 'var(--bd-accent-3)',
          warn:    'var(--bd-accent-warn)',
          err:     'var(--bd-accent-err)',

          /* State */
          success:    'var(--bd-success)',
          'success-dim':'var(--bd-success-dim)',
          error:      'var(--bd-error)',
          'error-dim':'var(--bd-error-dim)',

          /* Nav */
          nav:        'var(--bd-nav-bg)',
          'nav-border':'var(--bd-nav-border)',

          /* Phase colors (ideal/glimmer define these; others fallback to accent) */
          'phase-values':    'var(--bd-phase-values, var(--bd-accent-1))',
          'phase-strengths': 'var(--bd-phase-strengths, var(--bd-accent-3))',
          'phase-interests': 'var(--bd-phase-interests, var(--bd-accent-2))',
          'phase-purpose':   'var(--bd-phase-purpose, var(--bd-accent-warn))',
          'phase-report':    'var(--bd-phase-report, var(--bd-accent-1))',
        },
      },

      /* Background gradients using CSS vars */
      backgroundImage: {
        'bd-gradient': 'linear-gradient(to bottom, var(--bd-bg), var(--bd-bg-mid), var(--bd-bg-end))',
        'bd-primary-gradient': 'linear-gradient(to right, var(--bd-primary), var(--bd-accent-1), var(--bd-accent-2))',
      },

      boxShadow: {
        'bd':    '0 4px 16px var(--bd-shadow)',
        'bd-lg': '0 8px 32px var(--bd-shadow)',
      },
    },
  },
  plugins: [],
};
