#!/usr/bin/env python
"""Teste pentru tb_gen_index.py: eticheta de găzduire din antetul paginii Apps Store.

Rulează din rădăcina repo-ului de hook-uri:

    python3 -m unittest tests/test_tb_gen_index.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import tb_gen_index  # noqa: E402

MANIFEST = {"version": "19.0.1.0.0", "category": "Tools", "license": "OPL-1"}


class TestHostingBadge(unittest.TestCase):
    def _addon(self, with_init):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp))
        with open(os.path.join(tmp, "__manifest__.py"), "w", encoding="utf-8") as handle:
            handle.write(repr(MANIFEST))
        if with_init:
            open(os.path.join(tmp, "__init__.py"), "w", encoding="utf-8").close()
        return tmp

    def test_python_addon_is_not_online(self):
        addon = self._addon(with_init=True)
        self.assertFalse(tb_gen_index.is_data_only(addon))
        badges = tb_gen_index.build_badges(MANIFEST, "en", data_only=tb_gen_index.is_data_only(addon))
        self.assertIn("Odoo.sh &bull; On-premise", badges)
        self.assertNotIn("Odoo Online", badges)

    def test_data_only_addon_is_online(self):
        addon = self._addon(with_init=False)
        self.assertTrue(tb_gen_index.is_data_only(addon))
        for lang in ("en", "ro"):
            badges = tb_gen_index.build_badges(MANIFEST, lang, data_only=True)
            self.assertIn("Odoo Online &bull; Odoo.sh", badges)


class TestStoreDesign(unittest.TestCase):
    """Elementele preluate de pe paginile bune din store (09.11.2026)."""

    def test_feature_icon_earliest_keyword_wins(self):
        self.assertEqual(tb_gen_index.feature_icon("Additional vehicle data: serial number"), "car")
        self.assertEqual(tb_gen_index.feature_icon("Generate the <strong>e-Factura</strong> XML"), "university")
        self.assertEqual(tb_gen_index.feature_icon("Steps: ordered activities"), "check")

    def test_marker_only_on_plain_titles(self):
        plain = tb_gen_index.marker_title("Key Features")
        self.assertTrue(plain.startswith("Key <span"))
        self.assertIn(tb_gen_index.MARKER_URL, plain)
        self.assertEqual(tb_gen_index.marker_title("Use <code>x</code>"), "Use <code>x</code>")

    def test_headings(self):
        out = tb_gen_index.style_headings("<h2>Key Features</h2><h3>Details</h3>")
        self.assertIn("Caveat", out)
        self.assertIn("border-left-width:4px", out)
        self.assertNotIn("border-left:", out)

    def test_gallery_numbers_lone_images(self):
        html = '<p><img alt="First" src="a.png" /></p><p>Text <img alt="x" src="i.png"/></p><p><img alt="Second" src="b.png"/></p>'
        out = tb_gen_index.style_gallery(html)
        self.assertIn(">1</span>", out)
        self.assertIn(">2</span>", out)
        self.assertIn("First", out)
        self.assertIn('<p>Text <img alt="x" src="i.png"/></p>', out)

    def test_hero_gradient_keeps_solid_fallback(self):
        bg = tb_gen_index.HERO_BG % tb_gen_index.TB
        self.assertTrue(bg.startswith("background-color:#006F42;background-image:"))
        self.assertNotIn("%%", bg)


if __name__ == "__main__":
    unittest.main()
