#!/usr/bin/env python3
"""UX09: real transactional hosts-pipeline statistics, no network or device writes."""
from pathlib import Path
import hashlib
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_hosts_update_safe import HostsUpdateTests

class UX09Pipeline(HostsUpdateTests):
    def setUp(self):
        super().setUp()
        op=self.root/'.ux09-operation';op.mkdir()
        self.events=op/'events.tsv';self.events.write_text('')
        self.env['BH_UX09_EVENTS']=str(self.events)
    def _stats(self):
        records=[r for r in self.events.read_text().splitlines() if r.startswith('STATS|')]
        self.assertTrue(records,'missing actual backend measurements')
        numbers=records[-1].split('|')[1:]
        self.assertEqual(len(numbers),8)
        return tuple(map(int,numbers))
    def test_source_url_dedup_and_overlap_measurements(self):
        (self.root/'sources.txt').write_text('https://fixture.example/hosts.txt\n'
           'https://fixture.example/hosts-alt.txt\nhttps://fixture.example/hosts.txt\n')
        self.fetcher.write_text('''#!/bin/sh
case "$1" in
  https://fixture.example/hosts.txt|https://fixture.example/hosts-alt.txt) cp "$BH_FIXTURE_HOSTS" "$2" ;;
  *) exit 6 ;;
esac
''')
        self.fetcher.chmod(0o755)
        (self.root/'blacklist.txt').write_text('trap.otherexample\n')
        (self.root/'whitelist.txt').write_text('ads.example\n')
        expected_hash=hashlib.sha256((self.root/'sources.txt').read_bytes()).hexdigest()
        self.go()
        raw,dup,unique,excluded,final,sources,skipped,changed=self._stats()
        self.assertEqual((raw,dup,unique,excluded,final,sources,skipped,changed),(7,4,3,1,2,2,1,1))
        self.assertIn('SKIPPED_DUPLICATE_URL|Count 1',self.events.read_text())
        # Compare complete hosts rows: `ads.example\n` is also a suffix of
        # `images.ads.example\n`, so a substring check gives a false failure.
        generated_lines = self.active.read_text().splitlines()
        self.assertNotIn('0.0.0.0 ads.example', generated_lines)
        self.assertIn('0.0.0.0 images.ads.example', generated_lines)
        self.assertEqual((self.root/'.sources-applied.sha256').read_text().strip(),expected_hash)
        self.assertTrue((self.root/'.sources-applied.epoch').read_text().strip().isdigit())
    def test_success_second_update_is_unchanged(self):
        self.go()
        self.events.write_text('')
        self.go()
        self.assertEqual(self._stats()[-1],0)
        self.assertIn('UNCHANGED|',self.events.read_text())
    def test_download_failure_does_not_publish_fake_success(self):
        old=self.active.read_bytes()
        (self.root/'sources.txt').write_text('https://fixture.example/hosts.txt\nhttps://fixture.example/missing.txt\n')
        p=self.go(ok=False)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(old,self.active.read_bytes())
        self.assertFalse((self.root/'.sources-applied.sha256').exists())
        self.assertNotIn('STATS|',self.events.read_text())

if __name__=='__main__':unittest.main(verbosity=2)
