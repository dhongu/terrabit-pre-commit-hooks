#!/usr/bin/env python
"""Verifica modulele Odoo 19/20 pentru API-urile eliminate sau redenumite.

Regulile vin din capcanele intalnite la migrarea pe 19.0 si 20.0: unele rup
instalarea (`<tree>`, `attrs=`, `<group expand>` in search), altele dau eroare
doar la rulare (`product.uom_po_id`), iar cateva sunt ignorate fara nicio eroare
(`_sql_constraints`, optiunea `format` a widget-ului integer).

Se verifica DOAR ce incarca Odoo din modul:
  - XML/CSV: fisierele din cheile `data` si `demo` ale manifestului
    (`oca_data_manual` si fisierele nelistate nu se incarca);
  - Python: fisierele atinse de importurile active pornind de la `__init__.py`
    (un `# from . import x` comentat scoate `x.py` din verificare);
  - testele (`tests/__init__.py` si importurile lui), cu severitatea redusa
    la avertisment;
  - `static/description/index.html` (pagina Odoo Apps).
Folderul `migrations/` nu se verifica: scripturile de migrare lucreaza intentionat
cu campurile vechi.

Python-ul se analizeaza pe AST, deci comentariile si docstring-urile nu dau
alarme. XML-ul se analizeaza pe arbore, nu pe text.

Versiunea Odoo se citeste din `version` din manifest (`19.0.x.y.z`); pentru un
manifest fara serie se foloseste `--odoo-version`.

Exceptie explicita, pe aceeasi linie sau pe linia de deasupra:

    from odoo import _  # tb-lint: disable=O19-PY-01 fara env in clientul API
    <!-- tb-lint: disable=O19-XML-03 -->

sau pentru tot fisierul: `tb-lint: disable-file=O19-PY-01`.

Folosire:

    tb-odoo-lint fisier1.py fisier2.xml          # ca hook pre-commit
    tb-odoo-lint --addons-dir odoo-addons/deltatech   # audit pe o suita

Iese cu 1 daca a gasit o constatare blocanta (`block`); cu `--warn-only` iese
mereu cu 0.
"""

# pylint: disable=print-used
# `print` este interfata unui hook de pre-commit: pre-commit capteaza stdout/stderr
# si le arata utilizatorului. Un logger nu ar aparea nicaieri.
import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from xml.parsers import expat

BLOCK = "block"
WARN = "warn"

