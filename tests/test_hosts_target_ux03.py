#!/usr/bin/env python3
"""UX03 journal, bind-mount fallback, reset and crash-recovery contracts."""
import os, pathlib, subprocess, tempfile, unittest
MOD=pathlib.Path(__file__).resolve().parents[1]/'module'
class TargetTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
  self.root=pathlib.Path(t.name)
  self.target=self.root/'hosts';self.target.write_text('127.0.0.1 localhost\n0.0.0.0 old.test\n')
  self.candidate=self.root/'candidate';self.candidate.write_text('127.0.0.1 localhost\n0.0.0.0 new.test\n')
  self.env=dict(os.environ,BH_HOSTS_TEST_MODE='1',BH_HOSTS_ROOT=str(self.root))
 def call(self,*args,env=None,ok=True):
  p=subprocess.run(['sh',str(MOD/'hosts_target_safe.sh'),*map(str,args)],env=env or self.env,text=True,capture_output=True,timeout=12)
  if ok:self.assertEqual(p.returncode,0,p.stderr+'\n'+p.stdout)
  return p
 def test_atomic_commit_and_clean_journal(self):
  p=self.call('commit',self.target,self.candidate)
  self.assertIn('BH_TARGET_ATOMIC_PASS',p.stdout)
  self.assertEqual(self.target.read_text(),self.candidate.read_text())
  self.assertFalse((self.root/'.hosts-target-journal').exists())
 def test_force_bind_mount_inplace_and_recovery_after_crash(self):
  env=dict(self.env,BH_HOSTS_FORCE_INPLACE='1')
  self.assertIn('BH_TARGET_INPLACE_VERIFIED_PASS',self.call('commit',self.target,self.candidate,env=env).stdout)
  self.candidate.write_text('127.0.0.1 localhost\n0.0.0.0 evennew.test\n')
  before=self.target.read_bytes()
  crashed=dict(env,BH_HOSTS_FAILPOINT='after-journal')
  self.assertNotEqual(self.call('commit',self.target,self.candidate,env=crashed,ok=False).returncode,0)
  self.assertEqual(self.target.read_bytes(),before)
  self.assertTrue((self.root/'.hosts-target-journal').exists())
  self.call('recover',self.target)
  self.assertFalse((self.root/'.hosts-target-journal').exists())
  self.assertEqual(self.target.read_bytes(),before)
 def test_partial_journal_is_never_used_to_overwrite_active_hosts(self):
  journal=self.root/'.hosts-target-journal'
  journal.mkdir()
  (journal/'previous').write_text('truncated')
  (journal/'target').write_text(str(self.target)+'\n')
  prior=self.target.read_bytes()
  self.assertNotEqual(self.call('recover',self.target,ok=False).returncode,0)
  self.assertEqual(self.target.read_bytes(),prior)
  self.assertTrue(journal.exists())
 def test_unfinished_journal_blocks_new_commit(self):
  fail=dict(self.env,BH_HOSTS_FAILPOINT='after-journal')
  self.call('commit',self.target,self.candidate,env=fail,ok=False)
  self.assertNotEqual(self.call('commit',self.target,self.candidate,ok=False).returncode,0)
  self.call('recover',self.target)
  self.call('commit',self.target,self.candidate)
 def test_symlink_target_refused(self):
  link=self.root/'link';link.symlink_to(self.target)
  self.assertNotEqual(self.call('commit',link,self.candidate,ok=False).returncode,0)
  self.assertIn('old.test',self.target.read_text())
 def test_reset_and_toggle_restore(self):
  (self.root/'custom.txt').write_text('1.2.3.4 keep.test\ndisabled|1.2.3.4 skip.test\n')
  writer=MOD/'hosts_reset_safe.sh'
  def run(*args):
   p=subprocess.run(['sh',str(writer),*map(str,args)],env=self.env,text=True,capture_output=True,timeout=12)
   self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
   return p.stdout
  run('toggle',self.target,self.root,MOD)
  self.assertTrue((self.root/'bindhosts_backup').exists())
  self.assertIn('keep.test',self.target.read_text())
  self.assertNotIn('old.test',self.target.read_text())
  self.assertNotIn('skip.test',self.target.read_text())
  run('toggle',self.target,self.root,MOD)
  self.assertIn('old.test',self.target.read_text())
  self.assertFalse((self.root/'bindhosts_backup').exists())
  run('reset',self.target,self.root,MOD)
  self.assertNotIn('old.test',self.target.read_text())
 def test_partial_inplace_write_is_recovered_on_next_boot(self):
  prior=self.target.read_bytes()
  env=dict(self.env,BH_HOSTS_FORCE_INPLACE='1',BH_HOSTS_FAILPOINT='partial-inplace')
  p=self.call('commit',self.target,self.candidate,env=env,ok=False)
  self.assertNotEqual(p.returncode,0)
  self.assertNotEqual(self.target.read_bytes(),prior)
  self.assertTrue((self.root/'.hosts-target-journal').exists())
  self.call('recover',self.target)
  self.assertEqual(self.target.read_bytes(),prior)
 def test_inspect_is_strictly_read_only(self):
  before=self.target.read_bytes()
  files=sorted(x.name for x in self.root.iterdir())
  out=self.call('inspect',self.target)
  self.assertIn('journal=clean',out.stdout)
  self.assertEqual(self.target.read_bytes(),before)
  self.assertEqual(sorted(x.name for x in self.root.iterdir()), files)
  self.assertFalse((self.root/'.hosts-target-lock').exists())
 def test_read_only_device_acceptance_does_not_write_state(self):
  module=self.root/'fake-installed-module'
  (module/'system/etc').mkdir(parents=True)
  target=module/'system/etc/hosts'
  target.write_bytes(self.target.read_bytes())
  (module/'mode.sh').write_text('operating_mode=0\n')
  (module/'hosts_target_safe.sh').write_bytes((MOD/'hosts_target_safe.sh').read_bytes())
  fakebin=self.root/'fakebin';fakebin.mkdir()
  fakeid=fakebin/'id'
  fakeid.write_text('#!/bin/sh\nif [ "$1" = -u ]; then echo 0; else /usr/bin/id "$@"; fi\n')
  fakeid.chmod(0o755)
  env=dict(self.env,BH_ACCEPT_MODDIR=str(module),BH_ACCEPT_STATE=str(self.root),
           PATH=str(fakebin)+':'+self.env.get('PATH','/usr/bin:/bin'))
  runner=MOD/'hosts_mount_acceptance.sh'
  snapshot=sorted(x.name for x in self.root.iterdir())
  old=target.read_bytes()
  ok=subprocess.run(['sh',str(runner),'--read-only'],env=env,
                    capture_output=True,text=True,timeout=8)
  self.assertEqual(ok.returncode,0,ok.stdout+'\n'+ok.stderr)
  self.assertIn('BH_ACCEPT_READ_ONLY_PASS',ok.stdout)
  self.assertEqual(target.read_bytes(),old)
  self.assertEqual(sorted(x.name for x in self.root.iterdir()),snapshot)
  bad=subprocess.run(['sh',str(runner),'--probe-live'],env=env,
                     capture_output=True,text=True,timeout=8)
  self.assertNotEqual(bad.returncode,0)
  self.assertEqual(target.read_bytes(),old)
  self.assertFalse((self.root/'.hosts-target-lock').exists())
 def test_rename_not_powerloss_atomic_on_forced_bind(self):
  p=self.call('commit',self.target,self.candidate,env=dict(self.env,BH_HOSTS_FORCE_INPLACE='1'))
  self.assertIn('BH_TARGET_INPLACE_VERIFIED_PASS',p.stdout)
if __name__=='__main__':unittest.main(verbosity=2)
