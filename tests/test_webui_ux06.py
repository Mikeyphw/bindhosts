#!/usr/bin/env python3
"""UX06 integration checks: no shell interpolation of untrusted backup contents."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(path):return (ROOT/path).read_text()
class Contract(unittest.TestCase):
    def test_legacy_unsafe_restore_removed(self):
        s=read('webui/page/more/more.js')
        self.assertNotIn('RESTORE_EOF',s)
        self.assertNotIn('JSON_EOF',s)
        self.assertNotIn('exportConfig()',s)
        self.assertNotIn('restoreConfig()',s)
        self.assertIn('mountBackupControls(section)',s)
    def test_filenames_and_backend_verbs_fixed(self):
        s=read('webui/utils/backup_safe.js')
        self.assertIn('filenameRE',s)
        self.assertIn("new Set(['status','health','list','create','verify','preview','restore','export','import','imports'])",s)
        self.assertIn("root.querySelector('#ux06-import-select').value",s)
        self.assertNotIn('FileSelector',s)
        self.assertNotIn('eval(',s)
        self.assertNotIn('innerHTML',s)
        self.assertIn('await confirmAction(',s)
    def test_recovery_before_boot_tasks(self):
        s=read('module/service.sh')
        self.assertLess(s.index('config_backup_safe.sh" recover'),s.index('apply_description &'))
    def test_restore_not_an_automatic_update(self):
        s=read('module/config_backup_safe.sh')
        self.assertNotIn('--force-update',s)
        self.assertIn('.ux06-restore-pending',s)
    def test_ui_ids_exist(self):
        s=read('webui/page/more/more.html')
        for name in ['ux06-create','ux06-verify','ux06-restore','ux06-export','ux06-import','ux06-select','ux06-health','ux06-confirm-dialog','ux06-import-select']:
            self.assertIn('id="'+name+'"',s)
    def test_tests_in_all_workflows(self):
        for p in ['.github/workflows/bindhosts-ux-ci.yml','.github/workflows/trackerguard-ci.yml','.github/workflows/release.yml']:
            text=read(p)
            self.assertIn('test_backup_safe_ux06.py',text)
            self.assertIn('test_webui_ux06.py',text)
if __name__=='__main__':unittest.main(verbosity=2)
