# terrabit-pre-commit-hooks

Hook-urile [pre-commit](https://pre-commit.com) comune ale suitelor de module Odoo Terrabit
(deltatech, bitshop, terrabit, l10n_ro_ent etc.). Până la v1.0.0 fiecare suită ținea o copie
în `scripts/`, sincronizată de mână.

## Hook-uri

| id | Ce face | Rulează |
|---|---|---|
| `license-compat` | licența modulului e compatibilă cu a dependențelor (Odoo Apps) | la commit, pe `__manifest__.py` |
| `update-pyproject-name` | `[project].name` din `pyproject.toml` = `odoo-addon-<modul>` | la commit, pe `pyproject.toml` |
| `check-module-icon` | modulul are `static/description/icon.png`, nu o iconiță generică | la commit, pe `__manifest__.py` |
| `check-po-vs-pot` | traducerile noi din `.po` există în `.pot` (altfel Odoo le ignoră în tăcere) | la commit, pe `i18n/*.po` |
| `check-xpath-position` | avertizează la xpath-urile care aleg nodul doar după poziție (`td[2]`, `th[last()]`) | la commit, pe `*.xml` |
| `tb-gen-index` | generează `static/description/index.html` (Apps Store) din `readme/*.md` | manual |
| `tb-fisa-badge` | badge „Fișă consultant” în `README.rst` | manual |
| `tb-test-stats` | scrie `scripts/test_stats.json` (teste + acoperire Codecov) | manual |
| `tb-test-badge` | badge „N automated tests · X% code coverage” în `README.rst`, din `scripts/test_stats.json` | manual |

## Unelte (nu hook-uri)

- `tb_apps_preview.py` — emulează sanitizer-ul Odoo Apps Store pe un `index.html` și scrie alături
  `index.apps-light.html` / `index.apps-dark.html` pentru QA vizual (`--report` = doar riscurile pe dark):

  ```bash
  python3 ../terrabit-pre-commit-hooks/terrabit_pre_commit_hooks/tb_apps_preview.py <modul>/static/description/index.html
  ```

## Folosire într-o suită

```yaml
- repo: https://github.com/dhongu/terrabit-pre-commit-hooks
  rev: v1.3.0
  hooks:
    - id: license-compat
    - id: update-pyproject-name
    - id: check-module-icon
    - id: check-po-vs-pot
    - id: check-xpath-position
    - id: tb-gen-index
      args: [--lang, ro, --scope-note]   # doar unde e nevoie
    - id: tb-fisa-badge
    - id: tb-test-stats
    - id: tb-test-badge
```

Hook-urile manuale:

```bash
pre-commit run tb-test-stats --hook-stage manual
pre-commit run tb-gen-index --hook-stage manual
pre-commit run tb-fisa-badge --hook-stage manual
pre-commit run tb-test-badge --hook-stage manual   # după tb-test-stats
```

`tb-gen-index` caută suitele-frate în directorul părinte al suitei (cardurile „More apps”,
dependențele plătite), deci rezultatul complet se obține local, cu toate suitele clonate
una lângă alta.

## `check-xpath-position`

Un pas ca `td[2]`, `group[1]`, `th[last()]`, `td[last()-1]` sau `*[position() > 1]` se strică
în tăcere când alt modul (cu id de vedere mai mic) inserează un element înainte: vederea e
dezactivată la update sau, mai rău, modificarea ajunge pe alt nod. Caz real: la PTC, pe
14.10.2026, `deltatech_sale_cancel_order.portal_my_orders_cancel`
(`//t[@t-foreach='orders']/tr/td[2]/span[1]`) a căzut după ce `deltatech_delivery_relay` a
inserat celula AWB.

Nu se semnalează indexul pus după un filtru (`span[@t-field='order.date_order'][1]`,
`field[@name='x'][2]`), pașii fără index (`/tr/td` cu `position="after"`) și indexul din
interiorul unui predicat sau string (`div[span[2]]`, `[@t-if="x[0]"]`).

Hook-ul e un avertisment (iese cu 0, mesajele apar prin `verbose: true`); cu `args: [--strict]`
blochează commit-ul. Când poziția chiar e intenția, comentariul de pe linia dinainte suprimă
avertismentul:

```xml
<!-- xpath-position: ok -->
<xpath expr="//tr/td[last()]" position="after">
```

## Teste

```bash
python3 -m unittest discover -s tests
```

## Modificări

O schimbare se face aici, apoi tag nou (`vX.Y.Z`) și `rev:` actualizat în suite
(`pre-commit autoupdate --repo https://github.com/dhongu/terrabit-pre-commit-hooks`).
Înainte de tag se testează dintr-o suită cu:

```bash
pre-commit try-repo ../terrabit-pre-commit-hooks tb-gen-index --hook-stage manual --all-files
```
