#!/usr/bin/env python3
"""R3 HF02: pm parser and fail-closed package snapshot tests; no Android required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
R2=ROOT/'module/trackerguard_r2.sh'

def function_body():
    src=R2.read_text()
    return src[src.index('tg_r2_snapshot() {'):src.index('\n\ntg_r2_once()',src.index('tg_r2_snapshot() {'))]

GOOD=(
    'package:/data/app/~~0ABc==/com.example-a1==/base.apk=com.example.alpha versionCode:201\n'
    'package:/data/app/~~5d9==/com.example-b2==/base.apk=com.example.beta versionCode:0\n'
)

class SnapshotContract(unittest.TestCase):
    def exercise(self, text, pm_rc=0, cmd_output=None):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR') or None) as d:
            root=Path(d);p=root/'pm';raw=root/'raw'
            raw.write_text(text)
            p.write_text('#!/bin/sh\ncat "$TG_RAW"\nexit '+str(pm_rc)+'\n');p.chmod(0o755)
            mockbin=root/'bin';mockbin.mkdir()
            if cmd_output is not None:
                b=mockbin/'cmd';b.write_text('#!/bin/sh\n[ "$1" = package ] || exit 13\ncat "$TG_CMD_RAW"\n');b.chmod(0o755)
                (root/'cmdraw').write_text(cmd_output)
            else:
                # A present but failing command must not mask pm failure.
                b=mockbin/'cmd';b.write_text('#!/bin/sh\nexit 13\n');b.chmod(0o755)
            sh=root/'test.sh';sh.write_text('say() { echo "$*"; }\n'+function_body()+'\ntg_r2_snapshot "$TG_STATE_DIR/snapshot"\n')
            env=dict(os.environ,TG_PM=str(p),TG_RAW=str(raw),TG_STATE_DIR=str(root),
                     TG_CMD_RAW=str(root/'cmdraw'),PATH=str(mockbin)+':'+os.environ.get('PATH','/usr/bin:/bin'))
            cp=subprocess.run(['sh',str(sh)],env=env,capture_output=True,text=True,timeout=12)
            return cp, (root/'snapshot').read_text() if (root/'snapshot').exists() else ''

    def test_normal_android16_base64_paths(self):
        cp,output=self.exercise(GOOD)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertIn('com.example.alpha|package:',output)
        self.assertIn('versionCode:201',output)
        self.assertEqual(len(output.splitlines()),2)

    def test_optional_known_metadata(self):
        cp,output=self.exercise('package:/data/app/~~abc==/base.apk=com.example.alpha versionCode:7 stopped=false uid:12345\n')
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertEqual(output.count('versionCode:7'),1)

    def test_reject_unexpected_nonpackage_line_without_names(self):
        cp,output=self.exercise(GOOD+'Unexpected platform failure\n')
        self.assertNotEqual(cp.returncode,0)
        self.assertIn('R2_SNAPSHOT_PARSE_FAILED: valid=2 invalid=1',cp.stderr)
        self.assertNotIn('com.example.alpha',cp.stderr)
        self.assertEqual(output,'')

    def test_reject_empty_inventory_no_mass_uninstall(self):
        cp,output=self.exercise('')
        self.assertNotEqual(cp.returncode,0)
        self.assertIn('valid=0 invalid=0',cp.stderr)
        self.assertEqual(output,'')

    def test_reject_invalid_version_and_package(self):
        for raw in (
          'package:/data/app/base.apk=com.example.alpha versionCode:-1\n',
          'package:/data/app/base.apk=com.example.bad-name versionCode:20\n',
          'package:/data/app/base.apk=com.example.alpha versionCode:1\npackage:/data/app/other.apk=com.example.alpha versionCode:2\n',
        ):
            with self.subTest(raw=raw[:45]):
                cp,_=self.exercise(raw)
                self.assertNotEqual(cp.returncode,0)

    def test_pm_failure_fallback_to_cmd_package(self):
        cp,output=self.exercise('',pm_rc=3,cmd_output=GOOD)
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.assertIn('R2_SNAPSHOT_PM_FALLBACK',cp.stderr)
        self.assertEqual(len(output.splitlines()),2)

    def test_both_package_managers_failed(self):
        cp,output=self.exercise('',pm_rc=3)
        self.assertNotEqual(cp.returncode,0)
        self.assertIn('R2_SNAPSHOT_FAILED: both pm and cmd package queries failed',cp.stderr)
        self.assertEqual(output,'')

if __name__=='__main__':unittest.main(verbosity=2)