# id: ({versiune: severitate}, mesaj, cum se repara)
REGULI = {
    # ---- Python, Odoo 19 ----
    "O19-PY-01": (
        {"19": WARN, "20": WARN},
        "`_` importat din odoo",
        'folosește `self.env._("text")`; `_` rămâne doar unde nu există `env` (cu tb-lint: disable)',
    ),
    "O19-PY-02": (
        {"19": BLOCK, "20": BLOCK},
        "`_sql_constraints` e ignorat fără eroare din Odoo 19",
        'declară `_nume = models.Constraint("UNIQUE(...)", "mesaj")` (sau models.Index / UniqueIndex)',
    ),
    "O19-PY-03": (
        {"19": BLOCK, "20": BLOCK},
        "câmp sau model eliminat în Odoo 19",
        "vezi înlocuitorul de mai jos",
    ),
    "O19-PY-04": (
        {"19": WARN, "20": WARN},
        "`product_uom` pe linia de vânzare/achiziție (redenumit `product_uom_id` în Odoo 19)",
        "folosește `product_uom_id`; `stock.move` păstrează `product_uom`",
    ),
    "O19-PY-05": (
        {"19": BLOCK, "20": BLOCK},
        "`create` cu `@api.model` primește o listă de valori, nu un dict",
        "folosește `@api.model_create_multi` și `def create(self, vals_list)`",
    ),
    "O19-PY-06": (
        {"19": WARN, "20": WARN},
        "`cr.execute()` cu text compus, fără `SQL()`",
        'construiește interogarea cu `SQL("... %s", valoare)` din odoo.tools',
    ),
    "O19-PY-07": (
        {"19": BLOCK, "20": BLOCK},
        "`name_search` cu `args` (în Odoo 19 parametrul e `domain`)",
        '`def name_search(self, name="", domain=None, operator="ilike", limit=100)`',
    ),
    "O19-PY-08": (
        {"19": WARN, "20": WARN},
        '`@route(type="json")` e depreciat din Odoo 19',
        'folosește `type="jsonrpc"`',
    ),
    "O19-PY-09": (
        {"19": WARN, "20": WARN},
        "`mobile` pe partener (eliminat în Odoo 19)",
        "folosește `phone`; pe alte modele decât res.partner, dezactivează regula pe linie",
    ),
    "O19-PY-10": (
        {"19": WARN, "20": WARN},
        "`groups_id` (redenumit `group_ids` pe res.users, ir.ui.view, ir.ui.menu, ir.actions.*)",
        "folosește `group_ids`; pe un model propriu cu câmpul `groups_id`, dezactivează regula pe linie",
    ),
    # ---- XML, Odoo 19 ----
    "O19-XML-01": ({"19": BLOCK, "20": BLOCK}, "element `<tree>` în view", "înlocuiește `<tree>` cu `<list>`"),
    "O19-XML-02": (
        {"19": BLOCK, "20": BLOCK},
        "atribut `attrs=`/`states=` (eliminate din 17.0)",
        "folosește direct `invisible=`, `readonly=`, `required=` cu expresii Python",
    ),
    "O19-XML-03": (
        {"19": BLOCK, "20": BLOCK},
        "`<group string/expand>` în search view (invalid RNG din Odoo 19, rupe instalarea)",
        "lasă `<group>` gol sau doar cu `name`; eticheta o pune clientul",
    ),
    "O19-XML-04": (
        {"19": BLOCK, "20": BLOCK},
        "tag-ul `<report>` (eliminat)",
        'declară `<record model="ir.actions.report">`',
    ),
    "O19-XML-05": (
        {"19": BLOCK, "20": BLOCK},
        "câmp invalid pe `ir.actions.act_window`",
        "`view_type` nu mai există (șterge-l); `target=inline` nu mai există (folosește `current`)",
    ),
    "O19-XML-06": (
        {"19": BLOCK, "20": BLOCK},
        "`allowed_company_ids` în `domain_force` al unui ir.rule (nedefinit acolo, eroare de domeniu)",
        "în ir.rule variabila e `company_ids`",
    ),
    "O19-XML-07": (
        {"19": BLOCK, "20": BLOCK},
        "câmp redenumit pe grupuri/utilizatori/acțiuni/meniuri",
        "res.groups: `category_id` → `privilege_id` (res.groups.privilege), `users` → `user_ids`; "
        "res.users, ir.ui.view, ir.ui.menu, ir.actions.*: `groups_id` → `group_ids`",
    ),
    "O19-XML-08": (
        {"19": WARN, "20": WARN},
        "opțiunea `format` e ignorată fără eroare (widget integer/float)",
        "folosește `enable_formatting`",
    ),
    "O19-XML-09": (
        {"19": BLOCK, "20": BLOCK},
        "`<?xml ?>` la începutul `static/description/index.html` rupe registry-ul",
        "șterge declarația XML; pagina e HTML",
    ),
    # ---- Odoo 20 ----
    "O20-PY-01": (
        {"20": BLOCK},
        "`get_param`/`set_param` pe ir.config_parameter (eliminate în Odoo 20)",
        "folosește API-ul tipizat: get_str/get_int/get_float/get_bool și set_str/set_int/set_float/set_bool",
    ),
    "O20-PY-02": (
        {"20": WARN},
        "scriere pe `is_company` (în Odoo 20 e calculat din commercial_partner și has_vat)",
        "nu-l scrie și nu decide fiscal pe el",
    ),
    "O20-PY-03": (
        {"20": BLOCK},
        "API eliminat în Odoo 20",
        "`toggle_active()` → `action_archive()/action_unarchive()`; `_table_query` → proprietatea "
        "`_table_sql` care întoarce SQL; `registry._init` → `not registry.ready`",
    ),
    "O20-PY-04": (
        {"20": BLOCK},
        "`ir.attachment.datas` (eliminat în Odoo 20, scrierea e ignorată fără eroare)",
        "scrie octeții în `raw` (sau `BinaryBytes(...)` din odoo.tools)",
    ),
    "O20-PY-05": (
        {"20": WARN},
        "`mail.tracking.value` / `tracking_value_ids` (mutate în modulul mail_tracking în Odoo 20)",
        "adaugă `mail_tracking` în depends sau renunță la valorile de tracking stocate",
    ),
    "O20-PY-06": (
        {"20": WARN},
        "`base64.b64encode()` (bytes) scris într-un câmp Binary (în Odoo 20 dă TypeError la scriere)",
        "scrie octeții prin `BinaryBytes(continut)` din odoo.tools, un text base64 cu `.decode()` "
        "sau, pe ir.attachment, în `raw`",
    ),
    "O20-XML-01": (
        {"20": BLOCK},
        "`ir.model.access.csv` (modelul de ACL e eliminat în Odoo 20)",
        "convertește în `security/ir.access.csv` (`odoo-bin upgrade_code --script 19.4-00-ir-access`)",
    ),
    "O20-XML-02": (
        {"20": BLOCK},
        "record `ir.rule` (regulile de înregistrare sunt eliminate în Odoo 20)",
        "mută domeniul pe un rând `ir.access` (același script upgrade_code)",
    ),
    "O20-XML-03": (
        {"20": BLOCK},
        "element eliminat din view-uri în Odoo 20",
        "`t-esc` → `t-out`; butonul `toggle_active`/widget `boolean_button` → arhivarea standard "
        "sau `boolean_toggle`; câmpul `datas` → `raw`",
    ),
    "O20-XML-04": (
        {"20": WARN},
        "iconiță Font Awesome (clientul web folosește Material Symbols în Odoo 20)",
        "preferă Material Symbols; Font Awesome rămâne doar pentru compatibilitate",
    ),
}

