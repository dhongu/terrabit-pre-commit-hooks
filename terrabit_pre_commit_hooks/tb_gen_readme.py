#!/usr/bin/env python3
# ©  2026 Terrabit
# See README.rst file on addons root folder for license details
"""Generează README.rst din fragmentele ``readme/*.md``, fără ``oca-gen-addon-readme``.

Înlocuiește lanțul manual ``oca-gen-addon-readme`` -> ``tb-fisa-badge`` -> ``tb-test-badge``:
generatorul OCA rescria README.rst și ștergea badge-urile puse de celelalte hook-uri, iar
ordinea corectă exista doar într-un comentariu din ``.pre-commit-config.yaml``.

Formatul rămâne cel al generatorului OCA cu șablonul Terrabit (``gen_addon_readme.rst.jinja``):
titlu, antet generat cu digestul sursei, badge-uri, DESCRIPTION, cuprins, secțiunile
CONTEXT / INSTALL / CONFIGURE / USAGE / DEVELOP / (ROADMAP) / HISTORY ca „Changelog”,
Bug Tracker, Credits (autori, contribuitori, alte credite, mentenanți) și footer. În plus,
după badge-urile OCA vin direct ``|badge_fisa|`` (modul cu ``readme/FISA_CONSULTANT.md``) și
``|badge_tests|`` (modul cu teste în ``scripts/test_stats.json``), cu aceeași logică ca
``tb-fisa-badge`` și ``tb-test-badge``, care sunt refolosite, nu duplicate.

- fragmentele ``.md`` se convertesc cu pandoc, cu aceleași opțiuni ca generatorul OCA
  (``gfm-raw_html-gfm_auto_identifiers``); fragmentele ``.rst`` intră ca atare;
- titlurile din fragmente se normalizează: dacă README-ul generat nu trece de docutils
  („Inconsistent title style: skip from level 2 to 4”), titlurile fiecărui fragment se
  refac relativ la titlul secțiunii, fără niveluri sărite; în același pas imaginile pandoc
  (``|image1|``) primesc prefixul fragmentului, iar ``_`` de la sfârșit de cuvânt din textul
  alternativ dispare (altfel docutils pică pe „Duplicate substitution” / „Undefined
  substitution”); README-urile valide rămân neatinse;
- digestul sursei din antet se păstrează dacă există (ca ``--keep-source-digest``), ca să nu
  apară conflicte de merge; ``--update-digest`` îl reînnoiește;
- idempotent: README.rst se rescrie doar dacă s-a schimbat conținutul;
- ``--files`` (cum le dă pre-commit) limitează lucrul la modulele atinse; un fișier din
  ``scripts/`` (``test_stats.json``) atinge toate modulele, ceea ce e rapid: conversia
  pandoc rulează în paralel.

Nu generează ``static/description/index.html`` (se ocupă ``tb-gen-index``) și nu rulează
``tb-test-stats`` (numără testele și citește Codecov, deci rămâne hook separat, înainte).

Rulare::

    pre-commit run tb-test-stats --hook-stage manual
    pre-commit run tb-gen-readme --hook-stage manual --all-files
"""

import argparse
import ast
import concurrent.futures
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urljoin

from terrabit_pre_commit_hooks.tb_fisa_badge import fisa_badge, repo_from_git
from terrabit_pre_commit_hooks.tb_gen_index import TEST_STATS
from terrabit_pre_commit_hooks.tb_test_badge import tests_badge

FRAGMENTS_DIR = "readme"
# nivelul titlului secțiunii fragmentului în README (2 = secțiune, 3 = sub-secțiune la Credits)
FRAGMENTS = {
    "DESCRIPTION": 2,
    "CONTEXT": 2,
    "INSTALL": 2,
    "CONFIGURE": 2,
    "USAGE": 2,
    "ROADMAP": 2,
    "DEVELOP": 2,
    "CONTRIBUTORS": 3,
    "CREDITS": 3,
    "HISTORY": 2,
}
PANDOC_FORMAT = "gfm-raw_html-gfm_auto_identifiers"
MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py", "__terp__.py")

