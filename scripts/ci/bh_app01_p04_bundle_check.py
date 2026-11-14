#!/usr/bin/env python3
"""Validate the actual Vite UX10 Android assets; never infer a bundle from source."""
import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]

def verify(root: Path) -> None:
    output = root / 'android/companion/app/src/main/assets/ux10'
    html = output / 'index.html'
    assert html.is_file() and 2000 < html.stat().st_size < 1_000_000, 'P04 index.html not built'
    content = html.read_text(encoding='utf-8')
    assert 'id="content-container"' in content, 'not the UX10 entrypoint'
    for name in ('home', 'hosts', 'apps', 'more'):
        assert f'page="{name}"' in content, f'missing UX10 page {name}'
    assert (output / 'locales/strings/en.xml').is_file(), 'localizations not bundled'
    assert (output / 'icon.png').is_file(), 'icon missing'
    manifest = output / '.vite/manifest.json'
    assert manifest.is_file(), 'Vite output manifest missing'
    entries = json.loads(manifest.read_text())
    assert 'index.html' in entries, 'wrong Vite entrypoint'
    # Manifest files must exist inside Android assets and be nontrivial.
    js = list(output.rglob('*.js'))
    assert js and sum(p.stat().st_size for p in js) > 50_000, 'UX10 JS bundle missing'
    for entry in entries.values():
        target = entry.get('file')
        if target:
            assert (output / target).is_file(), f'missing Vite asset {target}'
    print(f'BH_APP01_P04_UX10_BUNDLE_PASS pages=home,hosts,apps,more js_files={len(js)}')

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=ROOT)
    a=parser.parse_args()
    try:verify(a.repo.resolve())
    except (AssertionError,ValueError,KeyError) as e:
        print('BH_APP01_P04_REFUSED '+str(e),file=sys.stderr)
        raise SystemExit(1)
