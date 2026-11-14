#!/usr/bin/env python3
"""UX09E physical Android acceptance; strict read-only preflight + consented UI walk.

No implicit root writes, installs, reboots, UI taps or host-file replacements.
Only user-driven WebUI actions in the opt-in manual walkthrough can modify state.
A screenshot is taken only with the additional --capture flag.
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

REPO = 'Mikeyphw/bindhosts'
SOURCE_SHA = 'f32076e87164499ad693f9365c30a622e0fcc832'
MODULE = '/data/adb/modules/bindhosts'
STATE = '/data/adb/bindhosts'
SCRIPTS = {
    'hosts_operation_ux09.sh': '54ec639642b0c694a8a93acc9b64475ea689bc12c535b69af34c99ccca0ddb22',
    'source_catalog_batch_ux09.sh': '37d9db2726e9802391d73305c8b8005e6304724c3a0fd1daa9dbfe453ff4258b',
}
SERIAL = re.compile(r'[A-Za-z0-9._:-]{1,100}\Z')
STATUS_RE = re.compile(r'^BH_UX09_STATE=(IDLE|RUNNING|DONE|FAILED|INTERRUPTED)$', re.M)
CONTROL_RE = re.compile(r'^BH_HOSTS_STATE=(ACTIVE|PAUSED|INACTIVE|DISABLED)$', re.M)
APPLIED_RE = re.compile(r'^BH_UX09_APPLIED=(CURRENT|PENDING|UNKNOWN)$', re.M)
EVENT_RE = re.compile(r'^(PREPARING|DOWNLOADING|PARSED|SKIPPED_DUPLICATE_URL|DEDUPLICATING|ALLOWLIST|GENERATING|COMMITTING|DONE|UNCHANGED|FAILED|STATS)\|[A-Za-z0-9_ .=:\-|]{1,160}$')
STATS_RE = re.compile(r'^STATS\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$')

class Refused(Exception):
    pass

def need(condition: bool, message: str):
    if not condition:
        raise Refused(message)

def parse_key(s: str, regex: re.Pattern, description: str) -> str:
    match = regex.search(s)
    need(match is not None, f'{description} missing or unrecognized')
    return match.group(1)

def parse_events(output: str) -> list[str]:
    lines = [x for x in output.splitlines() if x]
    need(len(lines) <= 150, 'unbounded operation events')
    need(all(len(x) < 180 and EVENT_RE.fullmatch(x) for x in lines), 'unsafe/unrecognized operation events; not logging contents')
    return lines

def stats_from(events: list[str]) -> tuple[int, ...] | None:
    candidates = [x for x in events if x.startswith('STATS|')]
    if not candidates:
        return None
    selected = [STATS_RE.fullmatch(x) for x in candidates]
    need(all(selected), 'malformed STATS event')
    values = tuple(int(x) for x in selected[-1].groups())
    raw, duplicates, unique, excluded, final, downloads, skipped, changed = values
    need(raw >= unique and raw - unique == duplicates, 'invalid dedup counters')
    need(unique >= final and unique - final == excluded, 'invalid allowlist counters')
    need(downloads >= 1, 'invalid source count')
    return values

def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()

def safe_report_data(report: dict) -> dict:
    # Reporting contract: no package identities, URLs, IFW rules or source contents.
    return {key: value for key, value in report.items() if key in {
        'source_sha', 'serial', 'api', 'abi', 'root_uid', 'script_pins', 'hosts_state',
        'operation_state', 'applied_state', 'event_types', 'stats', 'last_applied_epoch',
        'baseline_fingerprints', 'manual_checks', 'outcome', 'capture_paths', 'timestamp',
    }}

class ADB:
    def __init__(self, serial: str, timeout=40):
        need(bool(SERIAL.fullmatch(serial)), 'unsafe ADB serial')
        self.serial = serial
        self.timeout = timeout

    def run(self, *args: str, check=True, binary=False, timeout=None):
        try:
            p = subprocess.run(['adb', '-s', self.serial, *args], capture_output=True,
                               timeout=timeout or self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Refused('ADB unavailable/timed out: ' + type(exc).__name__) from exc
        if check and p.returncode:
            # Deliberately do not return command stdout/stderr (can include private data).
            raise Refused(f'ADB command refused rc={p.returncode} ({args[0]})')
        return p if binary else p.stdout.decode('utf-8', errors='replace').replace('\r', '')

    def shell(self, command: str, check=True) -> str:
        return self.run('shell', 'su', '-c', command, check=check)

    def file_sha(self, fixed_name: str) -> str:
        need(fixed_name in SCRIPTS, 'not an allowlisted module script')
        line = self.shell(f'sha256sum {MODULE}/{fixed_name}')
        m = re.fullmatch(r'([0-9a-f]{64})\s+\S+\s*', line)
        need(bool(m), 'module source digest unavailable')
        return m.group(1)

    def hash_state(self) -> dict[str, str]:
        # Root-private files are never read or printed; only hashes are retrieved.
        names = ('sources.txt', 'sources_whitelist.txt', 'blacklist.txt', 'whitelist.txt', 'custom.txt')
        result = {}
        for name in names:
            line = self.shell(f'if [ -f {STATE}/{name} ] && [ ! -L {STATE}/{name} ]; then sha256sum {STATE}/{name}; else echo absent; fi')
            if line.strip() == 'absent':
                result[name] = 'absent'
            else:
                match = re.fullmatch(r'([0-9a-f]{64})\s+\S+\s*', line)
                need(bool(match), 'invalid state fingerprint for ' + name)
                result[name] = match.group(1)
        return result

    def inspect(self) -> dict:
        device = self.run('get-state').strip()
        need(device == 'device', 'ADB device unavailable')
        sdk = self.run('shell', 'getprop', 'ro.build.version.sdk').strip()
        abi = self.run('shell', 'getprop', 'ro.product.cpu.abi').strip()
        uid = self.shell('id -u').strip()
        need(uid == '0', 'root access not available')
        pins = {}
        for name, wanted in SCRIPTS.items():
            actual = self.file_sha(name)
            pins[name] = actual == wanted
        need(all(pins.values()), 'installed module is not UX09 commit ' + SOURCE_SHA[:12] + ' — install the qualified module first')
        ctrl = parse_key(self.shell(f'sh {MODULE}/bindhosts.sh --hosts-control status'), CONTROL_RE, 'hosts control state')
        operation = parse_key(self.shell(f'sh {MODULE}/hosts_operation_ux09.sh status'), STATUS_RE, 'operation state')
        applied_output = self.shell(f'sh {MODULE}/source_catalog_batch_ux09.sh applied-status')
        applied = parse_key(applied_output, APPLIED_RE, 'applied state')
        epoch = re.search(r'^BH_UX09_LAST_APPLIED_EPOCH=(\d+)$', applied_output, re.M)
        events = parse_events(self.shell(f'sh {MODULE}/hosts_operation_ux09.sh events'))
        return dict(source_sha=SOURCE_SHA, serial=self.serial, api=sdk, abi=abi, root_uid=uid,
                    script_pins=pins, hosts_state=ctrl, operation_state=operation,
                    applied_state=applied, event_types=[x.split('|', 1)[0] for x in events],
                    stats=stats_from(events), last_applied_epoch=int(epoch.group(1)) if epoch else None,
                    baseline_fingerprints=self.hash_state(), timestamp=int(time.time()))

    def screenshot(self, destination: Path) -> None:
        p = self.run('exec-out', 'screencap', '-p', binary=True)
        need(p.returncode == 0 and p.stdout.startswith(b'\x89PNG\r\n\x1a\n'), 'screenshot unavailable')
        destination.write_bytes(p.stdout)
        destination.chmod(0o600)


def display(report: dict):
    try:
        from rich.console import Console
        from rich.table import Table
        con = Console()
        table = Table(title='Bindhosts UX09E — read-only device inspection')
        table.add_column('Check'); table.add_column('Observed')
        for name in ('api', 'abi', 'root_uid', 'hosts_state', 'operation_state', 'applied_state'):
            table.add_row(name, str(report.get(name)))
        for name, good in report['script_pins'].items():
            table.add_row('Source pin ' + name, 'PASS' if good else 'REFUSED')
        con.print(table)
        if report['stats'] is not None:
            con.print('Last measured counters:', report['stats'])
    except ImportError:
        for name in ('api', 'abi', 'root_uid', 'hosts_state', 'operation_state', 'applied_state'):
            print(f'{name}={report.get(name)}')
        print('script_pins=', report['script_pins'])


def prompt_step(message: str, device: ADB, report: dict, capture_dir: Path | None, label: str):
    print('\n' + message)
    answer = input('Confirm what you actually saw [y/N]: ').strip().lower()
    need(answer == 'y', 'user did not confirm visible UI stage: ' + label)
    report.setdefault('manual_checks', []).append(label)
    if capture_dir is not None:
        path = capture_dir / f'{len(report["manual_checks"]):02d}-{label}.png'
        device.screenshot(path)
        report.setdefault('capture_paths', []).append(str(path))


def walk(device: ADB, report: dict, capture_dir: Path | None, test_update: bool, test_toggle: bool, test_source: bool):
    initial_state = report['hosts_state']
    need(initial_state in ('ACTIVE', 'PAUSED', 'INACTIVE'), 'cannot test UI with disabled/unknown hosts state')
    need(report['operation_state'] != 'RUNNING', 'another update is running; no concurrent UI acceptance')
    prompt_step('Open KernelSU → bindhosts WebUI → Sources. Verify Presets / My sources / Advanced are visible,\n'
                'and Energized has only one managed selection at a time. Do NOT change sources yet.',
                device, report, capture_dir, 'sources-topology')
    prompt_step('Open Rules. Verify Pause/Resume, Update hosts, and Refresh status controls are displayed.\n'
                'Verify the current displayed blocking state agrees with the device: ' + initial_state,
                device, report, capture_dir, 'rules-buttons')
    prompt_step('Open More. Verify blocked-page HTTP/HTTPS response settings and certificate warnings are there,\n'
                'not on the Sources page. DO NOT generate/install CA certificates.',
                device, report, capture_dir, 'response-settings')
    if test_toggle:
        need(initial_state in ('ACTIVE', 'PAUSED'), 'toggle needs ACTIVE or PAUSED baseline')
        need(input('Type TOGGLE_REAL_HOSTS to authorize manual Pause/Resume checks: ').strip() == 'TOGGLE_REAL_HOSTS',
             'toggle authorization missing')
        first = 'Pause blocking' if initial_state == 'ACTIVE' else 'Resume blocking'
        expected = 'PAUSED' if initial_state == 'ACTIVE' else 'ACTIVE'
        prompt_step(f'In Rules, tap {first}. Verify progress feedback and the changed button label.',
                    device, report, capture_dir, 'blocking-toggle-first')
        actual = parse_key(device.shell(f'sh {MODULE}/bindhosts.sh --hosts-control status'), CONTROL_RE, 'post-toggle state')
        need(actual == expected, f'toggle did not reach {expected}; stop before more changes')
        second = 'Resume blocking' if initial_state == 'ACTIVE' else 'Pause blocking'
        prompt_step(f'In Rules, tap {second}. Verify the original label/state is restored.',
                    device, report, capture_dir, 'blocking-toggle-restore')
        actual = parse_key(device.shell(f'sh {MODULE}/bindhosts.sh --hosts-control status'), CONTROL_RE, 'restored blocking state')
        need(actual == initial_state, 'blocking state was not restored; manual recovery required')
        report['manual_checks'].append('toggle-readback-restored')
    if test_source:
        need(input('Type EDIT_REAL_SOURCES to authorize a manual source selection + restore test: ').strip() == 'EDIT_REAL_SOURCES',
             'source edit authorization missing')
        prompt_step('In Sources, toggle ONE catalog-managed preset and tap Save selection.\n'
                    'Confirm the page reports saved changes pending an Update; do not update yet.',
                    device, report, capture_dir, 'source-selection-saved')
        edited = device.hash_state()
        need(edited['sources.txt'] != report['baseline_fingerprints']['sources.txt'],
             'sources file did not change; cannot confirm atomic preset selection')
        applied_output = device.shell(f'sh {MODULE}/source_catalog_batch_ux09.sh applied-status')
        need(parse_key(applied_output, APPLIED_RE, 'pending source state') == 'PENDING',
             'source changes not reported pending; investigate before update')
        prompt_step('Restore the PREVIOUS preset selection in Sources, then Save selection.\n'
                    'Check that the former selections are visible again.',
                    device, report, capture_dir, 'source-selection-restored')
        need(device.hash_state() == report['baseline_fingerprints'],
             'original sources were not restored byte-for-byte; STOP and inspect manually')
        report['manual_checks'].append('source-byte-restore-pass')
    if test_update:
        need(initial_state in ('ACTIVE', 'INACTIVE'), 'resume blocking through WebUI before accepting Update')
        print('\nWARNING: the next manual action rebuilds your REAL hosts file from configured network lists.\n'
              'No automatic rollback is attempted; the existing journaled writer is used.')
        need(input('Type UPDATE_REAL_HOSTS to permit testing the Update button: ').strip() == 'UPDATE_REAL_HOSTS',
             'real update authorization missing')
        prompt_step('In Rules, tap Update hosts. Verify the operation terminal opens, shows REAL stage events,\n'
                    'and displays measured duplicate/unique/final counters at completion.',
                    device, report, capture_dir, 'update-terminal')
        after = device.inspect()
        need(after['operation_state'] == 'DONE', 'backend did not complete update')
        need(after['stats'] is not None and after['stats'][5] >= 1, 'missing valid real update statistics')
        need('STATS' in after['event_types'], 'no measured STATS event')
        need(after['applied_state'] == 'CURRENT', 'saved sources are not verified as applied')
        need(after['baseline_fingerprints'] == report['baseline_fingerprints'],
             'source configuration changed unexpectedly; investigate before further writes')
        report.update({key:after[key] for key in ('operation_state','applied_state','stats','event_types','last_applied_epoch')})
        report['manual_checks'].append('update-backend-receipt')
    report['outcome'] = 'MANUAL_UI_AND_BACKEND_UPDATE_PASS' if test_update else 'MANUAL_UI_OBSERVED'
    if test_toggle: report['outcome'] += '_TOGGLE_VERIFIED'
    if test_source: report['outcome'] += '_SOURCE_RESTORED'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('probe', 'walk'))
    parser.add_argument('--serial', default='localhost:5555')
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--ack', default='')
    parser.add_argument('--capture', action='store_true', help='opt-in private screenshots of currently displayed app')
    parser.add_argument('--test-update', action='store_true', help='user manually performs a real hosts update, separate approval required')
    parser.add_argument('--test-toggle', action='store_true', help='manual Pause/Resume with verified state restoration')
    parser.add_argument('--test-source', action='store_true', help='manual preset change and exact source restoration')
    args = parser.parse_args(argv)
    need(not (args.action == 'probe' and (args.ack or args.capture or args.test_update or args.test_toggle or args.test_source)), 'probe must remain strictly read-only')
    need(not (args.action == 'walk' and args.ack != 'I_AUTHORIZE_UX09_MANUAL_UI_ACCEPTANCE'),
         'manual UI acceptance requires explicit authorization phrase')
    need(not ((args.test_update or args.test_toggle or args.test_source) and args.action != 'walk'), 'live UI options only available during consented walk')
    device = ADB(args.serial)
    report = device.inspect()
    display(report)
    print('BH_UX09E_SOURCE_PIN_PASS', SOURCE_SHA)
    print('BH_UX09E_DEVICE_READ_ONLY_PASS', f'API={report["api"]} ABI={report["abi"]}')
    if args.action == 'probe':
        print('BH_UX09E_READ_ONLY_COMPLETE — WebUI visual acceptance is NOT verified')
        return 0
    output_dir = args.output_dir or Path.home()/'.local/share/bindhosts-ux09e'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()
    capture_dir = output_dir / ('capture-' + str(int(time.time()))) if args.capture else None
    if capture_dir:
        capture_dir.mkdir(mode=0o700, exist_ok=False)
        print('Screenshots may contain personal information; capture is explicit and local only.')
    before = report['baseline_fingerprints']
    try:
        walk(device, report, capture_dir, args.test_update, args.test_toggle, args.test_source)
        after = device.hash_state()
        need(before == after, 'rule/source files changed during UI walkthrough — cannot qualify')
        print('BH_UX09E_PRIVATE_SOURCES_STABLE_PASS')
        print('BH_UX09E_' + report['outcome'])
        return_code = 0
    except Refused as exc:
        report['outcome'] = 'REFUSED:' + str(exc)
        return_code = 2
    finally:
        target = output_dir / ('ux09e-' + str(int(time.time())) + '.json')
        target.write_text(json.dumps(safe_report_data(report), indent=2, sort_keys=True) + '\n')
        target.chmod(0o600)
        print('BH_UX09E_LOCAL_REPORT=' + str(target))
    if return_code:
        raise Refused(report['outcome'])
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Refused, KeyboardInterrupt) as e:
        print('BH_UX09E_REFUSED: ' + (str(e) or 'interrupted'), file=sys.stderr)
        sys.exit(2)
