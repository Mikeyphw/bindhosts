"""PH02 synthetic and hostile acceptance tests. Never accesses a real device or GitHub."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
import bh_app01_p07_ph02 as ph

SHA = 'a' * 40
APK_BYTES = b'actual-synthetic-hosted-apk' + bytes(range(128))
APK = __import__('hashlib').sha256(APK_BYTES).hexdigest()

def good_pr():
    return {'number': 19, 'state': 'open',
            'head': {'sha': SHA, 'ref': ph.BRANCH, 'repo': {'full_name': ph.REPO}},
            'base': {'ref': ph.BASE}}

def good_runs():
    a=[]
    for n,(path,name) in enumerate(ph.REQUIRED.items(),1):
        a.append({'id': 400+n, 'path': '.github/workflows/'+path, 'name': name,
                  'head_sha': SHA, 'event': 'pull_request', 'status': 'completed',
                  'conclusion': 'success', 'created_at':'2026-11-15T03:18:55Z'})
    return {'workflow_runs': a}

def hierarchy(*,cancel=True,clickable=True):
    second=('''<node text="Cancel" clickable="true" enabled="true" bounds="[10,20][90,80]" />'''
            if cancel and clickable else
            '''<node text="Cancel" clickable="false" enabled="true" bounds="[10,20][90,80]" />'''
            if cancel else '')
    return ('''<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'''
            '''<node text="Update Bindhosts rules?" clickable="false" />''' + second +
            '</hierarchy>').encode()

class GithubProof(unittest.TestCase):
    def test_valid_pr(self):
        ph.verify_pr(good_pr(), SHA)
    def test_reject_pr_metadata_drifts(self):
        variations=[('number',20),('state','closed')]
        for key,value in variations:
            p=good_pr();p[key]=value
            with self.subTest(key=key),self.assertRaises(ph.Refused):ph.verify_pr(p,SHA)
        for nested,key,value in [('head','sha','c'*40),('head','ref','other'),
                                 ('base','ref','main')]:
            p=good_pr();p[nested][key]=value
            with self.subTest(nested=nested),self.assertRaises(ph.Refused):ph.verify_pr(p,SHA)
        p=good_pr();p['head']['repo']['full_name']='other/repo'
        with self.assertRaises(ph.Refused):ph.verify_pr(p,SHA)
    def test_sha_strict(self):
        for sha in ('',SHA+'0','A'*40, '../'+SHA):
            with self.subTest(sha=sha[:10]),self.assertRaises(ph.Refused):ph.verify_pr(good_pr(),sha)
    def test_exact_four_green_workflows(self):
        r=ph.verify_runs(good_runs(),SHA)
        self.assertEqual(set(r),set(ph.REQUIRED))
        self.assertEqual(len(set(r.values())),4)
    def test_latest_failure_cannot_hide_earlier_success(self):
        p=good_runs()
        later={**p['workflow_runs'][1], 'id':9001, 'created_at':'2026-11-16T12:00:00Z', 'conclusion':'failure'}
        p['workflow_runs'].append(later)
        with self.assertRaisesRegex(ph.Refused,'NOT_GREEN'):ph.verify_runs(p,SHA)
    def test_reject_missing_or_wrong_workflow(self):
        for change in ('missing','wrong_sha','wrong_event','wrong_name','skipped','pending','wrong_path'):
            p=good_runs()
            if change=='missing':p['workflow_runs'].pop(2)
            if change=='wrong_sha':p['workflow_runs'][2]['head_sha']='c'*40
            if change=='wrong_event':p['workflow_runs'][2]['event']='workflow_dispatch'
            if change=='wrong_name':p['workflow_runs'][2]['name']='Similar title'
            if change=='skipped':p['workflow_runs'][2]['conclusion']='skipped'
            if change=='pending':p['workflow_runs'][2]['status']='in_progress'
            if change=='wrong_path':p['workflow_runs'][2]['path']='.github/workflows/fake.yml'
            with self.subTest(change=change),self.assertRaises(ph.Refused):ph.verify_runs(p,SHA)
    def test_artifact_must_be_exact_and_usable(self):
        a={'id':31,'name':'bh-app01-p07-api36-'+SHA,'expired':False,'size_in_bytes':4096}
        self.assertEqual(ph.select_artifact({'artifacts':[a]},SHA)[0],31)
        for k,v in [('id',0),('expired',True),('size_in_bytes',30),('name','other')]:
            p=dict(a);p[k]=v
            with self.subTest(key=k),self.assertRaises(ph.Refused):ph.select_artifact({'artifacts':[p]},SHA)
        with self.assertRaises(ph.Refused):ph.select_artifact({'artifacts':[a,a]},SHA)
    def test_endpoint_allowlist(self):
        for url in ('repos/other/repo/pulls/19','repos/Mikeyphw/bindhosts/issues/19',
                    'repos/Mikeyphw/bindhosts/actions/runs/../../secrets',
                    'repos/Mikeyphw/bindhosts/actions/runs?head_sha=A&per_page=100'):
            with self.subTest(url=url),self.assertRaises(ph.Refused):ph.gh_api(url)
    def test_live_provenance_mocked_positive_and_tampering(self):
        receipt={'schema':'bh-app01/p07/hosted/v1','apk_sha256':APK,'source_sha':SHA}
        def api(path):
            if path.endswith('/pulls/19'):return good_pr()
            if '/artifacts?' in path:return {'artifacts':[{'id':33,'name':'bh-app01-p07-api36-'+SHA,'expired':False,'size_in_bytes':2222}]}
            return good_runs()
        def exe(argv,**kwargs):
            if argv[:3]==['gh','run','download']:
                d=Path(argv[-1]); (d/'hosted-receipt.json').write_text(json.dumps(receipt))
                (d/'hosted-app-debug.apk').write_bytes(APK_BYTES)
            return SimpleNamespace(stdout=b'',returncode=0)
        with tempfile.TemporaryDirectory() as tmp,patch.object(ph,'verify_git_checkout'),\
                patch.object(ph,'gh_api',side_effect=api),patch.object(ph,'execute',side_effect=exe),\
                patch.object(ph,'hosted_qualify',return_value=receipt):
            result=ph.verified_hosted(tmp,SHA,Path(tmp)/'private')
            self.assertTrue(result['github_workflows_independently_verified'])
            self.assertFalse(result['physical_android16_qualified'])
            self.assertEqual(result['hosted_apk_sha256'],APK)
            self.assertEqual((Path(tmp)/'private/hosted-app-debug.apk').read_bytes(),APK_BYTES)
            self.assertEqual(json.loads((Path(tmp)/'private/github-proof.json').read_text())['source_sha'],SHA)
            self.assertEqual((Path(tmp)/'private/github-proof.json').stat().st_mode & 0o777,0o600)
        with tempfile.TemporaryDirectory() as tmp,patch.object(ph,'verify_git_checkout'),\
                patch.object(ph,'gh_api',side_effect=api),patch.object(ph,'execute',side_effect=exe),\
                patch.object(ph,'hosted_qualify',return_value={**receipt,'apk_sha256':'d'*64}):
            with self.assertRaisesRegex(ph.Refused,'DOES_NOT_MATCH'):
                ph.verified_hosted(tmp,SHA,Path(tmp)/'private')

class PhysicalUi(unittest.TestCase):
    def test_valid_cancel_only_coordinates(self):
        self.assertEqual(ph.qs_cancel_coordinates(hierarchy()),(50,50))
    def test_refuse_missing_disabled_or_ambiguous_cancel(self):
        for content in (hierarchy(cancel=False), hierarchy(clickable=False),
                        hierarchy()+b'x',b'<hierarchy><node text="Update"/></hierarchy>',
                        b'<'*3000):
            with self.subTest(n=len(content)),self.assertRaises(ph.Refused):ph.qs_cancel_coordinates(content)
    def test_nonce_and_serial_refusal(self):
        self.assertTrue(ph.temp_hierarchy_path('0'*16).startswith('/sdcard/Download/.bh-'))
        for nonce in ('../../../etc','2'*17,'123','x'*16):
            with self.assertRaises(ph.Refused):ph.temp_hierarchy_path(nonce)
        with self.assertRaises(ph.Refused):ph.adb('emulator-5554',['get-state'])
    def test_ack_precedes_adb_or_other_device_action(self):
        with patch.object(ph,'physical_inspect') as checked:
            with self.assertRaisesRegex(ph.Refused,'APPROVAL_REQUIRED'):
                ph.ui_smoke(ph.SERIAL,SHA,Path('none'),Path('out'),ack='')
            checked.assert_not_called()
    def test_preflight_failure_prevents_mutation(self):
        with patch.object(ph,'physical_inspect',return_value={'read_only_status':'INCONCLUSIVE'}) as probe,\
             patch.object(ph,'adb') as ad:
            with self.assertRaisesRegex(ph.Refused,'NOT_READY'):
                ph.ui_smoke(ph.SERIAL,SHA,Path('none'),Path('out'),ack=ph.ACK)
            ad.assert_not_called()
    def test_real_qs_cancel_mocked_success_without_root(self):
        calls=[]
        def a(serial,args,**kwargs):
            calls.append(tuple(args))
            if args[:3]==['shell','test','-e']:
                return SimpleNamespace(returncode=1,stdout=b'')
            if args[:3]==['shell','am','start']:
                return SimpleNamespace(returncode=0,stdout=b'Status: ok\n')
            if args[:3]==['shell','dumpsys','activity']:
                return SimpleNamespace(returncode=0,stdout=b'topResumedActivity=ActivityRecord{123 com.mikeyphw.bindhosts/.MainActivity t9}')
            return SimpleNamespace(returncode=0,stdout=b'')
        preflight={'read_only_status':'READY_FOR_APPROVAL_GATES',
                   'hosted_apk_matches_installed':True,'installed_apk_sha256':APK,'serial_hash':'0123456789abcdef'}
        read_n=iter([hierarchy(), b'<hierarchy/>'])
        with tempfile.TemporaryDirectory() as tmp,patch.object(ph,'physical_inspect',return_value=preflight),\
                patch.object(ph,'adb',side_effect=a),patch.object(ph,'ui_hierarchy',side_effect=lambda *arg:next(read_n)):
            r=ph.ui_smoke(ph.SERIAL,SHA,Path(tmp)/'hosted-receipt.json',tmp,ack=ph.ACK)
            self.assertTrue(r['cancel_button_tapped'])
            self.assertTrue(r['temporary_device_ui_file_cleanup_verified'])
            self.assertFalse(r['physical_android16_qualified'])
            self.assertTrue(any(x[:3]==('shell','input','tap') and x[3:]==('50','50') for x in calls))
            self.assertFalse(any('su' in x or 'install' in x or 'update' in x for x in calls))
            self.assertEqual(sum(x[:3]==('shell','rm','-f') for x in calls),1)
            self.assertTrue((Path(tmp)/'physical-ui-smoke.json').is_file())
    def test_failed_dialog_attempt_still_cleans_owned_temp(self):
        calls=[]
        def a(serial,args,**kwargs):
            calls.append(tuple(args))
            if args[:3]==['shell','test','-e']:return SimpleNamespace(returncode=1,stdout=b'')
            if args[:3]==['shell','am','start']:return SimpleNamespace(returncode=0,stdout=b'Status: ok\n')
            return SimpleNamespace(returncode=0,stdout=b'')
        p={'read_only_status':'READY_FOR_APPROVAL_GATES','hosted_apk_matches_installed':True}
        with tempfile.TemporaryDirectory() as tmp,patch.object(ph,'physical_inspect',return_value=p),\
                patch.object(ph,'adb',side_effect=a),patch.object(ph,'ui_hierarchy',side_effect=lambda *args:hierarchy(cancel=False)),\
                patch.object(ph.time,'sleep'):
            with self.assertRaisesRegex(ph.Refused,'NOT_OBSERVED'):
                ph.ui_smoke(ph.SERIAL,SHA,None,tmp,ack=ph.ACK)
            self.assertEqual(sum(x[:3]==('shell','rm','-f') for x in calls),1)
    def test_failed_cleanup_never_reports_pass(self):
        def a(serial,args,**kwargs):
            if args[:3]==['shell','test','-e']:return SimpleNamespace(returncode=1,stdout=b'')
            if args[:3]==['shell','am','start']:return SimpleNamespace(returncode=0,stdout=b'Status: ok\n')
            if args[:3]==['shell','rm','-f']:return SimpleNamespace(returncode=2,stdout=b'')
            return SimpleNamespace(returncode=0,stdout=b'')
        p={'read_only_status':'READY_FOR_APPROVAL_GATES','hosted_apk_matches_installed':True}
        with tempfile.TemporaryDirectory() as tmp,patch.object(ph,'physical_inspect',return_value=p),\
                patch.object(ph,'adb',side_effect=a),patch.object(ph,'ui_hierarchy',return_value=hierarchy()):
            # After a successful Cancel, cleanup must still refuse if device XML cannot be removed.
            with self.assertRaisesRegex(ph.Refused,'CLEANUP_FAILED'):
                ph.ui_smoke(ph.SERIAL,SHA,None,tmp,ack=ph.ACK)
    def test_required_ux_ci_retriggers_on_p07_acceptance_changes(self):
        workflow=(ROOT/'.github/workflows/bindhosts-ux-ci.yml').read_text()
        self.assertIn("'scripts/ci/bh_app01_p07_*'",workflow)
        self.assertIn("'tests/test_bh_app01_p07_*'",workflow)
        self.assertIn("'docs/BH_APP01_P07_*'",workflow)
        self.assertIn('pull_request:',workflow)

    def test_no_root_or_install_in_code(self):
        src=(ROOT/'scripts/ci/bh_app01_p07_ph02.py').read_text()
        self.assertNotIn("['shell', 'su'", src)
        self.assertNotIn("['install'", src)
        self.assertNotIn("['shell', 'pm', 'clear'",src)
        self.assertIn('physical_android16_qualified\': False',src)

if __name__=='__main__':unittest.main()
