import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built into ./dist and served by dashboard/server.py on the robot. Dev: `npm run dev` proxies /api + /ws to :8097.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, target: 'es2020', sourcemap: false,
    rollupOptions: { output: { manualChunks(id) { if (id.includes('node_modules')) return 'vendor' } } } },
  server: { port: 5198, proxy: { '/api': 'http://127.0.0.1:8097', '/ws': { target: 'ws://127.0.0.1:8097', ws: true } } },
})
