"""P07 PH03 module+tested APK provenance/security tests; no Android writes."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import hashlib

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'scripts/ci/bh_app01_p07_bundle_apk.py'
spec=importlib.util.spec_from_file_location('bh_p07_module_bundle',SRC)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
SHA='a'*40
APK=b'PK'+b'hosted synthetic apk bytes'*100
DIG=hashlib.sha256(APK).hexdigest()


def pull(sha=SHA):
    return {'number':19,'state':'open','head':{'sha':sha,'ref':mod.BRANCH,'repo':{'full_name':mod.REPO}},
            'base':{'ref':'feature/bindhosts-ux10-mobile-webui-20261114'}}


def runs(source=SHA):
    return {'workflow_runs':[
        {'id':500+i,'run_attempt':1,'status':'completed','conclusion':'success','head_sha':source,
         'name':name,'event':'pull_request','path':'.github/workflows/'+fn}
        for i,(fn,name) in enumerate(mod.WORKFLOWS.items())]}


def makezip(path, *, sha=SHA, digest=DIG, data=APK):
    with zipfile.ZipFile(path,'w') as z:
        for name, content in {
            'module.prop':b'id=bindhosts\nversionCode=21612\n',
            'customize.sh':b'#!/bin/sh\n',
            'bindhosts-app.sh':b'#!/bin/sh\n',
            'META-INF/com/google/android/update-binary':b'#!/bin/sh\n',
            'companion/bindhosts-companion.apk':data,
            'companion/bindhosts-companion.sha256':(digest+'\n').encode(),
            'companion/source-commit.txt':(sha+'\n').encode(),
            'companion/hosted-acceptance.json':json.dumps({'source_sha':sha,'apk_sha256':digest,
                'package':mod.APP,'physical_android16_qualified':False,'personal_release_qualified':False,'release_qualified':False}).encode(),
        }.items():z.writestr(name,content)
        for abi in mod.ABIS:
            for tool in mod.TOOLS:z.writestr(f'bin/{abi}/{tool}',b'\x7fELFsynthetic binary')


class P07Module(unittest.TestCase):
    def test_four_exact_head_pull_request_workflows(self):
        self.assertEqual(len(mod.select_completed_runs(pull(),runs(),SHA)),4)
        self.assertIsNone(mod.select_completed_runs(pull(),runs('b'*40),SHA))
        r=runs();r['workflow_runs'].pop()
        self.assertIsNone(mod.select_completed_runs(pull(),r,SHA))
        r=runs();r['workflow_runs'][2]['status']='in_progress'
        self.assertIsNone(mod.select_completed_runs(pull(),r,SHA))
        r=runs();r['workflow_runs'][2]['conclusion']='failure'
        with self.assertRaisesRegex(ValueError,'WORKFLOW_FAILED'):
            mod.select_completed_runs(pull(),r,SHA)

    def test_wrong_pr_state_and_ref_refuse(self):
        for changes in [{'state':'closed'}, {'number':99}]:
            p=pull();p.update(changes)
            with self.assertRaises(ValueError):mod.select_completed_runs(p,runs(),SHA)
        p=pull();p['head']['sha']='b'*40
        with self.assertRaisesRegex(ValueError,'PR_HEAD_OR_BASE_DRIFT'):
            mod.select_completed_runs(p,runs(),SHA)
        p=pull();p['head']['repo']['full_name']='attacker/repo'
        with self.assertRaisesRegex(ValueError,'PR_HEAD_OR_BASE_DRIFT'):
            mod.select_completed_runs(p,runs(),SHA)

    def test_wrong_events_and_merge_commit_are_not_qualified(self):
        r=runs();r['workflow_runs'][0]['event']='push'
        self.assertIsNone(mod.select_completed_runs(pull(),r,SHA))
        r=runs();r['workflow_runs'][0]['path']='.github/workflows/foreign.yml'
        self.assertIsNone(mod.select_completed_runs(pull(),r,SHA))

    def test_latest_failure_overrides_previous_success(self):
        r=runs();bad=dict(r['workflow_runs'][0],id=999,conclusion='failure')
        r['workflow_runs'].append(bad)
        with self.assertRaisesRegex(ValueError,'WORKFLOW_FAILED'):
            mod.select_completed_runs(pull(),r,SHA)

    def test_valid_module_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'module.zip';makezip(p)
            mod.verify_bundle(p,SHA)

    def test_sha_and_source_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'module.zip'
            makezip(p,digest='b'*64)
            with self.assertRaisesRegex(ValueError,'APK_SHA_MISMATCH'):
                mod.verify_bundle(p,SHA)
            makezip(p,sha='b'*40)
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_DRIFT'):
                mod.verify_bundle(p,SHA)

    def test_missing_native_binary_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'module.zip';makezip(p)
            with zipfile.ZipFile(p) as z:data={n:z.read(n) for n in z.namelist()}
            data.pop('bin/arm64-v8a/axmlscan')
            with zipfile.ZipFile(p,'w') as z:
                for n,b in data.items():z.writestr(n,b)
            with self.assertRaisesRegex(ValueError,'NATIVE_BINARY_MISSING'):
                mod.verify_bundle(p,SHA)

    def test_duplicate_member_and_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'module.zip';makezip(p)
            with zipfile.ZipFile(p,'a') as z:
                z.writestr('../escape.txt',b'bad')
            with self.assertRaisesRegex(ValueError,'MALFORMED_MODULE_ARCHIVE'):
                mod.verify_bundle(p,SHA)

    def test_hosted_evidence_rejects_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((ValueError,OSError)):
                mod.verified_hosted(Path(tmp),SHA)

    def test_offline_installer_has_no_legacy_network_or_uninstall(self):
        s=(ROOT/'module/bindhosts-app.sh').read_text()
        custom=(ROOT/'module/customize.sh').read_text()
        for x in ('com.mikeyphw.bindhosts','sha256sum','pm install -r','EMBEDDED_APK_SHA_MISMATCH','INSTALLED_APK_SHA_MISMATCH'):
            self.assertIn(x,s)
        for x in ('curl ','wget ','releases/latest','pm uninstall ','pm clear ','su -c'):
            self.assertNotIn(x,s)
        self.assertIn('sh "$MODPATH/bindhosts-app.sh"',custom)
        self.assertNotIn('KEY_VOLUMEUP',custom)
        self.assertNotIn('itejo443',custom)
        self.assertIn('versionCode=21612',(ROOT/'module/module.prop').read_text())

    def test_workflow_is_sha_scoped_not_gradle_or_physical(self):
        s=(ROOT/'.github/workflows/bh-app01-module-with-apk.yml').read_text()
        for marker in ('pull_request:', 'github.event.pull_request.head.sha', 'gh run download',
                       'bh_app01_p07_bundle_apk.py gate', 'bh_app01_p07_bundle_apk.py package',
                       'SOURCE_SHA', 'actions/upload-artifact@v4', 'ndk;27.2.12479018',
                       'blocked_response_tls', 'bh-app01-module-companion-'):
            self.assertIn(marker,s)
        for bad in ('continue-on-error: true','--force','adb install','pm install -r \"','gradle -p android/companion'):
            self.assertNotIn(bad,s)
        self.assertNotIn('getevent', (ROOT/'module/customize.sh').read_text())


if __name__=='__main__':unittest.main()