LICENSE_BADGES = {
    "AGPL-3": (
        "https://img.shields.io/badge/license-AGPL--3-blue.png",
        "http://www.gnu.org/licenses/agpl-3.0-standalone.html",
        "License: AGPL-3",
    ),
    "LGPL-3": (
        "https://img.shields.io/badge/license-LGPL--3-blue.png",
        "http://www.gnu.org/licenses/lgpl-3.0-standalone.html",
        "License: LGPL-3",
    ),
    "GPL-3": (
        "https://img.shields.io/badge/license-GPL--3-blue.png",
        "http://www.gnu.org/licenses/gpl-3.0-standalone.html",
        "License: GPL-3",
    ),
}
DEVELOPMENT_STATUS_BADGES = {
    "mature": (
        "https://img.shields.io/badge/maturity-Mature-brightgreen.png",
        "https://odoo-community.org/page/development-status",
        "Mature",
    ),
    "production/stable": (
        "https://img.shields.io/badge/maturity-Production%2FStable-green.png",
        "https://odoo-community.org/page/development-status",
        "Production/Stable",
    ),
    "beta": (
        "https://img.shields.io/badge/maturity-Beta-yellow.png",
        "https://odoo-community.org/page/development-status",
        "Beta",
    ),
    "alpha": (
        "https://img.shields.io/badge/maturity-Alpha-red.png",
        "https://odoo-community.org/page/development-status",
        "Alpha",
    ),
}

# Șablonul Terrabit (identic cu gen_addon_readme.rst.jinja al suitelor), cu badge-uri numite,
# ca să poată intra |badge_fisa| și |badge_tests| lângă |badge1|, |badge2|.
TEMPLATE = """{%- macro fragment(name, title, sub='=') %}
{%- if name in fragments %}
{{- title }}
{{ sub * title|length }}

{{ fragments[name] }}
{% endif %}
{%- endmacro -%}

{{ '=' * manifest.name|length }}
{{ manifest.name }}
{{ '=' * manifest.name|length }}

..
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   !! This file is generated by oca-gen-addon-readme !!
   !! changes will be overwritten.                   !!
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   !! source digest: {{ source_digest }}
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

{% for (name, image, target, alt) in badges -%}
.. |{{ name }}| image:: {{ image }}
    :target: {{ target or '#' }}
    {%- if alt %}
    :alt: {{ alt }}
    {%- endif %}
{% endfor %}
{% for (name, _i, _t, _a) in badges %}|{{ name }}|{% if loop.index != badges|length %} {% endif %}{% endfor %}

{{ fragments.get('DESCRIPTION', '') }}
{% if development_status == 'alpha' -%}

.. IMPORTANT::
   This is an alpha version, the data model and design can change at any time without warning.
   Only for development or testing purpose, do not use in production.
   `More details on development status <https://odoo-community.org/page/development-status>`_

{% endif -%}

**Table of contents**

.. contents::
   :local:

{{ fragment('CONTEXT', 'Use Cases / Context') }}
{{- fragment('INSTALL', 'Installation') }}
{{- fragment('CONFIGURE', 'Configuration') }}
{{- fragment('USAGE', 'Usage') }}
{{- fragment('DEVELOP', 'Development') }}
{{ ROADMAP_LINE }}
{{- fragment('HISTORY', 'Changelog') -}}
Bug Tracker
===========

Bugs are tracked on `Terrabit Issues <https://www.terrabit.ro/helpdesk>`_.
In case of trouble, please check there if your issue has already been reported.

Do not contact contributors directly about support or help with technical issues.

Credits
=======

{% if authors -%}
Authors
{{ level3_underline * 7 }}

{% for author in authors -%}
* {{ author }}
{% endfor %}
{% endif -%}

{{ fragment('CONTRIBUTORS', 'Contributors', sub=level3_underline) }}
{{- fragment('CREDITS', 'Other credits', sub=level3_underline) -}}
Maintainers
{{ level3_underline * 11 }}
{%- if org_name == 'OCA' %}

This module is maintained by the OCA.

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization whose
mission is to support the collaborative development of Odoo features and
promote its widespread use.
{%- endif %}

{%- if manifest.maintainers %}
{% for maintainer in manifest.maintainers %}
.. |maintainer-{{ maintainer }}| image:: https://github.com/{{ maintainer }}.png?size=40px
    :target: https://github.com/{{ maintainer }}
    :alt: {{ maintainer}}
{%- endfor %}

{% if org_name == 'OCA' -%}
Current `maintainer{% if manifest.maintainers|length > 1 %}s{% endif %} <https://odoo-community.org/page/maintainer-role>`__:
{%- else -%}
Current maintainer{% if manifest.maintainers|length > 1 %}s{% endif %}:
{%- endif %}

{% for maintainer in manifest.maintainers %}|maintainer-{{ maintainer }}| {% endfor -%}
{% endif %}

This module is part of the `{{ org_name }}/{{ repo_name }} <https://github.com/{{ org_name }}/{{ repo_name }}/tree/{{ branch }}/{{ addon_name }}>`_ project on GitHub.

{% if org_name == 'OCA' -%}
You are welcome to contribute. To learn how please visit https://odoo-community.org/page/Contribute.

{%- else -%}
You are welcome to contribute.

{%- endif %}
"""
ROADMAP_FRAGMENT = "{{- fragment('ROADMAP', 'Known issues / Roadmap') -}}"
DIGEST_RE = re.compile(r"!! source digest: (sha256:\w+)")


