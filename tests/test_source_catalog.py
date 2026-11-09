#!/usr/bin/env python3
"""UX01 root catalog fixture tests; no external network, no Android build."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'module/source_catalog.sh'
CAT = ROOT / 'module/data/source-catalog.tsv'

class SourceCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bh-catalog-')
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.sources = self.state / 'sources.txt'
        self.sources.write_text('# preserved\nhttps://adaway.org/hosts.txt\n'
                                'disabled|https://sample.example/private.txt # user-owned\n')
        self.env = {**os.environ, 'BH_CATALOG_TEST_ROOT': '1',
                    'BH_CATALOG_ROOT': str(self.state), 'BH_CATALOG_FILE': str(CAT)}

    def cli(self, *args, ok=True, env=None):
        result = subprocess.run(['sh', str(SCRIPT), *args], env=env or self.env,
                                text=True, capture_output=True, timeout=8)
        if ok:
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        else:
            self.assertNotEqual(result.returncode, 0, (result.stdout, result.stderr))
        return result

    def status(self):
        return dict(row.split('|', 1) for row in self.cli('status').stdout.strip().splitlines())

    def test_default_external_and_off(self):
        self.assertEqual(self.status()['adaway'], 'external')
        self.assertEqual(self.status()['energized-blu'], 'off')
        self.assertEqual(self.sources.read_text().splitlines()[0], '# preserved')

    def test_cubic_reversible_without_modifying_custom_sources(self):
        before = self.sources.read_text()
        self.cli('enable', 'cubic')
        self.assertEqual(self.status()['cubic'], 'on')
        self.assertIn('source-catalog:cubic', self.sources.read_text())
        self.cli('enable', 'cubic')
        self.assertEqual(self.sources.read_text().count('source-catalog:cubic'), 1)
        self.cli('disable', 'cubic')
        self.assertEqual(self.status()['cubic'], 'off')
        self.assertEqual(self.sources.read_text(), before)

    def test_energized_tiers_mutually_exclusive_only_for_owned(self):
        self.cli('enable', 'energized-spark')
        self.cli('enable', 'energized-blu')
        self.assertEqual(self.status()['energized-spark'], 'off')
        self.assertEqual(self.status()['energized-blu'], 'on')
        self.cli('enable', 'energized-ultimate')
        self.assertEqual(self.status()['energized-blu'], 'off')
        self.assertEqual(self.status()['energized-ultimate'], 'on')
        self.assertEqual(self.sources.read_text().count('source-catalog:'), 1)

    def test_does_not_disable_manual_equivalent(self):
        self.cli('disable', 'adaway', ok=False)
        self.assertEqual(self.sources.read_text().count('https://adaway.org/hosts.txt'), 1)
        self.assertNotIn('source-catalog', self.sources.read_text())

    def test_disabled_manual_entry_is_not_overwritten(self):
        url = 'https://energized.pro/blu/hosts.txt'
        with self.sources.open('a') as stream:
            stream.write('disabled|' + url + ' # my disabled entry\n')
        before = self.sources.read_bytes()
        self.cli('enable', 'energized-blu')
        self.assertIn('source-catalog:energized-blu', self.sources.read_text())
        self.cli('disable', 'energized-blu')
        self.assertEqual(self.sources.read_bytes(), before)

    def test_user_enabled_preset_url_refuses_catalog_management(self):
        url = 'https://energized.pro/spark/hosts.txt'
        with self.sources.open('a') as stream:
            stream.write(url + ' # external user source\n')
        before = self.sources.read_bytes()
        self.cli('enable', 'energized-spark', ok=False)
        self.assertEqual(self.sources.read_bytes(), before)
        self.assertEqual(self.status()['energized-spark'], 'external')

    def test_reject_unknown_ids_and_shell_metacharacters(self):
        original = self.sources.read_bytes()
        for value in ('unknown', 'cubic;touch /tmp/owned', "cubic'", '../cubic', ''):
            self.cli('enable', value, ok=False)
        self.assertEqual(self.sources.read_bytes(), original)

    def test_symlink_and_lock_refusal(self):
        outside = self.state / 'outside'
        outside.write_text('safe')
        self.sources.unlink()
        self.sources.symlink_to(outside)
        self.cli('enable', 'cubic', ok=False)
        self.assertEqual(outside.read_text(), 'safe')
        self.sources.unlink()
        self.sources.write_text('')
        (self.state / '.source-catalog.lock').mkdir()
        self.cli('enable', 'cubic', ok=False)
        self.assertEqual(self.sources.read_text(), '')

    def test_catalog_malformed_refused_before_write(self):
        bad = self.state / 'malformed.tsv'
        bad.write_text('bad|Example|http://no-tls.invalid/list|core\n')
        env = {**self.env, 'BH_CATALOG_FILE': str(bad)}
        old = self.sources.read_bytes()
        self.cli('enable', 'bad', ok=False, env=env)
        self.assertEqual(self.sources.read_bytes(), old)

if __name__ == '__main__':
    unittest.main(verbosity=2)
