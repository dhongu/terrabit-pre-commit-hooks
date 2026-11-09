# Istoric

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