class ReadmeError(Exception):
    pass


# --- surse -----------------------------------------------------------------------------------


def read_manifest(addon_dir):
    for name in MANIFEST_NAMES:
        path = os.path.join(addon_dir, name)
        if os.path.isfile(path):
            with open(path, encoding="utf8") as f:
                return path, ast.literal_eval(f.read())
    return None, None


def source_digest(manifest_path, addon_dir):
    """sha256 peste manifest și tot ``readme/`` (nume + conținut), ca digestul generatorului OCA."""
    relative_to = addon_dir
    files = [os.path.relpath(manifest_path, relative_to)]
    top = os.path.join(addon_dir, FRAGMENTS_DIR)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames.sort()
        reldir = os.path.relpath(dirpath, relative_to)
        for filename in sorted(filenames):
            if not filename.startswith("."):
                files.append(os.path.normpath(os.path.join(reldir, filename)))
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode("utf-8"))
        with open(os.path.join(relative_to, rel), "rb") as f:
            digest.update(f.read())
    return "sha256:" + digest.hexdigest()


def existing_digest(readme):
    if not os.path.isfile(readme):
        return None
    with open(readme, encoding="utf8") as f:
        match = DIGEST_RE.search(f.read())
    return match.group(1) if match else None


def fragment_path(addon_dir, name):
    """(cale, format) al fragmentului sau (None, None); ambele formate deodată e eroare."""
    found = [
        (os.path.join(addon_dir, FRAGMENTS_DIR, name + ext), ext)
        for ext in (".rst", ".md")
        if os.path.exists(os.path.join(addon_dir, FRAGMENTS_DIR, name + ext))
    ]
    if len(found) > 1:
        raise ReadmeError(f"{name}: există și .md, și .rst în {addon_dir}/readme, lăsați unul")
    return found[0] if found else (None, None)


# --- conversie ------------------------------------------------------------------------------

HEADING = re.compile(r"^(#{1,6})([ \t]+.*)$")
FENCE = re.compile(r"^ {0,3}(```|~~~)")


def normalize_headings(markdown):
    """Titlurile ATX fără niveluri sărite, relativ la titlul secțiunii (nivel 2 în md)."""
    out, fence, previous = [], None, 0
    for line in markdown.split("\n"):
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            fence = None if fence == marker else (fence or marker)
        heading = None if fence or match else HEADING.match(line)
        if heading:
            level = min(len(heading.group(1)), previous + 1)
            previous = level
            line = "#" * (level + 1) + heading.group(2)
        out.append(line)
    return "\n".join(out)


IMAGE_ALT = re.compile(r"(!\[)([^\]]*)(\]\()")


def sanitize_image_alts(markdown):
    """Fără ``_`` la sfârșit de cuvânt în textul alternativ: pandoc îl scrie ca substituție RST ruptă."""
    return IMAGE_ALT.sub(lambda m: m.group(1) + re.sub(r"_(?=\s|$)", "", m.group(2)) + m.group(3), markdown)


def pandoc_executable():
    path = shutil.which("pandoc")
    if path:
        return path
    try:
        import pypandoc

        return pypandoc.get_pandoc_path()
    except (ImportError, OSError):
        raise ReadmeError("pandoc lipsește: instalați pandoc sau pypandoc-binary") from None


def markdown_to_rst(markdown, level):
    result = subprocess.run(
        [
            pandoc_executable(),
            "-f",
            PANDOC_FORMAT,
            "-t",
            "rst",
            f"--shift-heading-level-by={level - 2}",
            "--sandbox",
        ],
        input=markdown,
        capture_output=True,
        text=True,
        encoding="utf8",
    )
    if result.returncode:
        raise ReadmeError(f"pandoc a eșuat: {result.stderr.strip()}")
    return result.stdout


