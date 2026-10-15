import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 7471,
    strictPort: true,
    proxy: {
      '/api/admin/v1': {
        target: 'http://127.0.0.1:7460',
        // Change Host for the backend loopback guard. Origin remains the browser's origin.
        changeOrigin: true,
        proxyTimeout: 20000,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-element': ['vue', 'vue-router', 'pinia', 'element-plus'],
        },
      },
    },
    chunkSizeWarningLimit: 1300,
  },
})
