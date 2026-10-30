#!/usr/bin/env python
"""Verifica faptul ca fiecare modul Odoo instalabil are iconita si bannerul lui.

Pentru fiecare __manifest__.py primit ca argument, scriptul verifica, in
directorul modulului, imaginile din static/description/. Modulele
neinstalabile (installable=False) sunt ignorate. Hook-ul pica daca:

- icon.png lipseste sau este una dintre iconitele generice ale suitelor
  (rotile dintate): iconita se deseneaza pentru modul (icon.svg +
  ``rsvg-convert -w 256 -h 256 icon.svg -o icon.png``), nu se copiaza;
- manifestul nu are cheia ``images`` sau modulul nu are banner.json: bannerul
  Odoo Apps (main_screenshot.png, 560x280) se genereaza din banner.json;
- main_screenshot.png este bannerul comun al suitei deltatech (cel al modulului
  ``deltatech``, copiat de hook-ul local check-module-images al suitei), nu unul
  al modulului.

Hook-ul `check-module-icon` din dhongu/terrabit-pre-commit-hooks, folosit de toate
suitele (inclusiv l10n-romania).
"""

import ast
import hashlib
import os
import sys

DESCRIPTION_REL_DIR = os.path.join("static", "description")
ICON_REL_PATH = os.path.join(DESCRIPTION_REL_DIR, "icon.png")
BANNER_REL_PATH = os.path.join(DESCRIPTION_REL_DIR, "main_screenshot.png")
BANNER_JSON_REL_PATH = os.path.join(DESCRIPTION_REL_DIR, "banner.json")
# Modulul al carui banner e chiar cel comun
BANNER_SOURCE_MODULE = "deltatech"

# SHA-256 al iconitelor generice (rotile dintate) raspandite in suite
GENERIC_ICONS = {
    "c274d2bc663218ea1ccc7f99e37914e0637581312e5a7917924980c96357980f",  # deltatech, color
    "48482f5020de708ddb802263dc87fca67b56635a893f99f1e7f13bdbeddc8eca",  # varianta veche, verde
    "e0984c5cfa3adc29fe6460f1a177fbcc599580c58ee05488a9ebe4d9ce71ecca",  # color, recodata
}

# SHA-256 al bannerului comun „Deltatech – Shared base for the Deltatech suite”
GENERIC_BANNERS = {
    "4bcf5232d0c1dddfe3af1c512f215f7aed6aa6d3dc6653e732a7732421888e1e",  # deltatech 18.0
    "99b4371fdbea4d1ecdb23b194f446b03d000eafbc219d9e521b97f313e227b85",  # deltatech 19.0
    "8627af5f661b7720fe99a0619162d0b42f9efc29fb1ce60b6372f70235bcb371",  # deltatech 20.0
}

HELP_ICON = "iconita se deseneaza pentru modul (skill-ul iconita-modul: icon.svg, apoi rsvg-convert)"
HELP_BANNER = "bannerul se genereaza din banner.json (skill-ul banner-modul)"


def read_manifest(manifest_path):
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return ast.literal_eval(f.read())
    except (SyntaxError, ValueError):
        # Lasam alte hook-uri sa raporteze manifestul invalid
        return None


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def generic_banners(module_dir):
    """Bannerele comune cunoscute, plus cel al modulului deltatech din acelasi repo."""
    banners = set(GENERIC_BANNERS)
    source = os.path.join(os.path.dirname(os.path.abspath(module_dir)), BANNER_SOURCE_MODULE, BANNER_REL_PATH)
    if os.path.exists(source):
        banners.add(sha256(source))
    return banners


def check_module(module_dir, manifest):
    """Intoarce lista problemelor modulului."""
    problems = []
    icon_path = os.path.join(module_dir, ICON_REL_PATH)
    if not os.path.exists(icon_path):
        problems.append(f"lipseste {ICON_REL_PATH}: {HELP_ICON}")
    elif sha256(icon_path) in GENERIC_ICONS:
        problems.append(f"iconita generica (rotile dintate): {HELP_ICON}")

    if not manifest.get("images"):
        problems.append(f"manifestul nu are cheia 'images': {HELP_BANNER}")
    if not os.path.exists(os.path.join(module_dir, BANNER_JSON_REL_PATH)):
        problems.append(f"lipseste {BANNER_JSON_REL_PATH}: {HELP_BANNER}")

    banner_path = os.path.join(module_dir, BANNER_REL_PATH)
    is_source = os.path.basename(os.path.abspath(module_dir)) == BANNER_SOURCE_MODULE
    if not is_source and os.path.exists(banner_path) and sha256(banner_path) in generic_banners(module_dir):
        problems.append(f"main_screenshot.png este bannerul comun Deltatech, copiat: {HELP_BANNER}")
    return problems


def main(argv):
    failed = []

    for manifest_path in argv:
        if os.path.basename(manifest_path) != "__manifest__.py":
            continue
        manifest = read_manifest(manifest_path)
        if manifest is None or not manifest.get("installable", True):
            continue
        module_dir = os.path.dirname(manifest_path)
        problems = check_module(module_dir, manifest)
        if problems:
            failed.append((module_dir, problems))

    if failed:
        print(f"{len(failed)} module nu au iconita sau bannerul lor:")
        for module_dir, problems in sorted(failed):
            print(f"  - {module_dir}")
            for problem in problems:
                print(f"      {problem}")

    return 1 if failed else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
