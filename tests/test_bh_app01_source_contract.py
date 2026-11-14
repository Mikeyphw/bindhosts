from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SourceContract(unittest.TestCase):
    def test_same_status_contract(self):
        schema = json.loads((ROOT / 'contracts/bh-app01-v1.json').read_text())
        self.assertEqual(schema['api_version'], 1)
        self.assertEqual(set(schema['allowed_operations']), {'hello','status'})
        self.assertFalse(schema['future_mutations_enabled'])

    def test_native_no_unrestricted_shell_bridge(self):
        activity = (ROOT / 'android/companion/app/src/main/java/com/mikeyphw/bindhosts/MainActivity.java').read_text()
        runner = (ROOT / 'android/companion/app/src/main/java/com/mikeyphw/bindhosts/RootRunner.java').read_text()
        tile = (ROOT / 'android/companion/app/src/main/java/com/mikeyphw/bindhosts/ProtectionTileService.java').read_text()
        self.assertNotIn('addJavascriptInterface', activity)
        self.assertIn('addWebMessageListener', activity)
        self.assertIn('isMainFrame', activity)
        self.assertIn('Unsupported operation', runner)
        self.assertNotIn('force-update', tile)
        self.assertNotIn('force-reset', tile)
        self.assertIn('STATE_UNAVAILABLE', tile)

    def test_no_native_web_network_or_backup(self):
        manifest = (ROOT / 'android/companion/app/src/main/AndroidManifest.xml').read_text()
        html = (ROOT / 'android/companion/app/src/main/assets/index.html').read_text()
        self.assertNotIn('android.permission.INTERNET', manifest)
        self.assertIn('android:allowBackup="false"', manifest)
        self.assertIn("connect-src 'none'", html)
        self.assertIn("frame-src 'none'", html)

if __name__ == '__main__': unittest.main(verbosity=2)
