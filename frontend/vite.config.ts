import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const projectRoot = fileURLToPath(new URL('..', import.meta.url));
const fallbackAppPort = 3001;

export default defineConfig(({ mode }) => {
  // Load the repository-root .env even when Vite is started from frontend/.
  const env = loadEnv(mode, projectRoot, '');
  const parsedPort = Number(process.env.APP_PORT ?? env.APP_PORT ?? '');
  const appPort = Number.isInteger(parsedPort) && parsedPort > 0 && parsedPort <= 65535
    ? parsedPort
    : fallbackAppPort;
  const apiProxy = {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
  };

  return {
    envDir: projectRoot,
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: appPort,
      strictPort: true,
      proxy: apiProxy,
    },
    preview: {
      host: '0.0.0.0',
      port: appPort,
      strictPort: true,
      proxy: apiProxy,
    },
  };
});
