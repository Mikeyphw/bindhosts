"""P04B P02: finite native paged-read API, real non-root shell fixtures."""
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'module/companion_read_v4.sh'
ANDROID = ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts'


class PagingSourceContract(unittest.TestCase):
    def test_contract(self):
        contract=json.loads((ROOT/'contracts/bh-app01-v4.json').read_text())
        self.assertEqual(contract['api_version'], 4)
        self.assertTrue(contract['read_only'])
        self.assertEqual(contract['page_size_bytes'],3072)
        self.assertEqual(contract['max_snapshot_bytes'],262144)
        self.assertEqual(contract['max_pages'],86)
    def test_bridge_no_generic_shell(self):
        runner=(ANDROID/'RootRunner.java').read_text()
        activity=(ANDROID/'MainActivity.java').read_text()
        frontend=(ROOT/'webui/runtime/companion_kernelsu_alt.mjs').read_text()
        transport=(ROOT/'webui/runtime/companion_transport.mjs').read_text()
        shell=SCRIPT.read_text()
        self.assertIn('companion_read_v4.sh', runner)
        self.assertIn('RootRunner.page(argument)', activity)
        self.assertIn("'read-page'", transport)
        self.assertIn('readPaginated', frontend)
        self.assertIn("digest('SHA-256',all)",frontend)
        self.assertIn('snapshot changed during pagination',shell)
        self.assertNotIn('eval ',shell)
        self.assertNotIn('sh -c "$REQUEST"',shell)
        self.assertNotIn('addJavascriptInterface',activity)
        ci=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        for name in ['companion_read_v4.sh','bh-app01-v4.json','test_bh_app01_p04b_pagination.mjs',':app:lintDebug']:
            self.assertIn(name,ci)


@unittest.skipIf(os.geteuid() == 0, 'fixture deliberately refuses UID 0; run unprivileged')
class PagingNonrootFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='bh-app01-v4-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.mod=self.root/'module';self.mod.mkdir()
        self.state=self.root/'state';self.state.mkdir()
        self.data=('alpha.example.org\n' * 560 + '\U0001f98a\n' + 'omega.example.org\n').encode()
        (self.state/'sources.txt').write_bytes(self.data)
        (self.state/'whitelist.txt').write_bytes(b'')
        (self.mod/'bindhosts.sh').write_text('''#!/bin/sh
if [ "$1" = tracker ] && [ "$2" = json ]; then
  case "$3" in status) echo '{"schema":2,"enrolled":[],"excluded":[]}' ;; rules) echo '[]' ;; esac
else exit 88; fi
''')
        (self.mod/'source_catalog.sh').write_text("#!/bin/sh\nprintf 'adaway|off\\n'\n")
        (self.mod/'source_catalog_batch_ux09.sh').write_text('#!/bin/sh\necho BH_UX09_APPLIED=CURRENT\n')
        self.env={**os.environ,'BH_APP01_V4_TEST_MODE':'1',
            'BH_APP01_V4_TEST_MODDIR':str(self.mod),'BH_APP01_V4_TEST_STATE':str(self.state)}
    def call(self,source='config-read',selector='sources',offset=0,expected='none'):
        req=f'{source}|{selector}|{offset}|{expected}'.encode()
        return subprocess.run(['sh',str(SCRIPT),base64.b64encode(req).decode()],
            capture_output=True,text=True,env=self.env,timeout=12)
    def test_large_file_roundtrip_digest(self):
        self.assertGreater(len(self.data),4800)
        chunks=[];offset=0;sha='none';pages=0
        while True:
            response=self.call(offset=offset,expected=sha)
            self.assertEqual(response.returncode,0,response.stderr)
            body=json.loads(response.stdout)
            self.assertEqual(body['api'],4)
            self.assertEqual(body['action'],'read-page')
            self.assertEqual(body['size'],len(self.data))
            self.assertEqual(body['offset'],offset)
            if sha!='none':self.assertEqual(body['sha256'],sha)
            sha=body['sha256'];chunks.append(base64.b64decode(body['encoded']))
            pages+=1
            if body['next'] is None:break
            offset=body['next']
            self.assertLess(pages,86)
        self.assertGreater(pages,1)
        self.assertEqual(b''.join(chunks),self.data)
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),sha)
        self.assertFalse(list(self.state.glob('.bh-app01-v4.*')))
    def test_change_between_pages_refused(self):
        first=json.loads(self.call().stdout)
        p=self.state/'sources.txt'
        p.write_bytes(self.data+b'changed.example.org\n')
        outcome=self.call(offset=first['next'],expected=first['sha256'])
        self.assertEqual(outcome.returncode,2)
        self.assertIn('snapshot changed',outcome.stderr)
        self.assertNotIn('"api":4',outcome.stdout)
    def test_empty_config_is_valid_read(self):
        p=self.call(selector='whitelist')
        self.assertEqual(p.returncode,0,p.stderr)
        obj=json.loads(p.stdout)
        self.assertEqual(obj['size'],0)
        self.assertEqual(obj['encoded'],'')
        self.assertIsNone(obj['next'])
    def test_oversized_fails_without_truncation(self):
        (self.state/'sources.txt').write_bytes(b'z'*262145)
        p=self.call()
        self.assertEqual(p.returncode,2)
        self.assertIn('256 KiB cap',p.stderr)
    def test_refusal_matrix(self):
        for source,selector,offset,sha in [
            ('config-write','sources',0,'none'),
            ('config-read','../../etc/shadow',0,'none'),
            ('config-read','custom_../../shadow',0,'none'),
            ('config-list','all',0,'none'),
            ('tracker','enroll~org.example',0,'none'),
            ('tracker','preview~bad_package',0,'none'),
            ('catalog','batch',0,'none'),
            ('packages','root',0,'none'),
            ('config-read','sources',300000,'none'),
            ('config-read','sources',0,'f'*64),
        ]:
            p=self.call(source,selector,offset,sha)
            self.assertNotEqual(p.returncode,0,(source,selector,offset,p.stdout))
            self.assertNotIn('"api":4',p.stdout)
    def test_symlink_target_and_state_refused(self):
        p=self.state/'sources.txt';p.unlink();p.symlink_to(self.root/'outside')
        self.assertEqual(self.call().returncode,2)
        p.unlink()
        real=self.root/'real-state';self.state.rename(real)
        self.state.symlink_to(real,target_is_directory=True)
        self.assertEqual(self.call().returncode,2)
    def test_catalog_and_tracker_reads(self):
        for source,selector,phrase in [('catalog','status','adaway'),('catalog','applied-status','CURRENT'),
                                         ('tracker','status','"schema"'),('tracker','rules','[]')]:
            p=self.call(source,selector)
            self.assertEqual(p.returncode,0,(source,selector,p.stderr))
            body=json.loads(p.stdout)
            self.assertIn(phrase,base64.b64decode(body['encoded']).decode())

if __name__=='__main__':unittest.main()
