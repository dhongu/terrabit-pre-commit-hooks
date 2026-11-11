#!/usr/bin/env python
"""Teste pentru hook-ul check_fisa_consultant.py.

Ruleaza din radacina repo-ului de hook-uri:

    python3 -m unittest tests/test_check_fisa_consultant.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "terrabit_pre_commit_hooks",
    "check_fisa_consultant.py",
)

ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(
    {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
)


class TestCheckFisaConsultant(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git("init", "-q")
        # modul existent fara fisa, deja in HEAD
        self.module("vechi_fara_fisa")
        # modul existent cu fisa
        self.module("vechi_cu_fisa", fisa=True)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.repo)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, env=ENV, check=True)

    def module(self, name, fisa=False, installable=True, sheet=None, screenshots=False):
        os.makedirs(os.path.join(self.repo, name, "readme"))
        manifest = {"name": name, "installable": installable}
        if sheet is not None:
            manifest["consultant_sheet"] = sheet
        with open(os.path.join(self.repo, name, "__manifest__.py"), "w") as f:
            f.write(repr(manifest))
        if screenshots:
            os.makedirs(os.path.join(self.repo, name, "readme", "screenshots"))
            with open(os.path.join(self.repo, name, "readme", "screenshots", "a.png"), "w") as f:
                f.write("x")
        if fisa:
            with open(os.path.join(self.repo, name, "readme", "FISA_CONSULTANT.md"), "w") as f:
                f.write("# Fisa\n")

    def run_hook(self, *modules):
        args = [f"{m}/__manifest__.py" for m in modules]
        return subprocess.run(
            [sys.executable, SCRIPT, *args], cwd=self.repo, env=ENV, capture_output=True, text=True, check=False
        )

    def test_existent_fara_fisa_doar_avertizeaza(self):
        result = self.run_hook("vechi_fara_fisa", "vechi_cu_fisa")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Avertisment", result.stdout)
        self.assertIn("vechi_fara_fisa", result.stdout)
        self.assertNotIn("vechi_cu_fisa", result.stdout)

    def test_modul_nou_fara_fisa_pica(self):
        self.module("nou")
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("module noi", result.stdout)

    def test_modul_nou_cu_fisa_trece(self):
        self.module("nou", fisa=True)
        self.git("add", "nou")
        self.assertEqual(self.run_hook("nou").returncode, 0)

    def test_modul_nou_neinstalabil_ignorat(self):
        self.module("nou", installable=False)
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_sheet_none_nou_fara_fisa_trece(self):
        self.module("nou", sheet="none")
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")

    def test_sheet_none_existent_nu_e_listat(self):
        self.module("tehnic", sheet="none")
        self.git("add", "tehnic")
        self.git("commit", "-q", "-m", "tehnic")
        result = self.run_hook("tehnic")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_sheet_none_cu_fisa_avertizeaza(self):
        self.module("tehnic", fisa=True, sheet="none")
        result = self.run_hook("tehnic")
        self.assertEqual(result.returncode, 0)
        self.assertIn("sheet=none", result.stdout.replace("consultant_", ""))

    def test_sheet_full_nou_fara_fisa_pica(self):
        self.module("nou", sheet="full")
        self.git("add", "nou")
        self.assertEqual(self.run_hook("nou").returncode, 1)

    def test_sheet_full_fara_capturi_avertizeaza(self):
        self.module("nou", fisa=True, sheet="full")
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 0)
        self.assertIn("capturi", result.stdout)

    def test_sheet_full_cu_capturi_trece_curat(self):
        self.module("nou", fisa=True, sheet="full", screenshots=True)
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_sheet_simple_fara_capturi_trece_curat(self):
        self.module("nou", fisa=True, sheet="simple")
        self.git("add", "nou")
        result = self.run_hook("nou")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_sheet_invalid_pica(self):
        self.module("vechi_fara_fisa2", sheet="complet")
        result = self.run_hook("vechi_fara_fisa2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalida", result.stdout)

    def test_repo_fara_commit(self):
        """Repo fara commit (HEAD inexistent): toate modulele sunt noi."""
        shutil.rmtree(os.path.join(self.repo, ".git"))
        self.git("init", "-q")
        result = self.run_hook("vechi_fara_fisa")
        self.assertEqual(result.returncode, 1, result.stdout)


if __name__ == "__main__":
    unittest.main()
