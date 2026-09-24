import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
// The app's version (also the Android versionName): the update check compares
// it with the latest GitHub release.
const { version: appVersion } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

export default defineConfig(({ mode }) => {
  // Supabase settings live in the repo-root .env shared with the backend (or in
  // build args under Docker). Only the public URL and anon key reach the bundle.
  const env = loadEnv(mode, '..', '')

  // The Android app has no /api proxy, so it calls the deployed backend directly.
  const mobileDefines = {}
  if (mode === 'android') {
    const apiUrl = (env.MOBILE_API_URL || '').replace(/\/$/, '')
    if (!apiUrl.startsWith('https://')) {
      throw new Error('Set MOBILE_API_URL in .env to the deployed backend, e.g. https://wattsplit-api.onrender.com/api')
    }
    mobileDefines['import.meta.env.VITE_API_URL'] = JSON.stringify(apiUrl)
  }

  return {
    plugins: [react()],
    define: {
      ...mobileDefines,
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(appVersion),
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(
        env.VITE_SUPABASE_URL || env.SUPABASE_URL || ''
      ),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(
        env.VITE_SUPABASE_ANON_KEY || env.SUPABASE_ANON_KEY || ''
      ),
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
