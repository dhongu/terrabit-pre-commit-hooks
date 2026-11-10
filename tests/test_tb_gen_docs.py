#!/usr/bin/env python
"""Teste pentru tb_gen_docs.py și tb_module_sources.py (README.rst + index.html într-o trecere).

Rulează din rădăcina repo-ului de hook-uri (necesită pandoc, jinja2, docutils, markdown):

    python3 -m unittest tests/test_tb_gen_docs.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import tb_gen_docs, tb_gen_readme, tb_module_sources  # noqa: E402

try:
    tb_gen_readme.pandoc_executable()
    HAS_PANDOC = True
except tb_gen_readme.ReadmeError:
    HAS_PANDOC = False

MANIFEST = """{
    "name": "Demo %s",
    "author": "Terrabit",
    "license": "AGPL-3",
    "version": "19.0.1.0.0",
}
"""
ARGS = ["--org-name=terrabit-solutions", "--repo-name=bitshop", "--no-roadmap"]


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(content)


class TestModuleSources(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        write(os.path.join(self.root, "a", "__manifest__.py"), MANIFEST % "a")
        write(os.path.join(self.root, "b", "__manifest__.py"), '{"name": "B", "installable": False}')
        write(os.path.join(self.root, "c", "__manifest__.py"), MANIFEST % "c")
        os.makedirs(os.path.join(self.root, "notamodule"))

    def test_all_addons_skips_non_installable_and_non_modules(self):
        self.assertEqual([a[0] for a in tb_module_sources.all_addons(self.root)], ["a", "c"])

    def test_files_select_touched_modules(self):
        files = [os.path.join(self.root, "c", "readme", "USAGE.md")]
        self.assertEqual([a[0] for a in tb_module_sources.all_addons(self.root, files)], ["c"])

    def test_scripts_file_touches_all(self):
        files = [os.path.join(self.root, "scripts", "test_stats.json")]
        self.assertEqual([a[0] for a in tb_module_sources.all_addons(self.root, files)], ["a", "c"])

    def test_load_stats(self):
        self.assertEqual(tb_module_sources.load_stats(self.root), {})
        write(os.path.join(self.root, "scripts", "test_stats.json"), json.dumps({"addons": {"a": {"tests": 2}}}))
        self.assertEqual(tb_module_sources.load_stats(self.root), {"a": {"tests": 2}})

    def test_github_repo_prefers_arguments(self):
        self.assertEqual(tb_module_sources.github_repo(self.root, "o", "r"), ("o", "r"))


@unittest.skipUnless(HAS_PANDOC, "pandoc lipsește")
class TestGenDocs(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        for name in ("alpha", "beta"):
            write(os.path.join(self.root, name, "__manifest__.py"), MANIFEST % name)
            write(os.path.join(self.root, name, "readme", "DESCRIPTION.md"), f"{name} does something useful.\n")
            write(os.path.join(self.root, name, "readme", "USAGE.md"), "1. Open the menu.\n")

    def run_hook(self, *extra):
        return tb_gen_docs.main(["--addons-dir", self.root, *ARGS, *extra])

    def path(self, name, *parts):
        return os.path.join(self.root, name, *parts)

    def test_generates_readme_and_index(self):
        self.assertEqual(self.run_hook(), 0)
        for name in ("alpha", "beta"):
            self.assertTrue(os.path.isfile(self.path(name, "README.rst")))
            self.assertTrue(os.path.isfile(self.path(name, "static", "description", "index.html")))

    def test_same_output_as_separate_hooks(self):
        self.run_hook()
        with open(self.path("alpha", "README.rst"), encoding="utf8") as f:
            readme = f.read()
        with open(self.path("alpha", "static", "description", "index.html"), encoding="utf8") as f:
            index = f.read()
        os.remove(self.path("alpha", "README.rst"))
        os.remove(self.path("alpha", "static", "description", "index.html"))
        tb_gen_readme.main(["--addons-dir", self.root, *ARGS])
        tb_gen_docs.tb_gen_index.process(self.path("alpha"))
        with open(self.path("alpha", "README.rst"), encoding="utf8") as f:
            self.assertEqual(f.read(), readme)
        with open(self.path("alpha", "static", "description", "index.html"), encoding="utf8") as f:
            self.assertEqual(f.read(), index)

    def test_no_index_and_no_readme(self):
        self.run_hook("--no-index")
        self.assertTrue(os.path.isfile(self.path("alpha", "README.rst")))
        self.assertFalse(os.path.exists(self.path("alpha", "static")))
        os.remove(self.path("alpha", "README.rst"))
        self.run_hook("--no-readme")
        self.assertFalse(os.path.exists(self.path("alpha", "README.rst")))
        self.assertTrue(os.path.isfile(self.path("alpha", "static", "description", "index.html")))

    def test_both_disabled_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.run_hook("--no-readme", "--no-index")

    def test_files_limit_both_outputs(self):
        self.run_hook(self.path("beta", "readme", "USAGE.md"))
        self.assertTrue(os.path.isfile(self.path("beta", "README.rst")))
        self.assertTrue(os.path.isfile(self.path("beta", "static", "description", "index.html")))
        self.assertFalse(os.path.exists(self.path("alpha", "README.rst")))
        self.assertFalse(os.path.exists(self.path("alpha", "static")))

    def test_idempotent(self):
        self.run_hook()
        snapshot = {}
        for name in ("alpha", "beta"):
            for rel in (("README.rst",), ("static", "description", "index.html")):
                with open(self.path(name, *rel), encoding="utf8") as f:
                    snapshot[(name, rel)] = f.read()
        self.run_hook()
        for (name, rel), content in snapshot.items():
            with open(self.path(name, *rel), encoding="utf8") as f:
                self.assertEqual(f.read(), content)

    def test_readme_failure_gives_exit_code_1(self):
        write(self.path("alpha", "readme", "USAGE.rst"), "Usage\n=====\n")  # .md și .rst deodată
        self.assertEqual(self.run_hook(), 1)
        self.assertTrue(os.path.isfile(self.path("beta", "README.rst")))


if __name__ == "__main__":
    unittest.main()
