#!/usr/bin/env python3
"""HF04: real POSIX-shell PM transport tests with synthetic failures, no device needed."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module' / 'trackerguard_r2_pm_query.sh'
GOOD = ('package:/data/app/~~a==/com.example-a==/base.apk=com.example.alpha versionCode:3\n'
        'package:/data/app/~~b==/com.example-b==/base.apk=com.example.beta versionCode:4\n')

class PMTransportHF04(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR') or None)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / 'state'; self.state.mkdir()
        self.output = self.state / 'out'
        self.good = self.root / 'good'; self.good.write_text(GOOD)
        self.pm = self.root / 'pm'; self.cmd = self.root / 'cmd'
        self.pm_log = self.root / 'pm.log'; self.cmd_log = self.root / 'cmd.log'
        self.env = dict(os.environ, TG_STATE_DIR=str(self.state), TG_PM=str(self.pm),
                        TG_CMD_BIN=str(self.cmd), TG_HF04_GOOD=str(self.good),
                        TG_HF04_PM_LOG=str(self.pm_log), TG_HF04_CMD_LOG=str(self.cmd_log))
        self.set_pm('success'); self.set_cmd('failure')

    def set_pm(self, mode):
        modes = {
            'success': 'cat "$TG_HF04_GOOD"',
            'failure': 'echo "Failure calling service package: Failed transaction (2147483646) com.example.sensitive" >&2; exit 7',
            'empty': 'exit 0',
            'retry': 'n=$(wc -l < "$TG_HF04_PM_LOG"); [ "$n" -gt 1 ] || { echo "temporary PM failure" >&2; exit 9; }; cat "$TG_HF04_GOOD"',
            'permission': 'echo "SecurityException private.package" >&2; exit 8',
        }
        self.pm.write_text('#!/bin/sh\necho x >> "$TG_HF04_PM_LOG"\n' + modes[mode] + '\n')
        self.pm.chmod(0o755)

    def set_cmd(self, mode):
        modes = {'success': 'cat "$TG_HF04_GOOD"',
                 'failure': 'echo "Cannot access package service com.example.secret" >&2; exit 11',
                 'empty': 'exit 0',
                 'permission': 'echo "SecurityException com.example.secret" >&2; exit 13'}
        self.cmd.write_text('#!/bin/sh\necho x >> "$TG_HF04_CMD_LOG"\n[ "$1" = package ] || exit 66\n' + modes[mode] + '\n')
        self.cmd.chmod(0o755)

    def call(self, target=None, timeout=14):
        return subprocess.run(['sh', str(MODULE), str(target or self.output)],
                              text=True, capture_output=True, env=self.env, timeout=timeout)

    def assert_clean(self):
        self.assertEqual(list(self.state.glob('r2pm-hf04.*')), [])

    def test_healthy_pm_no_cmd_fallback(self):
        p=self.call(); self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.output.read_text(), GOOD)
        self.assertFalse(self.cmd_log.exists()); self.assert_clean()

    def test_cmd_fallback_after_pm_failure(self):
        self.set_pm('failure'); self.set_cmd('success')
        p=self.call(); self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('R2_SNAPSHOT_PM_FALLBACK: using cmd package attempt=1',p.stderr)
        self.assertEqual(self.output.read_text(), GOOD)
        self.assertNotIn('com.example.sensitive',p.stderr); self.assert_clean()

    def test_transient_pm_retries_and_recovers(self):
        self.set_pm('retry')
        p=self.call(); self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('R2_SNAPSHOT_PM_RECOVERED: attempt=2',p.stderr)
        self.assertEqual(len(self.pm_log.read_text().splitlines()),2)
        self.assertEqual(self.output.read_text(),GOOD); self.assert_clean()

    def test_permanent_failure_keeps_target_bytes(self):
        self.set_pm('failure'); self.set_cmd('failure')
        self.output.write_text('PRIOR_SNAPSHOT_UNCHANGED')
        p=self.call(); self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.output.read_text(),'PRIOR_SNAPSHOT_UNCHANGED')
        self.assertIn('R2_PM_QUERY_FAILED: attempts=3',p.stderr)
        self.assertIn('pm_stderr_class=binder_transaction',p.stderr)
        self.assertNotIn('com.example',p.stderr)
        self.assertEqual(len(self.pm_log.read_text().splitlines()),3)
        self.assertEqual(len(self.cmd_log.read_text().splitlines()),3);self.assert_clean()

    def test_empty_success_does_not_replace_prior(self):
        self.set_pm('empty'); self.set_cmd('empty')
        self.output.write_text('OLD')
        p=self.call(); self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.output.read_text(),'OLD');self.assert_clean()

    def test_security_exception_is_classified_not_disclosed(self):
        self.set_pm('permission'); self.set_cmd('permission')
        p=self.call(); self.assertNotEqual(p.returncode,0)
        self.assertIn('pm_stderr_class=permission_or_selinux',p.stderr)
        self.assertIn('cmd_stderr_class=permission_or_selinux',p.stderr)
        self.assertNotIn('private.package',p.stderr)
        self.assertNotIn('com.example.secret',p.stderr);self.assert_clean()

    def test_symlink_target_refused_without_touch(self):
        alt=self.root/'outside'; alt.write_text('SENSITIVE')
        self.output.symlink_to(alt)
        p=self.call();self.assertNotEqual(p.returncode,0)
        self.assertEqual(alt.read_text(),'SENSITIVE');self.assert_clean()

    def test_target_outside_private_state_refused(self):
        alt=self.root/'outside'
        p=self.call(alt);self.assertNotEqual(p.returncode,0)
        self.assertFalse(alt.exists());self.assert_clean()

    def test_no_unbounded_sleep_or_live_write(self):
        txt=MODULE.read_text()
        self.assertIn('while [ "$attempt" -le 3 ]',txt)
        self.assertIn('</dev/null',txt)
        self.assertIn('TG_CMD_BIN',txt)
        self.assertNotIn('setenforce',txt)
        self.assertNotIn('monitor once',txt)
        self.assertNotIn('install -',txt)
        self.assertNotIn('/data/system/ifw/',txt)

if __name__=='__main__':unittest.main(verbosity=2)
