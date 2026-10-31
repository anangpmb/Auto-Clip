import { readFileSync } from 'node:fs';
import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

/** Ship the helper script with the site so users can download it from the page. */
function helperDownload(): Plugin {
  const file = 'helper/autoclip_helper.py';
  return {
    name: 'autoclip-helper-download',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'autoclip_helper.py', source: readFileSync(file, 'utf8') });
    },
    configureServer(server) {
      server.middlewares.use('/autoclip_helper.py', (_req, res) => {
        res.setHeader('Content-Type', 'text/x-python; charset=utf-8');
        res.end(readFileSync(file, 'utf8'));
      });
    },
  };
}

// Relative base so the build works at https://<user>.github.io/<repo>/
export default defineConfig({
  base: './',
  plugins: [svelte(), helperDownload()],
});