# Campuri/modele eliminate in 19 (O19-PY-03): ca atribut si ca text exact, cu inlocuitorul.
INLOCUITORI_19 = {
    "uom_po_id": "`uom_id` (sau `seller.product_uom_id` pentru unitatea furnizorului)",
    "procurement.group": "`stock.reference`",
    "uom.category": "arborele `relative_uom_id` din uom.uom",
    "account.fiscal.position.tax": "`account.tax.original_tax_ids`",
}
ELIMINATE_19_ATRIBUTE = {"uom_po_id"}
ELIMINATE_19_TEXT = {"uom_po_id", "procurement.group", "uom.category", "account.fiscal.position.tax"}
LINII_SOL_POL = {"sale.order.line", "purchase.order.line"}
NUME_LINIE = {"self", "line", "rec", "record", "sol", "pol", "order_line"}
RE_DEZACTIVARE = re.compile(r"tb-lint:\s*disable=([\w,\s-]+)")
# dezactivarea pylint-odoo pentru SQL compus acopera si O19-PY-06
RE_PYLINT_SQL = re.compile(r"pylint:\s*disable=[\w,\s-]*\b(?:E8103|sql-injection)\b")
RE_DEZACTIVARE_FISIER = re.compile(r"tb-lint:\s*disable-file=([\w,\s-]+)")
RE_SERIE = re.compile(r"^\s*(\d+)\.0\.")
RE_FORMAT_OPTIUNE = re.compile(r"""['"]format['"]\s*:""")
RE_FONT_AWESOME = re.compile(r"(?:^|\s)fa\s+fa-")
# O20-PY-06: numele care arata a camp Binary; `_id(s)`/`name` (relatii, nume de fisier) nu sunt binare
RE_CAMP_BINAR = re.compile(r"image|logo|icon|avatar|file|attachment|pdf|signature|binary|document")
RE_CAMP_NEBINAR = re.compile(r"(?:_ids?|name)$")
FUNCTII_B64_BYTES = {"b64encode", "standard_b64encode", "encodebytes"}
MODELE_GROUP_IDS = {
    "res.users",
    "ir.ui.view",
    "ir.ui.menu",
    "ir.actions.act_window",
    "ir.actions.server",
    "ir.actions.report",
    "ir.actions.act_url",
    "ir.actions.client",
}


@dataclass
class Constatare:
    cale: str
    linie: int
    regula: str
    severitate: str
    mesaj: str
    detaliu: str = ""

    def text(self):
        _versiuni, mesaj, fix = REGULI[self.regula]
        if self.regula == "O19-PY-03" and self.detaliu in INLOCUITORI_19:
            fix = f"folosește {INLOCUITORI_19[self.detaliu]}"
        detaliu = f" ({self.detaliu})" if self.detaliu else ""
        return f"{self.cale}:{self.linie}: [{self.regula}] {self.severitate}: {mesaj}{detaliu} → {fix}"


# --------------------------------------------------------------------------- modul


def gaseste_modul(cale):
    """Directorul modulului (cel cu `__manifest__.py`) care contine fisierul, sau None."""
    director = os.path.dirname(os.path.abspath(cale))
    while True:
        if os.path.isfile(os.path.join(director, "__manifest__.py")):
            return director
        parinte = os.path.dirname(director)
        if parinte == director:
            return None
        director = parinte


def citeste_manifest(modul):
    with open(os.path.join(modul, "__manifest__.py"), encoding="utf-8") as f:
        try:
            return ast.literal_eval(f.read())
        except (SyntaxError, ValueError):
            return {}


def versiune_odoo(manifest, implicita):
    m = RE_SERIE.match(str(manifest.get("version", "")))
    return m.group(1) if m else implicita


