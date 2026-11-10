#!/usr/bin/env python3
"""R3 device harness mocked lifecycle, safe refusal and source integration."""
from __future__ import annotations

import importlib.util
import io
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'tests/trackerguard-r3/run_device_acceptance.py'
spec = importlib.util.spec_from_file_location('r3_acceptance',SCRIPT)
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)

class MockADB:
    def __init__(self, fail=None):
        self.fail = fail
        self.is_installed=False
        self.monitor=False
        self.enrolled=False
        self.auto=False
        self.seen_lab=False
        self.manual='com.existing.app|receiver|com.existing.app.ManualReceiver\n'
        self.version=0
        self.calls=[]
        self.probes=[]
    def run(self,*args,**kwargs):
        self.calls.append(('run',args))
        if args[:2]==('install','-r'):
            self.version=1 if self.version==0 else 2
            self.is_installed=True
            if self.fail=='install' and self.version==1:
                raise r3.Refused('simulated install failure')
            return 'Success\n'
        if args and args[0]=='uninstall':
            self.is_installed=False
            return 'Success\n'
        if args==('get-state',):return 'device\n'
        raise AssertionError('unexpected adb run: '+str(args))
    def shell(self,*args,**kwargs):
        self.calls.append(('shell',args))
        if args[:2]==('getprop','ro.build.version.sdk'):return '36\n'
        if args[:2]==('getprop','ro.product.cpu.abi'):return 'arm64-v8a\n'
        if args[:3]==('pm','list','packages'):
            return 'package:'+r3.PKG+'\n' if self.is_installed else ''
        if args[:2]==('am','start'):return 'Status: ok\n'
        raise AssertionError('unexpected shell: '+str(args))
    def root(self,command,**kwargs):
        self.calls.append(('root',command))
        if command=='id -u':return '0\n'
        if command.startswith('test -f '):return 'ready\n'
        if command.endswith('/auto.tsv'):return r3.RULE+'\n' if self.auto else ''
        if command.endswith('/rules.tsv'):return self.manual+(r3.RULE+'\n' if self.auto else '')
        raise AssertionError('unexpected root: '+command)
    def installed(self):return self.is_installed
    def tracker(self,*args):
        self.calls.append(('tracker',args))
        if args==('json','status'):
            return '{"monitor_enabled":false,"enrolled":[],"excluded":[],"auto_rules":0}'
        if args==('monitor','enable'):
            self.monitor=True;return 'R2_MONITOR_ENABLED'
        if args==('monitor','disable'):
            self.monitor=False;return 'R2_MONITOR_DISABLED'
        if args==('enroll',r3.PKG):
            self.enrolled=True;self.auto=True;return 'R2_ENROLL_PASS'
        if args==('unenroll',r3.PKG):
            self.enrolled=False;self.auto=False;return 'R2_UNENROLL_PASS'
        if args==('monitor','once'):
            self.seen_lab=self.is_installed
            self.auto=self.enrolled and self.is_installed
            if self.fail=='update' and self.version==2 and self.is_installed:
                raise r3.Refused('simulated update failure')
            if self.version==2 and self.is_installed:
                return 'R2_OBSERVED: updated '+r3.PKG
            return 'R2_MONITOR_ONCE_PASS'
        raise AssertionError('unexpected tracker args: '+str(args))
    def state_bytes(self):
        return dict(rules_tsv=b'') if False else {'rules.tsv':self.manual.encode()+(r3.RULE+'\n').encode() if self.auto else self.manual.encode(),
              'auto.tsv':(r3.RULE+'\n').encode() if self.auto else b'',
              'enrolled.tsv':(r3.PKG+'\n').encode() if self.enrolled else b'',
              'excluded.tsv':b''}
    def probe(self,token,expected):
        self.probes.append((token,expected))
        if self.auto==expected:raise r3.Refused('simulated enforcement wrong state')
    def has_auto(self):return self.auto
    def has_rule(self):return self.auto
    def has_lab_observation(self):return self.seen_lab