IMAGE_PATH = re.compile(r".*\s*\.\..* (figure|image)::\s+(?P<path>.*?)\s*$")


def absolute_images(fragment, org, repo, branch, addon_name):
    """Căile relative ale imaginilor devin URL-uri raw GitHub (ca la generatorul OCA)."""
    module_url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{addon_name}/"
    lines = fragment.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = IMAGE_PATH.match(line)
        if not match or match.group("path").startswith("http"):
            continue
        path = match.group("path")
        lines[index] = line.replace(path, urljoin(module_url, path.replace("../", "")))
    fragment = "".join(lines)
    return fragment if fragment.endswith("\n") else fragment + "\n"


SUBSTITUTION = re.compile(r"\|(image\d+)\|")


def prefix_substitutions(rst, prefix):
    """``|image1|`` -> ``|usage_image1|``: pandoc numerotează imaginile pe fragment, iar două
    fragmente cu aceeași substituție dau „Duplicate substitution definition name”."""
    return SUBSTITUTION.sub(lambda m: f"|{prefix}_{m.group(1)}|", rst)


def load_fragments(addon_dir, addon_name, org, repo, branch, normalize):
    fragments, formats = {}, set()
    for name, level in FRAGMENTS.items():
        path, ext = fragment_path(addon_dir, name)
        if not path:
            continue
        formats.add(ext)
        with open(path, encoding="utf8") as f:
            content = f.read()
        if ext == ".md":
            if normalize:
                content = sanitize_image_alts(normalize_headings(content))
            content = markdown_to_rst(content, level)
        if normalize:
            content = prefix_substitutions(content, name.lower())
        if content.strip():
            fragments[name] = absolute_images(content, org, repo, branch, addon_name)
    if len(formats) > 1:
        raise ReadmeError(f"fragmente .md și .rst amestecate în {addon_dir}/readme")
    return fragments, ".rst" if formats == {".rst"} else ".md"


# --- randare --------------------------------------------------------------------------------


def make_badges(manifest, addon_dir, addon_name, org, repo, branch, stats):
    badges = []
    status = manifest.get("development_status", "Beta").lower()
    if status in DEVELOPMENT_STATUS_BADGES:
        badges.append(DEVELOPMENT_STATUS_BADGES[status])
    if manifest.get("license") in LICENSE_BADGES:
        badges.append(LICENSE_BADGES[manifest["license"]])
    badge_repo, badge_org = repo.replace("-", "--"), org.replace("-", "--")
    badges.append(
        (
            f"https://img.shields.io/badge/github-{badge_org}%2F{badge_repo}-lightgray.png?logo=github",
            f"https://github.com/{org}/{repo}/tree/{branch}/{addon_name}",
            f"{org}/{repo}",
        )
    )
    if org == "OCA":
        badges.append(make_weblate_badge(repo, branch, addon_name))
    named = [(f"badge{i}", *badge) for i, badge in enumerate(badges, 1)]
    fisa = fisa_badge(addon_dir, addon_name, org, repo, branch)
    if fisa:
        named.append(("badge_fisa", *fisa))
    tests = tests_badge(stats, org, repo, branch, addon_name)
    if tests:
        named.append(("badge_tests", *tests))
    return named, status


def make_weblate_badge(repo, branch, addon_name):
    branch = branch.replace(".", "-")
    return (
        "https://img.shields.io/badge/weblate-Translate%20me-F47D42.png",
        f"https://translation.odoo-community.org/projects/{repo}-{branch}/{repo}-{branch}-{addon_name}",
        "Translate me on Weblate",
    )


def render(addon_dir, addon_name, manifest, digest, org, repo, branch, stats, roadmap, normalize):
    from jinja2 import Template

    fragments, fragments_format = load_fragments(addon_dir, addon_name, org, repo, branch, normalize)
    badges, status = make_badges(manifest, addon_dir, addon_name, org, repo, branch, stats)
    authors = [a.strip() for a in manifest.get("author", "").split(",") if "(OCA)" not in a]
    template = TEMPLATE.replace("{{ ROADMAP_LINE }}", ROADMAP_FRAGMENT if roadmap else "")
    return Template(template).render(
        addon_name=addon_name,
        authors=authors,
        badges=badges,
        branch=branch,
        fragments=fragments,
        manifest=manifest,
        org_name=org,
        repo_name=repo,
        development_status=status,
        source_digest=digest,
        level3_underline="~" if fragments_format == ".rst" else "-",
    )


