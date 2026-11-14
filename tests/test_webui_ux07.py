#!/usr/bin/env python3
"""UX07 WebUI and backend policy contract."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class Contract(unittest.TestCase):
 def test_ui_controls(self):
  s=(R/'webui/page/more/more.html').read_text()
  for x in ('https-cert-create','https-cert-export','https-response-enable','https-response-disable','https-response-test','https-certificate-settings','not</strong> uninstall','SHA-256'):
   self.assertIn(x,s)
  j=(R/'webui/utils/blocked_response.js').read_text()
  for x in ('setupHttpsControls(view, confirmAction)','call(`https ${action}`)','await confirmAction(title,description)','certificate_fingerprint_sha256','android.settings.SECURITY_SETTINGS'):
   self.assertIn(x,j)
  self.assertNotIn('eval(',j)
 def test_no_android_silent_certificate_install(self):
  s=(R/'module/https_response.sh').read_text()
  for x in ('cert-create)','cert-export)','cert-status)','enable)','disable)','start)','stop)','test)','android_trust=not_verified','certificate_%s'):
   self.assertIn(x,s)
  for x in ('am start -a android.credentials.INSTALL','settings put','certutil -addstore','/system/etc/security/cacerts'):
   self.assertNotIn(x,s)
  go=(R/'native/blocked_response_tls/main.go').read_text()
  for x in ('127.0.0.1','GetCertificate','SNI not in managed blocklist','bh-response','crypto/tls','no forwarding','os.O_EXCL'):
   self.assertIn(x,go.lower() if x=='no forwarding' else go)
 def test_https_default_off(self):
  s=(R/'module/https_response.sh').read_text()
  self.assertIn('if [ -f "$FLAG" ]; then',s)
  self.assertIn('MODE=off',s)
  self.assertNotIn('touch "$FLAG"',s)
 def test_hosted_build_all_abis_and_release(self):
  for path in ('.github/workflows/trackerguard-ci.yml','.github/workflows/release.yml'):
   s=(R/path).read_text()
   self.assertIn('blocked_response_tls',s)
   self.assertIn('GOOS=android',s)
   for abi in ('arm64-v8a','armeabi-v7a','x86_64'):self.assertIn(abi,s)
 def test_no_unconditional_pr_merge_or_auto_cert(self):
  s=(R/'module/response_mode.sh').read_text()
  self.assertIn('https_replacement=conditional_user_ca_trust_required',s)
  self.assertIn('https)',s)
  assert 'https.enabled' not in (R/'module/service.sh').read_text()
if __name__=='__main__':unittest.main(verbosity=2)
