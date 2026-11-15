#!/usr/bin/env python3
"""Exact HEAD + four CI green -> download hosted-tested APK -> module ZIP.

Runs only in GitHub Actions; the synthetic unit tests never reach GitHub or ADB.
No device install, no local Gradle, no release signing, no remote module downloads.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import zipfile

REPO = 'Mikeyphw/bindhosts'
BRANCH = 'feature/bh-app01-p00-p03-companion-foundation-20261114'
PR = 19
WORKFLOWS = {
    'bh-app01-foundation.yml': 'BH-APP01 Companion Foundation',
    'bh-app01-p07-api36.yml': 'BH-APP01 P07 Hosted API36 UI Acceptance',
    'bindhosts-ux-ci.yml': 'bindhosts WebUI UX and sources catalog',
    'trackerguard-ci.yml': 'TrackerGuard R1 native scanner, IFW tests and module ZIP',
}
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
SHA64 = re.compile(r'[0-9a-f]{64}\Z')
APP = 'com.mikeyphw.bindhosts'
COMPANION = 'companion/bindhosts-companion.apk'
ABIS = ('arm64-v8a', 'armeabi-v7a', 'x86_64')
TOOLS = ('axmlscan', 'blocked_response', 'blocked_response_tls')


def refuse(message: str):
    raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gh_api(path: str):
    p = subprocess.run(['gh', 'api', path], capture_output=True, text=True, timeout=90)
    if p.returncode or len(p.stdout) > 5_000_000:
        refuse('GITHUB_API_UNAVAILABLE_' + str(p.returncode))
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise ValueError('GITHUB_API_MALFORMED_JSON') from e


def select_completed_runs(pull, listings, source: str):
    """Never accept a different PR/branch, synthetic merge commit or older run."""
    if not SHA40.fullmatch(source):
        refuse('INVALID_SOURCE_SHA')
    if not isinstance(pull, dict) or pull.get('number') != PR or pull.get('state') != 'open':
        refuse('PR_IDENTITY_INVALID')
    head = pull.get('head') or {}
    base = pull.get('base') or {}
    if (head.get('sha') != source or head.get('ref') != BRANCH or
        (head.get('repo') or {}).get('full_name') != REPO or
        base.get('ref') != 'feature/bindhosts-ux10-mobile-webui-20261114'):
        refuse('PR_HEAD_OR_BASE_DRIFT')
    if not isinstance(listings, dict) or not isinstance(listings.get('workflow_runs'), list):
        refuse('WORKFLOW_LIST_MALFORMED')
    matches = {}
    for filename, name in WORKFLOWS.items():
        candidates = [x for x in listings['workflow_runs'] if
            isinstance(x, dict) and x.get('head_sha') == source and
            x.get('name') == name and x.get('event') == 'pull_request' and
            (x.get('path') or '').endswith('/' + filename)]
        if not candidates:
            return None
        latest = max(candidates, key=lambda x: (int(x.get('id', 0)), int(x.get('run_attempt', 0))))
        if latest.get('status') != 'completed':
            return None
        if latest.get('conclusion') != 'success':
            refuse('EXACT_HEAD_REQUIRED_WORKFLOW_FAILED_' + filename + '_' + str(latest['id']))
        matches[filename] = int(latest['id'])
    return matches


def gate(sha: str, deadline: int, run_id_file: Path):
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('RUNNER_OS') != 'Linux':
        refuse('GITHUB_HOSTED_ONLY')
    if not SHA40.fullmatch(sha):
        refuse('SOURCE_SHA_INVALID')
    if subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip() != sha:
        refuse('LOCAL_HEAD_NOT_EXACT')
    until = time.monotonic() + deadline
    while True:
        pull = gh_api(f'repos/{REPO}/pulls/{PR}')
        runs = gh_api(f'repos/{REPO}/actions/runs?branch={BRANCH}&per_page=100')
        selected = select_completed_runs(pull, runs, sha)
        if selected:
            hosted = selected['bh-app01-p07-api36.yml']
            run_id_file.parent.mkdir(parents=True, exist_ok=True)
            run_id_file.write_text(str(hosted) + '\n', encoding='ascii')
            print('BH_APP01_P07_MODULE_CI_PIN_PASS ' + json.dumps(selected, sort_keys=True), flush=True)
            return
        if time.monotonic() >= until:
            refuse('REQUIRED_WORKFLOW_NOT_YET_GREEN_FOR_EXACT_HEAD')
        print('BH_APP01_P07_MODULE_WAITING_FOR_FOUR_PR_CI_RUNS ' + sha, flush=True)
        time.sleep(15)


def verified_hosted(evidence: Path, source: str) -> tuple[bytes, str, dict]:
    """Require *actual* hosted evidence and APK, not a submitted JSON claim."""
    from importlib.util import spec_from_file_location, module_from_spec
    signoff = Path(__file__).with_name('bh_app01_p07_signoff.py')
    spec = spec_from_file_location('p07_exact_hosted_signoff', signoff)
    assert spec is not None and spec.loader is not None
    m = module_from_spec(spec)
    spec.loader.exec_module(m)
    proof = m.qualify(evidence, source)
    recorded = json.loads((evidence / 'hosted-receipt.json').read_text())
    if recorded != proof:
        refuse('HOSTED_RECEIPT_NOT_INDEPENDENTLY_REPRODUCIBLE')
    if not proof['hosted_api36_qualified'] or proof['physical_android16_qualified'] or proof['release_qualified']:
        refuse('INVALID_HOSTED_QUALIFICATION')
    data = (evidence / 'hosted-app-debug.apk').read_bytes()
    if len(data) < 1024 or data[:2] != b'PK':
        refuse('HOSTED_APK_MISSING_OR_INVALID')
    digest = sha256(data)
    if digest != proof['apk_sha256'] or digest != (evidence / 'apk-sha256.txt').read_text().strip():
        refuse('HOSTED_APK_SHA_MISMATCH')
    lines = (evidence / 'emulator-installed-identity.txt').read_text().splitlines()
    fields = dict(l.split('=', 1) for l in lines if '=' in l)
    required = {
        'schema': 'bh-app01/p07/hf05', 'source_sha': source, 'emulator_api': '36',
        'emulator_abi': 'x86_64', 'package': APP, 'apk_sha256': digest,
        'installed_sha256': digest, 'physical_device_writes': 'false',
    }
    if any(fields.get(k) != v for k, v in required.items()):
        refuse('HOSTED_APK_INSTALLED_IDENTITY_MISMATCH')
    return data, digest, proof


def check_module(root: Path):
    required = ['module.prop', 'customize.sh', 'bindhosts-app.sh',
                'META-INF/com/google/android/update-binary',
                'META-INF/com/google/android/updater-script',
                'webroot/index.html', 'hosts_config_safe.sh', 'trackerguard.sh']
    required.extend(f'bin/{abi}/{tool}' for abi in ABIS for tool in TOOLS)
    for relative in required:
        p = root / relative
        if not p.is_file() or p.is_symlink() or p.stat().st_size == 0:
            refuse('MODULE_REQUIRED_PAYLOAD_ABSENT_' + relative)
    info = (root / 'module.prop').read_text()
    if 'id=bindhosts\n' not in info or 'versionCode=21612\n' not in info:
        refuse('MODULE_VERSION_NOT_UPDATED')
    for abi in ABIS:
        for tool in TOOLS:
            p = root / 'bin' / abi / tool
            with p.open('rb') as f: header = f.read(4)
            if header != b'\x7fELF':
                refuse('NATIVE_PAYLOAD_NOT_ELF_' + abi + '_' + tool)


def build_module(source: str, evidence: Path, module: Path, output: Path):
    if not SHA40.fullmatch(source): refuse('INVALID_SOURCE_SHA')
    if not module.is_dir() or module.is_symlink(): refuse('MODULE_TREE_UNSAFE')
    data, digest, receipt = verified_hosted(evidence, source)
    check_module(module)
    if (module / 'companion').exists():
        refuse('MODULE_COMPANION_STAGING_MUST_BE_ABSENT')
    # Materialize only in the GitHub-hosted throwaway checkout. The user's phone
    # and Termux never see this operation until *they* install the resulting ZIP.
    (module / 'companion').mkdir()
    try:
        (module / COMPANION).write_bytes(data)
        (module / 'companion/bindhosts-companion.sha256').write_text(digest + '\n', encoding='ascii')
        (module / 'companion/source-commit.txt').write_text(source + '\n', encoding='ascii')
        (module / 'companion/hosted-acceptance.json').write_text(json.dumps({
            'source_sha': source, 'apk_sha256': digest,
            'package': APP, 'hosted_api36_qualified': True,
            'physical_android16_qualified': False,
            'personal_release_qualified': False,
            'release_qualified': False,
            'tested_instrumentation_cases': receipt['test_count'],
        }, sort_keys=True, indent=2) + '\n')
        files = sorted(p for p in module.rglob('*') if p.is_file())
        archive = {}
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(module.resolve()):
                refuse('MODULE_SYMLINK_OR_PATH_ESCAPE')
            rel = path.relative_to(module).as_posix()
            if rel.startswith('/') or '..' in Path(rel).parts or rel in archive:
                refuse('UNSAFE_ARCHIVE_MEMBER')
            archive[rel] = path.read_bytes()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, content in archive.items():
                src = module / name
                perms = stat.S_IMODE(src.stat().st_mode)
                zi = zipfile.ZipInfo(name, (2026, 11, 15, 0, 0, 0))
                zi.create_system = 3
                zi.external_attr = (stat.S_IFREG | perms) << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        verify_bundle(output, source)
    finally:
        # Do not leave untrusted APK blobs untracked in the Git worktree.
        import shutil
        shutil.rmtree(module / 'companion')
    print('BH_APP01_P07_MODULE_APK_EMBEDDED_PASS sha=' + source + ' apk_sha256=' + digest + ' zip=' + str(output))


def verify_bundle(path: Path, source: str):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or not names or any(
            n.startswith('/') or '..' in Path(n).parts or n.endswith('/') for n in names
        ):
            refuse('MALFORMED_MODULE_ARCHIVE')
        for name in ('module.prop', 'customize.sh', 'bindhosts-app.sh',
                     'META-INF/com/google/android/update-binary', COMPANION,
                     'companion/bindhosts-companion.sha256', 'companion/source-commit.txt'):
            if name not in names:
                refuse('MISSING_MODULE_COMPONENT_' + name)
        if 'id=bindhosts\n' not in z.read('module.prop').decode():
            refuse('WRONG_MODULE_ID')
        if z.read('companion/source-commit.txt').decode().strip() != source:
            refuse('MODULE_APK_SOURCE_SHA_DRIFT')
        apk = z.read(COMPANION)
        if sha256(apk) != z.read('companion/bindhosts-companion.sha256').decode().strip():
            refuse('MODULE_APK_SHA_MISMATCH')
        metadata = json.loads(z.read('companion/hosted-acceptance.json'))
        if (metadata.get('source_sha') != source or metadata.get('apk_sha256') != sha256(apk) or
            metadata.get('package') != APP or metadata.get('physical_android16_qualified') is not False or
            metadata.get('personal_release_qualified') is not False or
            metadata.get('release_qualified') is not False):
            refuse('MODULE_HOSTED_EVIDENCE_DRIFT')
        for abi in ABIS:
            for tool in TOOLS:
                if f'bin/{abi}/{tool}' not in names:
                    refuse('MODULE_NATIVE_BINARY_MISSING')
    print('BH_APP01_P07_MODULE_ZIP_VERIFY_PASS sha=' + source + ' size=' + str(path.stat().st_size))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    g = sub.add_parser('gate'); g.add_argument('--source-sha', required=True); g.add_argument('--run-id-file', type=Path, required=True);g.add_argument('--deadline-seconds', type=int, default=1200)
    b = sub.add_parser('package');b.add_argument('--source-sha', required=True);b.add_argument('--evidence', type=Path, required=True);b.add_argument('--module', type=Path, default=Path('module'));b.add_argument('--output', type=Path, required=True)
    v = sub.add_parser('verify');v.add_argument('--source-sha', required=True);v.add_argument('--bundle', type=Path, required=True)
    a = p.parse_args()
    try:
        if a.action == 'gate': gate(a.source_sha, a.deadline_seconds, a.run_id_file)
        elif a.action == 'package': build_module(a.source_sha, a.evidence, a.module, a.output)
        else:verify_bundle(a.bundle, a.source_sha)
        return 0
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as e:
        print('BH_APP01_P07_MODULE_REFUSED: ' + str(e), file=sys.stderr)
        return 12


if __name__ == '__main__':
    sys.exit(main())
