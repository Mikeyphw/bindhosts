#!/usr/bin/env python3
"""Read-only Android 16 preflight. No APK install, activity launch, root or device writes."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
import sys

ACK = 'I_AUTHORIZE_READ_ONLY_DEVICE_PROBE'
APP = 'com.mikeyphw.bindhosts'


def query(serial, command, *, allow_absent=False):
    argv = ['adb', '-s', serial, 'shell', *command]
    response = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    if response.returncode != 0 and not allow_absent:
        raise RuntimeError(f'read-only ADB query failed: {command[0]} (exit {response.returncode})')
    if len(response.stdout) > 65536:
        raise RuntimeError('ADB response exceeded safe report bound')
    return response.stdout.strip()


def probe(serial):
    api = query(serial, ['getprop', 'ro.build.version.sdk'])
    abi = query(serial, ['getprop', 'ro.product.cpu.abi'])
    packages = query(serial, ['pm', 'path', APP], allow_absent=True)
    installed = any(p.startswith('package:') for p in packages.splitlines())
    details = query(serial, ['dumpsys', 'package', APP], allow_absent=True) if installed else ''
    if not re.fullmatch(r'\d{1,3}', api):
        raise RuntimeError('invalid API readback')
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', abi):
        raise RuntimeError('invalid ABI readback')
    return {
        'schema': 'bh-app01/p07/physical-readonly/v1',
        'adb_serial_hash': hashlib.sha256(serial.encode()).hexdigest()[:16],
        'api': int(api),
        'abi': abi,
        'app_installed': installed,
        'qs_protection_declared': installed and 'ProtectionTileService' in details,
        'qs_update_declared': installed and 'UpdateTileService' in details,
        'device_writes_performed': False,
        'root_access_requested': False,
        'physical_android16_qualified': False,
        'release_qualified': False,
        'next_gate': 'physical UI and root-controlled write/restoration tests require separate approval',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--ack', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.ack != ACK or not re.fullmatch(r'[a-zA-Z0-9_.:\-]+', a.serial):
        print('BH_APP01_P07_REFUSED: explicit read-only acknowledgement and valid serial required', file=sys.stderr)
        return 12
    try:
        report = probe(a.serial)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    except (subprocess.TimeoutExpired, RuntimeError, OSError) as exc:
        print(f'BH_APP01_P07_REFUSED: {exc}', file=sys.stderr)
        return 12
    print('BH_APP01_P07_READ_ONLY_INSPECTION_COMPLETE_NOT_QUALIFIED')
    print(f'API={report["api"]} ABI={report["abi"]} installed={report["app_installed"]} report={a.output}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
