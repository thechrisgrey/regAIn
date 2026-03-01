/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
const threePackages = new Set(['three', '@react-three/fiber', '@react-three/drei', 'three-custom-shader-material']);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (threePackages.has(id) || id.includes('node_modules/three/') || id.includes('node_modules/@react-three/') || id.includes('node_modules/three-custom-shader-material/')) {
            return 'three';
          }
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
