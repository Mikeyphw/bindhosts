#!/usr/bin/env python3
"""Static UI contracts to prevent broken routes, shell interpolation and catalog drift."""
import json
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]

class UX01Tests(unittest.TestCase):
    def read(self, name): return (ROOT / name).read_text()

    def test_catalog_json_matches_root_catalog(self):
        presets = json.loads(self.read('webui/catalog-presets.json'))
        lines = [x.split('|') for x in self.read('module/data/source-catalog.tsv').splitlines()
                 if x and not x.startswith('#')]
        self.assertEqual([(x['id'], x['url']) for x in presets], [(x[0], x[2]) for x in lines])
        self.assertEqual(len(presets), len(set(x['id'] for x in presets)))
        self.assertTrue(all(p['url'].startswith('https://') for p in presets))

    def test_router_and_navigation_have_both_new_pages(self):
        route = self.read('webui/route.js')
        index = self.read('webui/index.html')
        for name in ('catalog', 'apps'):
            self.assertIn(f"page/{name}/{name}.html?raw", route)
            self.assertIn(f"page/{name}/{name}.js", route)
            self.assertIn(f'{name}: {{ html:', route)
            self.assertIn(f'page="{name}"', index)
            self.assertIn(f'page/{name}/{name}.css', self.read('webui/index.css'))
        self.assertEqual(len(re.findall(r'page="(?:home|catalog|apps|hosts|more)"', index)), 5)
        self.assertIn('<span>Rules</span>', index)

    def test_catalog_only_allows_static_preset_commands(self):
        src = self.read('webui/page/catalog/catalog.js')
        self.assertIn('PRESET_IDS.has(preset.id)', src)
        self.assertIn('textContent', src)
        self.assertNotIn('innerHTML', src)
        self.assertIn('source_catalog.sh', src)
        self.assertIn('confirmAction', src)
        self.assertIn('Update hosts', self.read('webui/page/catalog/catalog.html'))

    def test_tracker_controls_validate_package_and_confirm(self):
        src = self.read('webui/page/apps/apps.js')
        self.assertIn('PACKAGE_RE.test(selected)', src)
        self.assertIn('packages.includes(selected)', src)
        self.assertIn('previewLoadedFor !== pkg', src)
        self.assertIn('confirmAction', src)
        self.assertNotIn('innerHTML', src)
        self.assertIn('Only receiver components', src)

    def test_amoled_and_escape_helpers_integrated(self):
        self.assertIn('bindAppearanceControls', self.read('webui/page/more/more.js'))
        self.assertIn('applyAppearance()', self.read('webui/index.js'))
        self.assertIn('id="ui-black-bg-toggle"', self.read('webui/page/more/more.html'))
        self.assertIn('body[data-black-background="true"]', self.read('webui/page/catalog/catalog.css'))
        self.assertIn('escapeHtml(name || url)', self.read('webui/page/hosts/hosts.js'))
        self.assertIn('escapeHtml(domains.join', self.read('webui/page/home/home.js'))
        self.assertIn('escapeHtml(entry.message)', self.read('webui/page/more/more.js'))

if __name__ == '__main__': unittest.main(verbosity=2)
