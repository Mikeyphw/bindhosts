#!/usr/bin/env python3
"""Fail-closed P07 hosted emulator receipt. Never implies physical/release acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

EXPECTED_TESTS = frozenset({
    'actualUx10BundleLoadsFromLocalAssetOrigin',
    'releaseManifestAndBridgeRefuseArbitraryCommands',
    'updateTileIntentRequiresExplicitConfirmationAndCanBeCancelled',
})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(evidence, sha):
    evidence = Path(evidence)
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('invalid expected source SHA')
    if (evidence / 'source-commit.txt').read_text().strip() != sha:
        raise ValueError('wrong source commit')
    if (evidence / 'emulator-api.txt').read_text().strip() != '36':
        raise ValueError('not a hosted API36 emulator')
    image = evidence / 'api36-home.png'
    b = image.read_bytes()
    if len(b) < 4096 or b[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('missing real hosted screenshot')
    apk = (evidence / 'apk-sha256.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}', apk):
        raise ValueError('missing APK SHA256 evidence')
    xmls = list(evidence.glob('*.xml'))
    if not xmls:
        raise ValueError('no instrumentation XML')
    found = set()
    for path in xmls:
        root = ET.parse(path).getroot()
        if root.tag not in ('testsuite', 'testsuites'):
            raise ValueError('unexpected test report type')
        for test in root.iter('testcase'):
            if list(test.iter('failure')) or list(test.iter('error')) or list(test.iter('skipped')):
                raise ValueError('failed, errored or skipped instrumented test')
            if 'P07HostedUiTest' in test.get('classname', ''):
                found.add(test.get('name'))
        for suite in root.iter('testsuite'):
            if int(suite.attrib.get('failures','0')) or int(suite.attrib.get('errors','0')) or int(suite.attrib.get('skipped','0')):
                raise ValueError('failed test suite')
    if found != EXPECTED_TESTS:
        raise ValueError(f'instrumentation coverage missing/unexpected: {sorted(found)}')
    return {
        'schema': 'bh-app01/p07/hosted/v1',
        'source_sha': sha,
        'emulator_api': 36,
        'tested': sorted(found),
        'test_count': len(found),
        'apk_sha256': apk,
        'screenshot_sha256': hashlib.sha256(b).hexdigest(),
        'hosted_api36_qualified': True,
        'physical_android16_qualified': False,
        'release_qualified': False,
        'device_write_tests_performed': False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--expected-sha', required=True)
    a = p.parse_args()
    try:
        receipt = qualify(a.evidence, a.expected_sha)
    except (ValueError, OSError, ET.ParseError) as error:
        print(f'BH_APP01_P07_REFUSED: {error}', file=sys.stderr)
        return 12
    out = a.evidence / 'hosted-receipt.json'
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print('BH_APP01_P07_HOSTED_API36_VERIFIED_NOT_PHYSICAL_ACCEPTANCE ' + receipt['source_sha'])
    return 0

if __name__ == '__main__':
    sys.exit(main())