def check_rst(text):
    """Mesajul de eroare docutils (titluri inconsistente etc.), sau None dacă README-ul e valid."""
    from docutils.core import publish_doctree
    from docutils.utils import SystemMessage

    try:
        publish_doctree(
            text,
            settings_overrides={
                "file_insertion_enabled": False,
                "raw_enabled": False,
                "halt_level": 2,
                "report_level": 5,
                "warning_stream": io.StringIO(),
            },
        )
    except SystemMessage as error:
        return str(error).splitlines()[0]
    return None


def generate(addon_dir, addon_name, manifest, org, repo, branch, stats, roadmap=True, update_digest=False):
    """Textul README.rst al modulului, sau None dacă modulul nu are readme/DESCRIPTION."""
    if not any(os.path.exists(os.path.join(addon_dir, FRAGMENTS_DIR, "DESCRIPTION" + ext)) for ext in (".md", ".rst")):
        return None
    manifest_path = read_manifest(addon_dir)[0]
    digest = source_digest(manifest_path, addon_dir)
    if not update_digest:
        digest = existing_digest(os.path.join(addon_dir, "README.rst")) or digest
    args = (addon_dir, addon_name, manifest, digest, org, repo, branch, stats, roadmap)
    text = render(*args, normalize=False)
    error = check_rst(text)
    if error:
        text = render(*args, normalize=True)
        error = check_rst(text)
        if error:
            raise ReadmeError(f"{addon_name}: README.rst invalid chiar după normalizarea titlurilor: {error}")
    return text


# --- hook -----------------------------------------------------------------------------------


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


def all_addons(addons_dir):
    for name in sorted(os.listdir(addons_dir)):
        addon_dir = os.path.join(addons_dir, name)
        if os.path.isdir(addon_dir):
            manifest = read_manifest(addon_dir)[1]
            if manifest is not None and manifest.get("installable", True):
                yield name, addon_dir, manifest


def process_addon(addon_dir, addon_name, manifest, org, repo, branch, stats, **options):
    text = generate(addon_dir, addon_name, manifest, org, repo, branch, stats, **options)
    if text is None:
        return False
    readme = os.path.join(addon_dir, "README.rst")
    if os.path.isfile(readme):
        with open(readme, encoding="utf8") as f:
            if f.read() == text:
                return False
    with open(readme, "w", encoding="utf8") as f:
        f.write(text)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="*", help="fișierele date de pre-commit; fără ele, toate modulele")
    parser.add_argument("--addons-dir", default=".")
    parser.add_argument("--org-name", help="organizația GitHub (implicit: din remote-ul origin)")
    parser.add_argument("--repo-name", help="repo-ul GitHub (implicit: din remote-ul origin)")
    parser.add_argument("--branch", default="19.0")
    parser.add_argument("--no-roadmap", action="store_true", help="fără secțiunea ROADMAP (șablonul bitshop/deltatech)")
    parser.add_argument("--update-digest", action="store_true", help="reînnoiește digestul sursei din antet")
    args = parser.parse_args(argv)

    org, repo = args.org_name, args.repo_name
    if not (org and repo):
        git_org, git_repo = repo_from_git(args.addons_dir)
        org, repo = org or git_org, repo or git_repo
    if not (org and repo):
        parser.error("nu pot determina repo-ul GitHub: dați --org-name și --repo-name")

    selected = addons_from_files(args.addons_dir, args.files) if args.files else None
    addons = [a for a in all_addons(args.addons_dir) if selected is None or a[0] in selected]

    stats = {}
    stats_path = os.path.join(args.addons_dir, TEST_STATS)
    if os.path.isfile(stats_path):
        with open(stats_path, encoding="utf8") as f:
            stats = json.load(f).get("addons", {})

    def work(addon):
        name, addon_dir, manifest = addon
        try:
            changed = process_addon(
                addon_dir,
                name,
                manifest,
                org,
                repo,
                args.branch,
                stats.get(name),
                roadmap=not args.no_roadmap,
                update_digest=args.update_digest,
            )
            return name, changed, None
        except ReadmeError as error:
            return name, False, str(error)

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
        for name, changed, error in pool.map(work, addons):
            if error:
                failed += 1
                sys.stderr.write(f"{name}: {error}\n")
            elif changed:
                sys.stdout.write(f"{name}: README.rst actualizat\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
