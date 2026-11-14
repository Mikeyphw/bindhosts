"""P04 bundle gate executable positive and adversarial fixtures; no Vite/network."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/ci/bh_app01_p04_bundle_check.py'

class BundleChecker(unittest.TestCase):
    def fixture(self, temp):
        dest=Path(temp)/'android/companion/app/src/main/assets/ux10'
        (dest/'assets').mkdir(parents=True, exist_ok=True)
        (dest/'.vite').mkdir(exist_ok=True)
        (dest/'locales/strings').mkdir(parents=True, exist_ok=True)
        html='''<!doctype html><div id="content-container"></div>
        <button page="home"></button><button page="hosts"></button>
        <button page="apps"></button><button page="more"></button>'''
        (dest/'index.html').write_text(html+' '*2200)
        (dest/'assets/main.js').write_text('/* bundled UX10 */\n'+'__bhCompanionPickText '+'x'*51000+' __bhCompanionPickText')
        (dest/'icon.png').write_bytes(b'fake-icon')
        (dest/'locales/strings/en.xml').write_text('<resources/>')
        (dest/'.vite/manifest.json').write_text(json.dumps({'index.html':{'file':'assets/main.js'}}))
        return dest

    def check(self, root):
        return subprocess.run([sys.executable, str(SCRIPT),'--repo',str(root)],capture_output=True,text=True,timeout=7)

    def test_complete_bundle_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.fixture(tmp)
            result=self.check(tmp)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('BH_APP01_P04_UX10_BUNDLE_PASS',result.stdout)

    def test_missing_pages_or_translations_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=self.fixture(tmp)
            html=dest/'index.html'
            html.write_text(html.read_text().replace('page="apps"','page="arbitrary"'))
            result=self.check(tmp)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('missing UX10 page apps',result.stderr)
            self.fixture(tmp)
            (dest/'locales/strings/en.xml').unlink()
            result=self.check(tmp)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('localizations not bundled',result.stderr)

    def test_missing_p06_native_picker_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=self.fixture(tmp)
            f=dest/'assets/main.js'
            f.write_text(f.read_text().replace('__bhCompanionPickText','BROKEN_PICKER'))
            res=self.check(tmp)
            self.assertNotEqual(res.returncode,0)
            self.assertIn('SAF picker bridge',res.stderr)

    def test_missing_js_or_dangling_manifest_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=self.fixture(tmp)
            (dest/'assets/main.js').unlink()
            self.assertNotEqual(self.check(tmp).returncode,0)
            self.fixture(tmp)
            (dest/'.vite/manifest.json').write_text(json.dumps({'index.html':{'file':'assets/not-there.js'}}))
            self.assertIn('missing Vite asset',self.check(tmp).stderr)

if __name__=='__main__':unittest.main()
