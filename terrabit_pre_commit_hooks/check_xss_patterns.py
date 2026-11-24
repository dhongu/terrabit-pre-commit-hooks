#!/usr/bin/env python
"""Opreste tiparele XSS din modulele Odoo: HTML construit din valori neescapate.

Regulile vin din auditul facut dupa CVE-2026-130029 (XSS in Odoo <= 20.0, reparat in
`odoo/tools/mail.py` si in DOMPurify). Toate cazurile gasite atunci se puteau vedea static:

  - deltatech_maintenance: `Markup(f"Created stock picking {link} ...")`;
  - deltatech_mcp: `Markup(f"{text}<br/>{link}")` cu textul raspunsului AI;
  - agroamat_blog: `Markup(json.dumps(...))` intr-un `<script>` si `fields.Html(sanitize=False)`;
  - agroamat_marketing: previzualizare `text/html` servita fara `Content-Security-Policy`.

Python (pe AST, deci comentariile si docstring-urile nu dau alarme):
  XSS-PY-01  `Markup(f"...{x}...")`
  XSS-PY-02  `Markup("..." + x)` si `Markup(x) + ...` cu `x` nelitera
  XSS-PY-03  `Markup("...%s" % x)`: `%` aplicat inainte de Markup
  XSS-PY-04  `Markup("...{}".format(x))`: `.format()` aplicat inainte de Markup
  XSS-PY-05  `Markup(json.dumps(...))`: `</script>` din date inchide eticheta
  XSS-PY-06  `fields.Html(..., sanitize=False)`, `sanitize_attributes=False`, `sanitize_tags=False`
  XSS-PY-07  `make_response(...)` cu `text/html` fara antetul `Content-Security-Policy`

Corect, nu se raporteaza: `Markup("...%s") % x` si `Markup("...{}").format(x)` (escapeaza `x`),
`Markup("a") + x` (escapeaza `x`), `Markup(_("..."))`.

JavaScript / OWL (pe linii; un argument care e doar un string literal nu se raporteaza):
  XSS-JS-01  `el.innerHTML = x` / `outerHTML`
  XSS-JS-02  `insertAdjacentHTML(pos, x)`
  XSS-JS-03  `$(...).html(x)`
  XSS-JS-04  `markup(x)` din OWL

XML (QWeb):
  XSS-XML-01 `t-raw=` (depreciat din Odoo 15; `t-out` cu Markup) - avertisment
  XSS-XML-02 `<iframe sandbox="allow-scripts allow-same-origin">`: continutul isi poate scoate sandbox-ul

Exceptie pe linia constatarii sau pe linia de deasupra, cu motiv obligatoriu:

    body = Markup(f"<b>{n}</b>")  # xss-ok: n este int
    // xss-ok: html vine din DOMPurify.sanitize
    <!-- xss-ok: sursa e un camp sanitizat -->

`xss-ok` fara motiv nu ascunde constatarea (XSS-OK-00). Fisierele din `tests/`, `static/lib/` si
`migrations/` nu se verifica. Iese cu 1 la erori; avertismentele (t-raw) nu opresc commit-ul, iar
`--warn-only` iese mereu cu 0. `--summary` adauga numarul de constatari pe regula.
"""

# pylint: disable=print-used
# `print` este interfata unui hook de pre-commit: pre-commit capteaza stdout si il arata.
import argparse
import ast
import os
import re
import sys
from collections import Counter

EROARE = "error"
AVERTISMENT = "warning"

