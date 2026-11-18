import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from 'tailwindcss';
import autoprefixer from 'autoprefixer';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    plugins: [react()],
    css: { postcss: { plugins: [tailwindcss({
      content: ['./index.html', './src/**/*.{ts,tsx}'],
      theme: { extend: {
        colors: Object.fromEntries(['surface', 'surface-dim', 'surface-bright', 'surface-container-lowest', 'surface-container-low', 'surface-container', 'surface-container-high', 'surface-container-highest', 'surface-variant', 'surface-tint', 'inverse-surface', 'background', 'background-white', 'on-surface', 'on-surface-variant', 'inverse-on-surface', 'on-background', 'outline', 'outline-variant', 'primary', 'on-primary', 'primary-container', 'on-primary-container', 'inverse-primary', 'primary-fixed', 'primary-fixed-dim', 'on-primary-fixed', 'on-primary-fixed-variant', 'secondary', 'on-secondary', 'secondary-container', 'on-secondary-container', 'secondary-fixed', 'secondary-fixed-dim', 'on-secondary-fixed', 'on-secondary-fixed-variant', 'tertiary', 'on-tertiary', 'tertiary-container', 'on-tertiary-container', 'tertiary-fixed', 'tertiary-fixed-dim', 'on-tertiary-fixed', 'on-tertiary-fixed-variant', 'error', 'on-error', 'error-container', 'on-error-container', 'status-info', 'status-success', 'status-warning', 'forest', 'living-green', 'card-border'].map(name => [name, `var(--${name})`])),
        fontFamily: { sans: ['Public Sans', 'sans-serif'] },
        borderRadius: { sm: '0.125rem', DEFAULT: '0.25rem', md: '0.375rem', lg: '0.5rem', xl: '0.75rem', full: '9999px' },
      } },
    }), autoprefixer()] } },
    server: { port: 5173, proxy: { '/api': env.VITE_PROXY_TARGET || 'http://localhost:8000' } },
    test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
  };
});
