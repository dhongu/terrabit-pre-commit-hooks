#!/usr/bin/env python3
# ©  2026 Terrabit
# See README.rst file on addons root folder for license details
"""Adaugă badge-ul „N automated tests · X% code coverage” în README.rst al modulelor.

Cifrele vin din ``scripts/test_stats.json`` al suitei (scris de ``tb-test-stats``), aceleași
ca în panoul de calitate al paginii Apps Store (``tb-gen-index``). Acoperirea apare doar de
la ``COVERAGE_MIN`` în sus; sub prag, badge-ul arată doar numărul de teste.

Ca la ``tb-fisa-badge``, README.rst e generat de ``oca-gen-addon-readme``, deci badge-ul se
pune după generare, de acest hook manual:

- modul cu teste: ``|badge_tests|`` lângă celelalte badge-uri, cu link la pagina modulului
  din Codecov (când arată acoperirea) sau la folderul ``tests/`` de pe GitHub;
- modul fără teste (sau fără intrare în ``test_stats.json``): badge-ul e scos.

Idempotent. Fără ``scripts/test_stats.json`` hook-ul nu face nimic.

Rulare::

    pre-commit run tb-test-stats --hook-stage manual
    pre-commit run tb-test-badge --hook-stage manual
"""

import argparse
import json
import os
import sys
from urllib.parse import quote

from terrabit_pre_commit_hooks.tb_fisa_badge import add_badge, repo_from_git, strip_badge
from terrabit_pre_commit_hooks.tb_gen_index import COVERAGE_MIN, TEST_STATS

TOKEN = "|badge_tests|"
DEFINITION_START = ".. |badge_tests| image::"
COLOR = "2ea44f"


def badge_text(stats):
    """Textul badge-ului, sau None dacă modulul nu are teste."""
    tests = stats.get("tests") or 0
    if not tests:
        return None
    text = f"{tests} automated test" + ("" if tests == 1 else "s")
    coverage = stats.get("coverage")
    if coverage is not None and coverage >= COVERAGE_MIN:
        text += f" · {int(coverage)}% code coverage"
    return text


def shields_url(text):
    """Badge static shields.io fără etichetă: `-` și `_` se dublează, restul se codifică."""
    message = text.replace("-", "--").replace("_", "__")
    return f"https://img.shields.io/badge/-{quote(message, safe='')}-{COLOR}.png"


def badge_target(stats, org, repo, branch, addon_name):
    coverage = stats.get("coverage")
    if coverage is not None and coverage >= COVERAGE_MIN:
        return f"https://app.codecov.io/gh/{org}/{repo}/tree/{branch}/{addon_name}"
    return f"https://github.com/{org}/{repo}/tree/{branch}/{addon_name}/tests"


def process_addon(addon_dir, addon_name, stats, org, repo, branch):
    readme = os.path.join(addon_dir, "README.rst")
    if not os.path.isfile(readme):
        return False
    with open(readme, encoding="utf8") as f:
        original = f.read()
    lines = strip_badge(original.split("\n"), token=TOKEN, definition_start=DEFINITION_START)
    text = badge_text(stats) if stats else None
    if text:
        with_badge = add_badge(
            lines,
            badge_target(stats, org, repo, branch, addon_name),
            token=TOKEN,
            definition_start=DEFINITION_START,
            image=shields_url(text),
            alt=text,
        )
        if with_badge is None:
            sys.stderr.write(f"{addon_name}: README.rst fără linie de badge-uri, sărit\n")
            return False
        lines = with_badge
    content = "\n".join(lines)
    if content == original:
        return False
    with open(readme, "w", encoding="utf8") as f:
        f.write(content)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--addons-dir", default=".")
    parser.add_argument("--org", help="organizația GitHub (implicit: din remote-ul origin)")
    parser.add_argument("--repo", help="repo-ul GitHub (implicit: din remote-ul origin)")
    parser.add_argument("--branch", default="19.0")
    args = parser.parse_args()

    stats_path = os.path.join(args.addons_dir, TEST_STATS)
    if not os.path.isfile(stats_path):
        sys.stderr.write(f"{stats_path} lipsește: rulați întâi tb-test-stats\n")
        return 0
    with open(stats_path, encoding="utf8") as f:
        addons_stats = json.load(f).get("addons", {})

    org, repo = args.org, args.repo
    if not (org and repo):
        git_org, git_repo = repo_from_git(args.addons_dir)
        org, repo = org or git_org, repo or git_repo
    if not (org and repo):
        parser.error("nu pot determina repo-ul GitHub: dați --org și --repo")

    changed = []
    for name in sorted(os.listdir(args.addons_dir)):
        addon_dir = os.path.join(args.addons_dir, name)
        if os.path.isfile(os.path.join(addon_dir, "__manifest__.py")):
            if process_addon(addon_dir, name, addons_stats.get(name), org, repo, args.branch):
                changed.append(name)
    for name in changed:
        sys.stdout.write(f"{name}: badge teste actualizat\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