REGULI = {
    "XSS-PY-01": (
        EROARE,
        'Markup(f"...") nu escapează valorile; folosește Markup("...{}").format(x)',
    ),
    "XSS-PY-02": (
        EROARE,
        'concatenare cu Markup pe o valoare neescapată; folosește Markup("...{}").format(x)',
    ),
    "XSS-PY-03": (
        EROARE,
        '`%` aplicat înainte de Markup nu escapează; scrie Markup("...%s") % x',
    ),
    "XSS-PY-04": (
        EROARE,
        '`.format()` aplicat înainte de Markup nu escapează; scrie Markup("...{}").format(x)',
    ),
    "XSS-PY-05": (
        EROARE,
        "Markup(json.dumps(...)) lasă `</script>` neatins; escapează `<`, `>`, `&` (\\u003c...) înainte de Markup",
    ),
    "XSS-PY-06": (
        EROARE,
        "câmp Html fără sanitizare; folosește sanitize_overridable=True sau un câmp readonly calculat",
    ),
    "XSS-PY-07": (
        EROARE,
        "răspuns text/html fără antet Content-Security-Policy (de ex. `sandbox`)",
    ),
    "XSS-JS-01": (
        EROARE,
        "innerHTML/outerHTML din valoare nelitera; folosește textContent sau DOMPurify.sanitize",
    ),
    "XSS-JS-02": (
        EROARE,
        "insertAdjacentHTML din valoare nelitera; folosește insertAdjacentText sau DOMPurify.sanitize",
    ),
    "XSS-JS-03": (
        EROARE,
        "$(...).html(x) din valoare nelitera; folosește .text(x) sau DOMPurify.sanitize",
    ),
    "XSS-JS-04": (
        EROARE,
        "markup(x) pe o valoare nelitera; marchează doar HTML sanitizat (DOMPurify / html_sanitize)",
    ),
    "XSS-XML-01": (
        AVERTISMENT,
        "t-raw este depreciat; folosește t-out cu o valoare Markup",
    ),
    "XSS-XML-02": (
        EROARE,
        "iframe cu sandbox allow-scripts + allow-same-origin își poate scoate sandbox-ul",
    ),
    "XSS-OK-00": (EROARE, "`xss-ok` fără motiv; scrie `xss-ok: <motiv>`"),
}

EXCLUSE = ("tests", "migrations")
# Motivul: textul de dupa `xss-ok:`, pana la `-->` / `*/` sau capatul liniei.
RE_EXCEPTIE = re.compile(r"xss-ok\b(?:\s*:((?:(?!-->|\*/).)*))?")


class Constatare:
    def __init__(self, cale, linie, regula, detaliu=""):
        self.cale = cale
        self.linie = linie
        self.regula = regula
        self.detaliu = detaliu

    @property
    def severitate(self):
        return REGULI[self.regula][0]

    def text(self):
        mesaj = REGULI[self.regula][1]
        if self.detaliu:
            mesaj = f"{self.detaliu}: {mesaj}"
        prefix = "" if self.severitate == EROARE else "avertisment: "
        return f"{self.cale}:{self.linie}: [{self.regula}] {prefix}{mesaj}"


def exclus(cale):
    parti = os.path.normpath(cale).split(os.sep)
    if any(p in EXCLUSE for p in parti[:-1]):
        return True
    norm = "/".join(parti)
    return "static/lib/" in norm or norm.endswith(".min.js")


def exceptii(linii):
    """(linii cu exceptie valida, linii cu `xss-ok` fara motiv), numerotate de la 1."""
    valide, fara_motiv = set(), set()
    for i, linie in enumerate(linii, 1):
        m = RE_EXCEPTIE.search(linie)
        if not m:
            continue
        (valide if (m.group(1) or "").strip() else fara_motiv).add(i)
    return valide, fara_motiv


# ---------------------------------------------------------------------------------- Python


def _e_markup(nod):
    func = nod.func if isinstance(nod, ast.Call) else None
    return (isinstance(func, ast.Name) and func.id == "Markup") or (
        isinstance(func, ast.Attribute) and func.attr == "Markup"
    )


def _e_traducere(nod):
    """`_("...")`, `_lt("...")`, `self.env._("...")` cu argument literal."""
    if not isinstance(nod, ast.Call) or not nod.args:
        return False
    func = nod.func
    nume = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    return nume in ("_", "_lt") and _e_literal(nod.args[0])


def _e_literal(nod):
    """String/numar constant, f-string fara valori, sau concatenare doar din astfel de bucati."""
    if isinstance(nod, ast.Constant):
        return True
    if isinstance(nod, ast.JoinedStr):
        return not any(isinstance(v, ast.FormattedValue) for v in nod.values)
    if isinstance(nod, ast.BinOp) and isinstance(nod.op, ast.Add):
        return _e_literal(nod.left) and _e_literal(nod.right)
    return False


def _sablon(nod):
    """Un string literal sau o traducere: lucruri pe care se aplica `%` sau `.format()`."""
    return (
        isinstance(nod, ast.Constant) and isinstance(nod.value, str)
    ) or _e_traducere(nod)


