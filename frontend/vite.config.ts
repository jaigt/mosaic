/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Split the heaviest vendor libraries into their own async chunks so
        // the initial bundle stays well under the 500kB warning threshold.
        // recharts and react-markdown are also React.lazy'd (see Message.tsx),
        // so these chunks load on demand.
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
