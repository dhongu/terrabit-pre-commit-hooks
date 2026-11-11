#!/usr/bin/env python
"""Verifica faptul ca modulele Odoo au fisa consultant (readme/FISA_CONSULTANT.md).

Pentru fiecare __manifest__.py primit ca argument (modulele instalabile):

Cheia `consultant_sheet` din manifest spune ce fisa are nevoie modulul:

- `full`: fisa cu capturi (readme/screenshots); fara capturi hook-ul avertizeaza;
- `simple`: fisa fara capturi;
- `none`: modulul nu are nevoie de fisa (tehnic, glue, conector fara UI propriu) si e sarit;
- cheia lipseste: modul netriat, se aplica regulile de mai jos;
- alta valoare: hook-ul pica.

Fara `none`:

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
SCREENSHOTS_REL_PATH = os.path.join("readme", "screenshots")
SHEET_KEY = "consultant_sheet"
SHEET_VALUES = ("full", "simple", "none")
HELP = "fisa se face cu skill-ul fisa-completa (Mentor, fa fisa pentru <modul>) sau pune consultant_sheet: none in manifest"


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


def has_screenshots(module_dir):
    path = os.path.join(module_dir, SCREENSHOTS_REL_PATH)
    return os.path.isdir(path) and any(name.lower().endswith(".png") for name in os.listdir(path))


def main(argv):
    new_missing = []
    old_missing = []
    invalid = []
    no_screenshots = []
    none_with_fisa = []

    for manifest_path in argv:
        if os.path.basename(manifest_path) != "__manifest__.py":
            continue
        manifest = read_manifest(manifest_path)
        if manifest is None or not manifest.get("installable", True):
            continue
        module_dir = os.path.dirname(manifest_path)
        sheet = manifest.get(SHEET_KEY)
        if sheet is not None and sheet not in SHEET_VALUES:
            invalid.append((module_dir, sheet))
            continue
        has_fisa = os.path.exists(os.path.join(module_dir, FISA_REL_PATH))
        if sheet == "none":
            if has_fisa:
                none_with_fisa.append(module_dir)
            continue
        if has_fisa:
            if sheet == "full" and not has_screenshots(module_dir):
                no_screenshots.append(module_dir)
            continue
        if in_head(manifest_path):
            old_missing.append(module_dir)
        else:
            new_missing.append(module_dir)

    if invalid:
        print(f"{SHEET_KEY} are o valoare invalida (permise: {', '.join(SHEET_VALUES)}):")
        for module_dir, value in sorted(invalid):
            print(f"  - {module_dir}: {value!r}")

    if no_screenshots:
        print(f"Avertisment: {len(no_screenshots)} module cu {SHEET_KEY}=full nu au capturi in {SCREENSHOTS_REL_PATH}:")
        for module_dir in sorted(no_screenshots):
            print(f"  - {module_dir}")

    if none_with_fisa:
        print(f"Avertisment: {len(none_with_fisa)} module cu {SHEET_KEY}=none au totusi {FISA_REL_PATH}:")
        for module_dir in sorted(none_with_fisa):
            print(f"  - {module_dir}")

    if old_missing:
        print(f"Avertisment: {len(old_missing)} module existente nu au {FISA_REL_PATH}:")
        for module_dir in sorted(old_missing):
            print(f"  - {module_dir}")

    if new_missing:
        print(f"{len(new_missing)} module noi nu au {FISA_REL_PATH} ({HELP}):")
        for module_dir in sorted(new_missing):
            print(f"  - {module_dir}")

    return 1 if new_missing or invalid else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
