#!/usr/bin/env python3
"""UX04 install contract: the dedicated responder permission block works under KSU 0644 defaults."""
from pathlib import Path
import os
import stat
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
script = (repo / 'module/customize.sh').read_text()
scan_start = '# TG_SCANNER_PERMISSIONS_BEGIN:'
scan_end = '# TG_SCANNER_PERMISSIONS_END'
start = '# UX04_RESPONDER_PERMISSIONS_BEGIN'
end = '# UX04_RESPONDER_PERMISSIONS_END'
assert script.count(scan_start) == 1 and script.count(scan_end) == 1
assert script.count(start) == 1 and script.count(end) == 1
assert script.index(scan_start) < script.index(scan_end) < script.index(start) < script.index(end)
block = script[script.index(start):script.index(end) + len(end)]
assert 'set_perm "$tg_response" 0 0 0755' in block
assert 'abort "UX04: missing native responder' in block

wrapper = r'''
set -eu
set_perm() {
  [ "$2" = 0 ] && [ "$3" = 0 ] && [ "$4" = 0755 ] || exit 42
  chmod "$4" "$1"
}
abort() { printf '%s\n' "$1" >&2; exit 43; }
''' + block + '\n'

abis = ('arm64-v8a', 'armeabi-v7a', 'x86_64')
with tempfile.TemporaryDirectory(prefix='ux04-installer-perms-') as temp:
    base = Path(temp)
    native = []
    for abi in abis:
        p = base / 'bin' / abi / 'blocked_response'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'ELF-stub-not-executed-by-test')
        p.chmod(0o644)
        native.append(p)
    unrelated = base / 'unrelated'
    unrelated.write_bytes(b'preserve 0644')
    unrelated.chmod(0o644)
    env = {**os.environ, 'MODPATH': str(base)}

    def run():
        return subprocess.run(['sh', '-c', wrapper], env=env,
                              capture_output=True, text=True, timeout=10)

    good = run()
    assert good.returncode == 0, (good.returncode, good.stdout, good.stderr)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in native)
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o644
    native[-1].unlink()
    failure = run()
    assert failure.returncode == 43, (failure.returncode, failure.stderr)
    assert 'missing native responder for x86_64' in failure.stderr
print('UX04_RESPONDER_INSTALL_PERMISSION_TEST_PASS')
