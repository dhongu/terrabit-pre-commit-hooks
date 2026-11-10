# Istoric

## 1.12.1

- `tb-gen-index` și `tb-gen-docs`: insigna **Uniunea Europeană** din antet folosește steagul european ca SVG inline
  (reproducerea oficială în culori de pe european-union.europa.eu, 12 stele aurii pe albastru), în
  locul iconiței `fa-globe`.

## 1.12.0

- Hook nou `tb-gen-docs`: generează `README.rst` (ca `tb-gen-readme`) și
  `static/description/index.html` (ca `tb-gen-index`) într-o singură trecere pe modul, cu
  aceleași fragmente, manifest, statistici de teste și selecție de module pe `--files`. În
  `.pre-commit-config.yaml` rămâne `tb-test-stats` urmat de `tb-gen-docs`, fără alte
  ordini de ținut minte. Opțiunile README-ului (`--org-name`, `--repo-name`, `--branch`,
  `--no-roadmap`, `--update-digest`) și ale paginii (`--lang`, `--allow-ro`, `--scope-note`,
  `--no-cross-sell`, `--force`) se dau la fel ca la hook-urile separate; `--no-readme` /
  `--no-index` sar peste una dintre ele. Rezultatul e byte cu byte cel al hook-urilor
  separate, care rămân disponibile neschimbate.
- `tb_module_sources.py`: stratul comun (modulele instalabile, selecția pe fișiere, statisticile
  din `scripts/test_stats.json`, org/repo din remote), folosit de `tb-gen-readme` și `tb-gen-docs`.

## 1.11.1

- `tb-gen-readme`: verificarea docutils se face sub lacăt. Rulată din fire paralele, dădea
  erori false („Definition list ends without a blank line”, „skip from level 2 to 4”) pe
  module valide, deci rezultatul depindea de ordinea firelor.
- `tb-gen-readme`: titlurile din `DESCRIPTION.md` (care stă înaintea secțiunilor README-ului)
  nu mai sparg ierarhia: când README-ul nu trece de docutils, devin text îngroșat; titlurile
  cu linie de `===` / `---` dedesubt (setext) sunt recunoscute și normalizate ca cele cu `#`.
  Modulele cu titluri în DESCRIPTION (ex. `deltatech_delivery`, `deltatech_valuation_area`),
  care picau și la generatorul OCA, se generează acum corect.

## 1.11.0

- Hook nou `tb-gen-readme`: generează `README.rst` din fragmentele `readme/*.md` fără
  `oca-gen-addon-readme`, în același format (șablonul Terrabit: badge-uri, autori,
  contribuitori, changelog din `HISTORY.md`, footer), cu insignele „Fișă consultant” și
  „teste automate” incluse direct. Până acum generatorul OCA rescria README.rst și ștergea
  insignele puse de `tb-fisa-badge` / `tb-test-badge`, iar ordinea corectă exista doar într-un
  comentariu din `.pre-commit-config.yaml`. Rulează pe `--files` (doar modulele atinse; un
  `scripts/test_stats.json` schimbat le atinge pe toate) și, cu conversia pandoc în paralel,
  face toată suita bitshop (118 module) în ~4 s, față de ~60 s la generatorul OCA.
  Titlurile RST din fragmente se normalizează când docutils respinge README-ul („skip from
  level 2 to 4”), la fel și imaginile pandoc duplicate (`|image1|`) sau cu `_` la sfârșit de
  cuvânt în textul alternativ. `--no-roadmap` pentru suitele cu șablonul fără ROADMAP
  (bitshop, deltatech), `--update-digest` pentru a reînnoi digestul sursei (implicit se păstrează,
  ca `--keep-source-digest`). Doar pentru suitele Terrabit; suitele OCA rămân pe generatorul OCA.
- `tb_fisa_badge.fisa_badge` și `tb_test_badge.tests_badge` expun specificația insignei,
  refolosită de `tb-gen-readme`; hook-urile `tb-fisa-badge` și `tb-test-badge` rămân neschimbate.

