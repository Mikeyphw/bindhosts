#!/usr/bin/env python3
"""UX02 fail-closed hosts rebuilding including invalid/partial sources and allowlist precision."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MOD = Path(__file__).resolve().parents[1] / 'module'

class HostsUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.work=self.root/'work'; self.work.mkdir()
        self.active=self.root/'hosts'; self.active.write_text('127.0.0.1 localhost\n0.0.0.0 old.example\n# old\n')
        self.root.joinpath('sources.txt').write_text('https://fixture.example/hosts.txt\n')
        self.root.joinpath('sources_whitelist.txt').write_text('')
        self.root.joinpath('whitelist.txt').write_text('')
        self.root.joinpath('blacklist.txt').write_text('')
        self.root.joinpath('custom.txt').write_text('')
        self.fetcher=self.root/'fetch.sh'
        self.fetcher.write_text('''#!/bin/sh
case "$1" in
  https://fixture.example/hosts.txt) cp "$BH_FIXTURE_HOSTS" "$2" ;;
  https://fixture.example/allow.txt) cp "$BH_FIXTURE_ALLOW" "$2" ;;
  *) exit 6 ;;
esac
''')
        self.fetcher.chmod(0o755)
        self.hosts=self.root/'fixture_hosts'; self.hosts.write_text('0.0.0.0 ads.example\n0.0.0.0 images.ads.example\n0.0.0.0 trap.otherexample\n')
        self.allow=self.root/'fixture_allow'; self.allow.write_text('*.ads.example\n')
        self.env=dict(os.environ, BH_UPDATE_MODDIR=str(MOD), BH_UPDATE_TEST_MODE='1', BH_UPDATE_TEST_FETCH=str(self.fetcher), BH_FIXTURE_HOSTS=str(self.hosts), BH_FIXTURE_ALLOW=str(self.allow))

    def go(self, ok=True):
        p=subprocess.run(['sh',str(MOD/'hosts_update_safe.sh'),str(self.root),str(self.active),str(self.work),'21606'],env=self.env,capture_output=True,text=True,timeout=10)
        if ok: self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
        return p

    def test_empty_allowlist_does_not_discard_every_block(self):
        self.go()
        content=self.active.read_text()
        self.assertIn('0.0.0.0 ads.example\n',content)
        self.assertIn('0.0.0.0 images.ads.example\n',content)
        self.assertIn('0.0.0.0 trap.otherexample\n',content)

    def test_success_exact_whitelist_and_wildcard(self):
        (self.root/'sources_whitelist.txt').write_text('https://fixture.example/allow.txt\n')
        self.go()
        txt=self.active.read_text()
        self.assertNotIn('images.ads.example',txt)
        self.assertNotIn('ads.example\n',txt)
        self.assertIn('0.0.0.0 trap.otherexample\n',txt)
        self.assertTrue(txt.endswith('# bindhosts v21606\n'))
        self.assertIn('127.0.0.1 localhost',txt)

    def test_download_failure_preserves_old_bytes(self):
        original=self.active.read_bytes()
        (self.root/'sources.txt').write_text('https://fixture.example/hosts.txt\nhttps://fixture.example/missing.txt\n')
        p=self.go(ok=False)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.active.read_bytes(),original)
        self.assertFalse((self.root/'.hosts-update.lock').exists())

    def test_html_error_body_rejected_before_commit(self):
        self.hosts.write_text('<html><head><title>404</title></head></html>')
        original=self.active.read_bytes()
        self.assertNotEqual(self.go(ok=False).returncode,0)
        self.assertEqual(self.active.read_bytes(),original)

    def test_empty_and_http_sources_rejected(self):
        original=self.active.read_bytes()
        self.root.joinpath('sources.txt').write_text('http://insecure.example/hosts.txt\n')
        self.assertNotEqual(self.go(ok=False).returncode,0)
        self.assertEqual(self.active.read_bytes(),original)
        self.root.joinpath('sources.txt').write_text('disabled|https://fixture.example/hosts.txt\n')
        self.assertNotEqual(self.go(ok=False).returncode,0)
        self.assertEqual(self.active.read_bytes(),original)

    def test_disabled_custom_and_no_substring_whitelisting(self):
        self.root.joinpath('custom.txt').write_text('disabled|1.2.3.4 disabled.example\n1.2.3.4 added.example\n')
        self.root.joinpath('whitelist.txt').write_text('ads.example\n')
        self.go()
        txt=self.active.read_text()
        self.assertIn('1.2.3.4 added.example\n',txt)
        self.assertNotIn('disabled.example',txt)
        self.assertIn('images.ads.example',txt)
        self.assertIn('trap.otherexample',txt)
        self.assertNotIn('0.0.0.0 ads.example\n',txt)

    def test_reject_symlink_source_and_preserve(self):
        (self.root/'sources.txt').unlink()
        (self.root/'sources.txt').symlink_to(self.hosts)
        old=self.active.read_bytes()
        self.assertNotEqual(self.go(ok=False).returncode,0)
        self.assertEqual(self.active.read_bytes(),old)

if __name__ == '__main__': unittest.main(verbosity=2)
