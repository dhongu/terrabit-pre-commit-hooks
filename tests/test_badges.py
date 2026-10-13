#!/usr/bin/env python
"""Teste pentru tb_test_badge.py și tb_fisa_badge.py (badge-urile adăugate în README.rst).

Rulează din rădăcina repo-ului de hook-uri:

    python3 -m unittest tests/test_badges.py

Cazul principal: cele două hook-uri pun fiecare câte un badge pe aceeași linie de badge-uri,
iar rulările repetate, în orice ordine, nu trebuie să dubleze sau să piardă vreun token.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import tb_fisa_badge, tb_test_badge  # noqa: E402

README = """=====
Addon
=====

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/github-org%2Frepo-lightgray.png?logo=github
    :target: https://github.com/org/repo/tree/19.0/addon
    :alt: org/repo

|badge1| |badge2|

Description.
"""


class TestBadges(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addon = os.path.join(self.root, "addon")
        os.makedirs(os.path.join(self.addon, "readme"))
        with open(os.path.join(self.addon, "__manifest__.py"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.addon, "README.rst"), "w") as f:
            f.write(README)
        os.makedirs(os.path.join(self.root, "scripts"))
        self.write_stats({"tests": 26, "coverage": 88.4})

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_stats(self, stats):
        with open(os.path.join(self.root, "scripts", "test_stats.json"), "w") as f:
            json.dump({"addons": {"addon": stats} if stats else {}}, f)

    def readme(self):
        with open(os.path.join(self.addon, "README.rst")) as f:
            return f.read()

    def badges_line(self):
        return next(line for line in self.readme().split("\n") if line.startswith("|badge1|"))

    def run_tests_badge(self):
        sys.argv = ["tb-test-badge", f"--addons-dir={self.root}", "--org=org", "--repo=repo"]
        tb_test_badge.main()

    def run_fisa_badge(self):
        sys.argv = ["tb-fisa-badge", f"--addons-dir={self.root}", "--org=org", "--repo=repo"]
        tb_fisa_badge.main()

    def add_fisa(self):
        with open(os.path.join(self.addon, "readme", "FISA_CONSULTANT.md"), "w") as f:
            f.write("# Fișă\n")

    def test_badge_with_coverage(self):
        self.run_tests_badge()
        content = self.readme()
        self.assertEqual(self.badges_line(), "|badge1| |badge2| |badge_tests|")
        self.assertIn("-26%20automated%20tests%20%C2%B7%2088%25%20code%20coverage-2ea44f.png", content)
        self.assertIn(":target: https://app.codecov.io/gh/org/repo/tree/19.0/addon", content)
        self.assertIn(":alt: 26 automated tests · 88% code coverage", content)

    def test_coverage_below_threshold_shows_tests_only(self):
        self.write_stats({"tests": 3, "coverage": 69.9})
        self.run_tests_badge()
        content = self.readme()
        self.assertIn(":alt: 3 automated tests\n", content)
        self.assertNotIn("coverage", content)
        self.assertIn(":target: https://github.com/org/repo/tree/19.0/addon/tests", content)

    def test_idempotent(self):
        self.run_tests_badge()
        first = self.readme()
        self.run_tests_badge()
        self.assertEqual(self.readme(), first)

    def test_updated_figures_replace_old_badge(self):
        self.run_tests_badge()
        self.write_stats({"tests": 30, "coverage": 91.0})
        self.run_tests_badge()
        content = self.readme()
        self.assertEqual(content.count(".. |badge_tests| image::"), 1)
        self.assertIn(":alt: 30 automated tests · 91% code coverage", content)

    def test_removed_without_tests(self):
        self.run_tests_badge()
        self.write_stats(None)
        self.run_tests_badge()
        self.assertEqual(self.readme(), README)

    def test_with_fisa_any_order(self):
        self.add_fisa()
        self.run_fisa_badge()
        self.run_tests_badge()
        self.assertEqual(self.badges_line(), "|badge1| |badge2| |badge_fisa| |badge_tests|")
        both = self.readme()
        # rulări repetate, în ambele ordini: niciun token dublat, nimic pierdut
        self.run_fisa_badge()
        self.run_tests_badge()
        self.run_tests_badge()
        self.run_fisa_badge()
        content = self.readme()
        line = self.badges_line()
        self.assertEqual(line.count("|badge_fisa|"), 1)
        self.assertEqual(line.count("|badge_tests|"), 1)
        self.assertEqual(content.count(".. |badge_fisa| image::"), 1)
        self.assertEqual(content.count(".. |badge_tests| image::"), 1)
        # ordinea e fixă (EXTRA_ORDER): fișierul nu se mai schimbă după prima rulare
        self.assertEqual(content, both)
        self.assertLess(content.index(".. |badge_fisa| image::"), content.index(".. |badge_tests| image::"))

    def test_tests_badge_first_then_fisa(self):
        self.run_tests_badge()
        self.add_fisa()
        self.run_fisa_badge()
        self.assertEqual(self.badges_line(), "|badge1| |badge2| |badge_fisa| |badge_tests|")
        content = self.readme()
        self.assertLess(content.index(".. |badge_fisa| image::"), content.index(".. |badge_tests| image::"))

    def test_fisa_removed_keeps_tests_badge(self):
        self.add_fisa()
        self.run_fisa_badge()
        self.run_tests_badge()
        os.remove(os.path.join(self.addon, "readme", "FISA_CONSULTANT.md"))
        self.run_fisa_badge()
        self.assertEqual(self.badges_line(), "|badge1| |badge2| |badge_tests|")
        self.assertNotIn("badge_fisa", self.readme())


if __name__ == "__main__":
    unittest.main()
