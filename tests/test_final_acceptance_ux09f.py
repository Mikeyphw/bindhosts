#!/usr/bin/env python3
"""UX09F offline contracts: artifact provenance, refusal gates, no automatic writes."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

path=Path(__file__).with_name('final_acceptance_ux09f.py')
spec=importlib.util.spec_from_file_location('accept',path)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

class FakeDevice(a.Device):
    def __init__(self):
        super().__init__('localhost:5555')
        self.calls=[]
    def adb(self,*args,**kwargs):
        self.calls.append(args)
        table={
            ('get-state',):'device\n',
            ('shell','getprop','ro.build.version.sdk'):'36\n',
            ('shell','getprop','ro.product.cpu.abi'):'arm64-v8a\n',
            ('shell','getenforce'):'Enforcing\n',
        }
        if args in table:return type('P',(),{'stdout':table[args],'returncode':0})()
        raise AssertionError(args)
    def root(self,s,check=True,timeout=90):
        self.calls.append(('root',s))
        if s=='id -u':return '0\n'
        if 'sha256sum' in s:return 'a'*64+'  /data/adb/modules/bindhosts/hosts_operation_ux09.sh\n'
        if s=='/system/bin/pm list packages':return 'package:one\npackage:two\n'
        if s.endswith(' --hosts-control status'):return 'BH_HOSTS_STATE=ACTIVE\n'
        raise AssertionError(s)

class Contract(unittest.TestCase):
    def test_exact_run_pins(self):
        self.assertEqual(a.MODULE_RUN,43546943742)
        self.assertEqual(a.LAB_RUN,42670772403)
        self.assertEqual(len(a.PARENT),40)
        self.assertEqual(set(a.ARTIFACTS),{'module','v1','v2'})

    def test_script_blob_pins_present(self):
        self.assertGreaterEqual(len(a.MODULE_BLOBS),12)
        self.assertEqual(set(a.RUNNERS),{'ui','r3','mount'})
        for b in list(a.MODULE_BLOBS.values())+[x[1] for x in a.RUNNERS.values()]:
            self.assertRegex(b,r'^[a-f0-9]{40}$')

    def test_serial_safety(self):
        a.Device('localhost:5555')
        for x in ('','x;whoami','127.0.0.1 | id','$()','../../../etc','a'*100):
            with self.subTest(x=x),self.assertRaises(a.Refused):a.Device(x)

    def test_readonly_probe_has_no_device_write(self):
        d=FakeDevice()
        with mock.patch.object(a,'blob',return_value=b'script contents'),\
             mock.patch.object(d,'fingerprint',return_value=a.sha(b'script contents')):
            report=d.probe(Path('/tmp'))
        self.assertTrue(report['module_verified'])
        self.assertEqual(report['pm_packages'],2)
        s=str(d.calls)
        for token in ('ksud','module install','adb install',' rm ','--hosts-control update','--run'):
            self.assertNotIn(token,s)

    def test_pm_help_refused(self):
        d=FakeDevice()
        original=d.root
        def bad(s,check=True,timeout=90):
            if s=='/system/bin/pm list packages':return 'usage: package manager\n'
            return original(s,check=check,timeout=timeout)
        with mock.patch.object(a,'blob',return_value=b'script contents'),\
             mock.patch.object(d,'fingerprint',return_value=a.sha(b'script contents')),\
             mock.patch.object(d,'root',side_effect=bad):
            with self.assertRaisesRegex(a.Refused,'PackageManager inventory invalid'):d.probe(Path('/tmp'))

    def test_hf04_helper_not_optional(self):
        self.assertIn('trackerguard_r2_pm_query.sh',a.MODULE_BLOBS)
        self.assertIn('hosts_operation_ux09.sh',a.MODULE_BLOBS)
        self.assertIn('source_catalog_batch_ux09.sh',a.MODULE_BLOBS)

    def test_missing_artifact_receipt_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(a.Refused):a.prepared(Path('/tmp'),Path(d))

    def test_artifact_hash_drift_refused_before_install(self):
        with tempfile.TemporaryDirectory() as t:
            ws=Path(t);(ws/'module.zip').write_bytes(b'tampered')
            (ws/'artifacts.json').write_text(json.dumps({
                'schema':'BH_UX09F_PREPARE_V1','source_sha':a.PARENT,
                'module_run':a.MODULE_RUN,'lab_run':a.LAB_RUN,
                'files':{'module':{'file':'module.zip','sha256':'0'*64}}}))
            with self.assertRaisesRegex(a.Refused,'artifact integrity changed'):
                a.prepared(Path('/tmp'),ws)

    def test_archive_refuses_multiple_members_and_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            z=Path(d)/'test.zip';dest=Path(d)/'dest.apk'
            with zipfile.ZipFile(z,'w') as f:
                f.writestr('../evil.apk',b'abc'*400)
            with self.assertRaises(a.Refused):a.safe_extract_archive(z,dest,'.apk')
            with zipfile.ZipFile(z,'w') as f:
                f.writestr('a.apk',b'abc'*400)
                f.writestr('b.apk',b'abc'*400)
            with self.assertRaises(a.Refused):a.safe_extract_archive(z,dest,'.apk')

    def test_not_qualified_with_missing_stages(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(a.report(Path(d)))
            x=json.loads((Path(d)/'final-summary.json').read_text())
            self.assertFalse(x['complete'])
            self.assertEqual(len(x['stages']),9)

    def test_positive_summary_requires_all_nine_source_bound_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)
            stages=('mount-probe','mount-live','r3-probe','r3-live','ui','manual-matrix',
                    'rules-live','backup-live','response-live')
            for name in stages:
                a.receipt(ws,name,{'result':'PASS','serial':'localhost:5555'})
            self.assertFalse(a.report(ws),'manual/UI witnesses must be required')
            (ws/'manual.json').write_text(json.dumps({
                'results':{key:'PASS' for key,_ in a.MANUAL_CHECKS}}))
            required={'sources-topology','rules-buttons','response-settings','blocking-toggle-first',
                      'blocking-toggle-restore','toggle-readback-restored','source-selection-saved',
                      'source-selection-restored','source-byte-restore-pass','update-terminal','update-backend-receipt'}
            (ws/'ux09e-1794626950.json').write_text(json.dumps({
                'source_sha':'f32076e87164499ad693f9365c30a622e0fcc832',
                'outcome':'MANUAL_UI_AND_BACKEND_UPDATE_PASS_TOGGLE_VERIFIED_SOURCE_RESTORED',
                'manual_checks':sorted(required)}))
            self.assertTrue(a.report(ws))
            a.receipt(ws,'r3-live',{'result':'REFUSED','serial':'localhost:5555'})
            self.assertFalse(a.report(ws))

    def test_stale_or_forged_receipt_never_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)
            (ws/'r3-live.json').write_text(json.dumps({'result':'PASS'}))
            self.assertFalse(a.report(ws))
            obj=json.loads((ws/'final-summary.json').read_text())
            self.assertEqual(obj['stages']['r3-live']['result'],'INVALID_RECEIPT')

    def test_rule_live_requires_written_approval(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}), \
             mock.patch('builtins.input',return_value='no'), \
             mock.patch.object(d,'rule_fingerprints') as hashes:
            with self.assertRaises(a.Refused):a.rules_live(Path('/tmp'),Path(t),d)
            hashes.assert_not_called()

    def test_backup_live_requires_written_approval(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}), \
             mock.patch('builtins.input',return_value='no'), \
             mock.patch.object(d,'rule_fingerprints') as hashes:
            with self.assertRaises(a.Refused):a.backup_live(Path('/tmp'),Path(t),d)
            hashes.assert_not_called()

    def test_response_live_requires_written_approval(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}), \
             mock.patch.object(d,'response_mode',return_value='off'), \
             mock.patch.object(d,'root',return_value='BH_HOSTS_STATE=ACTIVE'), \
             mock.patch('builtins.input',return_value='no'):
            with self.assertRaises(a.Refused):a.response_live(Path('/tmp'),Path(t),d)

    def test_runner_read_only_argument_stream(self):
        d=FakeDevice()
        result=type('P',(),{'stdout':b'BH_ACCEPT_READ_ONLY_PASS','returncode':0})()
        with mock.patch.object(d,'adb',return_value=result) as ad:
            self.assertEqual(d.root_script_stdin(b'echo ok\n',['--read-only']),
                             'BH_ACCEPT_READ_ONLY_PASS')
            kw=ad.call_args.kwargs
            self.assertIn(b'set -- --read-only\n',kw['stdin'])
            self.assertIn(b'echo ok\n',kw['stdin'])
            self.assertEqual(ad.call_args.args[:4],('shell','-T','su','-c'))

    def test_mount_live_requires_typed_ack(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t, \
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}),\
             mock.patch.object(a,'blob',return_value=b'echo live'),\
             mock.patch('builtins.input',return_value='no'),\
             mock.patch.object(d,'root_script_stdin') as sh:
            with self.assertRaisesRegex(a.Refused,'mount live authorization missing'):
                a.mount(Path('/tmp'),Path(t),d,live=True)
            sh.assert_not_called()

    def test_r3_live_requires_typed_ack(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t,\
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}),\
             mock.patch.object(a,'pin_runner',return_value=Path(t)/'runner.py'),\
             mock.patch.object(a,'prepared',return_value={'files':{'v1':{'file':'a.apk'},'v2':{'file':'b.apk'}}}),\
             mock.patch('builtins.input',return_value='no'),\
             mock.patch.object(a,'run') as cmd:
            with self.assertRaisesRegex(a.Refused,'R3 live authorization missing'):
                a.r3(Path('/tmp'),Path(t),d,live=True)
            cmd.assert_not_called()

    def test_receipts_from_different_devices_cannot_be_combined(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)
            for i,stage in enumerate(('mount-probe','mount-live','r3-probe','r3-live','ui','manual-matrix',
                                      'rules-live','backup-live','response-live')):
                a.receipt(ws,stage,{'result':'PASS','serial':'localhost:5555' if i<4 else 'localhost:5554'})
            self.assertFalse(a.report(ws))

    def test_arm64_expected_module_scripts_are_allowlisted(self):
        self.assertTrue({'bindhosts.sh','trackerguard.sh','hosts_update_safe.sh',
                         'data/r3-lab-signatures.tsv','trackerguard_r2_pm_query.sh'} <= set(a.MODULE_BLOBS))

    def test_mismatched_android_target_refuses_before_live_actions(self):
        for wrong in ({'module_verified':True,'api':'35','abi':'arm64-v8a','selinux':'Enforcing'},
                      {'module_verified':True,'api':'36','abi':'x86_64','selinux':'Enforcing'},
                      {'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Permissive'},
                      {'module_verified':False,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}):
            with self.subTest(wrong=wrong),self.assertRaises(a.Refused):a.require_target(wrong)

    def test_ui_acceptance_explicit_ack_and_flags(self):
        d=FakeDevice()
        with tempfile.TemporaryDirectory() as t,\
             mock.patch.object(d,'probe',return_value={'module_verified':True,'api':'36','abi':'arm64-v8a','selinux':'Enforcing'}),\
             mock.patch.object(a,'pin_runner',return_value=Path(t)/'runner.py'),\
             mock.patch.object(a,'run',return_value=type('P',(),{'returncode':0})()) as cmd:
            a.ui(Path('/tmp'),Path(t),d,all_tests=True)
            argv=cmd.call_args.args[0]
            for marker in ('--test-toggle','--test-source','--test-update','I_AUTHORIZE_UX09_MANUAL_UI_ACCEPTANCE'):
                self.assertIn(marker,argv)

    def test_no_auto_reboot_merge_selinux_or_ca(self):
        s=path.read_text()
        for bad in ('svc power reboot','git merge','setenforce 0','/system/etc/security/cacerts','am start -a android.credentials.INSTALL'):
            self.assertNotIn(bad,s)

    def test_manual_incomplete_never_full_pass(self):
        with tempfile.TemporaryDirectory() as d, mock.patch('builtins.input',side_effect=['s']*len(a.MANUAL_CHECKS)):
            with self.assertRaisesRegex(a.Refused,'manual UI matrix has'):
                a.manual(Path(d),FakeDevice())
            dct=json.loads((Path(d)/'manual-matrix.json').read_text())
            self.assertEqual(dct['result'],'INCOMPLETE')

    def test_inspect_r3_lab_stays_test_only(self):
        self.assertEqual(a.LAB_PKG,'com.mikeyphw.trackerguard.ifwlab')
        self.assertNotIn('com.android.',a.LAB_PKG)
        self.assertIn('run_device_acceptance.py',a.RUNNERS['r3'][0])

if __name__=='__main__':unittest.main(verbosity=2)
