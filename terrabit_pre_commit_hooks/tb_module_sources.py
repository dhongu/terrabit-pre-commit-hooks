#!/usr/bin/env python3
# ©  2026 Terrabit
# See README.rst file on addons root folder for license details
"""Stratul comun al generatoarelor de documentație: ce module se procesează și din ce surse.

Folosit de ``tb-gen-readme`` (README.rst) și de ``tb-gen-docs`` (README.rst + index.html):

- ``all_addons`` / ``addons_from_files``: modulele instalabile ale suitei, sau doar cele atinse
  de fișierele date de pre-commit (un fișier din ``scripts/`` le atinge pe toate);
- ``load_stats``: intrările din ``scripts/test_stats.json`` (scris de ``tb-test-stats``);
- ``github_repo``: (org, repo) din argumente sau din remote-ul ``origin``.
"""

import ast
import json
import os

from terrabit_pre_commit_hooks.tb_fisa_badge import repo_from_git

MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py", "__terp__.py")
TEST_STATS = os.path.join("scripts", "test_stats.json")


def read_manifest(addon_dir):
    """(cale, manifest) al modulului, sau (None, None) dacă directorul nu e modul."""
    for name in MANIFEST_NAMES:
        path = os.path.join(addon_dir, name)
        if os.path.isfile(path):
            with open(path, encoding="utf8") as f:
                return path, ast.literal_eval(f.read())
    return None, None


def addons_from_files(addons_dir, files):
    """Modulele atinse de fișierele date; un fișier din ``scripts/`` (statistici) le atinge pe toate."""
    names = set()
    root = os.path.abspath(addons_dir)
    for file in files:
        rel = os.path.relpath(os.path.abspath(file), root)
        top = rel.split(os.sep, 1)[0]
        if top == "scripts":
            return None
        if top != os.pardir:
            names.add(top)
    return names


def all_addons(addons_dir, files=None):
    """(nume, director, manifest) ale modulelor instalabile; cu ``files``, doar cele atinse."""
    selected = addons_from_files(addons_dir, files) if files else None
    for name in sorted(os.listdir(addons_dir)):
        if selected is not None and name not in selected:
            continue
        addon_dir = os.path.join(addons_dir, name)
        if os.path.isdir(addon_dir):
            manifest = read_manifest(addon_dir)[1]
            if manifest is not None and manifest.get("installable", True):
                yield name, addon_dir, manifest


def load_stats(addons_dir):
    """{modul: {tests, coverage, lines}} din ``scripts/test_stats.json``; gol dacă lipsește."""
    path = os.path.join(addons_dir, TEST_STATS)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf8") as f:
        return json.load(f).get("addons", {})


def github_repo(addons_dir, org=None, repo=None):
    """(org, repo): cele date, completate din remote-ul origin; (None, None) dacă nu se află."""
    if not (org and repo):
        git_org, git_repo = repo_from_git(addons_dir)
        org, repo = org or git_org, repo or git_repo
    return (org, repo) if org and repo else (None, None)
