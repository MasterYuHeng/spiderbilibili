import path from 'node:path'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = (env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
  const shouldUseLocalProxy = !apiBaseUrl || apiBaseUrl === 'http://127.0.0.1:8014'

  return {
    plugins: [vue()],
    server: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      proxy: shouldUseLocalProxy
        ? {
            '/api': {
              target: 'http://127.0.0.1:8014',
              changeOrigin: true,
            },
          }
        : undefined,
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
  }
})
