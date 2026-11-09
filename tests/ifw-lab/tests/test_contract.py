#!/usr/bin/env python3
"""Offline contract and simulated before/blocked/after IFW safety tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PKG = 'com.mikeyphw.trackerguard.ifwlab'

MOCK_ADB = r'''#!/bin/sh
set -eu
[ "${1:-}" = -s ] && [ "${2:-}" = localhost:5555 ] || exit 2
shift 2
STATE=$TG_MOCK_STATE_DIR
case "$*" in
  'get-state') echo device ;;
  'install -r '*) echo Success ;;
  'shell getprop ro.build.version.sdk') echo 36 ;;
  'shell getprop ro.product.cpu.abi') echo arm64-v8a ;;
  'shell am start -W '*) echo 'Status: ok' ;;
  'shell run-as com.mikeyphw.trackerguard.ifwlab pwd') echo /data/user/0/com.mikeyphw.trackerguard.ifwlab ;;
  'shell run-as com.mikeyphw.trackerguard.ifwlab cat files/received-events.log') cat "$STATE/received" ;;
  'shell su -c pm list packages -3') echo 'package:com.mikeyphw.trackerguard.ifwlab' ;;
  'shell su -c sh /data/adb/modules/bindhosts/bindhosts.sh tracker list')
    echo 'com.noodlecake.altosodyssey|receiver|com.appsflyer.SingleInstallBroadcastReceiver'
    if [ "$(cat "$STATE/blocked")" = 1 ]; then
      echo 'com.mikeyphw.trackerguard.ifwlab|receiver|com.mikeyphw.trackerguard.ifwlab.ProbeReceiver'
    fi ;;
  'shell su -c sh /data/adb/modules/bindhosts/bindhosts.sh tracker add '*)
    echo 1 > "$STATE/blocked"; echo 'IFW rule written' ;;
  'shell su -c sh /data/adb/modules/bindhosts/bindhosts.sh tracker remove '*)
    echo 0 > "$STATE/blocked"; echo 'Removed rule' ;;
  'shell su -c ls -lZ /data/system/ifw/bindhosts_trackerguard.xml')
    echo '-rw------- 1 system system u:object_r:system_data_file:s0' ;;
  'shell am broadcast '*)
    token=''
    for v in "$@"; do token=$v; done
    if [ "$(cat "$STATE/blocked")" = 0 ] || [ "${TG_MOCK_ALLOW_WHILE_BLOCKED:-0}" = 1 ]; then
      printf '%s\n' "$token" >> "$STATE/received"
      echo 'Broadcast completed: result=243'
    else
      echo 'Broadcast completed: result=0'
    fi ;;
  *) echo "UNKNOWN_MOCK_ADB: $*" >&2; exit 2 ;;
esac
''' 


class LabContract(unittest.TestCase):
    def test_manifest_and_no_permissions(self):
        manifest = ET.parse(ROOT / 'app/src/main/AndroidManifest.xml').getroot()
        android = '{http://schemas.android.com/apk/res/android}'
        app = manifest.find('application')
        self.assertIsNotNone(app)
        self.assertIsNone(manifest.find('uses-permission'))
        self.assertEqual(app.attrib[android+'allowBackup'], 'false')
        receivers = app.findall('receiver')
        self.assertEqual(len(receivers), 1)
        self.assertEqual(receivers[0].attrib[android+'name'], '.ProbeReceiver')
        self.assertEqual(receivers[0].attrib[android+'exported'], 'true')
        action = receivers[0].find('intent-filter/action')
        self.assertEqual(action.attrib[android+'name'], PKG+'.PROBE')
        self.assertIsNotNone(app.find('activity'))
        code = (ROOT / 'app/src/main/java/com/mikeyphw/trackerguard/ifwlab/ProbeReceiver.java').read_text()
        self.assertIn('RECORD_FILE = "received-events.log"', code)
        self.assertIn('setResultCode(ORDERED_RESULT)', code)
        self.assertNotIn('android.permission.INTERNET', manifest.find('application').attrib)

    def test_gradle_settings_no_network_dependency(self):
        app = (ROOT/'app/build.gradle').read_text()
        self.assertIn('compileSdk 36', app)
        self.assertIn('targetSdk 35', app)
        self.assertIn('debuggable true', app)
        self.assertNotIn('implementation ', app)
        self.assertNotIn('android.permission.', (ROOT/'app/src/main/AndroidManifest.xml').read_text())

    def test_harness_is_shell_valid(self):
        subprocess.run(['sh','-n',str(ROOT/'run-device-test.sh')], check=True)
        script = (ROOT/'run-device-test.sh').read_text()
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('TG_IFW_LAB_PASS', script)
        self.assertIn('LAB_RULE_ALREADY_PRESENT', script)
        self.assertNotIn('restore --all', script)
        self.assertNotIn('tracker block', script)

    def exercise(self, allow_blocked=False):
        with tempfile.TemporaryDirectory(prefix='tg-ifw-lab-') as d:
            p=Path(d)
            adb=p/'adb'
            adb.write_text(MOCK_ADB)
            adb.chmod(0o755)
            # CI simulates Android waits without burning wall-clock time.
            sleep=p/'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n')
            sleep.chmod(0o755)
            state=p/'state'
            state.mkdir()
            (state/'blocked').write_text('0')
            (state/'received').write_text('')
            apk=p/'app-debug.apk'
            apk.write_text('offline test only')
            env=dict(os.environ)
            env.update(TG_MOCK_STATE_DIR=str(state), PATH=str(p)+os.pathsep+env['PATH'])
            if allow_blocked:
                env['TG_MOCK_ALLOW_WHILE_BLOCKED']='1'
            proc=subprocess.run(['sh',str(ROOT/'run-device-test.sh'),str(apk)],
                                env=env, capture_output=True, text=True, timeout=35)
            return proc, {'blocked': (state/'blocked').read_text().strip()=='1', 'received': (state/'received').read_text().splitlines()}

    def test_mocked_three_phase_enforcement_passes(self):
        proc, state = self.exercise()
        self.assertEqual(proc.returncode,0,proc.stdout+'\n'+proc.stderr)
        self.assertIn('TG_IFW_LAB_BASELINE_PASS',proc.stdout)
        self.assertIn('TG_IFW_LAB_BLOCK_PASS',proc.stdout)
        self.assertIn('TG_IFW_LAB_RESTORE_PASS',proc.stdout)
        self.assertIn('TG_IFW_LAB_PASS:',proc.stdout)
        self.assertFalse(state['blocked'])
        self.assertEqual(len(state['received']), 2)
        self.assertTrue(state['received'][0].startswith('TG_BEFORE_'))
        self.assertTrue(state['received'][1].startswith('TG_AFTER_'))

    def test_mocked_enforcement_failure_rolls_back(self):
        proc, state = self.exercise(allow_blocked=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn('TG_IFW_LAB_BLOCK_FAILED',proc.stdout)
        self.assertIn('SAFETY ROLLBACK',proc.stdout)
        self.assertFalse(state['blocked'])
        self.assertEqual(len(state['received']), 2)


if __name__=='__main__':
    unittest.main(verbosity=2)