class Modul:
    """Ce incarca Odoo dintr-un modul: XML/CSV din manifest, Python din importuri."""

    def __init__(self, director, versiune_implicita):
        self.director = director
        self.nume = os.path.basename(director)
        self.manifest = citeste_manifest(director)
        self.versiune = versiune_odoo(self.manifest, versiune_implicita)
        self.date = set()
        for cheie in ("data", "demo"):
            for rel in self.manifest.get(cheie, []) or []:
                self.date.add(os.path.normpath(os.path.join(director, rel)))
        self.python = set()
        self._urmeaza(os.path.join(director, "__init__.py"), self.python)
        self.teste = set()
        self._urmeaza(os.path.join(director, "tests", "__init__.py"), self.teste)
        self.teste -= self.python
        index = os.path.join(director, "static", "description", "index.html")
        self.index_html = index if os.path.isfile(index) else None

    def este_incarcat(self, cale):
        cale = os.path.normpath(os.path.abspath(cale))
        return cale in self.date or cale in self.python or cale in self.teste or cale == self.index_html

    def este_test(self, cale):
        return os.path.normpath(os.path.abspath(cale)) in self.teste

    def fisiere(self):
        return sorted(
            c for c in self.date | self.python | self.teste | ({self.index_html} - {None}) if os.path.isfile(c)
        )

    def _modul_python(self, baza):
        """`baza` (fara extensie) ca pachet (`baza/__init__.py`) sau fisier (`baza.py`)."""
        if os.path.isfile(os.path.join(baza, "__init__.py")):
            return os.path.join(baza, "__init__.py")
        if os.path.isfile(baza + ".py"):
            return baza + ".py"
        return None

    def _urmeaza(self, cale, acumulat):
        cale = os.path.normpath(cale)
        if cale in acumulat or not os.path.isfile(cale):
            return
        if os.sep + "migrations" + os.sep in cale:
            return
        acumulat.add(cale)
        try:
            with open(cale, encoding="utf-8") as f:
                arbore = ast.parse(f.read(), cale)
        except (SyntaxError, UnicodeDecodeError):
            return
        for nod in ast.walk(arbore):
            if not isinstance(nod, ast.ImportFrom):
                continue
            if nod.level:
                baza = os.path.dirname(cale)
                for _i in range(nod.level - 1):
                    baza = os.path.dirname(baza)
                parti = nod.module.split(".") if nod.module else []
            elif nod.module and nod.module.startswith(f"odoo.addons.{self.nume}"):
                baza = self.director
                parti = nod.module.split(".")[3:]
            else:
                continue
            tinta = os.path.join(baza, *parti)
            if parti:
                fisier = self._modul_python(tinta)
                if fisier:
                    self._urmeaza(fisier, acumulat)
                if not os.path.isdir(tinta):
                    continue
            for alias in nod.names:
                fisier = self._modul_python(os.path.join(tinta, alias.name))
                if fisier:
                    self._urmeaza(fisier, acumulat)


# --------------------------------------------------------------------------- dezactivari


def dezactivari(text):
    """({linie: {reguli}}, {reguli pe tot fisierul}). O dezactivare acopera linia ei si urmatoarea."""
    pe_linie, pe_fisier = {}, set()
    for nr, linie in enumerate(text.splitlines(), 1):
        for m in RE_DEZACTIVARE_FISIER.finditer(linie):
            pe_fisier |= {r.strip() for r in m.group(1).split(",") if r.strip()}
        for m in RE_DEZACTIVARE.finditer(linie):
            reguli = {r.strip().split()[0] for r in m.group(1).split(",") if r.strip()}
            for tinta in (nr, nr + 1):
                pe_linie.setdefault(tinta, set()).update(reguli)
        if RE_PYLINT_SQL.search(linie):
            for tinta in (nr, nr + 1):
                pe_linie.setdefault(tinta, set()).add("O19-PY-06")
    return pe_linie, pe_fisier


# --------------------------------------------------------------------------- Python


def _text(nod):
    return nod.value if isinstance(nod, ast.Constant) and isinstance(nod.value, str) else None


def _modele_clasa(clasa):
    """Modelele din `_name`/`_inherit` ale unei clase."""
    modele = set()
    for nod in clasa.body:
        if not isinstance(nod, ast.Assign):
            continue
        for tinta in nod.targets:
            if isinstance(tinta, ast.Name) and tinta.id in ("_name", "_inherit"):
                valori = nod.value.elts if isinstance(nod.value, (ast.List, ast.Tuple)) else [nod.value]
                modele |= {v for v in map(_text, valori) if v}
    return modele


def _camp_binar(nume):
    return bool(nume) and bool(RE_CAMP_BINAR.search(nume)) and not RE_CAMP_NEBINAR.search(nume)


