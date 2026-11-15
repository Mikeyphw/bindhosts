"""P07 hostile/positive evidence and real-hosted workflow source checks."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
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
        for marker in ('ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d', 'api-level: 36',
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
                         'location.origin', 'document.querySelector', 'AlertDialog.BUTTON_NEGATIVE',
                         'getAllowContentAccess()', 'getAllowFileAccess()',
                         'android.permission.INTERNET', 'assertFalse(RootRunner.',
                         'dialogHasText('):
            self.assertIn(fragment, code)
        self.assertIn('testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"',gradle)
        self.assertIn('androidTestImplementation("androidx.test.espresso:espresso-core:',gradle)
        self.assertNotIn('android.permission.INTERNET',manifest)
        self.assertNotIn('onView(withText("Update"))',code)

    def test_hf01_cold_start_modal_is_deferred_and_not_duplicated(self):
        activity = (APK/'src/main/java/com/mikeyphw/bindhosts/MainActivity.java').read_text()
        test = (APK/'src/androidTest/java/com/mikeyphw/bindhosts/P07HostedUiTest.java').read_text()
        self.assertIn('private void consumeUpdateIntent(Intent intent)', activity)
        self.assertIn('intent.setAction(null)', activity)
        self.assertIn('pendingUpdateConfirmation = true', activity)
        self.assertIn('private void scheduleUpdateConfirmation()', activity)
        self.assertIn('frame.post(() -> {', activity)
        self.assertIn('activityResumed = true;', activity)
        self.assertIn('activityResumed = false;', activity)
        self.assertIn('updateConfirmationScheduled', activity)
        self.assertIn('updateConfirmation.setOnDismissListener', activity)
        self.assertIn('updateConfirmation.dismiss()', activity)
        self.assertNotIn('intent.setAction(null); // Avoid repeating a prior confirmation after recreation.\n            showConfirmUpdate();',activity)
        self.assertIn('ActivityScenario.launch(MainActivity.class)',test)
        self.assertNotIn('ActivityScenario.launch(i)',test)
        self.assertIn('activity.onNewIntent(qs)',test)
        self.assertNotIn('activity.startActivity(qs)',test)
        self.assertIn('instrumentation.startActivitySync(launch)',test)
        self.assertNotIn('scenario.getState()',test)
        self.assertIn('requireNativeUpdateConfirmation(instrumentation, activity)',test)
        self.assertIn('cancel.performClick()',test)
        self.assertIn('dialogHasText(',test)
        self.assertNotIn('onView(withText("Cancel")).perform(click())',test)
        hosted=(ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        self.assertIn('adb shell am force-stop com.mikeyphw.bindhosts',hosted)
        self.assertIn('adb shell am start -W',hosted)
        self.assertIn('bh_app01_p07_qs_hierarchy.py',hosted)
        self.assertIn('QS_CONFIRM_CANCELLED',hosted)
        self.assertIn('qs-cold-start-receipt.txt',hosted)
        self.assertNotIn('adb shell input tap 0 0',hosted)

    def test_hf01_fail_closed_emulator_diagnostics(self):
        hosted=(ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        self.assertIn('trap collect_failure_evidence EXIT',hosted)
        self.assertIn('local status=$?',hosted)
        self.assertIn('exit "$status"',hosted)
        self.assertIn('emulator-failure-logcat.txt',hosted)
        self.assertIn('failed-command-exit.txt',hosted)
        self.assertIn('api36-failure.png',hosted)
        self.assertIn('androidTest-results/connected',hosted)
        self.assertIn('if (( status != 0 )); then',hosted)
        self.assertNotIn('|| true',hosted)

    def test_hf01_emulator_failure_trap_preserves_exit_and_evidence(self):
        # Execute real Bash control flow against inert fake commands. NO Gradle
        # or Android device is touched; the stub `gradle` simply exits 17.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fake=root/'bin'; fake.mkdir()
            scripts={
                'git': '#!/bin/sh\nprintf "'+'a'*40+'\\n"\n',
                'gradle': '#!/bin/sh\nexit 17\n',
                'adb': """#!/bin/sh
case "$1" in
  devices) printf 'List of devices attached\nemulator-5554 device product:sdk model:generic\n' ;;
  shell) case "$*" in *ro.build.version.sdk*) printf '36\n';; *ro.product.cpu.abi*) printf 'x86_64\n';; *) exit 9;; esac ;;
  logcat) printf 'HF01_HOSTED_EMULATOR_DIAGNOSTIC_MARKER\n' ;;
  exec-out) printf '\\211PNG\\r\\n\\032\\nFAILURE_SCREENSHOT' ;;
  *) exit 9 ;;
