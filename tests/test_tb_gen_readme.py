#!/usr/bin/env python
"""Teste pentru tb_gen_readme.py (README.rst generat din readme/*.md, cu badge-urile incluse).

Rulează din rădăcina repo-ului de hook-uri (necesită pandoc, jinja2 și docutils):

    python3 -m unittest tests/test_tb_gen_readme.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import tb_gen_readme  # noqa: E402

try:
    tb_gen_readme.pandoc_executable()
    HAS_PANDOC = True
except tb_gen_readme.ReadmeError:
    HAS_PANDOC = False

MANIFEST = """{
    "name": "Demo Module",
    "author": "Terrabit, Someone",
    "license": "AGPL-3",
    "version": "19.0.1.0.0",
    "maintainers": ["dhongu"],
}
"""
ARGS = ["--org-name=terrabit-solutions", "--repo-name=bitshop", "--no-roadmap"]


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(content)


@unittest.skipUnless(HAS_PANDOC, "pandoc lipsește")
class TestGenReadme(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.addon = os.path.join(self.root, "demo")
        write(os.path.join(self.addon, "__manifest__.py"), MANIFEST)
        write(os.path.join(self.addon, "readme", "DESCRIPTION.md"), "Does something useful.\n")
        write(os.path.join(self.addon, "readme", "USAGE.md"), "1. Open the menu.\n")
        write(os.path.join(self.addon, "readme", "HISTORY.md"), "## 19.0.1.0.0 (2026-11-10)\n\n- First version.\n")
        write(os.path.join(self.addon, "readme", "CONTRIBUTORS.md"), "- Someone\n")

    def run_hook(self, *extra):
        return tb_gen_readme.main(["--addons-dir", self.root, *ARGS, *extra])

    def readme(self):
        with open(os.path.join(self.addon, "README.rst"), encoding="utf8") as f:
            return f.read()

    def add_stats(self, tests=3, coverage=91.0):
        write(
            os.path.join(self.root, "scripts", "test_stats.json"),
            json.dumps({"addons": {"demo": {"tests": tests, "coverage": coverage}}}),
        )

    def test_sections_and_footer(self):
        self.assertEqual(self.run_hook(), 0)
        text = self.readme()
        self.assertTrue(text.startswith("===========\nDemo Module\n===========\n"))
        for section in ("Usage\n=====", "Changelog\n=========", "Bug Tracker", "Credits", "Contributors\n------------"):
            self.assertIn(section, text)
        self.assertIn("* Terrabit\n* Someone", text)
        self.assertIn("terrabit-solutions/bitshop <https://github.com/terrabit-solutions/bitshop/tree/19.0/demo>", text)

    def test_badges_present(self):
        write(os.path.join(self.addon, "readme", "FISA_CONSULTANT.md"), "# Fișă\n")
        self.add_stats()
        self.run_hook()
        text = self.readme()
        self.assertIn(".. |badge_fisa| image::", text)
        self.assertIn(".. |badge_tests| image::", text)
        self.assertIn("|badge1| |badge2| |badge3| |badge_fisa| |badge_tests|", text)
        self.assertIn("3 automated tests · 91% code coverage", text)
        self.assertIn("blob/19.0/demo/readme/FISA_CONSULTANT.md", text)

    def test_module_without_fisa(self):
        self.add_stats()
        self.run_hook()
        text = self.readme()
        self.assertNotIn("badge_fisa", text)
        self.assertIn("|badge1| |badge2| |badge3| |badge_tests|", text)

    def test_module_without_tests(self):
        write(os.path.join(self.addon, "readme", "FISA_CONSULTANT.md"), "# Fișă\n")
        self.add_stats(tests=0)
        self.run_hook()
        text = self.readme()
        self.assertNotIn("badge_tests", text)
        self.assertIn("|badge1| |badge2| |badge3| |badge_fisa|", text)

    def test_no_stats_file(self):
        self.run_hook()
        self.assertNotIn("badge_tests", self.readme())

    def test_skipped_title_levels_are_normalized(self):
        # `###` direct sub `Usage`, apoi `##` în Changelog: docutils pică pe „skip from level 2 to 4”
        write(os.path.join(self.addon, "readme", "USAGE.md"), "### Setup\n\nText.\n\n##### Deep\n\nMore.\n")
        write(os.path.join(self.addon, "readme", "CONFIGURE.md"), "#### Alone\n\nText.\n")
        self.assertEqual(self.run_hook(), 0)
        self.assertIsNone(tb_gen_readme.check_rst(self.readme()))
        self.assertIn("Setup\n-----", self.readme())

    def test_description_headings_do_not_break_sections(self):
        write(
            os.path.join(self.addon, "readme", "DESCRIPTION.md"),
            "Intro.\n\nOverview\n--------\n\nText.\n\n### Detail\n\nMore.\n",
        )
        write(os.path.join(self.addon, "readme", "USAGE.md"), "### Setup\n\nText.\n\n##### Deep\n\nMore.\n")
        self.assertEqual(self.run_hook(), 0)
        text = self.readme()
        self.assertIsNone(tb_gen_readme.check_rst(text))
        self.assertIn("**Overview**", text)
        self.assertIn("Usage\n=====", text)

    def test_setext_to_atx(self):
        self.assertEqual(tb_gen_readme.setext_to_atx("Title\n=====\n\nSub\n---\n\n- item\n---\n"), "# Title\n\n## Sub\n\n- item\n---\n")

    def test_valid_titles_are_left_alone(self):
        """README-ul care trece de docutils nu trece prin normalizare (ca să nu apară diferențe)."""
        write(os.path.join(self.addon, "readme", "USAGE.md"), "## Setup\n\nText.\n\n### Deep\n\nMore.\n")
        self.run_hook()
        manifest = tb_gen_readme.read_manifest(self.addon)[1]
        native = tb_gen_readme.render(
            self.addon, "demo", manifest, "sha256:x", "o", "r", "19.0", None, roadmap=False, normalize=False
        )
        self.assertIsNone(tb_gen_readme.check_rst(native))
        self.assertIn("Setup\n-----\n\nText.\n\nDeep\n~~~~", self.readme())

    def test_normalize_headings_ignores_code_fences(self):
        text = "#### A\n\n```\n# not a heading\n```\n\n###### B\n"
        self.assertEqual(tb_gen_readme.normalize_headings(text), "## A\n\n```\n# not a heading\n```\n\n### B\n")

    def test_idempotent(self):
        write(os.path.join(self.addon, "readme", "FISA_CONSULTANT.md"), "# Fișă\n")
        self.add_stats()
        self.run_hook()
        first = self.readme()
        mtime = os.path.getmtime(os.path.join(self.addon, "README.rst"))
        self.assertEqual(self.run_hook(), 0)
        self.assertEqual(self.readme(), first)
        self.assertEqual(os.path.getmtime(os.path.join(self.addon, "README.rst")), mtime)

    def test_badge_removed_when_fisa_deleted(self):
        fisa = os.path.join(self.addon, "readme", "FISA_CONSULTANT.md")
        write(fisa, "# Fișă\n")
        self.run_hook()
        os.remove(fisa)
        self.run_hook()
        self.assertNotIn("badge_fisa", self.readme())

    def test_digest_kept_unless_updated(self):
        self.run_hook()
        first = self.readme()
        write(os.path.join(self.addon, "readme", "USAGE.md"), "1. Changed.\n")
        self.run_hook()
        self.assertEqual(tb_gen_readme.existing_digest(os.path.join(self.addon, "README.rst")), tb_gen_readme.DIGEST_RE.search(first).group(1))
        self.run_hook("--update-digest")
        self.assertNotIn(tb_gen_readme.DIGEST_RE.search(first).group(1), self.readme())

    def test_files_limit_the_modules(self):
        other = os.path.join(self.root, "other")
        write(os.path.join(other, "__manifest__.py"), MANIFEST)
        write(os.path.join(other, "readme", "DESCRIPTION.md"), "Other.\n")
        self.run_hook(os.path.join(self.addon, "readme", "USAGE.md"))
        self.assertTrue(os.path.isfile(os.path.join(self.addon, "README.rst")))
        self.assertFalse(os.path.exists(os.path.join(other, "README.rst")))

    def test_module_without_description_is_skipped(self):
        os.remove(os.path.join(self.addon, "readme", "DESCRIPTION.md"))
        self.run_hook()
        self.assertFalse(os.path.exists(os.path.join(self.addon, "README.rst")))

    def test_addons_from_files(self):
        self.assertEqual(tb_gen_readme.addons_from_files(self.root, [os.path.join(self.root, "a", "readme", "X.md")]), {"a"})
        self.assertIsNone(tb_gen_readme.addons_from_files(self.root, [os.path.join(self.root, "scripts", "test_stats.json")]))


if __name__ == "__main__":
    unittest.main()