def _e_markup_sigur(nod):
    """Valoare care e deja Markup cu continut escapat sau literal."""
    if _e_markup(nod):
        return not nod.args or _e_literal(nod.args[0]) or _e_traducere(nod.args[0])
    if isinstance(nod, ast.BinOp) and isinstance(nod.op, ast.Mod):
        return _e_markup_sigur(nod.left)
    if (
        isinstance(nod, ast.Call)
        and isinstance(nod.func, ast.Attribute)
        and nod.func.attr in ("format", "join")
    ):
        return _e_markup_sigur(nod.func.value)
    return False


def _e_json_dumps(nod):
    return (
        isinstance(nod, ast.Call)
        and isinstance(nod.func, ast.Attribute)
        and nod.func.attr == "dumps"
        and isinstance(nod.func.value, ast.Name)
        and nod.func.value.id == "json"
    )


def _e_html_field(nod):
    func = nod.func
    if isinstance(func, ast.Attribute):
        return (
            func.attr == "Html"
            and isinstance(func.value, ast.Name)
            and func.value.id == "fields"
        )
    return isinstance(func, ast.Name) and func.id == "Html"


def _editabil(nod):
    """Un camp Html calculat fara `inverse` / `readonly=False` nu e scris de utilizator: continutul
    il construieste codul, iar acolo prind regulile pe Markup."""
    chei = {kw.arg: kw.value for kw in nod.keywords}
    if "compute" not in chei or "inverse" in chei:
        return True
    readonly = chei.get("readonly")
    return isinstance(readonly, ast.Constant) and readonly.value is False


RE_RANDARE = re.compile(
    r"_render_template\(|\bir\.qweb\b|request\.render\(|\._render\("
)


class _VizitatorPython(ast.NodeVisitor):
    def __init__(self, text, emite):
        self.text = text
        self.emite = emite
        self.atribuiri = {}  # constante de modul: nume -> sursa
        self.functie = []

    def visit_Module(self, nod):
        for instr in nod.body:
            if isinstance(instr, ast.Assign):
                sursa = ast.get_source_segment(self.text, instr) or ""
                for tinta in instr.targets:
                    if isinstance(tinta, ast.Name):
                        self.atribuiri[tinta.id] = sursa
        self.generic_visit(nod)

    def _in_functie(self, nod):
        self.functie.append(nod)
        self.generic_visit(nod)
        self.functie.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _in_functie

    def visit_Call(self, nod):
        if _e_markup(nod) and nod.args:
            self._markup(nod, nod.args[0])
        if _e_html_field(nod) and _editabil(nod):
            for kw in nod.keywords:
                if (
                    kw.arg in ("sanitize", "sanitize_attributes", "sanitize_tags")
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                ):
                    self.emite(kw.value, "XSS-PY-06", f"{kw.arg}=False")
        func = nod.func
        nume = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if nume == "make_response":
            self._make_response(nod)
        self.generic_visit(nod)

    def _markup(self, nod, arg):
        if isinstance(arg, ast.JoinedStr) and not _e_literal(arg):
            self.emite(nod, "XSS-PY-01")
        elif (
            isinstance(arg, ast.BinOp)
            and isinstance(arg.op, ast.Add)
            and not _e_literal(arg)
        ):
            self.emite(nod, "XSS-PY-02", 'Markup("..." + x)')
        elif (
            isinstance(arg, ast.BinOp)
            and isinstance(arg.op, ast.Mod)
            and _sablon(arg.left)
        ):
            if not _e_literal(arg.right) and not (
                isinstance(arg.right, ast.Tuple)
                and all(_e_literal(e) for e in arg.right.elts)
            ):
                self.emite(nod, "XSS-PY-03")
        elif (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "format"
            and _sablon(arg.func.value)
        ):
            self.emite(nod, "XSS-PY-04")
        elif _e_json_dumps(arg):
            self.emite(nod, "XSS-PY-05")

    def visit_BinOp(self, nod):
        # `Markup(x) + y`: x nu e escapat (y este). `Markup("a") + y` e corect.
        if isinstance(nod.op, ast.Add):
            for parte in (nod.left, nod.right):
                if (
                    _e_markup(parte)
                    and parte.args
                    and not _e_markup_sigur(parte)
                    and not _e_literal(parte.args[0])
                ):
                    arg = parte.args[0]
                    if isinstance(arg, (ast.Name, ast.Attribute, ast.Subscript)):
                        self.emite(parte, "XSS-PY-02", "Markup(x) + ...")
        self.generic_visit(nod)

    def _make_response(self, nod):
        apel = ast.get_source_segment(self.text, nod) or ""
        context = (
            ast.get_source_segment(self.text, self.functie[-1])
            if self.functie
            else apel
        )
        context = context or apel
        for nume in {n.id for n in ast.walk(nod) if isinstance(n, ast.Name)}:
            context += "\n" + self.atribuiri.get(nume, "")
        if "text/html" not in apel and not (
            "text/html" in context and "headers" in apel
        ):
            return
        if nod.args and _e_literal(nod.args[0]):
            return  # raspuns gol sau fix
        if RE_RANDARE.search(context):
            return  # fragment randat din QWeb, care escapeaza valorile
        if "content-security-policy" not in context.lower():
            self.emite(nod, "XSS-PY-07")


