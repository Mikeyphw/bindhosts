#!/usr/bin/env python3
"""UX05 source contracts for history page, safe export, hooks, CI and version."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def read(p):return (ROOT/p).read_text()

class UX05Contract(unittest.TestCase):
    def test_screen_reachable_from_more_without_sixth_tab(self):
        route=read('webui/route.js')
        more=read('webui/page/more/more.js')
        html=read('webui/page/more/more.html')
        self.assertIn('activityHtml',route)
        self.assertIn('activityModule',route)
        self.assertIn("name === 'activity' ? 'more' : name",route)
        self.assertIn("router.navigate('activity')",more)
        self.assertIn('id="ux05-activity-open"',html)
        self.assertIn('@import "./page/activity/activity.css";',read('webui/index.css'))
    def test_ui_does_not_execute_dynamic_commands_or_insert_html(self):
        ui=read('webui/page/activity/activity.js')
        self.assertIn('ux05_diagnostics.sh',ui)
        self.assertIn('textContent',ui)
        self.assertIn('confirmExport',ui)
        self.assertIn('showPrompt',ui)
        self.assertNotIn('innerHTML',ui)
        self.assertNotIn('eval(',ui)
        self.assertIn('^[A-Z0-9_]{1,48}$',ui)
        self.assertIn('No recorded events match this filter.',ui)
        html=read('webui/page/activity/activity.html')
        for field in ('ux05-event-list','ux05-result-filter','ux05-export-confirm','ux05-refresh'):
            self.assertIn(field,html)
    def test_hosts_source_update_and_legacy_operations_recorded(self):
        code=read('module/bindhosts.sh')
        for event in ('HOSTS_UPDATE_FAILED','HOSTS_UPDATE_OK','HOSTS_RESET_FAILED',
                      'HOSTS_RESET_OK','HOSTS_TOGGLE_FAILED','HOSTS_TOGGLE_OK',
                      'HOSTS_ALLOWLIST_FAILED','HOSTS_ALLOWLIST_OK','TG_ACTION_FAILED',
                      'TG_ACTION_OK','RESPONSE_SET_FAILED','RESPONSE_SET_OK'):
            self.assertIn(event,code)
        self.assertIn('exit "$_ux05_rc"',code)
        self.assertIn('ux05_diagnostics.sh',code)
    def test_journaled_writer_records_recovery_and_mount_mode(self):
        code=read('module/hosts_target_safe.sh')
        for key in ('RECOVERY_APPLIED','RECOVERY_WRITE_FAILED','RECOVERY_ALREADY_DONE',
                    'HOSTS_INPLACE_COMMIT','HOSTS_ATOMIC_COMMIT'):
            self.assertIn(key,code)
        self.assertIn('ux05_receipt',code)
        self.assertIn('BH_TARGET_COMMIT_PASS',code)
        self.assertIn('response start fail RESPONSE_START_FAILED',read('module/service.sh'))
    def test_backend_is_root_only_redacted_bounded_and_readonly(self):
        code=read('module/ux05_diagnostics.sh')
        for item in ('root required','receipt codes must be uppercase identifiers',
                     'tail -n 400','[ "$n" -le 100 ]','redacted','sources.txt',
                     'whitelist.txt'):
            if item=='whitelist.txt':self.assertNotIn(item,code)
            else:self.assertIn(item,code)
        self.assertNotIn('cat "$STATE/sources.txt" >>',code)
        self.assertIn('BH_UX05_EXPORT_PATH=',code)
    def test_release_ci_and_unchanged_trackerguard_defaults(self):
        for path in ('.github/workflows/bindhosts-ux-ci.yml',
                     '.github/workflows/trackerguard-ci.yml',
                     '.github/workflows/release.yml'):
            self.assertIn('test_ux05_diagnostics.py',read(path))
            self.assertIn('test_ux05_contract.py',read(path))
        self.assertIn('versionCode=21611',read('module/module.prop'))
        self.assertIn('v2.1.5-tg.0.11',read('update.json'))
        self.assertNotIn('monitor enable',read('module/ux05_diagnostics.sh'))

if __name__=='__main__':unittest.main(verbosity=2)
