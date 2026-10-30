#!/usr/bin/env python
"""Teste pentru hook-ul check_module_icon.py.

Ruleaza din radacina repo-ului de hook-uri:

    python3 tests/test_check_module_icon.py
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import check_module_icon  # noqa: E402

MANIFEST = '{\n    "name": "%s",\n    "installable": %s,\n%s}\n'
IMAGES = '    "images": ["static/description/main_screenshot.png"],\n'


class TestCheckModuleIcon(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        # Bannerul comun, in modulul deltatech din acelasi repo
        self.make_module("deltatech", banner=b"banner comun deltatech")

    def tearDown(self):
        shutil.rmtree(self.root)

    def make_module(self, name, icon=b"iconita proprie", banner=b"banner propriu", banner_json=True, images=True):
        module_dir = os.path.join(self.root, name)
        description = os.path.join(module_dir, "static", "description")
        os.makedirs(description)
        with open(os.path.join(module_dir, "__manifest__.py"), "w") as f:
            f.write(MANIFEST % (name, "True", IMAGES if images else ""))
        for file_name, content in (("icon.png", icon), ("main_screenshot.png", banner)):
            if content is not None:
                with open(os.path.join(description, file_name), "wb") as f:
                    f.write(content)
        if banner_json:
            with open(os.path.join(description, "banner.json"), "w") as f:
                f.write('{"title": "%s"}\n' % name)
        return os.path.join(module_dir, "__manifest__.py")

    def run_hook(self, *manifests):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_module_icon.main(list(manifests))
        return code, out.getvalue()

    def test_modul_curat(self):
        self.assertEqual(self.run_hook(self.make_module("mod_ok"))[0], 0)

    def test_modulul_sursa_are_bannerul_comun(self):
        self.assertEqual(self.run_hook(os.path.join(self.root, "deltatech", "__manifest__.py"))[0], 0)

    def test_iconita_lipsa(self):
        code, out = self.run_hook(self.make_module("mod_x", icon=None))
        self.assertEqual(code, 1)
        self.assertIn("lipseste", out)

    def test_iconita_generica(self):
        with mock_hashes(check_module_icon, icons={check_module_icon.hashlib.sha256(b"rotite").hexdigest()}):
            code, out = self.run_hook(self.make_module("mod_x", icon=b"rotite"))
        self.assertEqual(code, 1)
        self.assertIn("iconita generica", out)

    def test_banner_comun_copiat(self):
        code, out = self.run_hook(self.make_module("mod_x", banner=b"banner comun deltatech"))
        self.assertEqual(code, 1)
        self.assertIn("bannerul comun", out)

    def test_banner_comun_cunoscut_fara_modulul_deltatech(self):
        shutil.rmtree(os.path.join(self.root, "deltatech"))
        with mock_hashes(check_module_icon, banners={check_module_icon.hashlib.sha256(b"banner 19").hexdigest()}):
            code, out = self.run_hook(self.make_module("mod_x", banner=b"banner 19"))
        self.assertEqual(code, 1)
        self.assertIn("bannerul comun", out)

    def test_fara_banner_json(self):
        code, out = self.run_hook(self.make_module("mod_x", banner_json=False))
        self.assertEqual(code, 1)
        self.assertIn("banner.json", out)

    def test_fara_cheia_images(self):
        code, out = self.run_hook(self.make_module("mod_x", images=False))
        self.assertEqual(code, 1)
        self.assertIn("'images'", out)

    def test_modul_neinstalabil_ignorat(self):
        manifest = self.make_module("mod_x", icon=None, banner_json=False)
        with open(manifest, "w") as f:
            f.write(MANIFEST % ("mod_x", "False", ""))
        self.assertEqual(self.run_hook(manifest)[0], 0)


@contextlib.contextmanager
def mock_hashes(module, icons=None, banners=None):
    old = module.GENERIC_ICONS, module.GENERIC_BANNERS
    module.GENERIC_ICONS = icons or old[0]
    module.GENERIC_BANNERS = banners or old[1]
    try:
        yield
    finally:
        module.GENERIC_ICONS, module.GENERIC_BANNERS = old


if __name__ == "__main__":
    unittest.main()