def _b64_bytes(nod):
    """`base64.b64encode(x)` direct (bytes); cu `.decode()` deasupra devine text si nu se semnaleaza."""
    if not isinstance(nod, ast.Call):
        return False
    functie = nod.func
    nume = functie.attr if isinstance(functie, ast.Attribute) else getattr(functie, "id", None)
    return nume in FUNCTII_B64_BYTES


def _nume_decorator(dec):
    dec = dec.func if isinstance(dec, ast.Call) else dec
    try:
        return ast.unparse(dec)
    except Exception:  # pylint: disable=broad-except
        return ""


class VerificatorPython(ast.NodeVisitor):
    def __init__(self, emite):
        self.emite = emite
        self.clase = []  # stiva de seturi de modele
        self.parinti = {}
        self.icp_variabile = set()
        self.import_underscore = None
        self.clase_model = []  # stiva: clasa curenta e model Odoo (are self.env)

    def verifica(self, arbore):
        for parinte in ast.walk(arbore):
            for copil in ast.iter_child_nodes(parinte):
                self.parinti[copil] = parinte
        # variabile legate de ir.config_parameter (`icp = self.env["ir.config_parameter"].sudo()`)
        for nod in ast.walk(arbore):
            if isinstance(nod, ast.Assign) and "ir.config_parameter" in ast.unparse(nod.value):
                self.icp_variabile |= {t.id for t in nod.targets if isinstance(t, ast.Name)}
        self.visit(arbore)
        if self.import_underscore is not None and self.underscore_in_model:
            self.emite(self.import_underscore, "O19-PY-01")

    underscore_in_model = False

    def modele_curente(self):
        return self.clase[-1] if self.clase else set()

    # -- importuri
    def visit_ImportFrom(self, nod):
        if nod.module in ("odoo", "odoo.tools.translate") and any(a.name == "_" for a in nod.names):
            self.import_underscore = nod
        self.generic_visit(nod)

    # -- clase
    def visit_ClassDef(self, nod):
        self.clase.append(_modele_clasa(nod))
        baze = " ".join(ast.unparse(b) for b in nod.bases)
        self.clase_model.append(bool(re.search(r"\b(?:Model|TransientModel|AbstractModel)\b", baze)))
        for copil in nod.body:
            if isinstance(copil, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_sql_constraints" for t in copil.targets
            ):
                self.emite(copil, "O19-PY-02")
            if isinstance(copil, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_table_query" for t in copil.targets
            ):
                self.emite(copil, "O20-PY-03", "_table_query")
        self.generic_visit(nod)
        self.clase.pop()
        self.clase_model.pop()

    def visit_FunctionDef(self, nod):
        if self.clase:
            decoratori = [_nume_decorator(d) for d in nod.decorator_list]
            if nod.name == "create" and "api.model" in decoratori and "api.model_create_multi" not in decoratori:
                self.emite(nod, "O19-PY-05")
            if nod.name == "name_search" and any(a.arg == "args" for a in nod.args.args + nod.args.kwonlyargs):
                self.emite(nod, "O19-PY-07")
            if nod.name == "_table_query":
                self.emite(nod, "O20-PY-03", "_table_query")
        for dec in nod.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and _nume_decorator(dec).endswith("route")
                and any(k.arg == "type" and _text(k.value) == "json" for k in dec.keywords)
            ):
                self.emite(dec, "O19-PY-08")
        self.generic_visit(nod)

    visit_AsyncFunctionDef = visit_FunctionDef

    # -- atribute
    def _sub_hasattr(self, nod, nume):
        """Atributul e pazit de `hasattr(x, "nume")` in aceeasi expresie booleana."""
        parinte = self.parinti.get(nod)
        while parinte is not None and not isinstance(parinte, ast.stmt):
            if isinstance(parinte, ast.BoolOp):
                for valoare in ast.walk(parinte):
                    if (
                        isinstance(valoare, ast.Call)
                        and isinstance(valoare.func, ast.Name)
                        and valoare.func.id == "hasattr"
                        and len(valoare.args) == 2
                        and _text(valoare.args[1]) == nume
                    ):
                        return True
            parinte = self.parinti.get(parinte)
        return False

    def visit_Attribute(self, nod):
        atr = nod.attr
        if atr in ELIMINATE_19_ATRIBUTE:
            self.emite(nod, "O19-PY-03", atr)
        elif atr == "mobile" and not self._sub_hasattr(nod, "mobile"):
            self.emite(nod, "O19-PY-09")
        elif atr == "groups_id":
            self.emite(nod, "O19-PY-10")
        elif (
            atr == "product_uom"
            and self.modele_curente() & LINII_SOL_POL
            and isinstance(nod.value, ast.Name)
            and nod.value.id in NUME_LINIE
        ):
            self.emite(nod, "O19-PY-04")
        elif atr == "datas":
            self.emite(nod, "O20-PY-04")
        elif atr == "tracking_value_ids":
            self.emite(nod, "O20-PY-05")
        elif atr == "_init" and isinstance(nod.value, ast.Attribute) and nod.value.attr == "registry":
            self.emite(nod, "O20-PY-03", "registry._init")
        self.generic_visit(nod)

    def visit_Assign(self, nod):
        for tinta in nod.targets:
            if isinstance(tinta, ast.Attribute) and tinta.attr == "is_company":
                self.emite(nod, "O20-PY-02")
            if isinstance(tinta, ast.Attribute) and _camp_binar(tinta.attr) and _b64_bytes(nod.value):
                self.emite(nod, "O20-PY-06", tinta.attr)
        self.generic_visit(nod)

    # -- texte
    def visit_Constant(self, nod):
        valoare = _text(nod)
        if valoare in ELIMINATE_19_TEXT:
            self.emite(nod, "O19-PY-03", valoare)
        elif valoare == "mail.tracking.value":
            self.emite(nod, "O20-PY-05")

    def visit_Dict(self, nod):
        chei = {_text(k): k for k in nod.keys if k is not None}
        # `datas` ca cheie e si in payload-urile catre alte servere (RPC, API): se semnaleaza doar
        # cand dict-ul arata a valori de ir.attachment
        if "datas" in chei and chei.keys() & {"res_model", "res_id", "res_field", "mimetype", "type"}:
            self.emite(chei["datas"], "O20-PY-04")
        if "is_company" in chei:
            self.emite(chei["is_company"], "O20-PY-02")
        if "groups_id" in chei:
            self.emite(chei["groups_id"], "O19-PY-10")
        for cheie, valoare in zip(nod.keys, nod.values, strict=True):
            if _camp_binar(_text(cheie)) and _b64_bytes(valoare):
                self.emite(cheie, "O20-PY-06", _text(cheie))
        if "order_line" in chei:
            # sale.order/purchase.order create: liniile din `order_line` sunt SOL/POL
            valoare = nod.values[list(nod.keys).index(chei["order_line"])]
            for interior in ast.walk(valoare):
                if isinstance(interior, ast.Dict):
                    for cheie in interior.keys:
                        if _text(cheie) == "product_uom":
                            self.emite(cheie, "O19-PY-04")
        if "product_uom" in chei and self.modele_curente() & LINII_SOL_POL and "location_id" not in chei:
            self.emite(chei["product_uom"], "O19-PY-04")
        # cheile Constant sunt verificate si de visit_Constant (texte eliminate)
        self.generic_visit(nod)

    def visit_Call(self, nod):
        functie = nod.func
        # `_()` apelat intr-un model Odoo: acolo exista `self.env._`
        if isinstance(functie, ast.Name) and functie.id == "_" and self.clase_model and self.clase_model[-1]:
            self.underscore_in_model = True
        if isinstance(functie, ast.Attribute):
            if functie.attr == "execute" and ast.unparse(functie.value).endswith("cr") and nod.args:
                argument = nod.args[0]
                compus = isinstance(argument, ast.JoinedStr) or (
                    isinstance(argument, ast.BinOp) and isinstance(argument.op, (ast.Mod, ast.Add))
                )
                compus |= (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Attribute)
                    and argument.func.attr == "format"
                )
                # un text constant cu parametrii separati e sigur; riscul e textul compus
                if compus:
                    self.emite(nod, "O19-PY-06")
            if functie.attr == "name_search" and any(k.arg == "args" for k in nod.keywords):
                self.emite(nod, "O19-PY-07")
            if functie.attr in ("get_param", "set_param"):
                receptor = functie.value
                if isinstance(receptor, ast.Call) and isinstance(receptor.func, ast.Attribute):
                    receptor_text = ast.unparse(receptor)
                else:
                    receptor_text = ast.unparse(receptor)
                legat = "ir.config_parameter" in receptor_text or (
                    isinstance(receptor, ast.Name) and receptor.id in self.icp_variabile
                )
                if legat:
                    self.emite(nod, "O20-PY-01", functie.attr)
            if functie.attr == "toggle_active":
                self.emite(nod, "O20-PY-03", "toggle_active()")
            if functie.attr in ("create", "write") and "ir.attachment" in ast.unparse(functie.value):
                for argument in nod.args:
                    for interior in ast.walk(argument):
                        if isinstance(interior, ast.Dict):
                            for cheie in interior.keys:
                                if _text(cheie) == "datas":
                                    self.emite(cheie, "O20-PY-04")
        self.generic_visit(nod)


