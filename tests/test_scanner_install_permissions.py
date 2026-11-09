#!/usr/bin/env python3
"""Simulate KernelSU's default 0644 and customize.sh's permission override."""
from pathlib import Path
import os
import stat
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
script = (root / 'module/customize.sh').read_text()
start = '# TG_SCANNER_PERMISSIONS_BEGIN:'
end = '# TG_SCANNER_PERMISSIONS_END'
assert script.count(start) == 1 and script.count(end) == 1, 'missing/duplicate permission block'
block = script[script.index(start):script.index(end)+len(end)]
assert 'set_perm "$tg_scanner" 0 0 0755' in block
assert 'abort "TrackerGuard: missing native scanner' in block

abis = ('arm64-v8a', 'armeabi-v7a', 'x86_64')
wrapper = r'''
set -eu
set_perm() {
  [ "$2" = 0 ] && [ "$3" = 0 ] && [ "$4" = 0755 ] || exit 42
  chmod "$4" "$1"
}
abort() { printf '%s\n' "$1" >&2; exit 43; }
''' + block + '\n'

with tempfile.TemporaryDirectory(prefix='tg-installer-perms-') as td:
    base = Path(td)
    binaries = []
    for abi in abis:
        p = base / 'bin' / abi / 'axmlscan'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'ELF-not-executed-in-test')
        p.chmod(0o644)
        binaries.append(p)
    other = base / 'untouched.txt'
    other.write_text('ordinary file')
    other.chmod(0o644)
    env = {**os.environ, 'MODPATH': str(base)}
    def run():
        return subprocess.run(['sh', '-c', wrapper], env=env, text=True,
                              capture_output=True, timeout=10)
    p = run()
    assert p.returncode == 0, (p.stdout, p.stderr)
    for binary in binaries:
        assert stat.S_IMODE(binary.stat().st_mode) == 0o755, binary
    assert stat.S_IMODE(other.stat().st_mode) == 0o644
    # Missing scanner must abort module installation, not silently pass.
    binaries[-1].unlink()
    missing = run()
    assert missing.returncode == 43, (missing.returncode, missing.stderr)
    assert 'missing native scanner for x86_64' in missing.stderr
print('TG_R1_HF04_INSTALL_PERMISSION_TEST_PASS')
