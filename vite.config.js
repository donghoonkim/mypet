import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  // 상대 경로로 빌드해서 어느 하위 경로에 올려도 동작하게 한다
  base: './',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Tailscale(serve) 주소로 폰에서 접속할 수 있게 허용
    allowedHosts: ['.ts.net'],
  },
})
