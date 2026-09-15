import { defineConfig } from 'vite';

export default defineConfig({
  // Vite dev server 配置（用于开发模式 HMR）
  root: '.',
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8894',
        changeOrigin: true,
      },
    },
  },
  // 生产构建配置
  build: {
    outDir: 'dist',
    // 不处理 bundle.js（已有手动构建流程）
    rollupOptions: {
      input: 'index.html',
    },
  },
});