def verifica_python(text, emite):
    try:
        arbore = ast.parse(text)
    except (SyntaxError, ValueError):
        return
    _VizitatorPython(text, emite).visit(arbore)


# ---------------------------------------------------------------------------------- JS

RE_STRING_JS = (
    r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\$]|\\.|\$(?!\{))*`)"""
)
RE_LITERAL_JS = re.compile(
    rf"^\s*(?:{RE_STRING_JS}\s*(?:\+\s*{RE_STRING_JS}\s*)*)?$|^\s*_t\(\s*{RE_STRING_JS}\s*\)\s*$"
)
RE_INNER = re.compile(r"\.(innerHTML|outerHTML)\s*\+?=(?!=)\s*(.*)")
RE_ADJACENT = re.compile(r"\.insertAdjacentHTML\(")
RE_JQ_HTML = re.compile(r"\.html\(")
RE_MARKUP_JS = re.compile(r"(?<![\w.$])markup\(")
# `.html($el)` / `.html(this.$target.find(...)[0])`: un element, nu un string de HTML
RE_JQ_OBIECT = re.compile(r"\s*(?:this\.)?\$")
LUNGIME_MINIFICAT = 300


def _argumente(linie, start):
    """Textul dintre paranteza deschisa la `start - 1` si cea care o inchide (sau pana la capat)."""
    adancime, ghilimea, i = 1, None, start
    while i < len(linie):
        c = linie[i]
        if ghilimea:
            if c == "\\":
                i += 1
            elif c == ghilimea:
                ghilimea = None
        elif c in "'\"`":
            ghilimea = c
        elif c in "([{":
            adancime += 1
        elif c in ")]}":
            adancime -= 1
            if adancime == 0:
                return linie[start:i], True
        i += 1
    return linie[start:], False


def _split_virgula(text):
    """Imparte argumentele la virgulele de pe nivelul de sus."""
    parti, curent, adancime, ghilimea, i = [], [], 0, None, 0
    while i < len(text):
        c = text[i]
        if ghilimea:
            curent.append(c)
            if c == "\\" and i + 1 < len(text):
                curent.append(text[i + 1])
                i += 1
            elif c == ghilimea:
                ghilimea = None
        elif c in "'\"`":
            ghilimea = c
            curent.append(c)
        elif c in "([{":
            adancime += 1
            curent.append(c)
        elif c in ")]}":
            adancime -= 1
            curent.append(c)
        elif c == "," and adancime == 0:
            parti.append("".join(curent))
            curent = []
        else:
            curent.append(c)
        i += 1
    parti.append("".join(curent))
    return parti


def _literal_js(expr, complet=True):
    expr = expr.strip().rstrip(";").strip()
    if not complet and not expr:
        return True  # argumentul continua pe linia urmatoare: nu stim, nu raportam
    return bool(RE_LITERAL_JS.match(expr))


def _cod_js(linie):
    """Linia fara comentariul `//` de la final (in afara string-urilor)."""
    ghilimea, i = None, 0
    while i < len(linie):
        c = linie[i]
        if ghilimea:
            if c == "\\":
                i += 1
            elif c == ghilimea:
                ghilimea = None
        elif c in "'\"`":
            ghilimea = c
        elif linie.startswith("//", i):
            return linie[:i]
        i += 1
    return linie


