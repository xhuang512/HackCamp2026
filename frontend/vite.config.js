import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // src/lib/api.js calls /api/*. This forwards those to the FastAPI server
    // and strips the prefix, so /api/me/now hits /me/now on :8000. One origin
    // in dev means no CORS preflight and no hardcoded port in the app code.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