class R3Tests(unittest.TestCase):
    def test_read_only_no_mutating_tracker_commands(self):
        adb=MockADB()
        r3.inspect(adb)
        self.assertFalse(any(k=='tracker' for k,_ in adb.calls))
        self.assertTrue(all(k!='run' or args==('get-state',) for k,args in adb.calls))

    def apk_fixtures(self, directory):
        a=Path(directory)/'lab-v1.apk';b=Path(directory)/'lab-v2.apk'
        a.write_bytes(b'APK-v1\0'+b'a'*2048)
        b.write_bytes(b'APK-v2\0'+b'b'*2048)
        return a,b

    def test_opt_in_realistic_lifecycle_and_rollback(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB()
            with mock.patch.object(r3.time,'sleep',return_value=None), \
                 mock.patch.object(r3,'validate_lab_apk',return_value=None):
                r3.acceptance(adb,a,b)
            self.assertFalse(adb.is_installed)
            self.assertFalse(adb.monitor)
            self.assertFalse(adb.enrolled)
            self.assertFalse(adb.auto)
            self.assertFalse(adb.seen_lab)
            self.assertEqual([x[1] for x in adb.calls if x[0]=='run' and x[1][0]=='uninstall'],[("uninstall",r3.PKG),("uninstall",r3.PKG)])
            self.assertTrue(any(p[0].startswith('R3_BEFORE_') and p[1] for p in adb.probes))
            self.assertTrue(any(p[0].startswith('R3_UPDATED_BLOCK_') and not p[1] for p in adb.probes))
            self.assertTrue(any(p[0].startswith('R3_AFTER_UNENROLL_') and p[1] for p in adb.probes))
            self.assertEqual(len(adb.probes),5)

    def test_first_snapshot_failure_has_no_false_cleanup_failure(self):
        class SnapshotFailureADB(MockADB):
            def tracker(self, *args):
                if args == ('monitor', 'once'):
                    self.calls.append(('tracker', args))
                    raise r3.Refused('R2_SNAPSHOT_PARSE_FAILED: valid=0 invalid=1')
                return super().tracker(*args)
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=SnapshotFailureADB()
            with mock.patch.object(r3.time,'sleep',return_value=None), \
                 mock.patch.object(r3,'validate_lab_apk',return_value=None):
                with self.assertRaisesRegex(r3.Refused,'R2_SNAPSHOT_PARSE_FAILED'):
                    r3.acceptance(adb,a,b)
            self.assertFalse(adb.is_installed)
            self.assertFalse(adb.monitor)
            self.assertFalse(adb.enrolled)
            self.assertFalse(adb.auto)
            self.assertEqual(len([1 for k, args in adb.calls
                                  if k == 'tracker' and args == ('monitor','once')]),1)
            self.assertEqual(adb.manual, 'com.existing.app|receiver|com.existing.app.ManualReceiver\n')

    def test_baseline_monitor_once_precedes_v2_install(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB()
            with mock.patch.object(r3.time,'sleep',return_value=None), \
                 mock.patch.object(r3,'validate_lab_apk',return_value=None):
                r3.acceptance(adb,a,b)
            positions=[i for i,(kind,args) in enumerate(adb.calls)
                       if kind=='tracker' and args==('monitor','once')]
            installs=[i for i,(kind,args) in enumerate(adb.calls)
                      if kind=='run' and args[:2]==('install','-r')]
            self.assertTrue(positions and len(installs)==3)
            self.assertLess(installs[0], positions[0])
            self.assertLess(positions[0], installs[1])
            self.assertFalse(adb.has_lab_observation())

    def test_cleanup_refuses_residual_lab_in_observer(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB()
            with mock.patch.object(r3.time,'sleep',return_value=None), \
                 mock.patch.object(r3,'validate_lab_apk',return_value=None), \
                 mock.patch.object(adb,'has_lab_observation',return_value=True):
                with self.assertRaisesRegex(r3.Refused,'cleanup incomplete'):
                    r3.acceptance(adb,a,b)
            self.assertFalse(adb.is_installed)
            self.assertFalse(adb.auto)

    def test_mid_update_failure_still_unenrolls_and_preserves_manual_rules(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB(fail='update')
            with self.assertRaisesRegex(r3.Refused,'simulated update failure'):
                with mock.patch.object(r3.time,'sleep',return_value=None), \
                     mock.patch.object(r3,'validate_lab_apk',return_value=None):r3.acceptance(adb,a,b)
            self.assertFalse(adb.monitor)
            self.assertFalse(adb.is_installed)
            self.assertFalse(adb.auto)
            self.assertIn(('tracker',('unenroll',r3.PKG)),adb.calls)

    def test_reject_lab_already_installed_without_writes(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB();adb.is_installed=True
            with self.assertRaisesRegex(r3.Refused,'already installed'):
                with mock.patch.object(r3,'validate_lab_apk',return_value=None):
                    r3.acceptance(adb,a,b)
            self.assertFalse(any(k=='tracker' for k,_ in adb.calls))

    def test_reject_same_apk_before_ever_touching_device(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t);b.write_bytes(a.read_bytes())
            adb=MockADB()
            with self.assertRaisesRegex(r3.Refused,'identical'):
                r3.acceptance(adb,a,b)
            self.assertEqual(adb.calls,[])

    def test_refuse_unverified_apks_before_any_device_operation(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            adb=MockADB()
            with mock.patch.object(r3.shutil,'which',return_value=None):
                with self.assertRaisesRegex(r3.Refused,'aapt is required'):
                    r3.acceptance(adb,a,b)
            self.assertFalse(adb.calls)

    def test_verify_exact_package_version_and_no_permissions(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR','/tmp')) as t:
            a,b=self.apk_fixtures(t)
            ok=[subprocess.CompletedProcess([],0,stdout="package: name='"+r3.PKG+"' versionCode='1' versionName='0.1.0'\n"),
                subprocess.CompletedProcess([],0,stdout='package: '+r3.PKG+'\n')]
            with mock.patch.object(r3.shutil,'which',return_value='/usr/bin/aapt'), \
                 mock.patch.object(r3.subprocess,'run',side_effect=ok):
                r3.validate_lab_apk(a,1)
            mismatch=[subprocess.CompletedProcess([],0,stdout="package: name='com.bad.actor' versionCode='1'\n"),
                      subprocess.CompletedProcess([],0,stdout='')]
            with mock.patch.object(r3.shutil,'which',return_value='/usr/bin/aapt'), \
                 mock.patch.object(r3.subprocess,'run',side_effect=mismatch):
                with self.assertRaisesRegex(r3.Refused,'unexpected lab package'):
                    r3.validate_lab_apk(a,1)

    def test_signature_never_in_production_database(self):
        production=(ROOT/'module/data/tracker-signatures.tsv').read_text()
        isolated=(ROOT/'module/data/r3-lab-signatures.tsv').read_text()
        self.assertNotIn('com.mikeyphw.trackerguard.ifwlab.',production)
        self.assertIn('com.mikeyphw.trackerguard.ifwlab.|tg-r3-lab|review',isolated)
        self.assertIn('TG_R1_SIGNATURES=',SCRIPT.read_text())
        self.assertNotIn('restore --all',SCRIPT.read_text())

    def test_qualification_in_ci_and_lab_both_versioned(self):
        lab=(ROOT/'tests/ifw-lab/app/build.gradle').read_text()
        self.assertIn('tgLabVersionCode',lab)
        ci=(ROOT/'.github/workflows/trackerguard-ifw-lab.yml').read_text()
        self.assertIn('trackerguard-ifw-lab-v1',ci)
        self.assertIn('trackerguard-ifw-lab-v2',ci)
        self.assertIn('tgLabVersionCode=2',ci)
        module_ci=(ROOT/'.github/workflows/trackerguard-ci.yml').read_text()
        self.assertIn('test_trackerguard_r3.py',module_ci)

if __name__=='__main__':unittest.main(verbosity=2)
