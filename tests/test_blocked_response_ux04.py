#!/usr/bin/env python3
"""UX04 native server and opt-in response-mode tests; only 127.0.0.1 is used."""
import os, pathlib, shutil, socket, subprocess, tempfile, time, unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
class ResponseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not shutil.which('cc'):raise unittest.SkipTest('host C compiler required in CI')
  cls._tmp=tempfile.TemporaryDirectory();cls.bin=pathlib.Path(cls._tmp.name)/'blocked_response'
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2',str(BASE/'native/blocked_response.c'),'-o',str(cls.bin)],check=True)
 @classmethod
 def tearDownClass(cls):cls._tmp.cleanup()
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
  self.root=pathlib.Path(t.name)
  self.host=self.root/'hosts'
  self.host.write_text('127.0.0.1 localhost\n::1 localhost\n# bindhosts-custom-start\n127.0.0.1 manual.test\n# bindhosts-custom-end\n# bindhosts-block-start\n0.0.0.0 ads.test\n0.0.0.0 pixels.test\n# bindhosts-block-end\n# bindhosts v21607\n')
  sock=socket.socket();sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1];sock.close()
  self.env=dict(os.environ,BH_RESPONSE_BINARY=str(self.bin),BH_RESPONSE_PORT=str(self.port),BH_RESPONSE_TEST_MODE='1',BH_RESPONSE_MODDIR=str(BASE/'module'),BH_HOSTS_TEST_MODE='1',BH_HOSTS_ROOT=str(self.root))
  self.addCleanup(self.cleanup)
 def cmd(self,*args,ok=True):
  p=subprocess.run(['sh',str(BASE/'module/response_mode.sh'),str(self.root),str(self.host),*args],env=self.env,text=True,capture_output=True,timeout=25)
  if ok:self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
  return p
 def cleanup(self):
  pidfile=self.root/'response.pid'
  if pidfile.exists():
   try:
    pid=int(pidfile.read_text().strip());os.kill(pid,15)
   except (ValueError,ProcessLookupError,PermissionError):pass
 def test_server_loopback_and_correct_content_types(self):
  for mode,mime in [('transparent','image/gif'),('logo','image/svg+xml')]:
   p=subprocess.Popen([str(self.bin),'--port',str(self.port),'--mode',mode],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    for _ in range(25):
     if subprocess.run([str(self.bin),'--port',str(self.port),'--probe','--mode',mode],capture_output=True).returncode==0:break
     time.sleep(.04)
    else:self.fail('responder did not start')
    with socket.create_connection(('127.0.0.1',self.port),timeout=2) as sock:
     sock.sendall(b'GET /test HTTP/1.1\r\nHost: ads.test\r\n\r\n')
     data=b''
     while True:
      part=sock.recv(4096)
      if not part:break
      data+=part
    self.assertIn(mime.encode(),data)
    self.assertIn(b'X-Bindhosts-Response: UX04',data)
    self.assertIn(b'X-Bindhosts-Mode: '+mode.encode(),data)
    self.assertEqual(data.count(b'HTTP/1.1 200 OK'),1)
   finally:p.terminate();p.wait(timeout=3)
 def test_mode_optin_preserves_custom_and_rolls_back(self):
  self.assertIn('mode=off',self.cmd('status').stdout)
  before=self.host.read_text()
  self.cmd('set','transparent')
  after=self.host.read_text()
  self.assertIn('127.0.0.1 ads.test # bh-response',after)
  self.assertIn('127.0.0.1 manual.test',after)
  self.assertIn('server=running',self.cmd('status').stdout)
  self.cmd('set','off')
  self.assertEqual(self.host.read_text(),before)
  self.assertEqual((self.root/'response.mode').read_text().strip(),'off')
 def test_mode_refuses_unmarked_hosts(self):
  self.host.write_text('127.0.0.1 localhost\n0.0.0.0 ads.test\n')
  before=self.host.read_bytes()
  self.assertNotEqual(self.cmd('set','transparent',ok=False).returncode,0)
  self.assertEqual(self.host.read_bytes(),before)
  self.assertIn('mode=off',self.cmd('status').stdout)
 def test_switch_between_image_modes_and_self_heal_server(self):
  original=self.host.read_bytes()
  self.cmd('set','transparent')
  self.assertIn('server=running',self.cmd('status').stdout)
  self.cmd('set','logo')
  self.assertIn('mode=logo',self.cmd('status').stdout)
  self.assertIn('server=running',self.cmd('status').stdout)
  # A repeated explicit selection repairs a stopped responder.
  pidfile=self.root/'response.pid'
  pid=int(pidfile.read_text().strip())
  os.kill(pid,15)
  time.sleep(.07)
  result=self.cmd('set','logo')
  self.assertIn('BH_RESPONSE_SERVER_REPAIRED',result.stdout)
  self.assertIn('server=running',self.cmd('status').stdout)
  self.cmd('set','off')
  self.assertEqual(self.host.read_bytes(),original)
 def test_boot_start_failure_reverts_to_standard_blocking(self):
  self.cmd('set','transparent')
  # Simulate a missing CI-built executable during the next boot.
  env=dict(self.env,BH_RESPONSE_BINARY=str(self.root/'missing-binary'))
  p=subprocess.run(['sh',str(BASE/'module/response_mode.sh'),str(self.root),str(self.host),'start'],env=env,text=True,capture_output=True,timeout=25)
  self.assertNotEqual(p.returncode,0)
  self.assertIn('BH_RESPONSE_FAIL_CLOSED_PASS',p.stderr)
  self.assertIn('0.0.0.0 ads.test',self.host.read_text())
  self.assertEqual((self.root/'response.mode').read_text().strip(),'off')
 def test_update_integration_responder_active_and_offline_failure(self):
  # In the fully integrated UX02->UX04 pipeline, only the managed block
  # section gets loopback mapping, and no responder means no active rewrite.
  fixture=self.root/'fixture.txt'
  fixture.write_text('0.0.0.0 ads.test\n0.0.0.0 pixels.test\n')
  fetcher=self.root/'fetch-fixture.sh'
  fetcher.write_text('#!/bin/sh\ncp "$BH_TEST_SOURCE_FILE" "$2"\n')
  fetcher.chmod(0o755)
  for fname,content in {
      'sources.txt':'https://fixture.example/ads.txt\n',
      'sources_whitelist.txt':'', 'whitelist.txt':'',
      'blacklist.txt':'', 'custom.txt':'127.0.0.1 manual.test\n'
  }.items():
    (self.root/fname).write_text(content)
  update_env=dict(self.env,BH_UPDATE_MODDIR=str(BASE/'module'),BH_UPDATE_TEST_MODE='1',
                  BH_UPDATE_TEST_FETCH=str(fetcher),BH_TEST_SOURCE_FILE=str(fixture))
  def update(ok=True):
    p=subprocess.run(['sh',str(BASE/'module/hosts_update_safe.sh'),str(self.root),
                      str(self.host),str(self.root),'21607'],env=update_env,
                      text=True,capture_output=True,timeout=25)
    if ok:self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
    return p
  self.cmd('set','transparent')
  update()
  self.assertIn('127.0.0.1 ads.test # bh-response',self.host.read_text())
  self.assertIn('127.0.0.1 manual.test',self.host.read_text())
  self.cmd('stop')
  saved=self.host.read_bytes()
  self.assertNotEqual(update(ok=False).returncode,0)
  self.assertEqual(self.host.read_bytes(),saved)
  self.cmd('set','off')
  update()
  self.assertIn('0.0.0.0 ads.test',self.host.read_text())
  self.assertNotIn('ads.test # bh-response',self.host.read_text())
 def test_can_disable_after_explicit_reset_removed_managed_sections(self):
  self.cmd('set','transparent')
  self.host.write_text('127.0.0.1 localhost\n::1 localhost\n127.0.0.1 manual.test\n')
  self.cmd('set','off')
  self.assertEqual((self.root/'response.mode').read_text().strip(),'off')
  self.assertIn('server=not_running',self.cmd('status').stdout)
 def test_unrelated_loopback_listener_is_never_killed(self):
  blocker=socket.socket()
  blocker.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  blocker.bind(('127.0.0.1',self.port))
  blocker.listen(1)
  try:
    before=self.host.read_bytes()
    attempt=self.cmd('set','logo',ok=False)
    self.assertNotEqual(attempt.returncode,0)
    self.assertEqual(self.host.read_bytes(),before)
    self.assertFalse((self.root/'response.mode').exists())
    self.assertGreater(blocker.fileno(),0)
  finally:blocker.close()
 def test_no_automatic_mode_on_install(self):
  self.assertFalse((self.root/'response.mode').exists())
  self.assertEqual(self.cmd('status').stdout.splitlines()[0],'mode=off')
if __name__=='__main__':unittest.main(verbosity=2)