def verifica_python(cale, text, emite):
    try:
        arbore = ast.parse(text, cale)
    except SyntaxError as e:
        print(f"{cale}:{e.lineno}: nu se poate analiza ({e.msg})", file=sys.stderr)
        return
    VerificatorPython(lambda nod, regula, detaliu="": emite(nod.lineno, regula, detaliu)).verifica(arbore)


# --------------------------------------------------------------------------- XML


class Nod:
    __slots__ = ("tag", "attrib", "copii", "parinte", "linie", "text")

    def __init__(self, tag, attrib, parinte, linie):
        self.tag, self.attrib, self.parinte, self.linie = tag, attrib, parinte, linie
        self.copii, self.text = [], ""

    def iter(self):
        yield self
        for copil in self.copii:
            yield from copil.iter()

    def camp(self, nume):
        return next((c for c in self.copii if c.tag == "field" and c.attrib.get("name") == nume), None)


def parseaza_xml(text):
    """Arbore simplu cu numarul liniei pe fiecare element (ElementTree nu il pastreaza)."""
    parser = expat.ParserCreate()
    radacina = Nod("#document", {}, None, 0)
    stiva = [radacina]

    def start(tag, attrib):
        nod = Nod(tag, attrib, stiva[-1], parser.CurrentLineNumber)
        stiva[-1].copii.append(nod)
        stiva.append(nod)

    def sfarsit(_tag):
        stiva.pop()

    def date(text_bucata):
        stiva[-1].text += text_bucata

    parser.StartElementHandler = start
    parser.EndElementHandler = sfarsit
    parser.CharacterDataHandler = date
    parser.Parse(text.encode("utf-8"), True)
    return radacina


