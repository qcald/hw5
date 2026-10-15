import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward API requests to the FastAPI backend (uvicorn main:app --reload --port 8000)
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
