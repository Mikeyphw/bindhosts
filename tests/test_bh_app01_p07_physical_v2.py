"""Adversarial P07 physical ARM64 preflight fixtures; never invokes real ADB."""
from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bh_ph01', ROOT/'scripts/ci/bh_app01_p07_physical_v2.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = 'a'*40
APK = 'b'*64
PACKAGE = '/data/app/~~AbCd/com.mikeyphw.bindhosts-HfGt=/base.apk'


def hosted_file(path, **changes):
    data = dict(schema='bh-app01/p07/hosted/v1', source_sha=SHA,
                hosted_api36_qualified=True, physical_android16_qualified=False,
                release_qualified=False, emulator_api=36, test_count=3,
                apk_sha256=APK, device_write_tests_performed=False,
                real_cold_start_qs_confirm_and_cancel=True)
    data.update(changes)
    path.write_text(json.dumps(data)+'\n')
    return path


class P07PH01(unittest.TestCase):
    def mappings(self, installed=True):
        base = {
            ('get-state',): 'device',
            ('devices','-l'): 'List of devices attached\nlocalhost:5555 device product:test\n',
            ('shell','getprop','ro.build.version.sdk'): '36',
            ('shell','getprop','ro.product.cpu.abi'): 'arm64-v8a',
            ('shell','getprop','ro.kernel.qemu'): '',
            ('shell','getenforce'): 'Enforcing',
            ('shell','pm','path',MODULE.APP): 'package:'+PACKAGE if installed else '',
            ('shell','dumpsys','package',MODULE.APP): 'ProtectionTileService\nUpdateTileService',
            ('shell','pm','list','packages'): 'package:me.weishu.kernelsu\npackage:com.example.other',
            ('shell','sha256sum',PACKAGE): APK+'  '+PACKAGE,
        }
        return base

    def test_positive_readonly_but_never_physical_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = hosted_file(Path(tmp)/'hosted.json')
            seen=[]
            def fake(serial,args,**kw):
                seen.append(tuple(args))
                return self.mappings()[tuple(args)]
            with patch.object(MODULE, 'adb', side_effect=fake):
                r=MODULE.inspect('localhost:5555', SHA, receipt)
            self.assertEqual(r['read_only_status'],'READY_FOR_APPROVAL_GATES')
            self.assertTrue(r['hosted_apk_matches_installed'])
            self.assertFalse(r['physical_android16_qualified'])
            self.assertFalse(r['release_qualified'])
            self.assertFalse(r['root_access_requested'])
            self.assertEqual(r['root_manager_package_detected'], ['me.weishu.kernelsu'])
            self.assertEqual(seen.count(('shell','sha256sum',PACKAGE)),1)

    def test_absent_app_is_inconclusive(self):
        with patch.object(MODULE,'adb',side_effect=lambda s,a,**k:self.mappings(False)[tuple(a)]):
            r=MODULE.inspect('localhost:5555', SHA)
        self.assertFalse(r['app_installed'])
        self.assertFalse(r['hosted_apk_matches_installed'])
        self.assertEqual(r['read_only_status'],'INCONCLUSIVE')

    def test_mutated_device_is_denied(self):
        for key, value in [(('shell','getprop','ro.build.version.sdk'),'35'),
                           (('shell','getprop','ro.product.cpu.abi'),'x86_64'),
                           (('shell','getprop','ro.kernel.qemu'),'1'),
                           (('devices','-l'),'emulator-5554 device')]:
            with self.subTest(key=key):
                mapping=self.mappings();mapping[key]=value
                with patch.object(MODULE,'adb',side_effect=lambda s,a,**k:mapping[tuple(a)]):
                    with self.assertRaises(ValueError):MODULE.inspect('localhost:5555', SHA)

    def test_installed_apk_mismatch_is_unqualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=hosted_file(Path(tmp)/'receipt.json')
            m=self.mappings();m[('shell','sha256sum',PACKAGE)]='f'*64+'  '+PACKAGE
            with patch.object(MODULE,'adb',side_effect=lambda s,a,**kw:m[tuple(a)]):
                r=MODULE.inspect('localhost:5555', SHA, receipt)
            self.assertEqual(r['read_only_status'],'INCONCLUSIVE')
            self.assertFalse(r['hosted_apk_matches_installed'])

    def test_bad_hosted_receipts_refused(self):
        for value in ({'source_sha':'c'*40}, {'test_count':2},
                      {'physical_android16_qualified':True}, {'release_qualified':True},
                      {'device_write_tests_performed':True}, {'real_cold_start_qs_confirm_and_cancel':False}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                receipt=hosted_file(Path(tmp)/'hosted.json',**value)
                with self.assertRaises(ValueError):MODULE.load_hosted(receipt,SHA)

    def test_readonly_adb_allowlist_denies_mutation(self):
        for command in (['shell','su','-c','id'], ['install','a.apk'],
                        ['shell','am','start','-n','com.mikeyphw.bindhosts/.MainActivity'],
                        ['shell','pm','clear',MODULE.APP],
                        ['shell','sha256sum','/data/adb/modules/../secret']):
            with self.subTest(command=command), self.assertRaises(ValueError):
                MODULE.adb('localhost:5555', command)

    def test_adb_bounded_bytes_and_argv(self):
        class Response:
            def __init__(self,code=0,out=b'device',err=b''):
                self.returncode=code;self.stdout=out;self.stderr=err
        with patch.object(MODULE.subprocess,'run',return_value=Response()) as run:
            self.assertEqual(MODULE.adb('localhost:5555',['get-state']),'device')
            self.assertEqual(run.call_args.args[0],['adb','-s','localhost:5555','get-state'])
            self.assertFalse(run.call_args.kwargs.get('shell',False))
        with patch.object(MODULE.subprocess,'run',return_value=Response(out=b'X'*70000)):
            with self.assertRaises(ValueError):MODULE.adb('localhost:5555',['get-state'])
        with patch.object(MODULE.subprocess,'run',return_value=Response(1)):
            with self.assertRaises(ValueError):MODULE.adb('localhost:5555',['get-state'])

    def test_report_private_and_symlink_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out'/'report.json'
            MODULE.write_private(output, {'physical_android16_qualified':False})
            self.assertEqual(output.stat().st_mode & 0o777,0o600)
            self.assertFalse(json.loads(output.read_text())['physical_android16_qualified'])
            other=Path(tmp)/'other';other.write_text('DO NOT OVERWRITE')
            output.unlink();output.symlink_to(other)
            with self.assertRaises(ValueError):MODULE.write_private(output,{})
            self.assertEqual(other.read_text(),'DO NOT OVERWRITE')

    def test_invalid_serial_and_invalid_sha(self):
        with self.assertRaises(ValueError):MODULE.adb('bad serial',['get-state'])
        with self.assertRaises(ValueError):MODULE.inspect('localhost:5555','NOTSHA')

    def test_source_mentions_no_arbitrary_root_or_gradle(self):
        source=(ROOT/'scripts/ci/bh_app01_p07_physical_v2.py').read_text()
        self.assertIn('I_AUTHORIZE_READ_ONLY_DEVICE_PROBE',source)
        self.assertNotIn('shell=True',source)
        self.assertNotIn("['su'",source)
        self.assertNotIn("['install'",source)
        self.assertIn("'physical_android16_qualified': False",source)
        self.assertIn("'release_qualified': False",source)

if __name__=='__main__':unittest.main()
