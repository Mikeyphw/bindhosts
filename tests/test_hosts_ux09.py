#!/usr/bin/env python3
"""UX09 cross-area, offline-safe source handling and operation regressions."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UX09Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR') or None)
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.state=self.base/'state';self.state.mkdir()
        self.mod=self.base/'module';self.mod.mkdir()
        (self.mod/'data').mkdir()
        (self.mod/'data'/'source-catalog.tsv').write_text(
            '# id|name|url|group\n'
            'adaway|AdAway|https://example.org/away|core\n'
            'cubic|Cubic|https://example.org/cubic|comprehensive\n'
            'energized-spark|Spark|https://example.org/spark|energized\n'
            'energized-blu|Blu|https://example.org/blu|energized\n')
        (self.state/'sources.txt').write_text('https://custom.example/list\n'
            'https://example.org/away # source-catalog:adaway\n'
            'https://other.example/a # custom note\n')
        shutil.copy2(ROOT/'module/source_catalog_batch_ux09.sh',self.mod/'batch.sh')
        shutil.copy2(ROOT/'module/hosts_operation_ux09.sh',self.mod/'hosts_operation_ux09.sh')
        self.env=dict(os.environ,BH_CATALOG_TEST_ROOT='1',BH_CATALOG_ROOT=str(self.state),
            BH_CATALOG_FILE=str(self.mod/'data/source-catalog.tsv'),
            BH_UX09_TEST_MODE='1',BH_UX09_ROOT=str(self.state),BH_UX09_MODDIR=str(self.mod))
    def command(self,path,*args,ok=True,env=None):
        p=subprocess.run(['sh',str(path),*args],text=True,capture_output=True,env=env or self.env,timeout=30)
        if ok:self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        else:self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        return p
    @property
    def batch(self):return self.mod/'batch.sh'
    @property
    def op(self):return self.mod/'hosts_operation_ux09.sh'
    def test_atomic_batch_preserves_manual_url(self):
        self.command(self.batch,'batch','cubic,energized-blu')
        s=(self.state/'sources.txt').read_text()
        self.assertIn('https://custom.example/list',s)
        self.assertIn('https://other.example/a # custom note',s)
        self.assertNotIn('source-catalog:adaway',s)
        self.assertIn('source-catalog:cubic',s)
        self.assertIn('source-catalog:energized-blu',s)
        self.assertIn('BH_UX09_BATCH_UNCHANGED',self.command(self.batch,'batch','cubic,energized-blu').stdout)
    def test_exclusive_energized_rejects_before_write(self):
        original=(self.state/'sources.txt').read_bytes()
        self.command(self.batch,'batch','energized-blu,energized-spark',ok=False)
        self.assertEqual(original,(self.state/'sources.txt').read_bytes())
    def test_unknown_and_duplicate_presets_refused(self):
        for selection in ['cubic,cubic','wrong','adaway,,cubic','adaway,',';rm','energized-blu,missing']:
            with self.subTest(selection=selection):self.command(self.batch,'batch',selection,ok=False)
        self.assertIn('source-catalog:adaway',(self.state/'sources.txt').read_text())
    def test_update_lock_prevents_batch(self):
        (self.state/'.hosts-update.lock').mkdir()
        self.command(self.batch,'batch','none',ok=False)
        self.assertIn('source-catalog:adaway',(self.state/'sources.txt').read_text())
    def test_manual_status_separates_ownership(self):
        o=self.command(self.batch,'manual-list').stdout
        self.assertIn('https://custom.example/list',o)
        self.assertNotIn('source-catalog:adaway',o)
    def test_applied_vs_configured(self):
        self.assertIn('UNKNOWN',self.command(self.batch,'applied-status').stdout)
        import hashlib
        (self.state/'.sources-applied.sha256').write_text(hashlib.sha256((self.state/'sources.txt').read_bytes()).hexdigest()+'\n')
        self.assertIn('CURRENT',self.command(self.batch,'applied-status').stdout)
        self.command(self.batch,'batch','cubic')
        self.assertIn('PENDING',self.command(self.batch,'applied-status').stdout)
    def test_symlink_and_invalid_data_refused(self):
        src=self.state/'sources.txt';src.rename(self.state/'original')
        src.symlink_to(self.state/'original')
        self.command(self.batch,'batch','adaway',ok=False)
    def test_real_detached_worker_and_completion(self):
        script=self.base/'worker.sh';script.write_text('#!/bin/sh\n'
          'printf "PREPARING|Test worker initialized\\n" >> "$BH_UX09_ROOT/.ux09-operation/events.tsv"\n'
          'sleep 1\nprintf "STATS|10|3|7|1|6|2|1|1\\n" >> "$BH_UX09_ROOT/.ux09-operation/events.tsv"\n'
          'echo BH_HOSTS_UPDATE_PASS\n')
        env=dict(self.env,BH_UX09_TEST_COMMAND=str(script))
        p=self.command(self.op,'start',env=env)
        self.assertIn('BH_UX09_STARTED=',p.stdout)
        self.command(self.op,'start',env=env,ok=False)
        for _ in range(50):
            s=self.command(self.op,'status',env=env).stdout
            if 'BH_UX09_STATE=DONE' in s:break
            time.sleep(.08)
        self.assertIn('BH_UX09_STATE=DONE',s)
        ev=self.command(self.op,'events',env=env).stdout
        self.assertIn('STATS|10|3|7|1|6|2|1|1',ev)
        self.assertIn('BH_UX09_RECEIPT=PASS',s)
    def test_failed_worker_is_not_reported_success(self):
        script=self.base/'worker-fail.sh';script.write_text('#!/bin/sh\necho failure >&2\nexit 3\n')
        env=dict(self.env,BH_UX09_TEST_COMMAND=str(script))
        self.command(self.op,'start',env=env)
        for _ in range(40):
            s=self.command(self.op,'status',env=env).stdout
            if 'BH_UX09_STATE=FAILED' in s:break
            time.sleep(.05)
        self.assertIn('BH_UX09_STATE=FAILED',s)
        self.assertIn('BH_UX09_RECEIPT=FAIL',s)
    def test_operation_status_is_read_only_when_idle(self):
        before={f.relative_to(self.state).as_posix():f.read_bytes() for f in self.state.rglob('*') if f.is_file()}
        self.assertIn('BH_UX09_STATE=IDLE',self.command(self.op,'status').stdout)
        self.assertEqual('',self.command(self.op,'events').stdout)
        after={f.relative_to(self.state).as_posix():f.read_bytes() for f in self.state.rglob('*') if f.is_file()}
        self.assertEqual(before,after)

    def test_stale_running_worker_refused(self):
        op=self.state/'.ux09-operation';op.mkdir();(op/'state').write_text('RUNNING\n')
        (op/'pid').write_text('99999999\n')
        self.command(self.op,'start',ok=False)
        self.assertEqual('RUNNING\n',(op/'state').read_text())

    def test_operation_symlink_refused(self):
        (self.state/'.ux09-operation').symlink_to(self.mod,target_is_directory=True)
        self.command(self.op,'status',ok=False)
        self.command(self.op,'start',ok=False)

    def test_external_source_never_overwritten(self):
        p=self.state/'sources.txt'
        p.write_text('https://example.org/cubic # manually managed\n')
        self.command(self.batch,'batch','cubic')
        self.assertEqual(p.read_text(),'https://example.org/cubic # manually managed\n')
        self.assertIn('MANUAL|on|',self.command(self.batch,'manual-list').stdout)

    def test_catalog_update_lock_serializes_writers(self):
        lock=self.state/'.source-catalog.lock';lock.mkdir()
        self.command(self.batch,'batch','cubic',ok=False)
        self.assertIn('source-catalog:adaway',(self.state/'sources.txt').read_text())

    def test_hosted_ci_contracts(self):
        root=ROOT/'.github/workflows'
        for f in ['trackerguard-ci.yml','bindhosts-ux-ci.yml']:
            self.assertIn('python3 tests/test_hosts_ux09.py',(root/f).read_text())
            self.assertIn('python3 tests/test_hosts_update_ux09.py',(root/f).read_text())

    def test_ui_contracts(self):
        root=ROOT/'webui'
        ui=(root/'utils/hosts_operations_ux09.js').read_text()
        catalog=(root/'page/catalog/catalog.js').read_text()
        page=(root/'page/catalog/catalog.html').read_text()
        more=(root/'page/more/more.html').read_text()
        self.assertIn("backend('events')",ui)
        self.assertIn('beginHostsUpdate',catalog)
        self.assertIn('BATCH} batch',catalog)
        self.assertIn('ux09-energized',page)
        self.assertIn('id="response-mode"',more)
        self.assertNotIn('id="response-mode"',page)
    def test_hosts_update_instrumentation_present(self):
        src=(ROOT/'module/hosts_update_safe.sh').read_text()
        for item in ['SKIPPED_DUPLICATE_URL','ux09_event DEDUPLICATING','ux09_event STATS','ux09_applied','grep -Fqx --']:
            self.assertIn(item,src)

if __name__=='__main__':unittest.main(verbosity=2)
