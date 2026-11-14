"""UX03/UX04 UI and backend static contract (no device modification)."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class UX0304(unittest.TestCase):
 def test_ux03_manual_vs_auto_and_optin(self):
  apps=(ROOT/'webui/page/apps/apps.js').read_text()
  for s in ('json rules','source===\'auto\'','apps-scan-once','apps-refresh','monitor once','Preview the package first'):
   self.assertIn(s,apps)
  self.assertNotIn('eval(',apps)
 def test_response_http_only_disabled_by_default(self):
  shell=(ROOT/'module/response_mode.sh').read_text()
  server=(ROOT/'native/blocked_response.c').read_text()
  self.assertIn('MODE=off',shell)
  self.assertIn('127.0.0.1',server)
  self.assertNotIn('INADDR_ANY',server)
  self.assertIn('image/gif',server)
  self.assertIn('image/svg+xml',server)
  self.assertIn('https_replacement=conditional_user_ca_trust_required',shell)
 def test_ux04_controls_restricted_and_confirmed(self):
  js=(ROOT/'webui/utils/blocked_response.js').read_text()
  html=(ROOT/'webui/page/more/more.html').read_text()
  self.assertIn("new Set(['off','transparent','logo'])",js)
  self.assertIn('await confirmAction(',js)
  self.assertIn('id="response-mode"',html)
  self.assertNotIn('window.confirm(',js)
 def test_kernel_su_responder_has_explicit_executable_permissions(self):
  script=(ROOT/'module/customize.sh').read_text()
  self.assertIn('UX04_RESPONDER_PERMISSIONS_BEGIN',script)
  self.assertIn('set_perm "$tg_response" 0 0 0755',script)
  self.assertIn('[ -x "$tg_response" ]',script)
  self.assertLess(script.index('# TG_SCANNER_PERMISSIONS_END'),script.index('# UX04_RESPONDER_PERMISSIONS_BEGIN'))
  self.assertIn('# UX04_RESPONDER_PERMISSIONS_END',script)
 def test_boot_recovery_and_no_default_server(self):
  sh=(ROOT/'module/service.sh').read_text()
  self.assertIn('hosts_target_safe.sh" recover',sh)
  self.assertIn('response.mode',sh)
  self.assertIn('response_mode.sh',sh)
 def test_uninstall_retains_failed_recovery_journal(self):
  script=(ROOT/'module/uninstall.sh').read_text()
  self.assertIn('BH_UNINSTALL_JOURNAL_PRESERVED',script)
  self.assertIn('_bh_discard_state',script)
 def test_inspection_does_not_create_a_lock(self):
  writer=(ROOT/'module/hosts_target_safe.sh').read_text()
  self.assertLess(writer.index('if [ "$CMD" = inspect ]'),writer.index('\nlock\n'))
 def test_no_unconditional_live_probe(self):
  script=(ROOT/'tests/hosts-mount-acceptance.sh').read_text()
  self.assertIn('--accept-risk',script)
  self.assertIn('BH_ACCEPT_READ_ONLY_PASS',script)
  self.assertIn('_accept_mode=readonly',script)
  self.assertIn('BH_ACCEPT_LIVE_ROUNDTRIP_PASS',script)
 def test_update_uses_managed_sections_and_journal(self):
  s=(ROOT/'module/hosts_update_safe.sh').read_text()
  self.assertIn('bindhosts-block-start',s)
  self.assertIn('bindhosts-custom-start',s)
  self.assertIn('hosts_target_safe.sh" commit',s)
 def test_reset_no_unjournaled_active_write(self):
  s=(ROOT/'module/bindhosts.sh').read_text()
  self.assertIn('hosts_reset_safe.sh" reset',s)
  self.assertIn('hosts_reset_safe.sh" toggle',s)
if __name__=='__main__':unittest.main(verbosity=2)