def _arhitecturi(radacina):
    """(nodul arhitecturii, este template QWeb) pentru fiecare view din fisier."""
    for nod in radacina.iter():
        if nod.tag == "record" and nod.attrib.get("model") == "ir.ui.view":
            arch = nod.camp("arch")
            if arch is not None:
                yield arch, False
        elif nod.tag == "template":
            yield nod, True


def verifica_xml(cale, text, emite):
    try:
        radacina = parseaza_xml(text)
    except expat.ExpatError as e:
        print(f"{cale}:{e.lineno}: XML invalid ({e})", file=sys.stderr)
        return

    for arch, este_template in _arhitecturi(radacina):
        for nod in arch.iter():
            if nod is arch:
                continue
            if nod.tag == "tree":
                emite(nod.linie, "O19-XML-01")
            if not este_template:
                for atr in ("attrs", "states"):
                    if atr in nod.attrib:
                        emite(nod.linie, "O19-XML-02", atr)
            if nod.tag == "group" and ("string" in nod.attrib or "expand" in nod.attrib):
                # un <group> cu <filter> e un grup de search view (form-ul nu are <filter>)
                in_search = any(c.tag == "filter" for c in nod.copii)
                stramos = nod.parinte
                while stramos is not None and not in_search:
                    in_search = stramos.tag == "search"
                    stramos = stramos.parinte
                if in_search:
                    emite(nod.linie, "O19-XML-03")
            optiuni = nod.attrib.get("options", "")
            if RE_FORMAT_OPTIUNE.search(optiuni):
                emite(nod.linie, "O19-XML-08")
            if not este_template and "t-esc" in nod.attrib:
                emite(nod.linie, "O20-XML-03", "t-esc")
            if nod.tag == "button" and nod.attrib.get("name") == "toggle_active":
                emite(nod.linie, "O20-XML-03", "toggle_active")
            if nod.tag == "field" and nod.attrib.get("widget") == "boolean_button":
                emite(nod.linie, "O20-XML-03", "boolean_button")
            if RE_FONT_AWESOME.search(nod.attrib.get("class", "")) or RE_FONT_AWESOME.search(
                nod.attrib.get("icon", "")
            ):
                emite(nod.linie, "O20-XML-04")

    for nod in radacina.iter():
        if nod.tag == "report" and nod.parinte is not None and nod.parinte.tag in ("odoo", "data", "openerp"):
            emite(nod.linie, "O19-XML-04")
        if nod.tag != "record":
            continue
        model = nod.attrib.get("model", "")
        campuri = {c.attrib.get("name"): c for c in nod.copii if c.tag == "field"}
        if model == "ir.actions.act_window":
            if "view_type" in campuri:
                emite(campuri["view_type"].linie, "O19-XML-05", "view_type")
            tinta = campuri.get("target")
            if tinta is not None and tinta.text.strip() == "inline":
                emite(tinta.linie, "O19-XML-05", "target=inline")
        if model == "ir.rule":
            emite(nod.linie, "O20-XML-02")
            domeniu = campuri.get("domain_force")
            if domeniu is not None and "allowed_company_ids" in (domeniu.text + domeniu.attrib.get("eval", "")):
                emite(domeniu.linie, "O19-XML-06")
        if model == "res.groups":
            for vechi in ("category_id", "users"):
                if vechi in campuri:
                    emite(campuri[vechi].linie, "O19-XML-07", f"res.groups.{vechi}")
        if model in MODELE_GROUP_IDS and "groups_id" in campuri:
            emite(campuri["groups_id"].linie, "O19-XML-07", f"{model}.groups_id")
        if model == "ir.attachment" and "datas" in campuri:
            emite(campuri["datas"].linie, "O20-XML-03", "datas")