esac
""",
            }
            for name,body in scripts.items():
                p=fake/name
                p.write_text(body)
                p.chmod(0o755)
            env={**os.environ, 'GITHUB_ACTIONS':'true', 'RUNNER_OS':'Linux',
                 'SOURCE_SHA':'a'*40, 'PATH':str(fake)+os.pathsep+os.environ['PATH']}
            completed=subprocess.run(['bash',str(ROOT/'scripts/ci/bh_app01_p07_emulator.sh')],
                 cwd=root,env=env,text=True,capture_output=True,timeout=10)
            evidence=root/'android/companion/p07-evidence'
            self.assertEqual(completed.returncode,17,completed.stderr)
            self.assertEqual((evidence/'failed-command-exit.txt').read_text().strip(),'17')
            self.assertIn('HF01_HOSTED_EMULATOR_DIAGNOSTIC_MARKER',
                          (evidence/'emulator-failure-logcat.txt').read_text())
            self.assertTrue((evidence/'api36-failure.png').is_file())
            self.assertFalse((evidence/'api36-home.png').exists())
            with self.assertRaises((FileNotFoundError,ValueError)):
                sign.qualify(evidence,'a'*40)

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
        apk_bytes=b'hosted-tested-apk-debug' + bytes(range(256))
        apk_hash=__import__('hashlib').sha256(apk_bytes).hexdigest()
        (out/'hosted-app-debug.apk').write_bytes(apk_bytes)
        (out/'apk-sha256.txt').write_text(apk_hash+'\n')
        (out/'emulator-installed-identity.txt').write_text(
            'schema=bh-app01/p07/hf05\nsource_sha='+sha+
            '\nemulator_api=36\nemulator_abi=x86_64\npackage=com.mikeyphw.bindhosts'+
            '\napk_sha256='+apk_hash+'\ninstalled_sha256='+apk_hash+
            '\nphysical_device_writes=false\n')
        (out/'api36-home.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*6000)
        (out/'api36-qs-confirmation.png').write_bytes(b'\x89PNG\r\n\x1a\n'+b'y'*6000)
        (out/'qs-cold-start-am.txt').write_text('Status: ok\n')
        (out/'qs-cold-start-receipt.txt').write_text('schema=bh-app01/p07/hf02\nsource_sha='+sha+
            '\nemulator_api=36\ncold_start_confirm=PASS\nqs_cancel=PASS\nphysical_device_writes=false\n')
        (out/'qs-cold-start-logcat.txt').write_text('QS_CONFIRM_INTENT_ACCEPTED\nQS_CONFIRM_DIALOG_VISIBLE\nQS_CONFIRM_CANCELLED\n')
        (out/'qs-cold-start-hierarchy.xml').write_text('<hierarchy rotation="0"><node text="Update Bindhosts rules?" />'
            '<node text="Cancel" enabled="true" clickable="true" bounds="[10,20][110,120]" /></hierarchy>')
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
            self.assertTrue(receipt['real_cold_start_qs_confirm_and_cancel'])

    def test_evidence_negatives_refuse_without_silent_degradation(self):
        variations=[dict(present=False), dict(wrong_api=True),dict(fail=True),
                    dict(skip=True),dict(missing='api36-home.png'),
                    dict(missing='apk-sha256.txt'),dict(missing='hosted-app-debug.apk'),dict(missing='source-commit.txt'),
                    dict(missing='emulator-installed-identity.txt'),
                    dict(missing='qs-cold-start-receipt.txt'),
                    dict(missing='qs-cold-start-hierarchy.xml'),
                    dict(missing='api36-qs-confirmation.png'),
                    dict(missing='qs-cold-start-logcat.txt')]
        for n,variation in enumerate(variations):
            with self.subTest(case=n), tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'evidence';sha=self.create(out,**variation)
                with self.assertRaises((ValueError,FileNotFoundError)):
                    sign.qualify(out,sha)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';self.create(out)
            with self.assertRaises(ValueError):sign.qualify(out,'b'*40)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';sha=self.create(out)
            p=out/'emulator-installed-identity.txt'
            for variant in (p.read_text().replace('installed_sha256='+(out/'apk-sha256.txt').read_text().strip(),
                                                  'installed_sha256='+'d'*64),
                            p.read_text().replace('emulator_api=36','emulator_api=35'),
                            p.read_text().replace('physical_device_writes=false','physical_device_writes=true')):
                p.write_text(variant)
                with self.assertRaises(ValueError): sign.qualify(out,sha)

    def test_ph02_tested_apk_bytes_must_match_hosted_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';sha=self.create(out)
            tested=out/'hosted-app-debug.apk'
            tested.write_bytes(tested.read_bytes()+b'tampered')
            with self.assertRaises(ValueError):sign.qualify(out,sha)
            tested.unlink()
            with self.assertRaises((FileNotFoundError,ValueError)):sign.qualify(out,sha)

    def test_hf02_ui_hierarchy_parsing_and_adversarial_refusals(self):
        import importlib.util
        parser=ROOT/'scripts/ci/bh_app01_p07_qs_hierarchy.py'
        spec=importlib.util.spec_from_file_location('bh_hf02_parser',parser)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'screen.xml'
            p.write_text('<hierarchy><node text="Update Bindhosts rules?" />'
                         '<node text="CANCEL" enabled="true" clickable="true" bounds="[20,40][120,100]" /></hierarchy>')
            self.assertEqual(module.parse(p),(70,70))
            negatives=[
               '<hierarchy><node text="Update"/><node text="Cancel" enabled="true" clickable="true" bounds="[10,20][20,40]"/></hierarchy>',
               '<hierarchy><node text="Update Bindhosts rules?" /><node text="Update" enabled="true" clickable="true" bounds="[10,20][20,40]"/></hierarchy>',
               '<hierarchy><node text="Update Bindhosts rules?" /><node text="Cancel" enabled="false" clickable="true" bounds="[10,20][20,40]"/></hierarchy>',
               '<hierarchy><node text="Update Bindhosts rules?" /><node text="Cancel" enabled="true" clickable="true" bounds="[-5,20][20,40]"/></hierarchy>',
               '<html><node text="Update Bindhosts rules?" /><node text="Cancel" enabled="true" clickable="true" bounds="[10,20][20,40]"/></html>',
            ]
            for content in negatives:
                p.write_text(content)
                with self.assertRaises(ValueError):module.parse(p)

    def test_hf02_cold_start_receipt_wrong_sha_audit_and_failure_artifacts_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'evidence';sha=self.create(out)
            (out/'qs-cold-start-receipt.txt').write_text('schema=bh-app01/p07/hf02\nsource_sha='+'b'*40+'\nemulator_api=36\ncold_start_confirm=PASS\nqs_cancel=PASS\nphysical_device_writes=false\n')
            with self.assertRaises(ValueError):sign.qualify(out,sha)
            (out/'qs-cold-start-receipt.txt').write_text('schema=bh-app01/p07/hf02\nsource_sha='+sha+'\nemulator_api=36\ncold_start_confirm=PASS\nqs_cancel=PASS\nphysical_device_writes=false\n')
            (out/'qs-cold-start-logcat.txt').write_text('QS_CONFIRM_INTENT_ACCEPTED\nQS_CONFIRM_DIALOG_VISIBLE\n')
            with self.assertRaises(ValueError):sign.qualify(out,sha)
            (out/'qs-cold-start-logcat.txt').write_text('QS_CONFIRM_INTENT_ACCEPTED\nQS_CONFIRM_DIALOG_VISIBLE\nQS_CONFIRM_CANCELLED\n')
            (out/'failed-command-exit.txt').write_text('1\n')
            with self.assertRaises(ValueError):sign.qualify(out,sha)

    def test_hf06_reject_unfocused_espresso_background_root_and_preserve_real_cancel(self):
        source = (APK/'src/androidTest/java/com/mikeyphw/bindhosts/P07HostedUiTest.java').read_text()
        third = source.split('void updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled()',1)[1]
        third = third.split('\n    }',1)[0]
        self.assertIn('AlertDialog confirmation = requireNativeUpdateConfirmation', third)
        self.assertIn('dialogHasText(', third)
        self.assertIn('Button cancel = confirmation.getButton(AlertDialog.BUTTON_NEGATIVE)', third)
        self.assertIn('cancel.performClick()', third)
        self.assertIn('Cancel failed to dismiss real confirmation', third)
        self.assertNotIn('onView(', third)
        self.assertNotIn('ActivityScenario.launch(', third)
        # The real ADB cold-start/dialog/CANCEL action remains a separate gate.
        shell=(ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        for fragment in ('adb shell am force-stop', 'adb shell am start -W',
                         'qs-cold-start-hierarchy.xml', 'adb shell input tap "$x" "$y"',
                         'QS_CONFIRM_CANCELLED'):
            self.assertIn(fragment, shell)

    def test_hf04_cinderbox_api36_runner_is_pinned_and_disposable(self):
        workflow = WORKFLOW.read_text()
        proven = 'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d'
        for fragment in ('runs-on: ubuntu-24.04', proven,
                         'cores: 2', 'ram-size: 3072M', 'disk-size: 3072M',
                         '-camera-back none -camera-front none',
                         'github.event.pull_request.head.sha || github.sha',
                         'bh_app01_p07_signoff.py', 'if: always()'):
            self.assertIn(fragment, workflow)
        self.assertNotIn('continue-on-error: true', workflow)
        self.assertNotIn('abortOnError = false', workflow)

    def test_hf04_real_qs_and_instrumentation_lifecycle_without_androidx_close(self):
        source = (APK/'src/androidTest/java/com/mikeyphw/bindhosts/P07HostedUiTest.java').read_text()
        marker = 'void updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled()'
        self.assertEqual(source.count(marker), 1)
        test = source.split(marker, 1)[1].split('\n    }',1)[0]
        for must in ('instrumentation.startActivitySync(launch)',
                     'instrumentation.runOnMainSync(() -> {',
                     'activity.onNewIntent(qs)',
                     'requireNativeUpdateConfirmation(instrumentation, activity)',
                     'dialogHasText(', 'cancel.performClick()',
                     'assertFalse("Cancel unexpectedly finished the Activity"',
                     'assertNotNull("Cancel must leave the native WebView attached"',
                     'finally {', 'activity.finish();', 'instrumentation.waitForIdleSync()'):
            self.assertIn(must, test)
        for prohibited in ('ActivityScenario.launch(', 'scenario.getState()',
                           'scenario.close()', 'activity.startActivity(qs)',
                           'onView(withText("Update")).perform(click())'):
            self.assertNotIn(prohibited, test)
        # First existing UI test still uses a real ActivityScenario and assets.
        self.assertIn('try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class))', source)
        shell = (ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        verifier = (ROOT/'scripts/ci/bh_app01_p07_signoff.py').read_text()
        for token in ('adb shell am force-stop com.mikeyphw.bindhosts',
                      'adb shell am start -W -n com.mikeyphw.bindhosts/.MainActivity',
                      'adb shell input tap "$x" "$y"',
                      'qs-cold-start-receipt.txt', 'QS_CONFIRM_CANCELLED'):
            self.assertIn(token, shell)
        for token in ('EXPECTED_TESTS = frozenset({', 'qs-cold-start-receipt.txt',
                      'qs-cold-start-hierarchy.xml', 'real_cold_start_qs_confirm_and_cancel'):
            self.assertIn(token, verifier)
        self.assertNotIn('continue-on-error: true', WORKFLOW.read_text())

    def test_hf05_reinstall_happens_after_android_instrumentation_before_cold_start(self):
        sh=(ROOT/'scripts/ci/bh_app01_p07_emulator.sh').read_text()
        helper=(ROOT/'scripts/ci/bh_app01_p07_install_identity_hf05.sh').read_text()
        verifier=(ROOT/'scripts/ci/bh_app01_p07_signoff.py').read_text()
        build=sh.index(':app:connectedDebugAndroidTest')
        reinstall=sh.index('bash scripts/ci/bh_app01_p07_install_identity_hf05.sh')
        cold=sh.index('adb shell am force-stop com.mikeyphw.bindhosts')
        self.assertLess(build,reinstall)
        self.assertLess(reinstall,cold)
        for fragment in ('GITHUB_ACTIONS', 'SOURCE_SHA', 'git rev-parse HEAD',
                         'emulator-5554', 'ro.kernel.qemu', 'ro.build.version.sdk',
                         'ro.product.cpu.abi', 'install -r -t',
                         'pm path com.mikeyphw.bindhosts', 'shell sha256sum',
                         'INSTALLED_BYTES_MISMATCH', 'emulator-installed-identity.txt'):
            self.assertIn(fragment,helper)
        for fragment in ('emulator-installed-identity.txt', 'installed_sha256=',
                         'physical_device_writes=false', 'hosted installed APK byte identity'):
            self.assertIn(fragment,verifier)
        self.assertIn('adb shell input tap "$x" "$y"',sh)
        self.assertNotIn('continue-on-error: true', WORKFLOW.read_text())

    def test_hf05_real_bash_emulator_reinstall_fixture_and_adversarial_refusals(self):
        # All adbs here are synthetic executables in a temp dir; no real Android
        # connection or installation is made from these Python tests.
        import hashlib
        helper=ROOT/'scripts/ci/bh_app01_p07_install_identity_hf05.sh'
        sha='a'*40
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);bin=work/'bin';bin.mkdir()
            apk=work/'android/companion/app/build/outputs/apk/debug/app-debug.apk'
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b'DISPOSABLE_APK_HF05_'+bytes(range(64)))
            apk_hash=hashlib.sha256(apk.read_bytes()).hexdigest()
            ev=work/'android/companion/p07-evidence';ev.mkdir(parents=True)
            (ev/'apk-sha256.txt').write_text(apk_hash+'\n')
            script='''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$ADB_CALLS"
case "${HF05_SCENARIO:-good}" in physical) qemu=0;; *) qemu=1;; esac
if [ "$1" = devices ]; then
  printf 'List of devices attached\\nemulator-5554 device product:generic\\n'; exit 0
fi
[ "$1" = -s ] && [ "$2" = emulator-5554 ] || exit 41
shift 2
case "$1" in
 get-state) echo device ;;
 install) [ "${HF05_SCENARIO:-good}" != install_fail ] || exit 42
          echo Success ;;
 shell) shift
  case "$1" in
   getprop) case "$2" in
    ro.kernel.qemu) echo "$qemu";;
    ro.build.version.sdk) echo 36;;
    ro.product.cpu.abi) echo x86_64;;
    *) exit 43;; esac ;;
   pm) [ "${HF05_SCENARIO:-good}" != no_package ] || exit 44
       echo 'package:/data/app/~~fixture/com.mikeyphw.bindhosts-fake/base.apk' ;;
   sha256sum) if [ "${HF05_SCENARIO:-good}" = mismatch ]; then
                 printf '%064d  %s\\n' 0 "$2"
               else printf '%s  %s\\n' "$APK_HASH" "$2"; fi ;;
   *) exit 45;; esac ;;
 *) exit 46;;
esac
'''
            (bin/'adb').write_text(script);(bin/'adb').chmod(0o755)
            (bin/'git').write_text('#!/bin/sh\n[ "$1" = rev-parse ] || exit 47\n[ "$2" = HEAD ] || exit 48\nprintf "%s\\n" "'+sha+'"\n')
            (bin/'git').chmod(0o755)
            env={**os.environ,'GITHUB_ACTIONS':'true','RUNNER_OS':'Linux',
                 'SOURCE_SHA':sha,'APK_HASH':apk_hash,'ADB_CALLS':str(work/'calls'),
                 'PATH':str(bin)+os.pathsep+os.environ['PATH']}
            args=['bash',str(helper),'android/companion/app/build/outputs/apk/debug/app-debug.apk',
                  'android/companion/p07-evidence']
            ok=subprocess.run(args,cwd=work,env=env,text=True,capture_output=True,timeout=10)
            self.assertEqual(ok.returncode,0,ok.stderr)
            identity=(ev/'emulator-installed-identity.txt').read_text()
            self.assertIn('installed_sha256='+apk_hash,identity)
            self.assertIn('source_sha='+sha,identity)
            self.assertIn('install -r -t', (work/'calls').read_text())
            for bad in ('physical','mismatch','no_package','install_fail'):
                (ev/'emulator-installed-identity.txt').unlink(missing_ok=True)
                log=work/'calls';log.write_text('')
                done=subprocess.run(args,cwd=work,env={**env,'HF05_SCENARIO':bad},
                                    text=True,capture_output=True,timeout=10)
                self.assertEqual(done.returncode,12,(bad,done.stderr))
                self.assertFalse((ev/'emulator-installed-identity.txt').exists())
                if bad=='physical':self.assertNotIn('install -r -t',log.read_text())
            log=work/'calls';log.write_text('')
            denied=subprocess.run(args,cwd=work,env={**env,'SOURCE_SHA':'b'*40},
                                  text=True,capture_output=True,timeout=10)
            self.assertEqual(denied.returncode,12)
            self.assertNotIn('install -r -t',log.read_text())

if __name__=='__main__': unittest.main()
