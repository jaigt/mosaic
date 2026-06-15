/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // recharts is an intentionally large, lazy-loaded (React.lazy) async chunk
    // (~530kB) — it never touches the initial bundle (~78kB), so don't warn on it.
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // Split the heaviest vendor libraries into their own async chunks so
        // the initial bundle stays well under threshold. recharts and
        // react-markdown are also React.lazy'd (see Message.tsx), so these
        // chunks load on demand.
        manualChunks: {
          recharts: ['recharts'],
          markdown: ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
