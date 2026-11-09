#!/usr/bin/env python3
"""UX02 root-only configuration editor acceptance using a private fake state directory."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MOD = Path(__file__).resolve().parents[1] / 'module' / 'hosts_config_safe.sh'

class ConfigSafeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('sources', 'sources_whitelist', 'blacklist', 'whitelist', 'custom'):
            (self.root / (name + '.txt')).write_text('')
        self.env = dict(os.environ, BH_CONFIG_ROOT=str(self.root), BH_CONFIG_TEST_MODE='1')

    def call(self, *args, ok=True):
        p = subprocess.run(['sh', str(MOD), *args], env=self.env, capture_output=True, text=True, timeout=7)
        if ok:
            self.assertEqual(p.returncode,0,f'{args}: {p.stderr}\n{p.stdout}')
        return p

    @staticmethod
    def b64(s): return base64.b64encode(s.encode()).decode()

    def test_source_append_toggle_remove_exact_and_literal(self):
        f=self.root/'sources.txt'
        entry='https://example.org/hosts.txt # My list'
        self.call('add','sources',self.b64(entry))
        self.call('add','sources',self.b64(entry))
        self.assertEqual(f.read_text().splitlines(),[entry])
        self.call('toggle','sources',self.b64(entry))
        self.assertEqual(f.read_text().splitlines(),['disabled|'+entry])
        self.call('toggle','sources',self.b64('disabled|'+entry))
        self.assertEqual(f.read_text().splitlines(),[entry])
        self.call('remove','sources',self.b64(entry))
        self.assertEqual(f.read_text(),'')

    def test_punctuation_in_comment_cannot_execute_shell(self):
        f=self.root/'sources.txt'
        original='https://example.org/hosts.txt'
        self.call('add','sources',self.b64(original))
        attack='https://example.org/hosts.txt # $(touch /tmp/ux02-exploit)'
        p=self.call('replace','sources',self.b64(original),self.b64(attack),ok=False)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(f.read_text(),original+'\n')
        self.assertFalse(Path('/tmp/ux02-exploit').exists())

    def test_replace_duplicates_fails_closed(self):
        f=self.root/'whitelist.txt'
        f.write_text('example.com\nexample.com\n')
        p=self.call('replace','whitelist',self.b64('example.com'),self.b64('other.org'),ok=False)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(f.read_text(),'example.com\nexample.com\n')

    def test_reject_parent_traversal_and_symlinks(self):
        self.assertNotEqual(self.call('delete-custom','../../etc/passwd',ok=False).returncode,0)
        other=self.root/'foreign'
        other.write_text('important')
        (self.root/'custom_bad.txt').symlink_to(other)
        self.assertNotEqual(self.call('delete-custom','custom_bad.txt',ok=False).returncode,0)
        self.assertEqual(other.read_text(),'important')

    def test_chunked_editor_success_and_invalid_chunk_rollback(self):
        old='https://old.example/hosts.txt\n'
        f=self.root/'sources.txt'; f.write_text(old)
        token='ux02_secure_session_001'
        self.call('stage-begin',token)
        payload='https://new.example/hosts.txt\n' * 1000
        b=payload.encode()
        for i in range(0,len(b),6000):
            self.call('stage-chunk',token,base64.b64encode(b[i:i+6000]).decode())
        self.assertEqual(f.read_text(),old)
        self.call('stage-commit',token,'sources')
        self.assertEqual(f.read_text(),payload)
        bad='ux02_secure_session_002'
        self.call('stage-begin',bad)
        self.call('stage-chunk',bad,self.b64('http://insecure.invalid\n'))
        self.assertNotEqual(self.call('stage-commit',bad,'sources',ok=False).returncode,0)
        self.assertEqual(f.read_text(),payload)
        self.call('stage-abort',bad)

    def test_large_stage_commit_last_invalid_line_fails_closed(self):
        original='https://original.example/hosts.txt\n'
        f=self.root/'sources.txt'; f.write_text(original)
        token='ux02_secure_large_invalid'
        self.call('stage-begin',token)
        data=('https://valid.example/hosts.txt\n' * 1500 + 'http://bad.example/list\n').encode()
        for offset in range(0,len(data),6000):
            self.call('stage-chunk',token,base64.b64encode(data[offset:offset+6000]).decode())
        failed=self.call('stage-commit',token,'sources',ok=False)
        self.assertNotEqual(failed.returncode,0)
        self.assertEqual(f.read_text(),original)
        self.call('stage-abort',token)

    def test_raw_control_bytes_rejected_before_string_conversion(self):
        f=self.root/'sources.txt'
        for attack in ('https://example.com/ho\x00sts.txt',
                       'https://example.com/hosts.txt\n',
                       'https://example.com/ho\tsts.txt',
                       'https://example.com/hosts.txt\r'):
            self.assertNotEqual(self.call('add','sources',self.b64(attack),ok=False).returncode,0)
        self.assertEqual(f.read_text(),'')
        token='ux02_secure_binary_stage'
        self.call('stage-begin',token)
        self.call('stage-chunk',token,self.b64('https://valid.example/hosts.txt\n\x00https://other.example/hosts.txt\n'))
        self.assertNotEqual(self.call('stage-commit',token,'sources',ok=False).returncode,0)
        self.assertEqual(f.read_text(),'')
        self.call('stage-abort',token)

    def test_rename_refuses_overwrite_and_delete_core(self):
        original=self.root/'custom_foo.txt'; original.write_text('0.0.0.0 foo.example\n')
        existing=self.root/'custom_bar.txt'; existing.write_text('0.0.0.0 bar.example\n')
        self.assertNotEqual(self.call('rename-custom','custom_foo.txt','custom_bar.txt',ok=False).returncode,0)
        self.assertTrue(original.exists()); self.assertTrue(existing.exists())
        self.assertNotEqual(self.call('delete-custom','custom',ok=False).returncode,0)
        self.call('rename-custom','custom_foo.txt','custom_baz.txt')
        self.assertFalse(original.exists())
        self.call('delete-custom','custom_baz.txt')
        self.assertFalse((self.root/'custom_baz.txt').exists())

    def test_bad_base64_and_control_chars_rejected(self):
        for value in ('abc; touch /tmp/pwn', self.b64('a\nb'), self.b64('a\x00b')):
            self.assertNotEqual(self.call('add','sources',value,ok=False).returncode,0)
        self.assertEqual((self.root/'sources.txt').read_text(),'')

if __name__ == '__main__': unittest.main(verbosity=2)
