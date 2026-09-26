import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// /api/* -> http://localhost:8000/* (the model server). The prefix is stripped so the
// frontend can call /api/cells while the server keeps the contract's bare paths.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
    // the contract fixtures are imported from ../city so they stay single-source
    fs: { allow: ['..'] },
  },
})