def verifica_js(text, emite):
    in_comentariu = False
    for nr, linie in enumerate(text.split("\n"), 1):
        brut = linie.strip()
        if in_comentariu:
            if "*/" in brut:
                in_comentariu = False
            continue
        if brut.startswith("/*") and "*/" not in brut:
            in_comentariu = True
            continue
        if brut.startswith(("//", "*", "/*")) or len(brut) > LUNGIME_MINIFICAT:
            continue  # comentariu, sau cod minificat (biblioteca adusa in static/src)
        cod = _cod_js(linie)
        m = RE_INNER.search(cod)
        if m and not _literal_js(m.group(2), complet=bool(m.group(2).strip())):
            emite(nr, "XSS-JS-01", m.group(1))
        for m in RE_ADJACENT.finditer(cod):
            args, complet = _argumente(cod, m.end())
            parti = _split_virgula(args)
            if len(parti) >= 2 and not _literal_js(parti[1], complet):
                emite(nr, "XSS-JS-02")
        if "$" in cod:
            for m in RE_JQ_HTML.finditer(cod):
                if "$" not in cod[: m.start()]:
                    continue
                args, complet = _argumente(cod, m.end())
                if (
                    args.strip()
                    and not _literal_js(args, complet)
                    and not RE_JQ_OBIECT.match(args)
                ):
                    emite(nr, "XSS-JS-03")
        for m in RE_MARKUP_JS.finditer(cod):
            if re.search(r"\b(function|import)\b", cod[: m.start()]):
                continue
            args, complet = _argumente(cod, m.end())
            if not _literal_js(args, complet):
                emite(nr, "XSS-JS-04")


# ---------------------------------------------------------------------------------- XML

RE_COMENTARIU_XML = re.compile(r"<!--.*?-->", re.DOTALL)
RE_T_RAW = re.compile(r"\st-raw\s*=")
RE_IFRAME = re.compile(r"<iframe\b[^>]*>", re.DOTALL | re.IGNORECASE)
RE_SANDBOX = re.compile(r"""\bsandbox\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)


def _fara_comentarii(text):
    """Comentariile XML inlocuite cu spatii (pastreaza pozitiile si liniile)."""
    return RE_COMENTARIU_XML.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def verifica_iframe(text, emite):
    for m in RE_IFRAME.finditer(text):
        s = RE_SANDBOX.search(m.group(0))
        if not s:
            continue
        valori = (s.group(1) if s.group(1) is not None else s.group(2)).lower().split()
        if "allow-scripts" in valori and "allow-same-origin" in valori:
            emite(text.count("\n", 0, m.start() + s.start()) + 1, "XSS-XML-02")


def verifica_xml(text, emite):
    curat = _fara_comentarii(text)
    for m in RE_T_RAW.finditer(curat):
        emite(curat.count("\n", 0, m.start()) + 1, "XSS-XML-01")
    verifica_iframe(curat, emite)


# ---------------------------------------------------------------------------------- comun


def verifica_text(cale, text):
    """Constatarile pentru continutul unui fisier, dupa extensie, cu exceptiile `xss-ok` aplicate."""
    linii = text.split("\n")
    valide, fara_motiv = exceptii(linii)
    gasite = []

    def emite(nod_sau_linie, regula, detaliu=""):
        if isinstance(nod_sau_linie, int):
            prima = ultima = nod_sau_linie
        else:
            prima = nod_sau_linie.lineno
            ultima = getattr(nod_sau_linie, "end_lineno", None) or prima
        acoperite = set(range(prima - 1, ultima + 1))
        if acoperite & valide:
            return
        gasite.append(Constatare(cale, prima, regula, detaliu))

    if cale.endswith(".py"):
        verifica_python(text, emite)
    elif cale.endswith(".js"):
        verifica_js(text, emite)
        verifica_iframe(text, emite)
    elif cale.endswith(".xml"):
        verifica_xml(text, emite)
    gasite.extend(Constatare(cale, nr, "XSS-OK-00") for nr in sorted(fara_motiv))
    gasite.sort(key=lambda c: (c.linie, c.regula))
    return gasite


def verifica_fisier(cale):
    if exclus(cale) or not cale.endswith((".py", ".js", ".xml")):
        return []
    try:
        with open(cale, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"{cale}: nu s-a putut citi ({e})", file=sys.stderr)
        return []
    return verifica_text(cale, text)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--warn-only", action="store_true", help="iese mereu cu 0")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="numarul de constatari pe regula, la final",
    )
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    constatari = []
    for cale in args.files:
        constatari.extend(verifica_fisier(cale))
    for c in constatari:
        print(c.text())
    if args.summary:
        for regula, numar in sorted(Counter(c.regula for c in constatari).items()):
            print(f"{regula}\t{numar}")
    erori = [c for c in constatari if c.severitate == EROARE]
    return 1 if (erori and not args.warn_only) else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
