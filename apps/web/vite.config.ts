import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Local-only reverse proxy: preserves same-origin /api requests without changing backend CORS/auth.
const proxy = { '/api': { target: 'http://127.0.0.1:8000', rewrite: (path: string) => path.replace(/^\/api/, '') } };

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', strictPort: true, proxy },
  preview: { host: '127.0.0.1', strictPort: true, proxy },
});
