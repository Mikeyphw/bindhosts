"""P04B P03: exact More operations, sensitive receipts, paged Activity and UX06 reads."""
from pathlib import Path
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
MORE=ROOT/'module/companion_more_v5.sh'
PAGE=ROOT/'module/companion_read_v4.sh'
ANDROID=ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts'

class MoreSource(unittest.TestCase):
    def test_contract_is_narrow(self):
        c=json.loads((ROOT/'contracts/bh-app01-v5.json').read_text())
        self.assertEqual(c['api_version'],5)
        self.assertFalse(c['arbitrary_shell_supported'])
        self.assertFalse(c['auto_certificate_installation'])
        self.assertIn('rooted fixture refused',MORE.read_text())
        self.assertIn('read-page', (ANDROID/'MainActivity.java').read_text())
        self.assertIn('RootRunner.more(op, argument)',(ANDROID/'MainActivity.java').read_text())
        self.assertIn('companion_more_v5.sh',(ANDROID/'RootRunner.java').read_text())
        self.assertNotIn('eval "$ACTION"',MORE.read_text())
        self.assertNotIn('sh -c "$ACTION"',MORE.read_text())
        self.assertNotIn('addJavascriptInterface',(ANDROID/'MainActivity.java').read_text())
        self.assertNotIn('android.permission.INTERNET',(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text())
    def test_ci_and_lint_kept(self):
        ci=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        for x in ['companion_more_v5.sh','bh-app01-v5.json','test_bh_app01_p04b_more.mjs',':app:lintDebug']:
            self.assertIn(x,ci)
        self.assertNotIn('abortOnError = false',ci)

@unittest.skipIf(os.geteuid()==0, 'rooted synthetic fixtures must refuse UID 0')
class MoreFixtures(unittest.TestCase):
    ID='bh-20261114T181234-AbC123'
    ARCHIVE='bindhosts-backup-bh-20261114T181234-AbC123.tar'
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='bh-app01-more-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.mod=self.root/'mod';self.mod.mkdir()
        self.state=self.root/'state';self.state.mkdir()
        (self.mod/'config_backup_safe.sh').write_text('''#!/bin/sh
case "$1" in
  status) echo 'restore_journal=clean'; echo 'backup_schema=1' ;;
  health) echo 'BH_BACKUP_HEALTH|sources|enabled=1|disabled=0|duplicates=0' ;;
  list) echo 'bh-20261114T181234-AbC123|2048' ;;
  imports) echo 'bindhosts-backup-bh-20261114T181234-AbC123.tar' ;;
  verify) echo "BH_BACKUP_VERIFY_PASS: $2" ;;
  preview) echo "BH_BACKUP_PREVIEW|sources|current_bytes=20|backup_bytes=21|changed=1" ;;
  create) echo 'BH_BACKUP_CREATED: bh-20261114T181234-AbC123' ;;
  restore) echo "BH_BACKUP_RESTORE_PASS: $2" ;;
  export) echo 'BH_BACKUP_EXPORTED: /storage/emulated/0/Download/bindhosts-backup-bh-20261114T181234-AbC123.tar' ;;
  import) echo 'BH_BACKUP_IMPORTED: bh-20261114T181234-AbC123' ;;
  *) exit 88 ;;
esac
''')
        (self.mod/'ux05_diagnostics.sh').write_text('''#!/bin/sh
case "$1" in
  status) echo '{"schema":1,"receipts":500,"failures":2}' ;;
  history) printf '[{"ts":100,"area":"hosts","action":"update","result":"ok","code":"HOSTS_UPDATE_OK"}]\\n' ;;
  export) echo BH_UX05_EXPORT_PATH=/storage/emulated/0/Download/bindhosts_diagnostics_20261114T181234.json ;;
  *) exit 88 ;;
esac
''')
        (self.mod/'bindhosts.sh').write_text('''#!/bin/sh
[ "$1" = --response ] || exit 88
case "$2" in
  status) echo mode=off; echo https_mode=off; echo android_trust=not_verified ;;
  set) echo "BH_RESPONSE_MODE_PASS: $3" ;;
  https) case "$3" in
    cert-create) echo BH_HTTPS_CERT_INSTALL_IS_MANUAL ;;
    cert-export) echo BH_HTTPS_CA_INSTALL_REQUIRES_ANDROID_USER_ACTION ;;
    enable) echo BH_HTTPS_ENABLED_ANDROID_TRUST_UNVERIFIED ;;
    disable) echo BH_HTTPS_DISABLED_CA_REMAINS_INSTALLED_IF_USER_ADDED_IT ;;
    test) echo BH_HTTPS_LOCAL_TLS_PASS_ANDROID_TRUST_UNVERIFIED ;;
    *) exit 88;; esac ;;
  *) exit 88 ;;
esac
''')
        self.env={**os.environ,'BH_APP01_V4_TEST_MODE':'1','BH_APP01_V5_TEST_MODE':'1',
           'BH_APP01_V4_TEST_MODDIR':str(self.mod),'BH_APP01_V4_TEST_STATE':str(self.state),
           'BH_APP01_V5_TEST_MODDIR':str(self.mod),'BH_APP01_V5_TEST_STATE':str(self.state)}
    def more(self,op,arg):
        p=base64.b64encode(arg.encode()).decode()
        return subprocess.run(['sh',str(MORE),op,p],capture_output=True,text=True,env=self.env,timeout=8)
    def page(self,op,arg,offset=0,digest='none'):
        p=base64.b64encode(f'{op}|{arg}|{offset}|{digest}'.encode()).decode()
        return subprocess.run(['sh',str(PAGE),p],capture_output=True,text=True,env=self.env,timeout=8)
    def test_backup_receipts_are_exact(self):
        for arg,fragment in [
            ('create','BH_BACKUP_CREATED'),('restore~'+self.ID,'BH_BACKUP_RESTORE_PASS'),
            ('export~'+self.ID,'BH_BACKUP_EXPORTED'),('import~'+self.ARCHIVE,'BH_BACKUP_IMPORTED')]:
            p=self.more('backup',arg);self.assertEqual(p.returncode,0,(arg,p.stderr))
            body=json.loads(p.stdout);self.assertEqual((body['api'],body['action']),(5,'backup'))
            self.assertIn(fragment,base64.b64decode(body['encoded']).decode())
        self.assertFalse(list(self.state.glob('.bh-app01-v5.*')))
    def test_diagnostics_export_and_http_tls_actions(self):
        p=self.more('diagnostics','export');self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('BH_UX05_EXPORT_PATH=',base64.b64decode(json.loads(p.stdout)['encoded']).decode())
        for arg in ['set~off','set~transparent','set~logo','https~cert-create','https~cert-export','https~enable','https~disable','https~test']:
            p=self.more('response',arg);self.assertEqual(p.returncode,0,(arg,p.stderr))
    def test_paged_backup_diagnostics_and_status(self):
        cases=[('backup','status','restore_journal'),('backup','list',self.ID),('backup','health','sources'),
          ('backup','imports',self.ARCHIVE),('backup','verify~'+self.ID,'BH_BACKUP_VERIFY_PASS'),
          ('backup','preview~'+self.ID,'BH_BACKUP_PREVIEW'),('diagnostics','status','"schema"'),
          ('diagnostics','history~100','HOSTS_UPDATE_OK'),('response','status','android_trust=not_verified')]
        for op,arg,fragment in cases:
            p=self.page(op,arg);self.assertEqual(p.returncode,0,(op,arg,p.stderr))
            b=json.loads(p.stdout);content=base64.b64decode(b['encoded'])
            self.assertIn(fragment,content.decode())
            self.assertEqual(b['sha256'],hashlib.sha256(content).hexdigest())
    def test_bad_inputs_refuse_before_backend(self):
        for op,arg in [('backup','restore~../../../data'),('backup','restore~fake'),
                       ('backup','import~foo.tar'),('backup','verify~'+self.ID),
                       ('diagnostics','history~101'),('diagnostics','status'),
                       ('response','set~unknown'),('response','https~install'),
                       ('response','https~enable;reboot'),('root','export')]:
            p=self.more(op,arg);self.assertNotEqual(p.returncode,0,(op,arg))
            self.assertNotIn('"api":5',p.stdout)
        for op,arg in [('backup','restore~'+self.ID),('backup','preview~fake'),
                       ('diagnostics','export'),('diagnostics','history~0'),('response','https~enable')]:
            p=self.page(op,arg);self.assertNotEqual(p.returncode,0,(op,arg))
            self.assertNotIn('"api":4',p.stdout)
    def test_base64_encoded_binary_control_refused(self):
        for script,kind,bad in [(MORE,'backup',b'create\x00'),
                                 (MORE,'backup',b'create\n'),
                                 (MORE,'backup',b'create\r'),
                                 (PAGE,None,b'backup|status|0|none\x00')]:
            token=base64.b64encode(bad).decode()
            argv=['sh',str(script),kind,token] if kind else ['sh',str(script),token]
            p=subprocess.run(argv,capture_output=True,text=True,env=self.env,timeout=8)
            self.assertEqual(p.returncode,2,(script.name,bad,p.stdout,p.stderr))
            self.assertIn('control characters',p.stderr)

    def test_missing_backend_symlink_and_bad_receipt(self):
        orig=self.mod/'config_backup_safe.sh';orig.rename(self.mod/'real.sh')
        orig.symlink_to(self.mod/'real.sh');self.assertEqual(self.more('backup','create').returncode,2)
        orig.unlink();orig.write_text('#!/bin/sh\necho success\n')
        p=self.more('backup','create');self.assertEqual(p.returncode,2)
        self.assertIn('missing create receipt',p.stderr)
        self.mod.rename(self.root/'real-mod');self.mod.symlink_to(self.root/'real-mod',target_is_directory=True)
        self.assertEqual(self.more('diagnostics','export').returncode,2)

if __name__=='__main__':unittest.main()
