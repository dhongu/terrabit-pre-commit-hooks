# Istoric

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
