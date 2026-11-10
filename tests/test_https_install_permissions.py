#!/usr/bin/env python3
"""UX07: test KernelSU install exec-mode contract without Android Gradle."""
from pathlib import Path
import os,stat,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
script=(ROOT/'module/customize.sh').read_text()
a='# UX07_TLS_PERMISSIONS_BEGIN';b='# UX07_TLS_PERMISSIONS_END'
assert script.count(a)==script.count(b)==1
piece=script[script.index(a):script.index(b)+len(b)]
assert 'set_perm "$tg_tls" 0 0 0755' in piece
with tempfile.TemporaryDirectory(prefix='bh-ux07-perms-',dir=os.environ.get('TMPDIR')) as t:
 r=Path(t)
 for abi in ('arm64-v8a','armeabi-v7a','x86_64'):
  p=r/'bin'/abi/'blocked_response_tls';p.parent.mkdir(parents=True);p.write_bytes(b'ELF-test');p.chmod(0o644)
 scriptlet='''set -eu
set_perm(){ chmod "$4" "$1"; }
abort(){ echo "$1" >&2; exit 40; }
'''+piece
 env=dict(os.environ,MODPATH=str(r))
 p=subprocess.run(['sh','-c',scriptlet],env=env,capture_output=True,text=True)
 assert p.returncode==0,p.stderr
 for abi in ('arm64-v8a','armeabi-v7a','x86_64'):
  assert stat.S_IMODE((r/'bin'/abi/'blocked_response_tls').stat().st_mode)==0o755
 (r/'bin/x86_64/blocked_response_tls').unlink()
 p=subprocess.run(['sh','-c',scriptlet],env=env,capture_output=True,text=True)
 assert p.returncode==40 and 'missing TLS responder for x86_64' in p.stderr
print('UX07_TLS_INSTALL_PERMISSIONS_PASS')
