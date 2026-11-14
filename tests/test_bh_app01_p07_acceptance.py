"""P07 hostile/positive evidence and real-hosted workflow source checks."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/bh-app01-p07-api36.yml'
SIGN = ROOT / 'scripts/ci/bh_app01_p07_signoff.py'
PROBE = ROOT / 'scripts/ci/bh_app01_p07_physical_probe.py'
APK = ROOT / 'android/companion/app'

spec = importlib.util.spec_from_file_location('bh_p07_signoff', SIGN)
sign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sign)

class P07(unittest.TestCase):
    def test_only_hosted_gradle_and_real_emulator(self):
        w = WORKFLOW.read_text()
        hosted = (ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        for marker in ('reactivecircus/android-emulator-runner@v2', 'api-level: 36',
                       'target: google_apis', 'arch: x86_64',
                       'github.event.pull_request.head.sha || github.sha',
                       'SOURCE_SHA', 'bh_app01_p07_signoff.py', 'actions/upload-artifact@v4'):
            self.assertIn(marker, w)
        for marker in ('GITHUB_ACTIONS', 'RUNNER_OS', 'git rev-parse HEAD',
                       'ro.build.version.sdk', 'ro.product.cpu.abi',
                       ':app:connectedDebugAndroidTest', ':app:lintDebug',
                       'screencap -p', 'source-commit.txt', 'app-debug.apk'):
            self.assertIn(marker, hosted)
        self.assertNotIn('|| true', hosted)
        self.assertNotIn('continue-on-error: true', w)
        self.assertNotIn('abortOnError = false', w)

    def test_instrumented_ux10_and_cancel_safety(self):
        code = (APK/'src/androidTest/java/com/mikeyphw/bindhosts/P07HostedUiTest.java').read_text()
        gradle = (APK/'build.gradle.kts').read_text()
        manifest = (APK/'src/main/AndroidManifest.xml').read_text()
        for name in sign.EXPECTED_TESTS:
            self.assertIn('void '+name+'()', code)
        for fragment in ('ActivityScenario.launch', 'document.readyState',
                         'location.origin', 'document.querySelector', 'withText("Cancel")',
                         'getAllowContentAccess()', 'getAllowFileAccess()',
                         'android.permission.INTERNET', 'assertFalse(RootRunner.',
                         'onView(withText("Update Bindhosts rules?"))'):
            self.assertIn(fragment, code)
        self.assertIn('testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"',gradle)
        self.assertIn('androidTestImplementation("androidx.test.espresso:espresso-core:',gradle)
        self.assertNotIn('android.permission.INTERNET',manifest)
        self.assertNotIn('onView(withText("Update"))',code)

    def test_ci_required_p07_without_easing_release_policy(self):
        p = json.loads((ROOT/'ci/bh-app01-required-workflows.json').read_text())
        self.assertEqual(p['required_workflows'], [
            'bh-app01-foundation.yml', 'bh-app01-p07-api36.yml',
            'bindhosts-ux-ci.yml','trackerguard-ci.yml'])
        self.assertNotEqual(p['ci_qualification'],p['release_qualification'])
        doc=(ROOT/'docs/BH_APP01_P07_HOSTED_AND_PHYSICAL_ACCEPTANCE.md').read_text()
        self.assertIn('physical_android16_qualified=false',doc)

    def test_physical_probe_is_read_only_and_approval_gated(self):
        source = PROBE.read_text()
        for phrase in ('I_AUTHORIZE_READ_ONLY_DEVICE_PROBE','getprop', "'pm', 'path'",
                       "'dumpsys', 'package'", "'physical_android16_qualified': False",
                       "'device_writes_performed': False"):
            self.assertIn(phrase,source)
        for forbidden in ("'install'", "'uninstall'", "'su'", "'am', 'start'", "'shell', 'rm'", 'adb root'):
            self.assertNotIn(forbidden, source)

    def create(self, out, *, present=True, wrong_api=False, fail=False, skip=False, missing=None):
        out.mkdir()
        sha='a'*40
        (out/'source-commit.txt').write_text(sha+'\n')
        (out/'emulator-api.txt').write_text('35\n' if wrong_api else '36\n')
        (out/'apk-sha256.txt').write_text('c'*64+'\n')
        (out/'api36-home.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*6000)
        if present:
            testcase=''.join(f'<testcase classname="com.mikeyphw.bindhosts.P07HostedUiTest" name="{name}">' +
                              ('<failure />' if fail and k==0 else '<skipped />' if skip and k==0 else '')+
                              '</testcase>' for k,name in enumerate(sorted(sign.EXPECTED_TESTS)))
            (out/'TEST-P07.xml').write_text(f'<testsuite tests="3" failures="{int(fail)}" errors="0" skipped="{int(skip)}">{testcase}</testsuite>')
        if missing: (out/missing).unlink()
        return sha

    def test_evidence_positive_but_explicitly_not_physical_or_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';sha=self.create(out)
            receipt=sign.qualify(out,sha)
            self.assertTrue(receipt['hosted_api36_qualified'])
            self.assertFalse(receipt['physical_android16_qualified'])
            self.assertFalse(receipt['release_qualified'])
            self.assertEqual(receipt['test_count'],3)

    def test_evidence_negatives_refuse_without_silent_degradation(self):
        variations=[dict(present=False), dict(wrong_api=True),dict(fail=True),
                    dict(skip=True),dict(missing='api36-home.png'),
                    dict(missing='apk-sha256.txt'),dict(missing='source-commit.txt')]
        for n,variation in enumerate(variations):
            with self.subTest(case=n), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';sha=self.create(out,**variation)
                with self.assertRaises((ValueError,FileNotFoundError)):
                    sign.qualify(out,sha)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';self.create(out)
            with self.assertRaises(ValueError):sign.qualify(out,'b'*40)

if __name__=='__main__': unittest.main()
