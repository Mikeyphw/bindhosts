"""P05 host-control boundaries, source audit and synthetic non-root backend tests."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT/'module/companion_control_v2.sh'
ANDROID = ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts'

class P05Source(unittest.TestCase):
    def test_finite_contract_and_legacy_preservation(self):
        v1=json.loads((ROOT/'contracts/bh-app01-v1.json').read_text())
        v2=json.loads((ROOT/'contracts/bh-app01-v2.json').read_text())
        self.assertEqual(v1['api_version'],1)
        self.assertEqual(v2['api_version'],2)
        self.assertEqual(set(v2['allowed_operations']),{'pause','resume','update-start','update-status','update-events'})
        self.assertNotIn('tracker',v2['allowed_operations'])
        self.assertFalse(v2['host_command_interpolation'])

    def test_no_unrestricted_root_and_native_bridge(self):
        module=BACKEND.read_text()
        runner=(ANDROID/'RootRunner.java').read_text()
        activity=(ANDROID/'MainActivity.java').read_text()
        self.assertNotIn('eval ',module)
        self.assertNotIn('sh -c',module)
        self.assertIn('BH_APP01_P05_REFUSED:',module)
        self.assertIn('BH_HOSTS_PAUSE_PASS',module)
        self.assertIn('BH_HOSTS_RESUME_PASS',module)
        self.assertIn('read-back mismatch',module)
        self.assertIn('new ProcessBuilder("su", "-c", "/system/bin/sh " + script + " " + verb)',runner)
        self.assertIn('case "update-events"',runner)
        self.assertIn('isMainFrame',activity)
        self.assertNotIn('addJavascriptInterface',activity)
        self.assertNotIn('android.permission.INTERNET',(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text())

    def test_two_distinct_qs_tiles(self):
        manifest=(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text()
        protection=(ANDROID/'ProtectionTileService.java').read_text()
        update=(ANDROID/'UpdateTileService.java').read_text()
        self.assertIn('name=".UpdateTileService"',manifest)
        self.assertIn('name=".ProtectionTileService"',manifest)
        self.assertEqual(manifest.count('android.permission.BIND_QUICK_SETTINGS_TILE'),2)
        self.assertIn('AtomicBoolean',protection)
        self.assertIn('RootRunner.control(action)',protection)
        self.assertIn('RootRunner.read("status")',protection)
        self.assertIn('ACTION_CONFIRM_UPDATE',update)
        self.assertNotIn('RootRunner.control("update-start")',update)
        self.assertIn('setPositiveButton("Update"', (ANDROID/'MainActivity.java').read_text())

    def test_update_qs_tile_api_split_and_narrow_lint_exemption(self):
        source=(ANDROID/'UpdateTileService.java').read_text()
        self.assertIn('if (Build.VERSION.SDK_INT >= 34)',source)
        self.assertIn('startActivityAndCollapse(pending);',source)
        self.assertIn('launchLegacy(intent);',source)
        self.assertEqual(source.count('startActivityAndCollapse(intent);'),1)
        self.assertRegex(source,r'@SuppressLint\("StartActivityAndCollapseDeprecated"\)\s+private void launchLegacy\(Intent intent\)\s*\{\s*startActivityAndCollapse\(intent\);\s*\}')
        # No broad class or onClick suppression; deprecated call isolated to one legacy method.
        self.assertLess(source.index('public final class UpdateTileService'),source.index('@SuppressLint'))
        self.assertIn('setAction(MainActivity.ACTION_CONFIRM_UPDATE)',source)
        workflow=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        self.assertIn(':app:lintDebug',workflow)
        gradle=(ROOT/'android/companion/app/build.gradle.kts').read_text()
        self.assertNotIn('abortOnError = false',gradle)
        self.assertNotIn('disable.add("StartActivityAndCollapseDeprecated")',gradle)

    def test_explicit_ci_policy(self):
        policy=json.loads((ROOT/'ci/bh-app01-required-workflows.json').read_text())
        self.assertEqual(policy['schema'],'bh-app01/ci-policy/v1')
        self.assertEqual(policy['required_workflows'],['bh-app01-foundation.yml','bh-app01-p07-api36.yml','bindhosts-ux-ci.yml','trackerguard-ci.yml'])
        self.assertNotEqual(policy['ci_qualification'],policy['release_qualification'])

    def test_android_ci_has_gates(self):
        ci=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        for required in ('module/companion_control_v2.sh','bh-app01-v2.json','test_bh_app01_p05_runtime.mjs',':app:lintDebug'):
            self.assertIn(required,ci)
        self.assertNotIn('android-actions/setup-android@v3',ci)

@unittest.skipIf(os.geteuid() == 0, 'fixture mode explicitly refuses root; run unprivileged for positive tests')
class P05Backend(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='bh-p05-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.mod=self.root/'mod';self.mod.mkdir()
        self.state=self.root/'state';self.state.mkdir()
        (self.state/'hosts').write_text('ACTIVE\n')
        (self.state/'operation').write_text('IDLE\n')
        (self.mod/'bindhosts.sh').write_text('''#!/bin/sh
set -eu
[ "$1" = --hosts-control ] || exit 8
case "$2" in
  status) printf 'BH_HOSTS_STATE=%s\\n' "$(cat "$BH_APP01_V2_TEST_STATE/hosts")" ;;
  pause) [ "$(cat "$BH_APP01_V2_TEST_STATE/hosts")" = ACTIVE ] || exit 9; echo PAUSED > "$BH_APP01_V2_TEST_STATE/hosts"; echo BH_HOSTS_PAUSE_PASS ;;
  resume) [ "$(cat "$BH_APP01_V2_TEST_STATE/hosts")" = PAUSED ] || exit 9; echo ACTIVE > "$BH_APP01_V2_TEST_STATE/hosts"; echo BH_HOSTS_RESUME_PASS ;;
  *) exit 9 ;;
esac
''')
        (self.mod/'hosts_operation_ux09.sh').write_text('''#!/bin/sh
set -eu
case "$1" in
  status) printf 'BH_UX09_STATE=%s\\n' "$(cat "$BH_APP01_V2_TEST_STATE/operation")" ;;
  events) printf 'PREPARING|Ready\\n' ;;
  start) echo RUNNING > "$BH_APP01_V2_TEST_STATE/operation"; echo BH_UX09_STARTED=12345 ;;
  *) exit 11 ;;
esac
''')
        self.env={**os.environ,'BH_APP01_V2_TEST_MODE':'1','BH_APP01_V2_TEST_MODDIR':str(self.mod),'BH_APP01_V2_TEST_STATE':str(self.state)}
    def call(self,*args):
        return subprocess.run(['sh',str(BACKEND),*args],text=True,capture_output=True,env=self.env,timeout=8)
    def test_verified_reversible_toggle(self):
        p=self.call('pause');self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout),{'api':2,'action':'pause','hosts':'PAUSED','verified':True})
        self.assertEqual(self.call('pause').returncode,2)
        r=self.call('resume');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['hosts'],'ACTIVE')
    def test_update_start_status_events_and_busy_refusal(self):
        start=self.call('update-start');self.assertEqual(start.returncode,0,start.stderr)
        self.assertEqual(json.loads(start.stdout)['operation'],'RUNNING')
        self.assertEqual(self.call('update-start').returncode,2)
        self.assertEqual(self.call('pause').returncode,2)
        self.assertEqual(json.loads(self.call('update-status').stdout)['operation'],'RUNNING')
        self.assertIn('PREPARING|Ready',__import__('base64').b64decode(json.loads(self.call('update-events').stdout)['encoded']).decode())
    def test_unknown_extra_args_and_symlink_refusal(self):
        for args in [('tracker',),('pause','resume'),()]:
            self.assertEqual(self.call(*args).returncode,2)
        self.mod.rename(self.root/'mod-real')
        self.mod.symlink_to(self.root/'mod-real',target_is_directory=True)
        self.assertEqual(self.call('update-status').returncode,2)
    def test_disallow_update_while_paused_and_interrupted(self):
        (self.state/'hosts').write_text('PAUSED\n')
        self.assertEqual(self.call('update-start').returncode,2)
        (self.state/'hosts').write_text('ACTIVE\n')
        (self.state/'operation').write_text('INTERRUPTED\n')
        self.assertEqual(self.call('update-start').returncode,2)

if __name__=='__main__':unittest.main()
