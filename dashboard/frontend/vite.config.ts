import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built into ./dist and served by dashboard/server.py on the robot. Dev: `npm run dev` proxies /api + /ws to :8097.
// MuJoCo WASM is NOT bundled: loaded at runtime from jsDelivr, fallback /public/mujoco (see src/lib/mujoco.ts).
// The twin model lives in /public/model (dashboard/tools/build_twin_model.py).
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, target: 'es2020', sourcemap: false,
    rollupOptions: { output: { manualChunks(id) {
      if (id.includes('node_modules/three/')) return 'vendor-three'
      if (id.includes('node_modules')) return 'vendor'
    } } } },
  optimizeDeps: { exclude: ['/mujoco/mujoco.js'] },
  server: { port: 5198, proxy: { '/api': 'http://127.0.0.1:8097', '/ws': { target: 'ws://127.0.0.1:8097', ws: true } } },
})
