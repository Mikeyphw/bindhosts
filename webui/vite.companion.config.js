// P04: build the SAME UX10 entrypoint for a separate, strictly read-only Android host.
// The normal Vite configuration remains unchanged for KernelSU/WebUI-X.
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const local = path => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  base: './',
  resolve: {
    alias: [
      { find: /^kernelsu-alt$/, replacement: local('./runtime/companion_kernelsu_alt.mjs') },
      { find: /^webuix$/, replacement: local('./runtime/companion_webuix.mjs') },
    ],
  },
  build: {
    outDir: '../android/companion/app/src/main/assets/ux10',
    emptyOutDir: true,
    manifest: true,
  },
});
