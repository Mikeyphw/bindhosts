#!/usr/bin/env python3
"""UX09E: offline negative tests of physical acceptance contract; no ADB/device."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import subprocess
import io
import contextlib

HERE = Path(__file__).resolve().parent
S = importlib.util.spec_from_file_location('ux09e_device_acceptance', HERE/'ux09e_device_acceptance.py')
mod = importlib.util.module_from_spec(S)
S.loader.exec_module(mod)

class FakeADB(mod.ADB):
    def __init__(self, *, mismatch=False, operation='DONE', invalid_events=False):
        super().__init__('localhost:5555')
        self.mismatch = mismatch
        self.operation = operation
        self.invalid_events = invalid_events
        self.calls = []
    def run(self, *args, **kw):
        self.calls.append(args)
        if args == ('get-state',): return 'device\n'
        if args == ('shell','getprop','ro.build.version.sdk'): return '36\n'
        if args == ('shell','getprop','ro.product.cpu.abi'): return 'arm64-v8a\n'
        raise AssertionError('unexpected subprocess call: '+repr(args))
    def shell(self, command, check=True):
        self.calls.append(('root', command))
        if command == 'id -u': return '0\n'
        if command.startswith('sha256sum /data/adb/modules/bindhosts/'):
            name = command.rsplit('/',1)[-1]
            h = mod.SCRIPTS[name]
            if self.mismatch and name == 'source_catalog_batch_ux09.sh': h = '0'*64
            return f'{h}  {mod.MODULE}/{name}\n'
        if command.startswith('if [ -f /data/adb/bindhosts/'):
            name = command.split('/data/adb/bindhosts/',1)[1].split(' ',1)[0]
            return f'{"a"*64}  {mod.STATE}/{name}\n'
        if command.endswith('bindhosts.sh --hosts-control status'): return 'BH_HOSTS_STATE=ACTIVE\n'
        if command.endswith('hosts_operation_ux09.sh status'): return 'BH_UX09_STATE='+self.operation+'\n'
        if command.endswith('source_catalog_batch_ux09.sh applied-status'): return 'BH_UX09_APPLIED=CURRENT\nBH_UX09_LAST_APPLIED_EPOCH=1794650000\n'
        if command.endswith('hosts_operation_ux09.sh events'):
            return ('PREPARING|Initialized\nSTATS|10|2|8|3|5|2|1|1\n' if not self.invalid_events else 'STATS|1|2|3|4|5|6|7|1\n')
        raise AssertionError('unexpected root command: '+command)

class AcceptanceContract(unittest.TestCase):
    def test_serial_allowlist(self):
        mod.ADB('localhost:5555')
        for token in ('', 'x; rm -rf /', 'a b', '$(date)', '../x', 'z'*101):
            with self.subTest(token=token), self.assertRaises(mod.Refused): mod.ADB(token)

    def test_exact_stats_semantics(self):
        data = mod.stats_from(['PREPARING|ok','STATS|10|2|8|3|5|2|1|1'])
        self.assertEqual(data,(10,2,8,3,5,2,1,1))
        for invalid in ('STATS|10|1|8|3|5|2|1|1','STATS|10|2|8|2|5|2|1|1',
                        'STATS|10|2|8|3|5|0|1|1','STATS|10|2|8|3|5|2|1|4'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(mod.Refused): mod.stats_from([invalid])

    def test_event_allowlist_redacts_domains(self):
        self.assertEqual(mod.parse_events('PREPARING|Ready\nSTATS|10|2|8|3|5|2|1|1\n'),
                         ['PREPARING|Ready','STATS|10|2|8|3|5|2|1|1'])
        for value in ('DOWNLOADING|https://example.com\n','SHELL|ls\n','FAILED|`id`\n',
                      'DOWNLOADING|'+'x'*200+'\n'):
            with self.subTest(value=value), self.assertRaises(mod.Refused): mod.parse_events(value)

    def test_direct_pinned_source_and_no_write_commands(self):
        fake = FakeADB()
        report = fake.inspect()
        self.assertTrue(all(report['script_pins'].values()))
        self.assertEqual(report['api'],'36')
        self.assertEqual(report['hosts_state'],'ACTIVE')
        self.assertEqual(report['stats'],(10,2,8,3,5,2,1,1))
        self.assertEqual(len(report['baseline_fingerprints']),5)
        call_text='\n'.join(' '.join(args) for args in fake.calls)
        for token in (' module install ',' reboot ',' rm -','--hosts-control update','--hosts-control pause',
                      '--hosts-control resume','source_catalog_batch_ux09.sh batch'):
            self.assertNotIn(token,call_text)
        self.assertNotIn('https://',str(mod.safe_report_data(report)))

    def test_refuse_source_revision_mismatch(self):
        with self.assertRaisesRegex(mod.Refused,'installed module is not UX09'):
            FakeADB(mismatch=True).inspect()

    def test_invalid_statistics_refused_not_qualified(self):
        with self.assertRaises(mod.Refused): FakeADB(invalid_events=True).inspect()

    def test_parse_key_missing_and_unknown(self):
        for line in ('BH_UX09_STATE=GOOD','BH_UX09_STATE=','BH_UX09_STATE=DONE-FAIL','\n'):
            with self.subTest(line=line),self.assertRaises(mod.Refused):
                mod.parse_key(line,mod.STATUS_RE,'operation')

    def test_probe_refuses_write_flags(self):
        for args in (['probe','--test-update'],['probe','--ack','I_AUTHORIZE_UX09_MANUAL_UI_ACCEPTANCE'],['probe','--capture'],['probe','--test-toggle'],['probe','--test-source']):
            with self.subTest(args=args), self.assertRaises(mod.Refused):
                mod.main(args)

    def test_walk_requires_explicit_authorization(self):
        with self.assertRaises(mod.Refused): mod.main(['walk'])
        with self.assertRaises(mod.Refused): mod.main(['walk','--ack','yes'])

    def test_manual_check_requires_explicit_positive_response(self):
        fake=FakeADB();report={'manual_checks':[]}
        with mock.patch('builtins.input',return_value='no'):
            with self.assertRaises(mod.Refused): mod.prompt_step('test',fake,report,None,'test-step')
        self.assertEqual(report['manual_checks'],[])

    def test_no_private_data_in_report(self):
        d={'source_sha':'a','serial':'x','api':'36','hosts_state':'ACTIVE','source_urls':['https://private'],
           'packages':['com.example.secret'],'rule_domains':['track.example'],'raw_log':'PRIVATE','stats':None}
        result=mod.safe_report_data(d)
        for secret in ('source_urls','packages','rule_domains','raw_log'):
            self.assertNotIn(secret,result)

    def test_status_regex_exact_known_states(self):
        for state in ('IDLE','RUNNING','DONE','FAILED','INTERRUPTED'):
            self.assertEqual(mod.parse_key('BH_UX09_STATE='+state+'\n',mod.STATUS_RE,'state'),state)

    def test_snapshot_failure_is_not_marked_pass(self):
        fake=FakeADB(operation='FAILED')
        report=fake.inspect();self.assertEqual(report['operation_state'],'FAILED')
        self.assertNotIn('outcome',report)

    def test_fixed_script_pins_are_source_sha256(self):
        for name,digest in mod.SCRIPTS.items():
            self.assertRegex(name,r'^[a-z0-9_]+\.sh$')
            self.assertRegex(digest,r'^[0-9a-f]{64}$')

if __name__ == '__main__': unittest.main(verbosity=2)