def verifica_csv(cale, text, emite):
    if os.path.basename(cale) == "ir.model.access.csv" and text.strip():
        emite(1, "O20-XML-01")


def verifica_index_html(_cale, text, emite):
    if text.lstrip("﻿ \t\r\n").startswith("<?xml"):
        emite(1, "O19-XML-09")


# --------------------------------------------------------------------------- rulare


def verifica_fisier(cale, modul, cale_afisata=None):
    """Constatarile pentru un fisier incarcat de modul."""
    with open(cale, encoding="utf-8", errors="replace") as f:
        text = f.read()
    pe_linie, pe_fisier = dezactivari(text)
    este_test = modul.este_test(cale)
    rezultat = []

    def emite(linie, regula, detaliu=""):
        versiuni = REGULI[regula][0]
        severitate = versiuni.get(modul.versiune)
        if severitate is None or regula in pe_fisier or regula in pe_linie.get(linie, ()):
            return
        if este_test and severitate == BLOCK:
            severitate = WARN
        constatare = Constatare(cale_afisata or cale, linie, regula, severitate, REGULI[regula][1], detaliu)
        if constatare not in rezultat:
            rezultat.append(constatare)

    if cale == modul.index_html:
        verifica_index_html(cale, text, emite)
    elif cale.endswith(".py"):
        verifica_python(cale, text, emite)
    elif cale.endswith(".xml"):
        verifica_xml(cale, text, emite)
    elif cale.endswith(".csv"):
        verifica_csv(cale, text, emite)
    return rezultat


def module_din_director(director):
    for radacina, directoare, fisiere in os.walk(director):
        directoare[:] = sorted(d for d in directoare if not d.startswith(".") and d not in ("node_modules", "setup"))
        if "__manifest__.py" in fisiere:
            directoare[:] = []
            yield radacina


def ruleaza(cai, addons_dirs, versiune_implicita, include_neincarcate=False):
    module = {}
    tinte = []  # (cale, modul)

    def modul_pentru(director):
        if director not in module:
            module[director] = Modul(director, versiune_implicita)
        return module[director]

    for director in addons_dirs:
        for d in module_din_director(director):
            m = modul_pentru(os.path.abspath(d))
            tinte.extend((c, m) for c in m.fisiere())
    neincarcate = []
    for cale in cai:
        director = gaseste_modul(cale)
        if director is None:
            continue
        m = modul_pentru(director)
        absoluta = os.path.normpath(os.path.abspath(cale))
        if m.este_incarcat(absoluta) or include_neincarcate:
            tinte.append((absoluta, m))
        elif absoluta.endswith((".py", ".xml", ".csv")):
            neincarcate.append(cale)
    constatari = []
    vazute = set()
    for cale, m in tinte:
        if cale in vazute:
            continue
        vazute.add(cale)
        constatari.extend(verifica_fisier(cale, m, os.path.relpath(cale)))
    return constatari, neincarcate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*")
    parser.add_argument("--addons-dir", action="append", default=[], help="verifică toate modulele din director")
    parser.add_argument("--odoo-version", default="19", help="versiunea pentru manifestele fără serie (implicit 19)")
    parser.add_argument("--warn-only", action="store_true", help="iese cu 0 și la constatări blocante")
    parser.add_argument("--json", action="store_true", help="constatările ca JSON pe stdout")
    parser.add_argument(
        "--show-unloaded", action="store_true", help="arată fișierele primite care nu sunt încărcate de modul"
    )
    args = parser.parse_args(argv)

    constatari, neincarcate = ruleaza(args.files, args.addons_dir, args.odoo_version)
    if args.json:
        print(json.dumps([asdict(c) for c in constatari], ensure_ascii=False, indent=1))
    else:
        for c in constatari:
            print(c.text())
        if args.show_unloaded:
            for cale in neincarcate:
                print(f"{cale}: neverificat, nu e încărcat de modul (lipsește din `data` sau import comentat)")
    blocante = [c for c in constatari if c.severitate == BLOCK]
    return 1 if blocante and not args.warn_only else 0


def cli():
    sys.exit(main())


if __name__ == "__main__":
    cli()
