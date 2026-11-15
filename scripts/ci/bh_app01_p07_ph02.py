#!/usr/bin/env python3
"""BH-APP01 P07 PH02: GitHub-qualified hosted provenance and opt-in physical UI smoke.

Hosted verification is read-only on GitHub. Physical UI mode is opt-in and
makes ONLY a non-root Android Activity launch, UI hierarchy dump and Cancel tap.
It never installs, requests root, updates hosts, edits IFW, or signs releases.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from bh_app01_p07_physical_v2 import inspect as physical_inspect, write_private
from bh_app01_p07_signoff import qualify as hosted_qualify
from bh_app01_p07_qs_hierarchy import parse as qs_parse

REPO = 'Mikeyphw/bindhosts'
PR = 19
BRANCH = 'feature/bh-app01-p00-p03-companion-foundation-20261114'
BASE = 'feature/bindhosts-ux10-mobile-webui-20261114'
APP = 'com.mikeyphw.bindhosts'
SERIAL = 'localhost:5555'
ACK = 'I_AUTHORIZE_NONROOT_UI_SMOKE'
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
SHA64 = re.compile(r'[0-9a-f]{64}\Z')
REQUIRED = {
    'bh-app01-foundation.yml': 'BH-APP01 Companion Foundation',
    'bh-app01-p07-api36.yml': 'BH-APP01 P07 Hosted API36 UI Acceptance',
    'bindhosts-ux-ci.yml': 'bindhosts WebUI UX and sources catalog',
    'trackerguard-ci.yml': 'TrackerGuard R1 native scanner, IFW tests and module ZIP',
}
MAX_GH_OUTPUT = 5_000_000
MAX_ADB_OUTPUT = 2_000_000


class Refused(ValueError):
    pass


def refuse(reason):
    raise Refused(reason)


def execute(args, *, cwd=None, timeout=35, max_bytes=MAX_GH_OUTPUT, check=True):
    p = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, timeout=timeout, check=False)
    if len(p.stdout) > max_bytes or len(p.stderr) > 16384:
        refuse('SUBPROCESS_RESPONSE_TOO_LARGE')
    if check and p.returncode != 0:
        refuse('COMMAND_FAILED_' + Path(str(args[0])).name + '_rc_' + str(p.returncode))
    return p


def gh_api(path):
    if not re.fullmatch(r'repos/Mikeyphw/bindhosts/(pulls/19|actions/runs\?head_sha=[0-9a-f]{40}&per_page=100|actions/runs/[0-9]{1,20}/artifacts\?per_page=100)', path):
        refuse('GH_ENDPOINT_NOT_ALLOWLISTED')
    raw = execute(['gh', 'api', path], timeout=45).stdout
    try:
        obj = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise Refused('INVALID_GH_JSON') from exc
    if not isinstance(obj, dict):
        refuse('INVALID_GH_RESPONSE_SHAPE')
    return obj


def verify_pr(pr, sha):
    if not SHA40.fullmatch(sha):
        refuse('INVALID_SOURCE_SHA')
    if (pr.get('number') != PR or pr.get('state') != 'open'
            or not isinstance(pr.get('head'), dict) or not isinstance(pr.get('base'), dict)
            or pr['head'].get('sha') != sha or pr['head'].get('ref') != BRANCH
            or pr['base'].get('ref') != BASE
            or not isinstance(pr['head'].get('repo'), dict)
            or pr['head']['repo'].get('full_name') != REPO):
        refuse('PR_HEAD_BRANCH_OR_BASE_DRIFT')


def workflow_filename(run):
    path = str(run.get('path', '')).split('@', 1)[0]
    if path.startswith(REPO + '/'):
        path = path[len(REPO) + 1:]
    if not path.startswith('.github/workflows/'):
        return None
    return path.removeprefix('.github/workflows/')


def verify_runs(payload, sha):
    runs = payload.get('workflow_runs')
    if not isinstance(runs, list):
        refuse('WORKFLOW_LIST_MISSING')
    selected = {}
    for filename, expected_name in REQUIRED.items():
        matching = [r for r in runs if isinstance(r, dict)
                    and workflow_filename(r) == filename
                    and r.get('name') == expected_name
                    and r.get('head_sha') == sha and r.get('event') == 'pull_request']
        if not matching:
            refuse('REQUIRED_WORKFLOW_NOT_DISCOVERED_' + filename)
        # The newest run's latest attempt must pass; earlier success cannot hide a later failure.
        recent = max(matching, key=lambda r: (str(r.get('created_at', '')), int(r.get('id', 0))))
        if (recent.get('conclusion') != 'success' or recent.get('status') != 'completed'
                or not isinstance(recent.get('id'), int) or recent['id'] < 1):
            refuse('REQUIRED_WORKFLOW_NOT_GREEN_' + filename)
        selected[filename] = recent['id']
    return selected


def select_artifact(artifacts, sha):
    if not isinstance(artifacts.get('artifacts'), list):
        refuse('HOSTED_ARTIFACT_LIST_MISSING')
    name = 'bh-app01-p07-api36-' + sha
    found = [a for a in artifacts['artifacts'] if isinstance(a, dict) and a.get('name') == name]
    if len(found) != 1:
        refuse('EXPECTED_ONE_HOSTED_ARTIFACT')
    a = found[0]
    if (a.get('expired') is not False or not isinstance(a.get('id'), int) or a['id'] <= 0
            or not isinstance(a.get('size_in_bytes'), int) or a['size_in_bytes'] < 1000):
        refuse('HOSTED_ARTIFACT_UNUSABLE')
    return a['id'], name


def verify_git_checkout(root, sha):
    root = Path(root).resolve()
    if execute(['git', '-C', root, 'rev-parse', 'HEAD']).stdout.decode().strip() != sha:
        refuse('LOCAL_SOURCE_SHA_MISMATCH')
    if execute(['git', '-C', root, 'branch', '--show-current']).stdout.decode().strip() != BRANCH:
        refuse('WRONG_LOCAL_BRANCH')
    if execute(['git', '-C', root, 'status', '--porcelain', '--untracked-files=no']).stdout.strip():
        refuse('LOCAL_TRACKED_WORKTREE_DIRTY')


def private_directory(path):
    path = Path(path).expanduser()
    if path.is_symlink():
        refuse('OUTPUT_DIR_SYMLINK')
    # Refuse symlink components so private diagnostics cannot escape via a redirect.
    for component in (path, *path.parents):
        if component.is_symlink():
            refuse('OUTPUT_PATH_COMPONENT_SYMLINK')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir() or path.is_symlink():
        refuse('UNSAFE_OUTPUT_DIRECTORY')
    os.chmod(path, 0o700)
    return path.resolve()


def verified_hosted(root, sha, output_dir):
    """Verify the LIVE PR+all CI workflows and re-derive the hosted evidence receipt."""
    verify_git_checkout(root, sha)
    verify_pr(gh_api(f'repos/{REPO}/pulls/{PR}'), sha)
    runs = verify_runs(gh_api(f'repos/{REPO}/actions/runs?head_sha={sha}&per_page=100'), sha)
    run_id = runs['bh-app01-p07-api36.yml']
    artifact_id, artifact_name = select_artifact(
        gh_api(f'repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100'), sha)
    out = private_directory(output_dir)
    with tempfile.TemporaryDirectory(prefix='bh-p07-ph02-evidence-', dir=out) as scratch:
        evidence = Path(scratch)
        execute(['gh', 'run', 'download', str(run_id), '--repo', REPO,
                 '--name', artifact_name, '--dir', evidence], timeout=160, max_bytes=200000)
        # Check the extraction did not include symlinks or oversized unexpected files.
        files = list(evidence.rglob('*'))
        if len(files) > 35 or any(f.is_symlink() or not f.is_file() or f.stat().st_size > 10_000_000
                                  for f in files):
            refuse('HOSTED_ARTIFACT_UNSAFE_CONTENTS')
        if not (evidence / 'hosted-receipt.json').is_file():
            refuse('HOSTED_SIGNOFF_MISSING')
        try:
            printed = json.loads((evidence / 'hosted-receipt.json').read_text('utf-8'))
            actual = hosted_qualify(evidence, sha)
        except (OSError, ValueError, ET.ParseError) as exc:
            raise Refused('HOSTED_EVIDENCE_UNQUALIFIED') from exc
        if printed != actual:
            refuse('HOSTED_SIGNOFF_DOES_NOT_MATCH_EVIDENCE')
        receipt_hash = hashlib.sha256((evidence / 'hosted-receipt.json').read_bytes()).hexdigest()
        proof = {
            'schema': 'bh-app01/p07/ph02-github-proof/v1',
            'source_sha': sha, 'pr_number': PR, 'branch': BRANCH,
            'workflow_run_ids': runs, 'hosted_artifact_id': artifact_id,
            'hosted_artifact_name': artifact_name,
            'hosted_receipt_sha256': receipt_hash,
            'hosted_apk_sha256': actual['apk_sha256'],
            'github_workflows_independently_verified': True,
            'hosted_emulator_evidence_reverified': True,
            'physical_android16_qualified': False,
            'release_qualified': False,
        }
        # Export only the proved debug APK, private mode 0600; never install it.
        # A stale locally retained APK with different bytes is a refusal.
        apk_file = evidence / 'hosted-app-debug.apk'
        apk_bytes = apk_file.read_bytes()
        apk_target = out / 'hosted-app-debug.apk'
        if apk_target.is_symlink() or (apk_target.exists() and
                (not apk_target.is_file() or hashlib.sha256(apk_target.read_bytes()).hexdigest() != actual['apk_sha256'])):
            refuse('EXISTING_HOSTED_APK_IDENTITY_CONFLICT')
        if not apk_target.exists():
            fd, temporary = tempfile.mkstemp(prefix='.bh-p07-hosted-apk-', suffix='.tmp', dir=out)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'wb') as writer:
                    writer.write(apk_bytes)
                    writer.flush(); os.fsync(writer.fileno())
                os.replace(temporary, apk_target)
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
        write_private(out / 'github-proof.json', proof)
        write_private(out / 'hosted-receipt.json', printed)
    return proof


def adb(serial, args, *, timeout=30, ok=True, max_bytes=MAX_ADB_OUTPUT):
    if serial != SERIAL:
        refuse('PH02_REFUSED_DIFFERENT_DEVICE_SERIAL')
    # Finite fixed commands except the explicitly constructed temp filename and Cancel tap.
    argv = ['adb', '-s', SERIAL, *args]
    p = execute(argv, timeout=timeout, max_bytes=max_bytes, check=False)
    if ok and p.returncode:
        refuse('ADB_COMMAND_FAILED_' + '_'.join(args[:2]))
    return p


def temp_hierarchy_path(nonce):
    if not re.fullmatch(r'[0-9a-f]{16}', nonce):
        refuse('INVALID_TEMP_NONCE')
    return f'/sdcard/Download/.bh-app01-ph02-{nonce}.xml'


def ui_hierarchy(serial, path):
    r = adb(serial, ['shell', 'uiautomator', 'dump', path], timeout=26, ok=False, max_bytes=4000)
    if r.returncode != 0:
        refuse('UIAUTOMATOR_DUMP_FAILED')
    b = adb(serial, ['exec-out', 'cat', path], timeout=15).stdout
    if not 16 <= len(b) <= 2_000_000:
        refuse('UIAUTOMATOR_DUMP_SIZE_INVALID')
    return b


def qs_cancel_coordinates(raw):
    with tempfile.TemporaryDirectory(prefix='bh-app01-ui-tree-') as d:
        p = Path(d) / 'ui.xml'
        p.write_bytes(raw)
        try:
            return qs_parse(p)
        except (ValueError, ET.ParseError) as exc:
            raise Refused('REAL_QS_DIALOG_NOT_VISIBLE') from exc


def ui_smoke(serial, sha, hosted_receipt, output_dir, *, ack):
    if ack != ACK:
        refuse('EXPLICIT_NONROOT_UI_APPROVAL_REQUIRED')
    if serial != SERIAL:
        refuse('WRONG_DEVICE_SERIAL')
    inspection = physical_inspect(serial, sha, hosted_receipt)
    if inspection['read_only_status'] != 'READY_FOR_APPROVAL_GATES':
        refuse('PH01_PREFLIGHT_NOT_READY')
    if not inspection['hosted_apk_matches_installed']:
        refuse('INSTALLED_APK_DIFFERS_FROM_HOSTED_BUILD')
    out = private_directory(output_dir)
    # Creating/destroying an Android UI hierarchy temporary file and bringing the
    # companion Activity forward are the only Android changes in this mode.
    import secrets
    path = temp_hierarchy_path(secrets.token_hex(8))
    if adb(serial, ['shell', 'test', '-e', path], ok=False).returncode == 0:
        refuse('TEMP_FILE_COLLISION')
    created = False
    cancel_tapped = False
    before_hash = None
    cleanup_ok = True
    try:
        started = adb(serial, ['shell', 'am', 'start', '-W', '-n',
                               APP + '/.MainActivity', '-a', APP + '.CONFIRM_UPDATE'], timeout=30)
        if b'Status: ok' not in started.stdout:
            refuse('QS_INTENT_WAS_NOT_DELIVERED')
        xy = None
        for _ in range(8):
            # The UI dump writes only our named .xml; deletion is mandatory below.
            created = True
            raw = ui_hierarchy(serial, path)
            try:
                xy = qs_cancel_coordinates(raw)
                before_hash = hashlib.sha256(raw).hexdigest()
                break
            except Refused:
                time.sleep(1)
        if xy is None:
            refuse('QS_DIALOG_NOT_OBSERVED')
        # Never tap Update or allow caller-provided coordinates.
        adb(serial, ['shell', 'input', 'tap', str(xy[0]), str(xy[1])], timeout=12)
        cancel_tapped = True
        dismissed = False
        for _ in range(8):
            raw = ui_hierarchy(serial, path)
            try:
                qs_cancel_coordinates(raw)
            except Refused:
                dismissed = True
                break
            time.sleep(1)
        if not dismissed:
            refuse('QS_DIALOG_STILL_VISIBLE_AFTER_CANCEL')
        activity = adb(serial, ['shell', 'dumpsys', 'activity', 'activities'], max_bytes=200000).stdout
        if not re.search(rb'(?:topResumedActivity|mResumedActivity|ResumedActivity|mFocusedApp)[^\n]{0,400}' +
                         re.escape((APP + '/.MainActivity').encode()), activity):
            refuse('COMPANION_NOT_FOREGROUND_AFTER_CANCEL')
        result = {
            'schema': 'bh-app01/p07/ph02-physical-ui-smoke/v1',
            'source_sha': sha, 'serial_hash': inspection['serial_hash'],
            'hosted_apk_matches_installed': True,
            'installed_apk_sha256': inspection['installed_apk_sha256'],
            'real_qs_dialog_seen': True, 'cancel_button_tapped': True,
            'dialog_dismissed_after_cancel': True,
            'app_present_after_cancel': True,
            'qs_hierarchy_sha256': before_hash,
            'root_requested': False, 'apk_installed_or_uninstalled': False,
            'hosts_or_tracker_ifw_changed': False,
            'device_ui_interaction_performed': True,
            'temporary_device_ui_file_cleanup_verified': False,
            'physical_android16_qualified': False, 'release_qualified': False,
        }
    finally:
        if created:
            cleanup_ok = adb(serial, ['shell', 'rm', '-f', path], ok=False).returncode == 0
        if not cleanup_ok:
            refuse('TEMP_DEVICE_XML_CLEANUP_FAILED')
    result['temporary_device_ui_file_cleanup_verified'] = cleanup_ok
    write_private(out / 'physical-ui-smoke.json', result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['hosted', 'ui-smoke'])
    p.add_argument('--root', type=Path, default=Path.home() / 'Code/bindhosts')
    p.add_argument('--source-sha', required=True)
    p.add_argument('--output-dir', type=Path, default=Path.home() / '.local/state/bh-app01/p07-ph02')
    p.add_argument('--serial', default=SERIAL)
    p.add_argument('--ack', default='')
    a = p.parse_args(argv)
    try:
        if a.mode == 'ui-smoke' and a.ack != ACK:
            refuse('EXPLICIT_NONROOT_UI_APPROVAL_REQUIRED')
        proof = verified_hosted(a.root, a.source_sha, a.output_dir)
        print('BH_APP01_P07_PH02_GITHUB_PROVENANCE_PASS sha=' + a.source_sha)
        for name, run in proof['workflow_run_ids'].items():
            print(f'  {name}: {run} success')
        if a.mode == 'ui-smoke':
            res = ui_smoke(a.serial, a.source_sha,
                           Path(a.output_dir) / 'hosted-receipt.json',
                           a.output_dir, ack=a.ack)
            print('BH_APP01_P07_PH02_PHYSICAL_NONROOT_UI_SMOKE_PASS ' +
                  'qs_cancel=true temporary_cleanup=' + str(res['temporary_device_ui_file_cleanup_verified']).lower())
        print('tested_hosted_debug_apk=' + str(Path(a.output_dir) / 'hosted-app-debug.apk'))
        print('PHYSICAL_FULL_QUALIFICATION=false RELEASE_QUALIFICATION=false')
        print('private_report_dir=' + str(a.output_dir))
        return 0
    except (Refused, ValueError, OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        print('BH_APP01_P07_PH02_REFUSED ' + str(exc), file=sys.stderr)
        return 12


if __name__ == '__main__':
    sys.exit(main())
