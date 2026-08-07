import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 8080,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || `http://127.0.0.1:${process.env.SERVER_PORT || 5000}`,
        changeOrigin: true,
        ws: true
      }
    }
  }
})