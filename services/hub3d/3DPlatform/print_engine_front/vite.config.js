import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: [
      'mike.solainecreation.fr'
    ]
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: [
      'mike.solainecreation.fr'
    ]
  }
})