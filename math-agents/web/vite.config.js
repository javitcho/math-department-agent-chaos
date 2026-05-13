import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/sessions': 'http://localhost:5000',
      '/session': 'http://localhost:5000',
    }
  }
})
