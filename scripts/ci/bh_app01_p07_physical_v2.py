#!/usr/bin/env python3
"""BH-APP01 P07 PH01 read-only physical ARM64 acceptance preflight.

No root escalation, APK installation, Android writes, screenshots, or private data
collection. A hosted receipt can only bind evidence; it never qualifies a device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ACK = 'I_AUTHORIZE_READ_ONLY_DEVICE_PROBE'
APP = 'com.mikeyphw.bindhosts'
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
SHA64 = re.compile(r'[0-9a-f]{64}\Z')
SERIAL = re.compile(r'[A-Za-z0-9_.:-]{1,80}\Z')
APK_PATH = re.compile(r'/data/app/[A-Za-z0-9_./~+=-]+/base\.apk\Z')
MAX_RESPONSE = 65536


def refuse(reason):
    raise ValueError(reason)


def adb(serial, args, *, absent_ok=False):
    """Only explicit read-only ADB argv; no shell interpolation or root."""
    if not SERIAL.fullmatch(serial):
        refuse('INVALID_SERIAL')
    allowed = (
        ('get-state',), ('devices', '-l'),
        ('shell', 'getprop', 'ro.build.version.sdk'),
        ('shell', 'getprop', 'ro.product.cpu.abi'),
        ('shell', 'getprop', 'ro.kernel.qemu'),
        ('shell', 'getenforce'),
        ('shell', 'pm', 'path', APP),
        ('shell', 'dumpsys', 'package', APP),
        ('shell', 'pm', 'list', 'packages'),
    )
    if tuple(args) not in allowed and not (len(args) == 3 and args[:2] == ['shell', 'sha256sum']
            and APK_PATH.fullmatch(args[2]) and '/..' not in args[2]):
        refuse('COMMAND_NOT_ALLOWLISTED')
    result = subprocess.run(['adb', '-s', serial, *args], capture_output=True,
                            timeout=25, check=False)
    if len(result.stdout) > MAX_RESPONSE or len(result.stderr) > 8192:
        refuse('ADB_OUTPUT_TOO_LARGE')
    if result.returncode and not absent_ok:
        refuse('ADB_QUERY_FAILED_' + '_'.join(args[:3]))
    return result.stdout.decode('utf-8', 'strict').strip() if not result.returncode else ''


def load_hosted(path, source_sha):
    if path is None:
        return None
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
        refuse('HOSTED_RECEIPT_INVALID_FILE')
    try:
        o = json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('HOSTED_RECEIPT_INVALID_JSON') from exc
    if not isinstance(o, dict) or o.get('schema') != 'bh-app01/p07/hosted/v1' or o.get('source_sha') != source_sha:
        refuse('HOSTED_SOURCE_OR_SCHEMA_MISMATCH')
    if (o.get('hosted_api36_qualified') is not True or o.get('physical_android16_qualified') is not False
            or o.get('release_qualified') is not False or o.get('emulator_api') != 36
            or o.get('test_count') != 3 or not SHA64.fullmatch(o.get('apk_sha256', ''))):
        refuse('HOSTED_RECEIPT_NOT_QUALIFIED')
    if o.get('device_write_tests_performed') is not False or o.get('real_cold_start_qs_confirm_and_cancel') is not True:
        refuse('HOSTED_RECEIPT_INCOMPLETE')
    return {'apk_sha256': o['apk_sha256'], 'receipt_file_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def inspect(serial, source_sha, hosted_receipt=None):
    if not SHA40.fullmatch(source_sha):
        refuse('INVALID_SOURCE_SHA')
    hosted = load_hosted(hosted_receipt, source_sha)
    if adb(serial, ['get-state']) != 'device':
        refuse('DEVICE_NOT_ONLINE')
    all_devices = adb(serial, ['devices', '-l']).splitlines()
    connected = [line.split()[0] for line in all_devices if len(line.split()) >= 2 and line.split()[1] == 'device']
    if connected != [serial]:
        refuse('EXPECTED_EXACTLY_ONE_REQUESTED_DEVICE')
    api = adb(serial, ['shell', 'getprop', 'ro.build.version.sdk'])
    abi = adb(serial, ['shell', 'getprop', 'ro.product.cpu.abi'])
    emu = adb(serial, ['shell', 'getprop', 'ro.kernel.qemu'])
    if api != '36' or abi != 'arm64-v8a' or emu == '1':
        refuse('WRONG_PHYSICAL_ANDROID16_ARM64_TARGET')
    selinux = adb(serial, ['shell', 'getenforce'])
    if selinux not in ('Enforcing', 'Permissive', 'Disabled'):
        refuse('INVALID_SELINUX_READBACK')
    output = adb(serial, ['shell', 'pm', 'path', APP], absent_ok=True)
    installed_paths = [line.removeprefix('package:') for line in output.splitlines() if line.startswith('package:')]
    if len(installed_paths) > 1:
        refuse('MULTIPLE_PACKAGE_PATHS_NOT_QUALIFIED')
    if output and len(installed_paths) != 1:
        refuse('PACKAGE_PATH_RESPONSE_INVALID')
    installed = bool(installed_paths)
    installed_hash = None
    qs_protection = False
    qs_update = False
    if installed:
        path = installed_paths[0]
        if not APK_PATH.fullmatch(path) or '/..' in path:
            refuse('UNSAFE_INSTALLED_APK_PATH')
        checked = adb(serial, ['shell', 'sha256sum', path], absent_ok=True)
        token = checked.split()[0] if checked.split() else ''
        if SHA64.fullmatch(token):
            installed_hash = token
        package = adb(serial, ['shell', 'dumpsys', 'package', APP])
        qs_protection = 'ProtectionTileService' in package
        qs_update = 'UpdateTileService' in package
    manager_packages = adb(serial, ['shell', 'pm', 'list', 'packages'])
    manager_ids = ('me.weishu.kernelsu', 'com.rifsxd.ksunext', 'com.sukisu.ultra',
                   'com.topjohnwu.magisk')
    detected = [pkg for pkg in manager_ids if ('package:' + pkg) in manager_packages.splitlines()]
    match = hosted is not None and installed_hash is not None and installed_hash == hosted['apk_sha256']
    # An installed APK without published exact-source identity cannot qualify.
    status = 'READY_FOR_APPROVAL_GATES' if match and qs_protection and qs_update else 'INCONCLUSIVE'
    return {
        'schema': 'bh-app01/p07/physical-readonly/v2',
        'source_sha': source_sha,
        'serial_hash': hashlib.sha256(serial.encode()).hexdigest()[:16],
        'api': int(api), 'abi': abi, 'ro_kernel_qemu': emu or 'unset',
        'selinux': selinux, 'app_package': APP, 'app_installed': installed,
        'installed_apk_sha256': installed_hash,
        'qs_protection_declared': qs_protection, 'qs_update_declared': qs_update,
        'root_manager_package_detected': detected,
        'root_grant_verified': False, 'module_identity_verified': False,
        'hosted_receipt_provided': hosted is not None,
        'hosted_receipt_file_sha256': hosted['receipt_file_sha256'] if hosted else None,
        'hosted_apk_matches_installed': bool(match),
        'read_only_status': status,
        'device_writes_performed': False, 'root_access_requested': False,
        'hosted_workflow_independently_verified': False,
        'physical_android16_qualified': False, 'release_qualified': False,
        'still_required': ['independent hosted run/source verification',
                           'module/version read-back', 'explicit install and write-test approvals',
                           'UI/SAF and QS races', 'hosts byte restoration',
                           'TrackerGuard IFW foreign-rule preservation and cleanup',
                           'P08 artifact signing and rollback'],
    }


def write_private(path, content):
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        refuse('UNSAFE_REPORT_TARGET')
    fd, name = tempfile.mkstemp(prefix='.bh-p07-', suffix='.tmp', dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(content, out, sort_keys=True, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--hosted-receipt', type=Path)
    p.add_argument('--ack', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    try:
        if args.ack != ACK:
            refuse('EXPLICIT_READ_ONLY_APPROVAL_REQUIRED')
        result = inspect(args.serial, args.source_sha, args.hosted_receipt)
        write_private(args.output, result)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print('BH_APP01_P07_PH01_REFUSED ' + str(exc), file=sys.stderr)
        return 12
    print('BH_APP01_P07_PH01_READ_ONLY_INSPECTION_' + result['read_only_status'])
    print('app_installed=' + str(result['app_installed']) + ' apk_match=' +
          str(result['hosted_apk_matches_installed']) + ' physical_qualified=false')
    print('report=' + str(args.output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
