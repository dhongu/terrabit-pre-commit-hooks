#!/usr/bin/env python
"""Verifica faptul ca modulele Odoo au fisa consultant (readme/FISA_CONSULTANT.md).

Pentru fiecare __manifest__.py primit ca argument (modulele instalabile):

- modul NOU (manifestul nu exista in HEAD, deci e adaugat in acest commit):
  fara fisa, hook-ul pica;
- modul EXISTENT fara fisa: hook-ul doar avertizeaza, fara sa pice, ca lista
  modulelor fara fisa sa ramana vizibila fara sa blocheze modificarile lor.

In CI (`pre-commit run --all-files`) toate manifestele sunt deja in HEAD, deci
hook-ul doar avertizeaza.

Fisa se face cu skill-ul `fisa-completa` (Mentor). Un modul mutat sau migrat
(manifest nou pe alta cale) e tratat ca modul nou; daca fisa vine intr-un
commit ulterior, se poate sari hook-ul: `SKIP=check-fisa-consultant git commit`.

Hook-ul `check-fisa-consultant` din dhongu/terrabit-pre-commit-hooks.
"""

import ast
import os
import subprocess
import sys

FISA_REL_PATH = os.path.join("readme", "FISA_CONSULTANT.md")
HELP = "fisa se face cu skill-ul fisa-completa (Mentor, fa fisa pentru <modul>)"


def read_manifest(manifest_path):
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return ast.literal_eval(f.read())
    except (OSError, SyntaxError, ValueError):
        # Lasam alte hook-uri sa raporteze manifestul invalid
        return None


def in_head(path):
    """True daca fisierul exista in commit-ul HEAD (deci modulul nu e nou)."""
    rel = os.path.relpath(os.path.abspath(path)).replace(os.sep, "/")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:./{rel}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def main(argv):
    new_missing = []
    old_missing = []

    for manifest_path in argv:
        if os.path.basename(manifest_path) != "__manifest__.py":
            continue
        manifest = read_manifest(manifest_path)
        if manifest is None or not manifest.get("installable", True):
            continue
        module_dir = os.path.dirname(manifest_path)
        if os.path.exists(os.path.join(module_dir, FISA_REL_PATH)):
            continue
        if in_head(manifest_path):
            old_missing.append(module_dir)
        else:
            new_missing.append(module_dir)

    if old_missing:
        print(f"Avertisment: {len(old_missing)} module existente nu au {FISA_REL_PATH}:")
        for module_dir in sorted(old_missing):
            print(f"  - {module_dir}")

    if new_missing:
        print(f"{len(new_missing)} module noi nu au {FISA_REL_PATH} ({HELP}):")
        for module_dir in sorted(new_missing):
            print(f"  - {module_dir}")

    return 1 if new_missing else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
