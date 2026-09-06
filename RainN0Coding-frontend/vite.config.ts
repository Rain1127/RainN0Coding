import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'
import { resolveBuildTarget } from './build-target'

export default defineConfig(({ mode }) => {
  const isProduction = mode === 'production'
  const buildTarget = resolveBuildTarget(process.env.VITE_BUILD_TARGET)

  return {
    plugins: [
      vue(),
      tailwindcss(),
      Components({
        dts: false,
        resolvers: [AntDesignVueResolver({ importStyle: 'css-in-js' })],
      }),
    ],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
      },
    },
    base: isProduction ? buildTarget.base : '/',
    build: {
      outDir: isProduction ? buildTarget.outDir : 'dist',
      emptyOutDir: true,
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8123',
          changeOrigin: true,
        },
      },
    },
  }
})
