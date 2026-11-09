#!/usr/bin/env python3
"""R2 package observer, ownership, app exclusions, fail-closed reconciliation acceptance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / 'module' / 'trackerguard.sh'
FIXTURE = ROOT / 'tests' / 'make_axml_fixture.py'

class TrackerGuardR2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._build = tempfile.TemporaryDirectory(prefix='tg-r2-build-')
        cls.build = Path(cls._build.name)
        cls.scanner = cls.build / 'axmlscan'
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'native' / 'axmlscan.c'), '-o', str(cls.scanner)], check=True)
        subprocess.run(['python3', str(FIXTURE), str(cls.build)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls._build.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='tg-r2-runtime-')
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for d in ('ifw', 'state', 'bin'):
            (self.root / d).mkdir()
        self.apk = self.root / 'base.apk'
        shutil.copyfile(self.build / 'app-utf8.apk', self.apk)
        self.version = self.root / 'version'
        self.version.write_text('1')
        self.installed = self.root / 'installed'
        self.installed.write_text('1')
        self.pm = self.root / 'bin' / 'pm'
        self.pm.write_text(textwrap.dedent('''\
            #!/bin/sh
            if [ "$1" = list ] && [ "$2" = packages ]; then
              if [ "$3" = -3 ] && [ "${4:-}" = -f ]; then
                echo 'package:/data/app/sim/base.apk=com.example.stable versionCode:1'
                if [ "$(cat "$TG_TEST_INSTALLED")" = 1 ]; then
                  echo "package:$TG_TEST_APK=com.example.app versionCode:$(cat "$TG_TEST_VERSION")"
                fi
              else
                echo 'package:com.example.stable'
                if [ "$(cat "$TG_TEST_INSTALLED")" = 1 ]; then
                  echo 'package:com.example.app'
                fi
              fi
            elif [ "$1" = path ] && [ "$2" = com.example.app ]; then
              echo "package:$TG_TEST_APK"
            else
              exit 2
            fi
        '''))
        self.pm.chmod(0o755)
        self.bb = self.root / 'bin' / 'busybox'
        self.bb.write_text('#!/bin/sh\n[ "$1" = unzip ] || exit 2\nshift\nexec "$TG_TEST_UNZIP" "$@"\n')
        self.bb.chmod(0o755)
        self.env = dict(os.environ,
            TG_ROOT_SKIP='1', TG_STATE_DIR=str(self.root/'state'),
            TG_IFW_DIR=str(self.root/'ifw'), TG_PM=str(self.pm),
            TG_R1_MODDIR=str(ROOT/'module'), TG_R1_SCANNER=str(self.scanner),
            TG_R1_BUSYBOX=str(self.bb),
            TG_R1_SIGNATURES=str(ROOT/'module/data/tracker-signatures.tsv'),
            TG_R2_NO_WATCH_START='1',
            TG_TEST_APK=str(self.apk), TG_TEST_UNZIP=shutil.which('unzip') or '/usr/bin/unzip',
            TG_TEST_VERSION=str(self.version), TG_TEST_INSTALLED=str(self.installed))
        self.pkg='com.example.app'

    def run_tg(self,*args, success=True, env=None):
        cp=subprocess.run(['sh',str(MOD),*args],env=env or self.env,
                          capture_output=True,text=True,timeout=15)
        if success and cp.returncode:
            self.fail(f'{args}: {cp.returncode}\nSTDOUT: {cp.stdout}\nSTDERR: {cp.stderr}')
        return cp

    def rules(self):
        f=self.root/'state/rules.tsv'
        return f.read_text().splitlines() if f.exists() else []
    def autos(self):
        f=self.root/'state/auto.tsv'
        return f.read_text().splitlines() if f.exists() else []

    def test_defaults_monitor_dry_run_json(self):
        st=json.loads(self.run_tg('json','status').stdout)
        self.assertFalse(st['monitor_enabled'])
        self.assertEqual(st['enrolled'],[])
        self.assertEqual(self.rules(),[])
        self.run_tg('monitor','enable')
        st=json.loads(self.run_tg('json','status').stdout)
        self.assertTrue(st['monitor_enabled'])
        self.assertEqual(st['auto_rules'],0)
        self.assertEqual(self.rules(),[])
        self.run_tg('monitor','disable')
        self.assertFalse(json.loads(self.run_tg('json','status').stdout)['monitor_enabled'])

    def test_enroll_exclude_include_unenroll_manual_promotion(self):
        self.run_tg('enroll',self.pkg)
        self.assertNotIn(self.pkg+'|service|com.google.android.gms.measurement.AppMeasurementService',self.autos())
        self.assertIn(self.pkg+'|receiver|com.facebook.appevents.AppEventsReceiver',self.autos())
        self.assertFalse(any('|activity|' in s or '|provider|' in s for s in self.autos()))
        self.assertEqual(len(self.rules()),len(self.autos()))
        self.run_tg('add',self.pkg,'receiver','com.facebook.appevents.AppEventsReceiver')
        self.assertNotIn(self.pkg+'|receiver|com.facebook.appevents.AppEventsReceiver',self.autos())
        self.run_tg('exclude',self.pkg)
        self.assertEqual(self.autos(),[])
        self.assertEqual(self.rules(),[self.pkg+'|receiver|com.facebook.appevents.AppEventsReceiver'])
        self.run_tg('include',self.pkg)
        self.assertNotIn(self.pkg+'|service|com.google.android.gms.measurement.AppMeasurementService',self.autos())
        self.run_tg('unenroll',self.pkg)
        self.assertEqual(self.autos(),[])
        self.assertEqual(self.rules(),[self.pkg+'|receiver|com.facebook.appevents.AppEventsReceiver'])
        self.run_tg('restore',self.pkg)
        self.assertEqual(self.rules(),[])
        self.assertEqual(json.loads(self.run_tg('json','status').stdout)['enrolled'],[])

    def test_install_update_uninstall_reconciliation(self):
        self.run_tg('monitor','enable')
        self.run_tg('enroll',self.pkg)
        old=self.autos()
        self.version.write_text('2')
        cp=self.run_tg('monitor','once')
        self.assertIn('R2_OBSERVED: updated com.example.app',cp.stdout)
        self.assertEqual(self.autos(),old)
        self.assertIn('updated|com.example.app',(self.root/'state/monitor.log').read_text())
        self.installed.write_text('0')
        self.run_tg('monitor','once')
        self.assertEqual(self.autos(),[])
        self.assertEqual(self.rules(),[])
        # Keep enrollment on uninstall: if the same app is reinstalled, reapply safely.
        self.assertEqual(json.loads(self.run_tg('json','status').stdout)['enrolled'],[self.pkg])
        self.installed.write_text('1')
        self.version.write_text('3')
        self.run_tg('monitor','once')
        self.assertEqual(self.autos(),old)

    def test_scan_failure_fails_closed_and_retry(self):
        self.run_tg('monitor','enable')
        self.run_tg('enroll',self.pkg)
        prior=self.rules()
        self.version.write_text('7')
        bad=dict(self.env,TG_R1_SCANNER='/not/a/scanner')
        cp=self.run_tg('monitor','once',env=bad)
        self.assertIn('R2_MONITOR_ONCE_PASS',cp.stdout)
        self.assertEqual(self.rules(),prior)
        cp=self.run_tg('monitor','once')
        self.assertIn('R2_RECONCILE_PASS:',cp.stdout)
        self.assertEqual(self.rules(),prior)

    def test_manual_rule_survives_auto_reconciliation_and_json(self):
        self.run_tg('add',self.pkg,'activity','com.example.app.MainActivity')
        self.run_tg('enroll',self.pkg)
        st=json.loads(self.run_tg('json','rules').stdout)
        self.assertTrue(any(v['component']=='com.example.app.MainActivity' and v['source']=='manual' for v in st))
        self.assertTrue(any(v['source']=='auto' for v in st))
        self.run_tg('restore','--all')
        self.assertEqual(self.rules(),[])
        self.assertEqual(self.autos(),[])
        self.assertEqual(json.loads(self.run_tg('json','status').stdout)['enrolled'],[])

    def test_manual_batch_block_promotes_ownership(self):
        self.run_tg('enroll',self.pkg)
        self.assertTrue(self.autos())
        self.run_tg('block',self.pkg)
        self.assertEqual(self.autos(),[])
        previous=self.rules()
        self.run_tg('unenroll',self.pkg)
        self.assertEqual(self.rules(),previous)

    def test_bad_package_snapshot_fails_without_unblocking(self):
        self.run_tg('monitor','enable')
        self.run_tg('enroll',self.pkg)
        prior=self.rules()
        self.version.write_text('not-a-version')
        cp=self.run_tg('monitor','once',success=False)
        self.assertNotEqual(cp.returncode,0)
        self.assertEqual(self.rules(),prior)
        self.version.write_text('2')
        self.run_tg('monitor','once')
        self.assertEqual(self.rules(),prior)

if __name__=='__main__':
    unittest.main(verbosity=2)
