#!/usr/bin/env python3
"""BH-APP01 actual read-only shell API tests; no device or root writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'module' / 'companion_api.sh'
SCHEMA = Path(__file__).resolve().parents[1] / 'contracts' / 'bh-app01-v1.json'


class CompanionApiTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() == 0:
            self.skipTest('test-fixture path override is intentionally disabled under root')
        self.temp = tempfile.TemporaryDirectory(prefix='bh-app01-')
        self.addCleanup(self.temp.cleanup)
        self.mod = Path(self.temp.name) / 'module'
        self.state = Path(self.temp.name) / 'state'
        self.mod.mkdir()
        self.state.mkdir()
        (self.mod / 'module.prop').write_text('id=bindhosts\nversionCode=21611\n')
        self.hosts_state = 'ACTIVE'
        (self.mod / 'bindhosts.sh').write_text('#!/bin/sh\necho BH_HOSTS_STATE=ACTIVE\n')
        (self.mod / 'hosts_operation_ux09.sh').write_text('#!/bin/sh\necho BH_UX09_STATE=IDLE\n')
        self.env = dict(os.environ, BH_APP01_TEST_MODE='1', BH_APP01_TEST_MODDIR=str(self.mod), BH_APP01_TEST_STATE=str(self.state))

    def call(self, *args, env=None):
        return subprocess.run(['sh', str(SCRIPT), *args], env=env or self.env, capture_output=True, text=True, timeout=5)

    def test_hello_status_are_real_json(self):
        for verb in ('hello', 'status'):
            result = self.call(verb)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['api'], 1)
        self.assertEqual(json.loads(self.call('hello').stdout)['versionCode'], 21611)
        self.assertEqual(json.loads(self.call('status').stdout), {'api': 1, 'hosts': 'ACTIVE', 'operation': 'IDLE'})

    def test_read_state_matrix(self):
        for state in ('ACTIVE', 'PAUSED', 'INACTIVE', 'DISABLED'):
            (self.mod / 'bindhosts.sh').write_text(f'#!/bin/sh\necho BH_HOSTS_STATE={state}\n')
            self.assertEqual(json.loads(self.call('status').stdout)['hosts'], state)
        for operation in ('RUNNING', 'DONE', 'FAILED', 'INTERRUPTED'):
            (self.mod / 'hosts_operation_ux09.sh').write_text(f'#!/bin/sh\necho BH_UX09_STATE={operation}\n')
            self.assertEqual(json.loads(self.call('status').stdout)['operation'], operation)

    def test_fail_closed_input_and_output(self):
        for args in [(), ('status', 'bad'), ('--force-update',), ('pause',), (';touch /tmp/should-not-run',), ('hello\nstatus',), ('status', '--help')]:
            with self.subTest(args=args):
                r = self.call(*args)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(r.stdout, '')
        (self.mod / 'bindhosts.sh').write_text('#!/bin/sh\necho BH_HOSTS_STATE=ACTIVE\necho EXTRA\n')
        self.assertNotEqual(self.call('status').returncode, 0)
        (self.mod / 'bindhosts.sh').write_text('#!/bin/sh\necho BH_HOSTS_STATE=BOGUS\n')
        self.assertNotEqual(self.call('status').returncode, 0)
        (self.mod / 'module.prop').write_text('versionCode=123\"evil\n')
        self.assertNotEqual(self.call('hello').returncode, 0)

    def test_symlink_and_backend_failure_refused(self):
        (self.mod / 'bindhosts.sh').unlink()
        (self.mod / 'bindhosts.sh').symlink_to('/etc/passwd')
        self.assertNotEqual(self.call('status').returncode, 0)
        (self.mod / 'bindhosts.sh').unlink()
        (self.mod / 'bindhosts.sh').write_text('#!/bin/sh\nexit 12\n')
        self.assertNotEqual(self.call('status').returncode, 0)

    def test_override_without_test_mode_refused(self):
        env = dict(self.env, BH_APP01_TEST_MODE='0')
        self.assertNotEqual(self.call('hello', env=env).returncode, 0)

    def test_contract_disallows_all_writes(self):
        doc = json.loads(SCHEMA.read_text())
        self.assertFalse(doc['future_mutations_enabled'])
        self.assertEqual(set(doc['allowed_operations']), {'hello', 'status'})
        self.assertTrue(all(not op['mutates'] for op in doc['allowed_operations'].values()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
