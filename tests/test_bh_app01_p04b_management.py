"""P04B registry and fail-closed native management source invariants."""
from pathlib import Path
import json,os,subprocess,tempfile,unittest,base64
ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'module/companion_manage_v3.sh'
ANDROID=ROOT/'android/companion/app/src/main/java/com/mikeyphw/bindhosts'
class ManagementContracts(unittest.TestCase):
    def test_backend_finite_interface(self):
        s=MODULE.read_text()
        assert 'case "$VERB"' in s and 'config-read|config-list|config-write|catalog|tracker|packages' in s
        for x in ('source_catalog_batch_ux09.sh','hosts_config_safe.sh','bindhosts.sh','BH_APP01_V3_REFUSED'):
            self.assertIn(x,s)
        self.assertNotIn('eval "$ARGS"',s);self.assertNotIn('sh -c "$ARGS"',s)
        self.assertIn('rooted fixture refused',s)
    def test_explicit_native_bridge(self):
        activity=(ANDROID/'MainActivity.java').read_text()
        runner=(ANDROID/'RootRunner.java').read_text()
        self.assertIn('request.length() != 3',activity)
        self.assertIn('RootRunner.isManagementOperation(op)',activity)
        self.assertIn('RootRunner.validManagementArgument(argument)',activity)
        self.assertNotIn('addJavascriptInterface',activity)
        self.assertIn('Base64.encodeToString',runner)
        self.assertIn('companion_manage_v3.sh',runner)
        self.assertNotIn('new ProcessBuilder("su", "-c", argument)',runner)
        self.assertNotIn('android.permission.INTERNET',(ROOT/'android/companion/app/src/main/AndroidManifest.xml').read_text())
    def test_ci_and_schema(self):
        schema=json.loads((ROOT/'contracts/bh-app01-v3.json').read_text())
        self.assertEqual(schema['api_version'],3)
        self.assertFalse(schema['arbitrary_shell_supported'])
        ci=(ROOT/'.github/workflows/bh-app01-foundation.yml').read_text()
        self.assertIn('test_bh_app01_p04b_runtime.mjs',ci)
        self.assertIn('companion_manage_v3.sh',ci)
        self.assertIn(':app:lintDebug',ci)
    def test_lint_fix_folded(self):
        tile=(ANDROID/'UpdateTileService.java').read_text()
        self.assertIn('@SuppressLint("StartActivityAndCollapseDeprecated")',tile)
        self.assertIn('launchLegacy(intent);',tile)
        self.assertIn('startActivityAndCollapse(pending);',tile)

@unittest.skipIf(os.geteuid()==0, 'run synthetic module fixture as nonroot')
class V3Backend(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='bh-v3-fixture-');self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.mod=root/'mod';self.mod.mkdir();self.state=root/'state';self.state.mkdir()
        (self.state/'sources.txt').write_text('https://sample.org/hosts.txt\n')
        (self.mod/'hosts_config_safe.sh').write_text('#!/bin/sh\necho "BH_CONFIG_COMMIT_PASS: sources.txt"\n')
        (self.mod/'source_catalog.sh').write_text('#!/bin/sh\necho "adaway|off"\n')
        (self.mod/'source_catalog_batch_ux09.sh').write_text('#!/bin/sh\ncase "$1" in batch) echo "BH_UX09_BATCH_APPLIED";; *) echo BH_UX09_APPLIED=PENDING;; esac\n')
        (self.mod/'bindhosts.sh').write_text('#!/bin/sh\ncase "$3" in status) echo \'{"schema":2,"enrolled":[],"excluded":[]}\';; *) echo "TRACKER_TEST_PASS";; esac\n')
        self.env={**os.environ,'BH_APP01_V3_TEST_MODE':'1','BH_APP01_V3_TEST_MODDIR':str(self.mod),'BH_APP01_V3_TEST_STATE':str(self.state)}
    def call(self,op,args):
        payload=base64.b64encode(args.encode()).decode()
        return subprocess.run(['sh',str(MODULE),op,payload],capture_output=True,text=True,env=self.env,timeout=10)
    def test_finite_read_and_catalog(self):
        for op,arg,expected in [('config-read','sources','sample.org'),('catalog','status','adaway|off'),('catalog','batch|adaway','BH_UX09_BATCH_APPLIED'),('tracker','status','schema'),('config-write','add|sources|eA==','BH_CONFIG_COMMIT_PASS')]:
            p=self.call(op,arg);self.assertEqual(p.returncode,0,(op,p.stderr))
            reply=json.loads(p.stdout);self.assertEqual(reply['api'],3);self.assertEqual(reply['action'],op)
            self.assertIn(expected,base64.b64decode(reply['encoded']).decode())
    def test_denials(self):
        for op,arg in [('execute','id'),('catalog','batch|id;reboot'),('catalog','batch|a/../../root'),('tracker','monitor|reset'),('config-read','../../etc/passwd'),('config-write','delete-custom|sources'),('packages','root'),('config-write','add|sources|'),('tracker','enroll|bad;touch')]:
            p=self.call(op,arg);self.assertNotEqual(p.returncode,0,(op,arg,p.stdout))
            self.assertNotIn('"api":3',p.stdout)
    def test_symlink_state_refusal(self):
        original=self.state;renamed=original.parent/'realstate';original.rename(renamed);original.symlink_to(renamed,target_is_directory=True)
        p=self.call('catalog','status');self.assertNotEqual(p.returncode,0)

if __name__=='__main__':unittest.main()
