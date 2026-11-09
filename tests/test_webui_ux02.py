#!/usr/bin/env python3
"""UX02 integration regressions: privileged WebUI editing and fail-closed pipeline."""
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]

class UX02Contract(unittest.TestCase):
    def test_all_legacy_mutations_use_root_side_validated_api(self):
        source=(ROOT/'webui/page/hosts/hosts.js').read_text()
        self.assertIn('hosts_secure_io.js',source)
        for call in ('secureAdd(', 'secureRemove(', 'secureToggle(', 'secureReplaceLine(',
                     'secureDeleteCustom(', 'secureRenameCustom(', 'secureSaveFile(',
                     'secureFileSize(', 'secureImportCustom('):
            self.assertIn(call,source,call)
        for unsafe in ('sed -i \'${command}', 'echo "${line}" >>', 'HostEditorEOF',
                       'cp -f "${filePath}"', 'rm -f "${basePath}/${fileName}"',
                       'const command = `s,${currentLine}'):
            self.assertNotIn(unsafe,source)

    def test_backend_arguments_are_encoded_not_quoted_shell_fragments(self):
        js=(ROOT/'webui/utils/hosts_secure_io.js').read_text()
        self.assertIn('new TextEncoder()',js)
        self.assertIn('btoa(binary)',js)
        self.assertIn('crypto.getRandomValues',js)
        self.assertIn('stage-commit',js)
        self.assertIn('stage-abort',js)
        self.assertNotIn('eval(',js)

    def test_hosts_pipeline_fails_before_status_update(self):
        script=(ROOT/'module/bindhosts.sh').read_text()
        self.assertIn('hosts_update_safe.sh',script)
        self.assertIn('adblock || {',script)
        self.assertIn('hosts_config_safe.sh',script)
        self.assertNotIn('--no-check-certificate',script)
        helper=(ROOT/'module/hosts_update_safe.sh').read_text()
        self.assertIn('hosts_target_safe.sh',helper)
        self.assertIn('BH_TARGET_BIND_FALLBACK',(ROOT/'module/hosts_target_safe.sh').read_text())
        self.assertNotIn('--no-check-certificate ',helper)

    def test_ux01_features_not_dropped(self):
        router=(ROOT/'webui/route.js').read_text()
        self.assertIn('catalogHtml',router)
        self.assertIn('appsHtml',router)
        version=(ROOT/'module/module.prop').read_text()
        self.assertIn('version=v2.1.5-tg.0.7',version)
        self.assertIn('versionCode=21607',version)

    def test_ci_runs_new_tests(self):
        workflow=(ROOT/'.github/workflows/bindhosts-ux-ci.yml').read_text()
        for name in ('test_hosts_config_safe.py','test_hosts_update_safe.py','test_webui_ux02.py',
                     'hosts_secure_io.js','hosts_update_safe.sh'):
            self.assertIn(name,workflow)

if __name__=='__main__': unittest.main(verbosity=2)
