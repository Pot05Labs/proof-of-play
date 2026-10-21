/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Where /api is proxied in dev and preview. Default is the local API; set POP_API_TARGET to
// point the local build at another deployment, e.g. the cloud app.
// Declared locally so the config type-checks in a clean install without @types/node (as in the image build).
declare const process: { env: Record<string, string | undefined> };
const API_TARGET = process.env.POP_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
