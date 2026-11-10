#!/usr/bin/env python3
# ©  2026 Terrabit
# See README.rst file on addons root folder for license details
"""Generează README.rst și static/description/index.html din ``readme/*.md``, într-o singură trecere.

Unește ``tb-gen-readme`` (README.rst, cu insignele fișă și teste) și ``tb-gen-index`` (pagina
Apps Store): aceleași fragmente, același manifest, aceleași statistici de teste, aceeași
selecție de module pe ``--files``, deci un singur hook în ``.pre-commit-config.yaml`` și
nicio ordine de ținut minte între ele. Lanțul manual rămâne::

    pre-commit run tb-test-stats --hook-stage manual
    pre-commit run tb-gen-docs --hook-stage manual --all-files

Randările rămân separate (README.rst trece prin pandoc în RST, index.html prin markdown în
HTML cu designul Terrabit); ce se împarte e stratul de surse (``tb_module_sources``).
``tb-gen-readme`` și ``tb-gen-index`` rămân ca hook-uri de sine stătătoare, cu aceleași opțiuni.

Opțiunile README-ului (``--org-name``, ``--repo-name``, ``--branch``, ``--no-roadmap``,
``--update-digest``) și ale paginii (``--lang``, ``--allow-ro``, ``--scope-note``,
``--no-cross-sell``, ``--force``) se dau la fel ca la hook-urile separate;
``--no-readme`` / ``--no-index`` sar peste una dintre ele.

Cu ``--files`` (cum le dă pre-commit) lucrează doar pe modulele atinse. Cardurile „More apps”
și lista de dependențe din index.html citesc modulele-surori, deci o schimbare într-un modul
reîmprospătează pagina modulelor-surori doar la următoarea rulare pe toată suita.
"""

import argparse
import logging
import sys

from terrabit_pre_commit_hooks import tb_gen_index, tb_gen_readme
from terrabit_pre_commit_hooks.tb_module_sources import all_addons, github_repo, load_stats


def add_index_arguments(parser):
    """Opțiunile paginii Apps Store, aceleași ca la ``tb-gen-index``."""
    parser.add_argument("--no-cross-sell", action="store_true", help="fără secțiunea de module-surori")
    parser.add_argument("--force", action="store_true", help="suprascrie și index.html scrise manual")
    parser.add_argument(
        "--allow-ro", action="store_true", help="suită cu prezentare în RO (nu omite HISTORY cu diacritice)"
    )
    parser.add_argument(
        "--lang",
        choices=sorted(tb_gen_index.I18N),
        default="en",
        help="limba textelor generate (taburi, stats, note, CTA); `ro` implică --allow-ro",
    )
    parser.add_argument(
        "--scope-note",
        action="store_true",
        help="adaugă nota „ce acoperă prețul” (text scris pentru localizarea RO, l10n_ro_ent)",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="*", help="fișierele date de pre-commit; fără ele, toate modulele")
    parser.add_argument("--addons-dir", default=".")
    parser.add_argument("--no-readme", action="store_true", help="doar index.html")
    parser.add_argument("--no-index", action="store_true", help="doar README.rst")
    tb_gen_readme.add_readme_arguments(parser)
    add_index_arguments(parser)
    args = parser.parse_args(argv)
    if args.no_readme and args.no_index:
        parser.error("--no-readme și --no-index laolaltă nu lasă nimic de generat")
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    addons = list(all_addons(args.addons_dir, args.files))
    failed = 0
    if not args.no_readme:
        org, repo = github_repo(args.addons_dir, args.org_name, args.repo_name)
        if not (org and repo):
            parser.error("nu pot determina repo-ul GitHub: dați --org-name și --repo-name")
        _changed, failed = tb_gen_readme.run(
            addons, org, repo, args.branch, load_stats(args.addons_dir), not args.no_roadmap, args.update_digest
        )
    if not args.no_index:
        for _name, addon_dir, _manifest in addons:
            tb_gen_index.process(
                addon_dir,
                cross_sell=not args.no_cross_sell,
                force=args.force,
                allow_ro=args.allow_ro or args.lang == "ro",
                lang=args.lang,
                scope_note=args.scope_note,
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
