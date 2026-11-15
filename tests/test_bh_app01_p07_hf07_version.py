"""HF07: real UX02/UX05 version checks against independent synthetic fixtures.

No Android, GitHub, network or project tree modification. These tests execute
both regressions with coherent and deliberately inconsistent version pairs.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    f=ROOT/'tests'/name
    spec=importlib.util.spec_from_file_location('bh_hf07_'+name.removesuffix('.py'),f)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class HF07(unittest.TestCase):
    @staticmethod
    def fixture(root, suffix, code):
        files={
            'module/module.prop': f'id=bindhosts\nversion=v2.1.5-tg.0.{suffix}\nversionCode={code}\n',
            'webui/route.js': 'catalogHtml appsHtml activityHtml activityModule name === \'activity\' ? \'more\' : name',
            'update.json': '{"version":"v2.1.5-tg.0.11"}',
            'module/ux05_diagnostics.sh': '# bounded diagnostics, no monitor autoenable',
        }
        for path in ('.github/workflows/bindhosts-ux-ci.yml',
                     '.github/workflows/trackerguard-ci.yml',
                     '.github/workflows/release.yml'):
            files[path]='test_ux05_diagnostics.py test_ux05_contract.py'
        for path,body in files.items():
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)

    def run_contract(self, source, klass, name, root):
        with patch.object(source,'ROOT',root):
            getattr(klass(),name)()

    def test_ux02_versions_11_12_and_13_and_invalid_pairs(self):
        m=module('test_webui_ux02.py')
        for suffix,code in [(11,21611),(12,21612),(13,21613)]:
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as t:
                root=Path(t);self.fixture(root,suffix,code)
                self.run_contract(m,m.UX02Contract,'test_ux01_features_not_dropped',root)
        for suffix,code in [(12,21611),(12,21613),(10,21610)]:
            with self.subTest(bad=(suffix,code)),tempfile.TemporaryDirectory() as t:
                root=Path(t);self.fixture(root,suffix,code)
                with self.assertRaises(AssertionError):
                    self.run_contract(m,m.UX02Contract,'test_ux01_features_not_dropped',root)

    def test_ux05_versions_11_12_13_and_invalid_pairs(self):
        m=module('test_ux05_contract.py')
        for suffix,code in [(11,21611),(12,21612),(13,21613)]:
            with self.subTest(suffix=suffix),tempfile.TemporaryDirectory() as t:
                root=Path(t);self.fixture(root,suffix,code)
                self.run_contract(m,m.UX05Contract,'test_release_ci_and_unchanged_trackerguard_defaults',root)
        for suffix,code in [(12,21611),(12,21613),(10,21610)]:
            with self.subTest(bad=(suffix,code)),tempfile.TemporaryDirectory() as t:
                root=Path(t);self.fixture(root,suffix,code)
                with self.assertRaises(AssertionError):
                    self.run_contract(m,m.UX05Contract,'test_release_ci_and_unchanged_trackerguard_defaults',root)

    def test_tests_preserve_security_and_release_contracts(self):
        ux02=(ROOT/'tests/test_webui_ux02.py').read_text()
        ux05=(ROOT/'tests/test_ux05_contract.py').read_text()
        self.assertIn('hosts_secure_io.js',ux02)
        self.assertIn('monitor enable',ux05)
        self.assertIn("read('update.json')",ux05)
        self.assertIn('21600+int(release.group(1))',ux02)
        self.assertIn('21600+int(release.group(1))',ux05)

if __name__=='__main__':unittest.main()
