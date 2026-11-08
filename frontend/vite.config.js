import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Vite only loads env files from this directory, which is why VITE_API_URL
  // belongs in frontend/.env.local and not in the repo root .env: a value put
  // there never reaches the bundle and the app silently falls back to /api.
  // import.meta.dirname rather than process.cwd(): env files live next to
  // this file, and it keeps the config free of Node globals.
  const env = loadEnv(mode, import.meta.dirname, '')
  // uvicorn's default. BACKEND_PORT overrides it for anyone running the API
  // somewhere else, so nobody has to edit this file to do it.
  const target = env.BACKEND_URL ?? `http://localhost:${env.BACKEND_PORT ?? 8000}`

  return {
    plugins: [react()],
    server: {
      // src/lib/api.js calls /api/*. This forwards those to the FastAPI server
      // and strips the prefix, so /api/me/now hits /me/now. One origin in dev
      // means no CORS preflight and no hardcoded port in the app code.
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
