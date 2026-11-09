#!/usr/bin/env python3
"""UX05 isolated receipts, privacy and export regressions; no Android/root required."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'module'
SCRIPT = MODULE / 'ux05_diagnostics.sh'

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix='bh-ux05-test-', dir=os.environ.get('TMPDIR') or None)
        self.addCleanup(t.cleanup)
        self.state = Path(t.name)
        self.module = self.state / 'module'
        self.module.mkdir()
        (self.module / 'module.prop').write_text('id=bindhosts\nversion=v2.1.5-tg.0.8\n')
        (self.state / 'downloads').mkdir()
        self.env = dict(os.environ, BH_DIAG_TEST_MODE='1', BH_DIAG_STATE=str(self.state),
                        BH_DIAG_MODDIR=str(self.module), BH_DIAG_EXPORT_DIR=str(self.state/'downloads'))

    def call(self, *args, ok=True):
        p = subprocess.run(['sh', str(SCRIPT), *args], env=self.env, text=True,
                           capture_output=True, timeout=6)
        if ok:
            self.assertEqual(p.returncode, 0, (p.stdout, p.stderr))
        return p

    def test_default_status_is_read_only_and_empty(self):
        before = sorted(x.name for x in self.state.iterdir())
        data = json.loads(self.call('status').stdout)
        self.assertEqual(data['schema'], 1)
        self.assertEqual(data['journal'], 'clean')
        self.assertEqual(data['receipts'], 0)
        self.assertEqual(json.loads(self.call('history').stdout), [])
        self.assertEqual(before, sorted(x.name for x in self.state.iterdir()))

    def test_persistent_receipts_and_specific_status(self):
        self.call('record','hosts','update','ok','HOSTS_UPDATE_OK')
        self.call('record','tracker','monitor','fail','TG_ACTION_FAILED')
        records = json.loads(self.call('history','10').stdout)
        self.assertEqual(len(records),2)
        self.assertEqual(records[-1]['area'], 'tracker')
        status = json.loads(self.call('status').stdout)
        self.assertEqual((status['receipts'],status['failures']), (2,1))
        self.assertEqual(status['last_failure_code'],'TG_ACTION_FAILED')
        self.assertGreater(status['last_ok_ts'],0)
        self.assertEqual((self.state/'diagnostics/receipts.psv').stat().st_mode & 0o777, 0o600)

    def test_rejects_user_strings_urls_domains_and_invalid_fields(self):
        for args in [
            ('record','hosts','update','fail','https://secret.test/path?key=token'),
            ('record','hosts','update','fail','DOMAIN_ads.example'),
            ('record','hosts','update','fail','bad-code'),
            ('record','hosts','update','ok','ARBITRARY_UPPERCASE_CODE'),
            ('record','hosts','update','fail','A'*49),
            ('record','hosts','foobar','ok','SOMETHING'),
            ('record','hack','update','ok','OTHER'),
            ('history','10000'),
            ('export','/tmp/arbitrary.json'),
        ]:
            self.assertNotEqual(self.call(*args,ok=False).returncode,0,args)
        self.assertFalse((self.state/'diagnostics/receipts.psv').exists())

    def test_bounded_rotation_at_400(self):
        for i in range(415):
            code = 'HOSTS_ATOMIC_COMMIT' if i < 414 else 'HOSTS_INPLACE_COMMIT'
            self.call('record','hosts','commit','ok',code)
        lines = (self.state/'diagnostics/receipts.psv').read_text().splitlines()
        self.assertEqual(len(lines),400)
        self.assertIn('HOSTS_ATOMIC_COMMIT',lines[0]);self.assertIn('HOSTS_INPLACE_COMMIT',lines[-1])
        self.assertEqual(len(json.loads(self.call('history','100').stdout)),100)

    def test_symlink_diagnostics_refused(self):
        outside = self.state/'outside.txt';outside.write_text('preserve')
        folder=self.state/'diagnostics';folder.mkdir()
        (folder/'receipts.psv').symlink_to(outside)
        self.assertNotEqual(self.call('record','hosts','update','ok','HOSTS_UPDATE_OK',ok=False).returncode,0)
        self.assertNotEqual(self.call('history',ok=False).returncode,0)
        self.assertEqual(outside.read_text(),'preserve')

    def test_export_is_json_and_excludes_raw_sensitive_state(self):
        token='SECRET_CANARY_USER_URL_OR_PACKAGE'
        (self.state/'sources.txt').write_text('https://private.test/list?token='+token+'\n')
        (self.state/'whitelist.txt').write_text('sensitive.example\n')
        (self.state/'trackerguard').mkdir()
        (self.state/'trackerguard/rules.tsv').write_text('com.secret.app|receiver|Tracker')
        self.call('record','hosts','update','fail','HOSTS_UPDATE_FAILED')
        out=self.call('export').stdout.strip()
        self.assertTrue(out.startswith('BH_UX05_EXPORT_PATH='))
        path=Path(out.split('=',1)[1]);self.assertTrue(path.is_file())
        data=path.read_text()
        self.assertNotIn(token,data)
        self.assertNotIn('private.test',data)
        self.assertNotIn('sensitive.example',data)
        self.assertNotIn('com.secret.app',data)
        report=json.loads(data)
        self.assertTrue(report['redacted'])
        self.assertEqual(report['summary']['enabled_sources'],1)
        self.assertEqual(report['receipts'][0]['code'],'HOSTS_UPDATE_FAILED')

    def test_journal_and_monitor_are_read_only_status_fields(self):
        (self.state/'.hosts-target-journal').mkdir()
        (self.state/'response.mode').write_text('logo\n')
        (self.state/'trackerguard').mkdir()
        (self.state/'trackerguard/monitor.enabled').write_text('')
        (self.state/'sources.txt').write_text('# disabled\ndisabled|https://off.example\nhttps://enabled.example\n')
        d=json.loads(self.call('status').stdout)
        self.assertEqual(d['journal'],'pending')
        self.assertEqual(d['response_mode'],'logo')
        self.assertTrue(d['monitor_enabled'])
        self.assertEqual(d['enabled_sources'],1)

if __name__ == '__main__': unittest.main(verbosity=2)
