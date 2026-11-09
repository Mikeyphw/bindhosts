#!/usr/bin/env python3
"""R3 HF01: service must not mount an interrupted hosts write before recovery."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
SERVICE=(ROOT/'module/service.sh')
class BootRecoveryTests(unittest.TestCase):
    def test_recover_before_host_mount_and_fail_closed(self):
        s=SERVICE.read_text()
        mount=s.index('case $operating_mode in')
        early=s.index('# R3 HF01: a previous interrupted in-place write')
        self.assertLess(early,mount)
        self.assertIn('pre-mount hosts recovery failed; refusing mount',s)
        self.assertIn('7|8) _bh_recover_before_mount=',s)
        self.assertIn('overlay hosts recovery failed; refusing further services',s)
        self.assertIn('journal unexpectedly pending after pre-mount recovery',s)
    def test_pending_journal_refuses_mount_when_recovery_fails(self):
        service=SERVICE.read_text()
        start=service.index('# R3 HF01: a previous interrupted in-place write')
        end=service.index('# check opmodes and then do something',start)
        fragment=service[start:end]
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            d=Path(td); module=d/'mod'; state=d/'state'
            (module/'system/etc').mkdir(parents=True)
            state.mkdir()
            (state/'.hosts-target-journal').mkdir()
            (module/'system/etc/hosts').write_text('127.0.0.1 localhost\n')
            stub=module/'hosts_target_safe.sh'
            stub.write_text('#!/bin/sh\nprintf "%s\n" "$*" > "$BH_HOSTS_ROOT/called"\nexit "${R3_RECOVERY_RESULT:-0}"\n')
            stub.chmod(0o755)
            script=f'MODDIR="{module}"\nPERSISTENT_DIR="{state}"\noperating_mode=2\n'+fragment.replace('>> /dev/kmsg','>> "$PERSISTENT_DIR/kmsg"')+'\necho MOUNT_DISPATCH_OK\n'
            failed=subprocess.run(['sh','-c',script],env={**os.environ,'R3_RECOVERY_RESULT':'1'},capture_output=True,text=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertNotIn('MOUNT_DISPATCH_OK',failed.stdout)
            self.assertEqual((state/'called').read_text().strip(),'recover '+str(module/'system/etc/hosts'))
            passed=subprocess.run(['sh','-c',script],env={**os.environ,'R3_RECOVERY_RESULT':'0'},capture_output=True,text=True)
            self.assertEqual(passed.returncode,0,passed.stderr)
            self.assertIn('MOUNT_DISPATCH_OK',passed.stdout)
            (module/'system/etc/hosts').unlink()
            missing=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            self.assertNotEqual(missing.returncode,0)
            self.assertNotIn('MOUNT_DISPATCH_OK',missing.stdout)

    def test_overlay_mount_defers_recovery_until_upperdir_visible(self):
        service=SERVICE.read_text()
        start=service.index('# R3 HF01: a previous interrupted in-place write')
        end=service.index('# check opmodes and then do something',start)
        fragment=service[start:end]
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            d=Path(td);module=d/'mod';state=d/'state';module.mkdir();state.mkdir()
            (state/'.hosts-target-journal').mkdir()
            script=f'MODDIR="{module}"\nPERSISTENT_DIR="{state}"\noperating_mode=7\n'+fragment+'\necho MOUNT_DISPATCH_OK\n'
            outcome=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            self.assertEqual(outcome.returncode,0,outcome.stderr)
            self.assertIn('MOUNT_DISPATCH_OK',outcome.stdout)

    def test_bootstrap_atomic_publication_and_failure_cleanup(self):
        source=(ROOT/'module/post-fs-data.sh').read_text()
        begin=source.index('[ ! -L "$MODDIR/system/etc/hosts" ] || exit 1')
        end=source.index('hosts_set_perm "$MODDIR/system/etc/hosts"', begin)
        block=source[begin:end]
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            d=Path(td); mod=d/'module'; src=d/'system-hosts'; mod.mkdir()
            translated=block.replace('cat /system/etc/hosts', 'cat '+str(src))
            script=f'MODDIR="{mod}"\n'+translated+'\necho BOOTSTRAP_PASS\n'
            missing=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            target=mod/'system/etc/hosts'
            self.assertNotEqual(missing.returncode,0)
            self.assertFalse(target.exists())
            self.assertFalse(list((mod/'system/etc').glob('.hosts-init.*')))
            src.write_text('127.0.0.1 localhost\n')
            created=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            self.assertEqual(created.returncode,0,created.stderr)
            self.assertIn('BOOTSTRAP_PASS',created.stdout)
            self.assertIn('::1 localhost',target.read_text())
            self.assertFalse(list((mod/'system/etc').glob('.hosts-init.*')))
            target.unlink();target.symlink_to(src)
            symlink=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            self.assertNotEqual(symlink.returncode,0)
            self.assertEqual(src.read_text(),'127.0.0.1 localhost\n')

    def test_first_boot_initialization_uses_module_path(self):
        script=(ROOT/'module/post-fs-data.sh').read_text()
        self.assertIn('mv -f "$_bh_init_tmp" "$MODDIR/system/etc/hosts"', script)
        self.assertIn('[ ! -L "$MODDIR/system/etc/hosts" ] || exit 1', script)
        self.assertIn('mktemp "$MODDIR/system/etc/.hosts-init.XXXXXXXX"', script)
        self.assertNotIn('$MODPATH/system/etc/hosts', script)
        self.assertIn('mkdir -p "$MODDIR/system/etc" || exit 1', script)
    def test_no_unchecked_mount_before_recovery_guard(self):
        s=SERVICE.read_text()
        # Earlier `mount_bind()` and `overlay_routine()` are function bodies,
        # not run until their post-recovery dispatch.
        self.assertLess(s.index('pre-mount hosts recovery failed'),s.index('case $operating_mode in'))
        self.assertLess(s.index('case $operating_mode in'),s.index('apply_description &'))
if __name__=='__main__':unittest.main(verbosity=2)
