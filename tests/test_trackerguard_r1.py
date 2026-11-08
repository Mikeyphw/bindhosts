#!/usr/bin/env python3
"""TrackerGuard R1 native parser + CLI acceptance with simulated rooted Android package tools."""
import os
import pathlib
import random
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class TrackerGuardR1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='tg-r1-tests-')
        cls.t = pathlib.Path(cls.temp.name)
        cls.cc = cls.t / 'axmlscan'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        str(ROOT/'native/axmlscan.c'),'-o',str(cls.cc)],check=True)
        subprocess.run(['python3',str(ROOT/'tests/make_axml_fixture.py'),str(cls.t)],check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def cmd(self, *args, **kwargs):
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=5, **kwargs)

    def test_native_utf8_and_utf16_manifest(self):
        for enc in ('utf8', 'utf16'):
            p=self.cmd(self.cc,self.t/f'manifest-{enc}.axml')
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('package|com.example.app',p.stdout)
            self.assertIn('component|service|com.google.android.gms.measurement.AppMeasurementService|true',p.stdout)
            self.assertIn('component|receiver|com.adjust.sdk.AdjustReceiver|false',p.stdout)
            self.assertIn('component|provider|com.google.firebase.provider.FirebaseInitProvider|true',p.stdout)
            self.assertIn('component|activity|com.example.app.MainActivity|true',p.stdout)

    def test_malformed_binary_fails_closed(self):
        for name in ('truncated.axml','garbage.axml'):
            p=self.cmd(self.cc,self.t/name)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(p.stdout,'')
        source=(self.t/'manifest-utf8.axml').read_bytes()
        rng=random.Random(217)
        # Deterministic malformed inputs must never segfault or hang.
        for i in range(60):
            data=bytearray(source)
            for _ in range(rng.randint(1,6)):
                idx=rng.randrange(len(data))
                data[idx]=rng.randrange(256)
            case=self.t/f'corrupt-{i}.axml'
            case.write_bytes(data)
            p=self.cmd(self.cc,case)
            self.assertIn(p.returncode,(0,2),f'native crash: {p.returncode}: {p.stderr}')

    def test_signature_inventory_preview_and_batch_block(self):
        with tempfile.TemporaryDirectory(prefix='tg-r1-runtime-') as td:
            d=pathlib.Path(td)
            (d/'bin').mkdir()
            (d/'ifw').mkdir()
            (d/'state').mkdir()
            apk=d/'base.apk'
            shutil.copy2(self.t/'app-utf8.apk',apk)
            pm=d/'bin/pm'
            pm.write_text(textwrap.dedent('''\
                #!/bin/sh
                if [ "$1" = list ] && [ "$2" = packages ] && [ "$3" = -3 ]; then
                    echo package:com.example.app
                elif [ "$1" = path ] && [ "$2" = com.example.app ]; then
                    echo "package:$TG_TEST_APK"
                else exit 1; fi
                '''))
            pm.chmod(0o755)
            bb=d/'bin/busybox'
            bb.write_text('#!/bin/sh\n[ "$1" = unzip ] || exit 1\nshift\nexec "$TG_TEST_UNZIP" "$@"\n')
            bb.chmod(0o755)
            stub=d/'r0-test-stub.sh'
            stub.write_text(textwrap.dedent('''\
                #!/bin/sh
                set -u
                TG_FILE=$TG_IFW_DIR/bindhosts_trackerguard.xml
                TG_RULES=$TG_STATE_DIR/rules.tsv
                say() { printf '%s\\n' "$*"; }
                die() { echo "TrackerGuard: $*" >&2; exit 1; }
                validate_package() { case "$1" in com.example.app) :;; *) die invalid-package;; esac; }
                validate_type() { case "$1" in activity|service|receiver) :;; *) die invalid-type;; esac; }
                normalize_class() { printf '%s\\n' "$2"; }
                check_user_package() { "$TG_PM" list packages -3 | grep -Fxq "package:$1" || die missing-package; }
                prepare() { mkdir -p "$TG_STATE_DIR"; [ -e "$TG_RULES" ] || : > "$TG_RULES"; }
                lock() { mkdir "$TG_STATE_DIR/.lock" || die locked; trap 'rmdir "$TG_STATE_DIR/.lock"' EXIT; }
                check_owned() { :; }
                write_rules() { cp "$1" "$TG_RULES"; cp "$1" "$TG_FILE"; }
                . "$TG_R1_SCRIPT"
                case "$1" in
                  scan) tg_r1_scan "$2" ;;
                  preview) tg_r1_preview "$2" ;;
                  block) tg_r1_block "$2" ;;
                esac
                '''))
            stub.chmod(0o755)
            env={**os.environ,
                 'TG_STATE_DIR':str(d/'state'),'TG_IFW_DIR':str(d/'ifw'),
                 'TG_PM':str(pm),'TG_TEST_APK':str(apk),
                 'TG_TEST_UNZIP':shutil.which('unzip') or '/usr/bin/unzip',
                 'TG_R1_SCRIPT':str(ROOT/'module/trackerguard_r1.sh'),
                 'TG_R1_SCANNER':str(self.cc),
                 'TG_ROOT_SKIP':'1',
                 'TG_R1_MODDIR':str(ROOT/'module'),
                 'TG_R1_BUSYBOX':str(bb),
                 'TG_R1_SIGNATURES':str(ROOT/'module/data/tracker-signatures.tsv')}
            runner=ROOT/'module/trackerguard.sh' if (ROOT/'module/trackerguard.sh').is_file() else stub
            scan=self.cmd('sh',str(runner),'scan','com.example.app',env=env)
            self.assertEqual(scan.returncode,0,scan.stderr)
            self.assertIn('facebook-appevents|true|review',scan.stdout)
            self.assertIn('adjust|false|review',scan.stdout)
            self.assertEqual(scan.stdout.count('google-measurement'),1)
            self.assertFalse((d/'ifw/bindhosts_trackerguard.xml').exists())
            preview=self.cmd('sh',str(runner),'preview','com.example.app',env=env)
            self.assertEqual(preview.returncode,0,preview.stderr)
            self.assertIn('would-block',preview.stdout)
            self.assertIn('already-disabled',preview.stdout)
            self.assertFalse((d/'ifw/bindhosts_trackerguard.xml').exists())
            blocked=self.cmd('sh',str(runner),'block','com.example.app',env=env)
            self.assertEqual(blocked.returncode,0,blocked.stderr)
            state=(d/'state/rules.tsv').read_text()
            self.assertIn('com.example.app|service|com.google.android.gms.measurement.AppMeasurementService',state)
            self.assertIn('com.example.app|receiver|com.facebook.appevents.AppEventsReceiver',state)
            self.assertNotIn('com.adjust.sdk.AdjustReceiver',state)
            self.assertNotIn('com.google.firebase.provider.FirebaseInitProvider',state)
            blocked2=self.cmd('sh',str(runner),'block','com.example.app',env=env)
            self.assertEqual(blocked2.returncode,0,blocked2.stderr)
            self.assertEqual((d/'state/rules.tsv').read_text(),state)
            badenv={**env,'TG_R1_SIGNATURES':str(d/'invalid-signatures.tsv')}
            (d/'invalid-signatures.tsv').write_text('com.google.|BAD|review\n')
            refused=self.cmd('sh',str(runner),'block','com.example.app',env=badenv)
            self.assertNotEqual(refused.returncode,0,refused.stdout)
            self.assertEqual((d/'state/rules.tsv').read_text(),state)
            apk.write_bytes(b'not an apk')
            corrupted=self.cmd('sh',str(runner),'block','com.example.app',env=env)
            self.assertNotEqual(corrupted.returncode,0)
            self.assertEqual((d/'state/rules.tsv').read_text(),state)

if __name__=='__main__':
    unittest.main(verbosity=2)
