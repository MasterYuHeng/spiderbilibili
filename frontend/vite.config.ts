import path from 'node:path'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 4174,
    strictPort: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts/core') || id.includes('node_modules/zrender')) {
            return 'chart-core-vendor'
          }

          if (id.includes('node_modules/echarts/charts')) {
            return 'chart-series-vendor'
          }

          if (id.includes('node_modules/echarts/components') || id.includes('node_modules/echarts/renderers')) {
            return 'chart-components-vendor'
          }

          if (id.includes('node_modules/element-plus')) {
            return 'ui-vendor'
          }

          if (id.includes('node_modules/vue') || id.includes('node_modules/pinia') || id.includes('node_modules/vue-router')) {
            return 'vue-vendor'
          }

          return undefined
        },
      },
    },
  },
})
