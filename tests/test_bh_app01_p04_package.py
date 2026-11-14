"""P04 native UX10 asset parity source invariants; no Android SDK needed."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts/MainActivity.java'
VITE=ROOT/'webui/vite.companion.config.js'
WORKFLOW=ROOT/'.github/workflows/bh-app01-foundation.yml'
SHIM=ROOT/'webui/runtime/companion_kernelsu_alt.mjs'

class CompanionUx10Packaging(unittest.TestCase):
    def test_same_entrypoint_independent_build(self):
        v=VITE.read_text()
        self.assertIn("outDir: '../android/companion/app/src/main/assets/ux10'",v)
        self.assertIn('companion_kernelsu_alt.mjs',v)
        self.assertIn('companion_webuix.mjs',v)
        self.assertIn("base: './'",v)
        self.assertNotIn('rollupOptions',v)
        self.assertIn('emptyOutDir: true',v)

    def test_host_is_local_only(self):
        source=APP.read_text()
        self.assertIn('setDomStorageEnabled(true)',source)
        self.assertIn('assets/ux10/index.html',source)
        self.assertIn('!"https".equals(url.getScheme())',source)
        self.assertIn('appassets.androidplatform.net',source)
        self.assertIn('WebResourceResponse("text/plain", "UTF-8", 403',source)
        self.assertIn('VERIFIED HOSTS CONTROLS',source)
        self.assertIn('addWebMessageListener',source)
        self.assertNotIn('addJavascriptInterface',source)
        self.assertNotIn('setAllowFileAccess(true)',source)
        manifest=(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text()
        self.assertNotIn('android.permission.INTERNET',manifest)

    def test_read_registry_never_escalates(self):
        shim=SHIM.read_text()
        self.assertIn('nativeAppTransport',shim)
        self.assertIn('command === HOSTS_READ',shim)
        self.assertIn('command === MODULE_PROP_READ',shim)
        self.assertIn('return refused()',shim)
        self.assertIn('throw new Error(\'BH_APP01_P05_REFUSED',shim)
        self.assertNotIn('ProcessBuilder',shim)

    def test_ci_runs_real_webui_bundle_before_gradle(self):
        workflow=WORKFLOW.read_text()
        self.assertIn("pnpm --dir webui install --frozen-lockfile",workflow)
        self.assertIn('vite build --config vite.companion.config.js',workflow)
        self.assertIn('python3 scripts/ci/bh_app01_p04_bundle_check.py',workflow)
        self.assertIn('node tests/test_bh_app01_p04_runtime.mjs',workflow)
        self.assertLess(workflow.index('vite build --config'),workflow.index('gradle -p android/companion'))

    def test_same_webui_route_registry_when_full_checkout_present(self):
        routes=ROOT/'webui/route.js'
        if not routes.is_file():
            self.skipTest('Full UX10 WebUI source only available in the real repository checkout')
        content=routes.read_text()
        for name in ('home','hosts','apps','more','catalog','activity'):
            self.assertIn(f'{name}:',content)
        self.assertEqual((ROOT/'webui/index.html').is_file(),True)

if __name__=='__main__':unittest.main()
