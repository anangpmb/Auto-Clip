import { readFileSync } from 'node:fs';
import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

/** Ship the helper and its launchers with the site so users can download them from the page. */
function helperDownloads(): Plugin {
  const files: Record<string, string> = {
    'autoclip_helper.py': 'text/x-python',
    'install-mac.sh': 'text/x-shellscript',
    'AutoClip.bat': 'application/x-bat',
  };
  const read = (name: string) => readFileSync(`helper/${name}`, 'utf8');
  return {
    name: 'autoclip-helper-downloads',
    generateBundle() {
      for (const name of Object.keys(files)) this.emitFile({ type: 'asset', fileName: name, source: read(name) });
    },
    configureServer(server) {
      for (const [name, type] of Object.entries(files)) {
        server.middlewares.use(`/${name}`, (_req, res) => {
          res.setHeader('Content-Type', `${type}; charset=utf-8`);
          res.end(read(name));
        });
      }
    },
  };
}

// Relative base so the build works at https://<user>.github.io/<repo>/
export default defineConfig({
  base: './',
  plugins: [svelte(), helperDownloads()],
});
