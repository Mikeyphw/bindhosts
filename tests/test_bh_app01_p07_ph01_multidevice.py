#!/usr/bin/env python3
"""PH01 HF08: real parse path and multi-ADB target safety without physical ADB."""
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import bh_app01_p07_physical_v2 as p

SOURCE='a'*40
APP=p.APP
PATH='/data/app/~~fake/base.apk'
APK='b'*64

def fake_adb_factory(inventory):
    calls=[]
    mapping={
       ('get-state',): 'device',
       ('devices','-l'): inventory,
       ('shell','getprop','ro.build.version.sdk'): '36',
       ('shell','getprop','ro.product.cpu.abi'): 'arm64-v8a',
       ('shell','getprop','ro.kernel.qemu'): '',
       ('shell','getenforce'): 'Enforcing',
       ('shell','pm','path',APP): 'package:'+PATH,
       ('shell','sha256sum',PATH): APK+'  '+PATH,
       ('shell','dumpsys','package',APP): 'ProtectionTileService UpdateTileService',
       ('shell','pm','list','packages'): 'package:me.weishu.kernelsu',
    }
    def fake_adb(serial,args,**kwargs):
        calls.append((serial,tuple(args)))
        assert serial=='localhost:5555',serial
        return mapping[tuple(args)]
    return fake_adb,calls

class TargetSelectionTests(unittest.TestCase):
    def inspect(self,inventory):
        fake,calls=fake_adb_factory(inventory)
        with patch.object(p,'adb',side_effect=fake):
            result=p.inspect('localhost:5555',SOURCE)
        self.assertTrue(all(serial=='localhost:5555' for serial,_ in calls))
        self.assertEqual(result['read_only_status'],'INCONCLUSIVE')  # no hosted receipt
        self.assertFalse(result['physical_android16_qualified'])
        self.assertEqual(result['installed_apk_sha256'],APK)
        self.assertFalse(result['device_writes_performed'])
        return result

    def test_one_online_target(self):
        self.inspect('List of devices attached\nlocalhost:5555 device product:rosemary\n')
    def test_additional_emulator_does_not_block(self):
        self.inspect('List of devices attached\nemulator-5554 device product:sdk\nlocalhost:5555 device product:rosemary\n')
    def test_additional_tcp_device_does_not_block(self):
        self.inspect('List of devices attached\nlocalhost:5555 device\n192.168.0.12:5555 device\n')
    def test_offline_unrelated_does_not_block(self):
        self.inspect('List of devices attached\nemulator-5554 offline\nlocalhost:5555 device\n')
    def test_target_missing_refuses(self):
        with self.assertRaisesRegex(ValueError,'EXPECTED_EXACTLY_ONE_ONLINE_TARGET_DEVICE'):
            self.inspect('List of devices attached\nemulator-5554 device\n')
    def test_only_alias_not_target_refuses(self):
        with self.assertRaisesRegex(ValueError,'EXPECTED_EXACTLY_ONE_ONLINE_TARGET_DEVICE'):
            self.inspect('List of devices attached\n127.0.0.1:5555 device\n')
    def test_offline_target_refuses(self):
        with self.assertRaisesRegex(ValueError,'EXPECTED_EXACTLY_ONE_ONLINE_TARGET_DEVICE'):
            self.inspect('List of devices attached\nlocalhost:5555 offline\nemulator-5554 device\n')
    def test_duplicate_online_target_refuses(self):
        with self.assertRaisesRegex(ValueError,'EXPECTED_EXACTLY_ONE_ONLINE_TARGET_DEVICE'):
            self.inspect('List of devices attached\nlocalhost:5555 device\nlocalhost:5555 device\n')
    def test_getstate_not_device_refuses(self):
        fake,_=fake_adb_factory('List of devices attached\nlocalhost:5555 device\n')
        def f(serial,args,**kwargs):
            if args==['get-state']:return 'offline'
            return fake(serial,args,**kwargs)
        with patch.object(p,'adb',side_effect=f),self.assertRaisesRegex(ValueError,'DEVICE_NOT_ONLINE'):
            p.inspect('localhost:5555',SOURCE)
    def test_every_real_adb_operation_explicit_serial(self):
        from unittest.mock import Mock
        proc=Mock(returncode=0,stdout=b'device\n',stderr=b'')
        with patch.object(p.subprocess,'run',return_value=proc) as mock:
            self.assertEqual(p.adb('localhost:5555',['get-state']),'device')
        self.assertEqual(mock.call_args.args[0],['adb','-s','localhost:5555','get-state'])
    def test_no_new_adb_mutation_allowlist(self):
        for command in (['install','/tmp/a.apk'],['shell','su','-c','id'],['shell','rm','-rf','/sdcard']):
            with self.assertRaises(ValueError):p.adb('localhost:5555',command)

if __name__=='__main__':unittest.main(verbosity=2)
