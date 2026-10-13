#!/usr/bin/env python
"""Verifica faptul ca fiecare modul Odoo instalabil are iconita lui.

Pentru fiecare __manifest__.py primit ca argument, scriptul verifica existenta
fisierului static/description/icon.png in directorul modulului. Modulele
neinstalabile (installable=False) sunt ignorate.

- Daca icon.png lipseste, hook-ul pica: iconita se deseneaza pentru modul
  (icon.svg + ``rsvg-convert -w 256 -h 256 icon.svg -o icon.png``), nu se
  copiaza una generica.
- Daca icon.png este una dintre iconitele generice ale suitelor (rotile
  dintate), hook-ul doar avertizeaza, fara sa pice: iconita exista, dar nu
  spune nimic despre modul.

Hook-ul `check-module-icon` din dhongu/terrabit-pre-commit-hooks, folosit de toate
suitele (inclusiv l10n-romania).
"""

import ast
import hashlib
import os
import sys

ICON_REL_PATH = os.path.join("static", "description", "icon.png")

# SHA-256 al iconitelor generice (rotile dintate) raspandite in suite
GENERIC_ICONS = {
    "c274d2bc663218ea1ccc7f99e37914e0637581312e5a7917924980c96357980f",  # deltatech, color
    "48482f5020de708ddb802263dc87fca67b56635a893f99f1e7f13bdbeddc8eca",  # varianta veche, verde
    "e0984c5cfa3adc29fe6460f1a177fbcc599580c58ee05488a9ebe4d9ce71ecca",  # color, recodata
}


def is_installable(manifest_path):
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = ast.literal_eval(f.read())
    except (SyntaxError, ValueError):
        # Lasam alte hook-uri sa raporteze manifestul invalid
        return False
    return bool(manifest.get("installable", True))


def is_generic(icon_path):
    with open(icon_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() in GENERIC_ICONS


def main(argv):
    missing = []
    generic = []

    for manifest_path in argv:
        if os.path.basename(manifest_path) != "__manifest__.py":
            continue
        if not is_installable(manifest_path):
            continue
        module_dir = os.path.dirname(manifest_path)
        icon_path = os.path.join(module_dir, ICON_REL_PATH)
        if not os.path.exists(icon_path):
            missing.append(module_dir)
        elif is_generic(icon_path):
            generic.append(module_dir)

    if generic:
        print(f"Atentie: {len(generic)} module au iconita generica (rotile dintate), nu una proprie:")
        print("  " + ", ".join(os.path.basename(os.path.abspath(m)) for m in sorted(generic)))

    if missing:
        print(f"Lipseste {ICON_REL_PATH} la modulele:")
        for module_dir in sorted(missing):
            print(f"  - {module_dir}")
        print(
            "\nDesenati iconita modulului (icon.svg, apoi"
            " `rsvg-convert -w 256 -h 256 icon.svg -o icon.png`) si adaugati-o in commit."
        )

    return 1 if missing else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
