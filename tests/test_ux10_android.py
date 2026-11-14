#!/usr/bin/env python3
"""UX10 Android-only source/behavior regression; no network, phone, or Gradle."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class UX10Android(unittest.TestCase):
    def read(self,path):return (ROOT/path).read_text(encoding='utf8')
    def test_four_bottom_tabs_and_nested_sources(self):
        s=self.read('webui/index.html')
        self.assertEqual(len(re.findall(r'class="bottom-bar-item"',s)),4)
        self.assertNotIn('id="catalog" page="catalog"',s)
        for name in ['home','hosts','apps','more']:
            self.assertIn(f'page="{name}"',s)
        self.assertIn("name === 'catalog' ? 'hosts'",self.read('webui/route.js'))
        self.assertIn("router.currentView === 'catalog'",self.read('webui/index.js'))
        self.assertIn('id="ux10-manage-presets"',self.read('webui/page/hosts/hosts.html'))
        self.assertIn('id="ux10-sources-back"',self.read('webui/page/catalog/catalog.html'))
        self.assertIn("router.navigate('hosts')",self.read('webui/page/catalog/catalog.js'))
    def test_dialog_immediate_close_and_android_back(self):
        s=self.read('webui/utils/hosts_operations_ux09.js')
        self.assertIn('layer.hidden = true; // immediate dismissal',s)
        self.assertIn('layer.hidden = false;',s)
        self.assertIn('layer.hidden = true; // immediate dismissal',s)
        ix=self.read('webui/index.js')
        self.assertIn("document.getElementById('ux09-operation-confirm-no')?.click()",ix)
        self.assertIn("document.getElementById('ux09-operation-close')?.click()",ix)
        self.assertNotIn("dialog.addEventListener('closed'",s)
        h=self.read('webui/index.html')
        self.assertIn('id="ux09-operation-confirm" class="ux10-confirm-backdrop" hidden',h)
        self.assertNotIn('<md-dialog id="ux09-operation-confirm">',h)
        self.assertIn('role="dialog" aria-modal="true"',h)
        self.assertIn('id="ux09-operation-confirm-no"',h)
    def test_real_source_progress_and_privacy(self):
        sh=self.read('module/hosts_update_safe.sh')
        self.assertIn('ux10_source_label()',sh)
        self.assertIn('ux09_event DOWNLOADING "Source $source_count $(ux10_source_label',sh)
        self.assertIn('ux09_event PARSED "Source $source_count $(ux10_source_label',sh)
        self.assertIn('$_ux10_bytes bytes $_ux10_lines entries parsed',sh)
        self.assertIn('ux09_event FAILED "Source $source_count',sh)
        self.assertIn('_host=${_host%%',sh)
        self.assertNotIn('$_line" >> "$BH_UX09_EVENTS"',sh)
        u=self.read('webui/utils/hosts_operations_ux09.js')
        self.assertIn("backend('events')",u)
        self.assertIn('ux10-operation-source',u)
        self.assertIn('lastLineCount',u)
        self.assertIn('ux09-operation-summary',u)
    def test_presets_exit_guard_and_exclusive_tiers(self):
        catalog=self.read('webui/page/catalog/catalog.js')
        route=self.read('webui/route.js')
        self.assertIn('export function hasPendingSourceChanges()',catalog)
        self.assertIn('approveSourceExit()',catalog)
        self.assertIn('Discard unsaved presets?',catalog)
        self.assertIn('if(approved){selected=new Set(original);render();}',catalog)
        self.assertIn("'ux10-energized'",catalog)
        self.assertIn('None — disable all Energized tiers',catalog)
        self.assertIn("if(dirty()){showPrompt('Save or discard preset changes",catalog)
        self.assertIn('this.ux10ExitPending = true',route)
        self.assertIn('this.ux10LeaveApproved = true',route)
    def test_source_failure_observability_without_url_leakage(self):
        src=self.read('module/hosts_update_safe.sh')
        self.assertIn('download failed"',src)
        self.assertIn('invalid source syntax"',src)
        self.assertIn('contains no valid entries"',src)
        self.assertIn('ux10_source_label "$_line"',src)
        viewer=self.read('webui/utils/hosts_operations_ux09.js')
        self.assertIn("const attempted=rows.filter",viewer)
        self.assertIn("source.dataset.state=state",viewer)
        self.assertIn("'Source validated'",viewer)
        self.assertIn('lastSourceEvent',viewer)
    def test_android_touch_safe_areas(self):
        css=self.read('webui/utils/ux10_android.css')
        for token in ['var(--top-inset)','var(--bottom-inset)','min-height:48px','min-height:44px','max-width:520px']:
            self.assertIn(token,css)
        self.assertNotIn('min-width:1160px',css)
        self.assertIn('@media(max-width:390px)',css)
        self.assertIn('.ux09-op-header{flex-wrap:wrap;}',css)
    def test_dynamic_description_sources_and_claims(self):
        sh=self.read('module/dynamic_description_ux10.sh')
        for x in ['trackerguard/rules.tsv','app trackers blocked:', '(configured IFW rules)','module.prop','mktemp','! -L "$RULES"']:
            self.assertIn(x,sh)
        home=self.read('webui/page/home/home.js')
        self.assertIn('configured app tracker blocks (IFW rules)',home)
        self.assertIn("state.total_rules",home)
        self.assertIn('dynamic_description_ux10.sh',self.read('module/service.sh'))
        self.assertIn('dynamic_description_ux10.sh',self.read('module/trackerguard.sh'))
        self.assertIn('dynamic_description_ux10.sh',self.read('module/trackerguard_r2.sh'))
        self.assertIn('dynamic_description_ux10.sh',self.read('module/hosts_control_safe.sh'))
    def test_dynamic_description_real_shell_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            mod=Path(t)/'module';mod.mkdir();state=Path(t)/'state';rules=state/'trackerguard';rules.mkdir(parents=True)
            prop=mod/'module.prop';prop.write_text('id=bindhosts\nname=bindhosts\ndescription=status: active | blocked: 100\nversion=1\n')
            db=rules/'rules.tsv';db.write_text('com.example.app|receiver|com.example.app.Tracker\ncom.example.app|service|com.example.app.Telemetry\n')
            env=dict(os.environ,BH_UX10_TEST_MODE='1',BH_UX10_MODDIR=str(mod),BH_UX10_STATE=str(state))
            script=ROOT/'module/dynamic_description_ux10.sh'
            def go(ok=True):
                p=subprocess.run(['sh',str(script),'refresh'],text=True,capture_output=True,env=env,timeout=8)
                self.assertEqual(p.returncode==0,ok,(p.stdout,p.stderr));return p
            self.assertIn('count=2',go().stdout)
            self.assertIn('app trackers blocked: 2 (configured IFW rules)',prop.read_text())
            self.assertIn('UNCHANGED',go().stdout)
            db.write_text('com.example.app|receiver|com.example.app.Tracker\n')
            self.assertIn('count=1',go().stdout)
            self.assertEqual(prop.read_text().count('app trackers blocked:'),1)
            db.write_text('bad|unrecognized|secret\n')
            before=prop.read_bytes();go(ok=False);self.assertEqual(prop.read_bytes(),before)
            db.unlink();db.symlink_to(prop);go(ok=False);self.assertEqual(prop.read_bytes(),before)
    def test_source_pipeline_still_has_strict_commit(self):
        src=self.read('module/hosts_update_safe.sh')
        for value in ['hosts_target_safe.sh" commit','ux09_event DEDUPLICATING','ux09_event STATS','SKIPPED_DUPLICATE_URL']:
            self.assertIn(value,src)
    def test_two_hosted_workflows_test_ux10(self):
        for name in ('bindhosts-ux-ci.yml','trackerguard-ci.yml'):
            self.assertIn('python3 tests/test_ux10_android.py',self.read('.github/workflows/'+name))

if __name__=='__main__':unittest.main(verbosity=2)