## 1.10.0

- `tb-gen-index`: două insigne noi în antetul paginii Apps Store, cu aceleași reguli ca
  bannerul (skill-ul `banner-modul`): **limbile** livrate („EN · RO · DE · FR · IT · ES”),
  adică engleza plus fiecare `i18n/<limbă>.po` tradus cel puțin 90% (fără `fuzzy`), doar de la
  3 limbi în sus; **Uniunea Europeană** pentru modulele cu `"eu": true` în `banner.json`
  (aplică o regulă UE sau merg în mai multe țări europene).

## 1.9.0

- `tb-gen-index`: pagina Apps Store preia elementele paginilor bune din store
  (ex. eb_bill_integration): antet cu gradient verde (peste fundalul plin, păstrat ca rezervă),
  iconițe Font Awesome pe insignele din antet, pe taburi și pe cardurile de funcții (alese după
  cuvintele din text), titlurile `##` în fontul Caveat cu markerul verde al store-ului, eticheta
  tabului deasupra panoului și capturile singure în paragraf ca galerie numerotată, cu legenda
  din textul alternativ. Bara verde a titlurilor mici folosește `border-left-*`, pentru că
  store-ul taie `border-left` prescurtat.
- `tb_apps_preview.py` filtrează stilurile inline după whitelist-ul real al sanitizer-ului Odoo
  (`_Cleaner._style_whitelist`) și încarcă Font Awesome 4 și Caveat, ca pe store.

## 1.8.1

- `tb-gen-index`: numărul de module din pagina Apps Store (cardul cu cifra și textul despre
  aplicațiile Terrabit) devine „600+”, cât arată acum Apps Store pe 19.0, în loc de „350+”.

## 1.8.0

- `tb-gen-index`: la modulele fără cod Python (fără `__init__.py`), eticheta de găzduire din
  antetul paginii Apps Store devine „Odoo Online • Odoo.sh • On-premise”. Astfel de module se
  încarcă pe Odoo Online ca zip, din Apps > Import Module (`base_import_module`).

## 1.6.0

- `check-module-icon` pică, nu mai doar avertizează, la `icon.png` generic (rotițe dințate).
  Pică și dacă manifestul nu are cheia `images`, dacă lipsește `static/description/banner.json`
  sau dacă `main_screenshot.png` este bannerul comun „Deltatech – Shared base for the Deltatech
  suite”. Bannerul comun e recunoscut după hash-ul variantelor 18.0/19.0/20.0 și după bannerul
  modulului `deltatech` din același repo, pe care hook-ul local `check-module-images` al suitei
  îl copiază la modulele noi. Excepție: modulul `deltatech`. Iconița se desenează cu skill-ul
  `iconita-modul`, bannerul se generează cu `banner-modul`.

## 1.5.0

- `tb-odoo-lint`: regula O20-PY-06 (avertisment, doar pe 20.0) semnalează `base64.b64encode()`
  scris direct într-un câmp care arată a Binary (`image_*`, `*_file`, `*_attachment`, `*pdf*` ...).
  În Odoo 20 un câmp Binary nu mai primește bytes (`TypeError` din `fields_binary.convert_to_cache`);
  se scrie `BinaryBytes(continut)`, un text base64 cu `.decode()` sau, pe ir.attachment, `raw`.
  Pe câmpurile proprii care acceptă bytes (subclase Binary ca `LabelBinary`) se dezactivează pe
  linie cu `tb-lint: disable=O20-PY-06`. Preluată din regula L17 a
  [odoo-agent-pro-kit](https://github.com/infovpcs/odoo-agent-pro-kit) (Apache-2.0).

## 1.4.0

- Hook-ul `tb-odoo-lint`: API Odoo 19/20 eliminate sau redenumite, doar pe fișierele încărcate.
