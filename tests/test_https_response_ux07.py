#!/usr/bin/env python3
"""UX07 local TLS, certificate, managed-SNI, fail-closed and HTTP integration tests."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
GO=ROOT/'native/blocked_response_tls/main.go'

class TLSIntegration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not shutil.which('go'):raise unittest.SkipTest('Go compiler required')
  cls.tmp=tempfile.TemporaryDirectory(prefix='bh-ux07-bin-',dir=os.environ.get('TMPDIR'))
  cls.bin=Path(cls.tmp.name)/'blocked_response_tls'
  cls.http=Path(cls.tmp.name)/'blocked_response'
  subprocess.run(['go','build','-trimpath','-o',str(cls.bin),str(GO)],cwd=ROOT,check=True,timeout=130)
  # UX04's native C responder has separate real-socket tests. A minimal
  # probe/daemon shim isolates UX07 control-path behavior from those tests.
  cls.http.write_text('''#!/bin/sh
MODE=transparent; PROBE=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) MODE=$2; shift 2 ;;
    --port) shift 2 ;;
    --probe) PROBE=1; shift ;;
    *) exit 2 ;;
  esac
done
if [ "$PROBE" = 1 ]; then
  [ -f "$BH_TEST_HTTP_MARKER" ] && [ "$(cat "$BH_TEST_HTTP_MARKER")" = "$MODE" ]
  exit $?
fi
printf '%s\n' "$MODE" > "$BH_TEST_HTTP_MARKER"
trap 'rm -f "$BH_TEST_HTTP_MARKER"; exit 0' INT TERM
while :; do sleep 1; done
''')
  cls.http.chmod(0o755)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
  self.tmpdir=tempfile.TemporaryDirectory(prefix='bh-ux07-',dir=os.environ.get('TMPDIR'))
  self.addCleanup(self.tmpdir.cleanup)
  self.path=Path(self.tmpdir.name)
  self.state=self.path/'state';self.state.mkdir();self.state.chmod(0o700)
  self.hosts=self.path/'hosts'
  self.hosts.write_text('127.0.0.1 localhost\n# bindhosts-custom-start\n127.0.0.1 manual.test\n# bindhosts-custom-end\n# bindhosts-block-start\n0.0.0.0 ads.test\n0.0.0.0 pixels.test\n# bindhosts-block-end\n')
  sock=socket.socket();sock.bind(('127.0.0.1',0));self.http_port=sock.getsockname()[1];sock.close()
  sock=socket.socket();sock.bind(('127.0.0.1',0));self.tls_port=sock.getsockname()[1];sock.close()
  self.env=dict(os.environ,BH_RESPONSE_BINARY=str(self.http),BH_TEST_HTTP_MARKER=str(self.path/'http.marker'),BH_RESPONSE_PORT=str(self.http_port),BH_RESPONSE_TEST_MODE='1',BH_RESPONSE_MODDIR=str(ROOT/'module'),BH_HOSTS_TEST_MODE='1',BH_HOSTS_ROOT=str(self.state),BH_HTTPS_TEST_MODE='1',BH_HTTPS_MODDIR=str(ROOT/'module'),BH_HTTPS_BINARY=str(self.bin),BH_HTTPS_PORT=str(self.tls_port),BH_HTTPS_DOWNLOAD=str(self.path))
  self.addCleanup(self.cleanup)
 def cleanup(self):
  for name in ('https.pid','response.pid'):
   p=self.state/name
   if p.exists():
    try:os.kill(int(p.read_text().strip()),15)
    except (ValueError,ProcessLookupError,PermissionError):pass
 def runux(self,*args,ok=True):
  p=subprocess.run(['sh',str(ROOT/'module/response_mode.sh'),str(self.state),str(self.hosts),*args],env=self.env,text=True,capture_output=True,timeout=27)
  if ok:self.assertEqual(p.returncode,0,f'{args!r}\n{p.stdout}\n{p.stderr}')
  return p
 def runbin(self,*args,ok=True):
  p=subprocess.run([str(self.bin),*args],capture_output=True,text=True,timeout=7)
  if ok:self.assertEqual(p.returncode,0,p.stderr)
  return p
 def conn(self,name):
  c=ssl.create_default_context(cafile=str(self.state/'.ux07-tls/ca.crt'))
  sock=socket.create_connection(('127.0.0.1',self.tls_port),timeout=2)
  return c.wrap_socket(sock,server_hostname=name)
 def test_ca_generated_on_device_private_and_no_overwrite(self):
  self.runux('https','cert-create')
  pair=self.state/'.ux07-tls'
  for f in ('ca.crt','ca.key'):
   self.assertEqual(stat.S_IMODE((pair/f).stat().st_mode),0o600)
  self.assertEqual(stat.S_IMODE(pair.stat().st_mode),0o700)
  before=(pair/'ca.key').read_bytes()
  self.assertNotEqual(self.runux('https','cert-create',ok=False).returncode,0)
  self.assertEqual(before,(pair/'ca.key').read_bytes())
  result=self.runux('https','cert-export')
  self.assertIn('BH_HTTPS_CERT_EXPORTED:',result.stdout)
  exported=list(self.path.glob('bindhosts-local-ca-*.crt'))
  self.assertEqual(len(exported),1)
  self.assertEqual(exported[0].read_bytes(),(pair/'ca.crt').read_bytes())
  self.assertFalse(any('key' in p.name for p in self.path.glob('*.crt')))
  self.assertIn('certificate=present',self.runux('status').stdout)
  self.assertRegex(self.runux('status').stdout,r'certificate_fingerprint_sha256=[0-9A-F]{64}')
  # O_EXCL: never overwrite the public certificate or follow a symlink.
  first=exported[0].read_bytes()
  self.assertNotEqual(self.runux('https','cert-export',ok=False).returncode,0)
  self.assertEqual(exported[0].read_bytes(),first)
  exported[0].unlink()
  exported[0].symlink_to(self.hosts)
  before=self.hosts.read_bytes()
  self.assertNotEqual(self.runux('https','cert-export',ok=False).returncode,0)
  self.assertEqual(self.hosts.read_bytes(),before)
 def test_tls_managed_domain_only_and_non_proxy(self):
  self.runux('set','logo')
  self.runux('https','cert-create')
  self.runux('https','enable')
  self.assertIn('https_server=running',self.runux('status').stdout)
  self.assertIn('BH_HTTPS_LOCAL_TLS_PASS',self.runux('https','test').stdout)
  with self.conn('ads.test') as c:
   c.sendall(b'GET /abc HTTP/1.1\r\nHost: ads.test\r\nConnection: close\r\n\r\n')
   raw=c.recv(4096)
   self.assertIn(b'image/svg+xml',raw)
   self.assertIn(b'X-Bindhosts-Mode: logo',raw)
  with self.assertRaises((ssl.SSLError,ssl.SSLCertVerificationError,ConnectionError,OSError)):
   with self.conn('manual.test'):pass
  with self.assertRaises((ssl.SSLError,ssl.SSLCertVerificationError,ConnectionError,OSError)):
   with self.conn('notblocked.test'):pass
  self.runux('set','transparent')
  with self.conn('ads.test') as c:
   c.sendall(b'GET / HTTP/1.1\r\nHost: ads.test\r\nConnection: close\r\n\r\n')
   self.assertIn(b'image/gif',c.recv(4096))
  self.runux('https','disable')
  self.assertIn('https_mode=off',self.runux('status').stdout)
  self.assertTrue((self.state/'.ux07-tls/ca.key').exists())
 def test_original_hosts_restored_and_https_default_off(self):
  before=self.hosts.read_bytes()
  self.assertIn('https_mode=off',self.runux('status').stdout)
  self.runux('set','logo')
  self.runux('https','cert-create')
  self.runux('https','enable')
  self.runux('set','off')
  self.assertEqual(self.hosts.read_bytes(),before)
  self.assertIn('https_mode=off',self.runux('status').stdout)
  self.assertIn('https_server=not_running',self.runux('status').stdout)
 def test_native_export_rejects_unrelated_destination(self):
  self.runux('https','cert-create')
  bogus=self.path/'unrelated-export.crt'
  refused=self.runbin('--action','cert-export','--state',str(self.state/'.ux07-tls'),'--dest',str(bogus),ok=False)
  self.assertNotEqual(refused.returncode,0)
  self.assertFalse(bogus.exists())
  # Even an appropriately named export cannot overwrite existing bytes.
  fingerprint=self.runbin('--action','cert-status','--state',str(self.state/'.ux07-tls')).stdout.strip().split('=',1)[1]
  allowed=self.path/f'bindhosts-local-ca-{fingerprint[:16]}.crt'
  allowed.write_text('user data must survive')
  refused=self.runbin('--action','cert-export','--state',str(self.state/'.ux07-tls'),'--dest',str(allowed),ok=False)
  self.assertNotEqual(refused.returncode,0)
  self.assertEqual(allowed.read_text(),'user data must survive')
 def test_tls_rejects_certificate_symlinks(self):
  path=self.state/'.ux07-tls';path.mkdir()
  (path/'ca.crt').symlink_to(self.hosts)
  self.assertNotEqual(self.runux('https','cert-create',ok=False).returncode,0)
  self.assertFalse((path/'ca.key').exists())
 def test_tls_refuses_without_http_or_cert(self):
  self.assertNotEqual(self.runux('https','enable',ok=False).returncode,0)
  self.runux('set','transparent')
  self.assertNotEqual(self.runux('https','enable',ok=False).returncode,0)
  self.assertIn('https_mode=off',self.runux('status').stdout)
 def test_no_unsigned_host_or_network_interception(self):
  self.runux('set','logo')
  self.runux('https','cert-create')
  self.runux('https','enable')
  # When removed from the managed blocklist, the domain stops receiving certs.
  self.hosts.write_text(self.hosts.read_text().replace('127.0.0.1 ads.test # bh-response','0.0.0.0 ads.test'))
  time.sleep(10.3)
  with self.assertRaises((ssl.SSLError,ssl.SSLCertVerificationError,ConnectionError,OSError)):
   with self.conn('ads.test'):pass

if __name__=='__main__':unittest.main(verbosity=2)
