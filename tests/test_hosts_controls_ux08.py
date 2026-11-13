#!/usr/bin/env python3
"""UX08: real POSIX-shell pause/resume tests and UI command-contract tests."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'module'

class UX08HostsControls(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.getenv('TMPDIR') or None)
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.state = self.work / 'state'
        self.state.mkdir()
        self.target = self.work / 'hosts'
        self.original = (b'127.0.0.1 localhost\n::1 localhost\n'
                         b'# bindhosts-custom-start\n# bindhosts-custom-end\n'
                         b'# bindhosts-block-start\n0.0.0.0 ads.example\n'
                         b'# bindhosts-block-end\n# bindhosts v21602\n')
        self.target.write_bytes(self.original)
        self.mod = self.work / 'module'
        self.mod.mkdir()
        for name in ('hosts_control_safe.sh', 'hosts_reset_safe.sh',
                     'hosts_target_safe.sh', 'hosts_update_parse.awk'):
            shutil.copy2(MODULE / name, self.mod / name)
        (self.mod / 'module.prop').write_text('id=bindhosts\ndescription=status: active\n')
        (self.mod / 'bindhosts.sh').write_text(
            '#!/bin/sh\n'
            '[ "$1" = --force-update ] || exit 50\n'
            '[ ! -e "$BH_UX08_TEST_STATE/bindhosts_backup" ] || exit 51\n'
            'printf "# bindhosts-block-start\\n0.0.0.0 fresh.example\\n# bindhosts-block-end\\n# bindhosts v21602\\n" >> "$BH_UX08_TEST_TARGET"\n'
            'echo BH_UPDATE_SAFE_PASS\n')
        self.env = dict(os.environ, BH_HOSTS_TEST_MODE='1',
                        BH_UX08_TEST_STATE=str(self.state),
                        BH_UX08_TEST_TARGET=str(self.target),
                        BH_HOSTS_ROOT=str(self.state))

    def action(self, command, *, ok=True):
        p = subprocess.run(['sh', str(self.mod / 'hosts_control_safe.sh'), command,
                            str(self.target), str(self.state), str(self.mod)],
                           capture_output=True, text=True, env=self.env, timeout=15)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + '\n' + p.stderr)
        else:
            self.assertNotEqual(p.returncode, 0, p.stdout + '\n' + p.stderr)
        return p

    def test_status_read_only(self):
        before = {f.name: f.read_bytes() for f in self.work.rglob('*') if f.is_file()}
        self.assertIn('BH_HOSTS_STATE=ACTIVE', self.action('status').stdout)
        after = {f.name: f.read_bytes() for f in self.work.rglob('*') if f.is_file()}
        self.assertEqual(before, after)

    def test_pause_resume_exactly_restores_original(self):
        self.assertIn('BH_HOSTS_PAUSE_PASS', self.action('pause').stdout)
        self.assertTrue((self.state / 'bindhosts_backup').is_file())
        self.assertEqual((self.state / 'bindhosts_backup').read_bytes(), self.original)
        self.assertNotIn(b'ads.example', self.target.read_bytes())
        self.assertIn('status: paused', (self.mod / 'module.prop').read_text())
        self.assertIn('BH_HOSTS_STATE=PAUSED', self.action('status').stdout)
        self.assertIn('BH_HOSTS_RESUME_PASS', self.action('resume').stdout)
        self.assertFalse((self.state / 'bindhosts_backup').exists())
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertIn('status: active', (self.mod / 'module.prop').read_text())
        self.assertIn('BH_HOSTS_STATE=ACTIVE', self.action('status').stdout)

    def test_update_refused_while_paused(self):
        self.action('pause')
        neutral = self.target.read_bytes()
        self.assertIn('paused', self.action('update', ok=False).stderr)
        self.assertEqual(self.target.read_bytes(), neutral)
        self.assertTrue((self.state / 'bindhosts_backup').exists())

    def test_duplicate_or_wrong_action_refused(self):
        self.action('resume', ok=False)
        self.action('pause')
        self.action('pause', ok=False)
        self.action('nonexistent', ok=False)

    def test_mutual_exclusion_with_update_lock(self):
        lock = self.state / '.hosts-update.lock'
        lock.mkdir()
        self.assertIn('another hosts operation', self.action('pause', ok=False).stderr)
        self.assertEqual(self.target.read_bytes(), self.original)
        lock.rmdir()
        self.action('pause')
        self.assertFalse(lock.exists())

    def test_symlink_and_conflicting_backup_refused(self):
        backup = self.state / 'bindhosts_backup'
        backup.symlink_to(self.target)
        self.action('status', ok=False)
        self.action('pause', ok=False)
        backup.unlink()
        backup.write_bytes(self.original)
        self.assertIn('BH_HOSTS_STATE=INCONSISTENT', self.action('status', ok=False).stdout)
        self.action('resume', ok=False)

    def test_module_disabled_no_write(self):
        (self.mod / 'disable').touch()
        self.assertIn('BH_HOSTS_STATE=DISABLED', self.action('status').stdout)
        self.action('pause', ok=False)
        self.action('update', ok=False)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_update_readback(self):
        self.target.write_text('127.0.0.1 localhost\n')
        self.assertIn('BH_HOSTS_STATE=INACTIVE', self.action('status').stdout)
        self.assertIn('BH_HOSTS_UPDATE_PASS', self.action('update').stdout)
        self.assertIn('BH_HOSTS_STATE=ACTIVE', self.action('status').stdout)

    def test_webui_no_ambiguous_fabs(self):
        index = (ROOT / 'webui/index.html').read_text()
        hosts = (ROOT / 'webui/page/hosts/hosts.js').read_text()
        html = (ROOT / 'webui/page/hosts/hosts.html').read_text()
        controls = (ROOT / 'webui/utils/hosts_controls.js').read_text()
        script = (MODULE / 'bindhosts.sh').read_text()
        updater = (MODULE / 'hosts_update_safe.sh').read_text()
        self.assertNotIn('id="force-update-btn"', index)
        self.assertNotIn('id="action-btn"', index)
        self.assertNotIn('runBindhosts("--action")', hosts)
        self.assertIn('mountHostsControls()', hosts)
        self.assertIn('refreshHostsControls()', hosts)
        for name in ('hosts-control-toggle', 'hosts-control-update', 'hosts-control-status'):
            self.assertIn(name, html)
        self.assertIn('BH_HOSTS_${action.toUpperCase()}_PASS', controls)
        self.assertIn('--hosts-control', controls)
        self.assertIn('hosts_control_safe.sh', script)
        self.assertNotIn('\"$PERSISTENT_DIR/bindhosts_backup\" > /dev/null 2>&1', script)
        self.assertIn('blocking paused; resume before updating', updater)

if __name__ == '__main__':
    unittest.main(verbosity=2)
