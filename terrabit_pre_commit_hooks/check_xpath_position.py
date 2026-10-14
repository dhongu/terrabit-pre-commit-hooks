#!/usr/bin/env python
"""Semnaleaza xpath-urile din vederile mostenite care aleg nodul DOAR dupa pozitie.

Un pas ca `td[2]`, `group[1]`, `td[last()-1]` sau `*[position() > 1]` depinde de cate elemente au inserat inainte celelalte
module instalate. Cand un modul cu id de vedere mai mic adauga o celula, un
grup sau un camp inaintea nodului vizat, xpath-ul nu mai gaseste nodul (Odoo
dezactiveaza vederea la update) sau, mai rau, gaseste ALT nod si modificarea
ajunge in locul gresit, fara nicio eroare.

Caz real (PTC, 14.10.2026): `deltatech_sale_cancel_order.portal_my_orders_cancel`
avea `//t[@t-foreach='orders']/tr/td[2]/span[1]`; `deltatech_delivery_relay`
insereaza o celula AWB dupa prima celula, deci `td[2]` nu mai era data comenzii,
iar vederea a fost dezactivata la update.

Ce NU se semnaleaza:
  - `[last()]` simplu: un element inserat inainte nu il muta, iar unul adaugat
    la final il muta odata cu intentia (after/before/inside "la final");
  - indexul pus dupa un filtru pe atribut: `span[@t-field='order.date_order'][1]`,
    `field[@name='x'][2]` - pozitia se numara doar intre nodurile filtrate;
  - pasii fara index (`/tr/td` cu position="after"), idiomul standard;
  - indexul din interiorul unui predicat (`div[span[2]]`) sau al unui string
    (`[@t-if="x[0]"]`).

Exceptie explicita, cand pozitia chiar este intentia:

    <!-- xpath-position: ok -->
    <xpath expr="//tr/td[1]" position="after">

Hook-ul este un avertisment: iese cu 0, iar mesajele se vad prin `verbose: true`.
Cu `--strict` iese cu 1 daca a gasit ceva.
"""

# pylint: disable=print-used
# `print` este interfata unui hook de pre-commit: pre-commit capteaza stdout/stderr
# si le arata utilizatorului. Un logger nu ar aparea nicaieri.
import argparse
import html
import re
import sys

# `<xpath` urmat de atribute; valorile pot contine `>` si ghilimelele celelalte.
RE_XPATH = re.compile(r"""<xpath\b((?:\s+[\w:.-]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*/?>""")
RE_EXPR = re.compile(r"""(?:^|\s)expr\s*=\s*(?:"([^"]*)"|'([^']*)')""")
RE_COMENTARIU = re.compile(r"<!--.*?-->", re.DOTALL)
RE_EXCEPTIE = re.compile(r"<!--\s*xpath-position\s*:\s*ok\s*-->")
# Predicat pozitional: [2], [last()-1], sau orice foloseste position(). `[last()]` simplu nu.
RE_POZITIONAL = re.compile(r"^\s*(?:\d+|last\(\s*\)\s*-\s*\d+)\s*$|\bposition\(\s*\)")

SFAT = "un alt modul care inserează un element înainte îl deplasează; ancorează pe @name/@id/@t-field/hasclass(...)"


def pasi(expr):
    """Imparte expresia in pasi la `/` si `|` de pe nivelul de sus.

    Separatorii din string-uri, predicate `[...]` sau paranteze nu conteaza.
    """
    rezultat, curent, adancime, ghilimea = [], [], 0, None
    for c in expr:
        if ghilimea:
            curent.append(c)
            if c == ghilimea:
                ghilimea = None
            continue
        if c in "'\"":
            ghilimea = c
        elif c in "[(":
            adancime += 1
        elif c in "])":
            adancime = max(adancime - 1, 0)
        elif c in "/|" and adancime == 0:
            rezultat.append("".join(curent))
            curent = []
            continue
        curent.append(c)
    rezultat.append("".join(curent))
    return [p.strip() for p in rezultat if p.strip()]


def predicate(pas):
    """Continutul predicatelor `[...]` de pe nivelul de sus al unui pas, in ordine.

    Ce e intre paranteze (`(//td[@a])[2]`) nu este predicat al pasului.
    """
    rezultat, curent, adancime, paranteze, ghilimea = [], [], 0, 0, None
    for c in pas:
        if ghilimea:
            if c == ghilimea:
                ghilimea = None
        elif c in "'\"":
            ghilimea = c
        elif adancime == 0 and c in "()":
            paranteze += 1 if c == "(" else -1
            continue
        elif paranteze:
            continue
        elif c == "[":
            adancime += 1
            if adancime == 1:
                curent = []
                continue
        elif c == "]":
            adancime -= 1
            if adancime == 0:
                rezultat.append("".join(curent))
                continue
        if adancime >= 1:
            curent.append(c)
    return rezultat


def pasi_pozitionali(expr):
    """Pasii al caror PRIM predicat alege nodul dupa pozitie.

    La `(expr)[n]` se verifica si interiorul, iar indexul exterior conteaza doar
    daca ultimul pas din paranteza nu are filtru: `(//label[@for='x'])[1]` este
    un index dupa filtru, `(//td)[2]` nu.
    """
    rezultat = []
    for pas in pasi(expr):
        if pas.startswith("("):
            interior = pas[1 : sfarsit_paranteza(pas)]
            rezultat.extend(pasi_pozitionali(interior))
            ultimul = (pasi(interior) or [""])[-1]
            if predicate(ultimul):
                continue
        preds = predicate(pas)
        if preds and RE_POZITIONAL.search(preds[0]):
            rezultat.append(pas)
    return rezultat


def sfarsit_paranteza(pas):
    """Indexul `)` care inchide paranteza de la inceputul pasului."""
    adancime, ghilimea = 0, None
    for i, c in enumerate(pas):
        if ghilimea:
            if c == ghilimea:
                ghilimea = None
        elif c in "'\"":
            ghilimea = c
        elif c == "(":
            adancime += 1
        elif c == ")":
            adancime -= 1
            if adancime == 0:
                return i
    return len(pas)


def verifica_text(text):
    """Intoarce (linie, pas, expr) pentru fiecare pas pozitional din fisier."""
    comentarii = [m.span() for m in RE_COMENTARIU.finditer(text)]
    linii = text.split("\n")
    gasite = []
    for m in RE_XPATH.finditer(text):
        if any(start <= m.start() < end for start, end in comentarii):
            continue  # xpath comentat
        m_expr = RE_EXPR.search(m.group(1))
        if not m_expr:
            continue
        expr = html.unescape(m_expr.group(1) if m_expr.group(1) is not None else m_expr.group(2))
        linie = text.count("\n", 0, m.start()) + 1
        # Comentariul de exceptie: pe linia dinainte, sau imediat inainte pe aceeasi linie.
        inainte = text[text.rfind("\n", 0, m.start()) + 1 : m.start()]
        if RE_EXCEPTIE.search(inainte) or (linie > 1 and RE_EXCEPTIE.search(linii[linie - 2])):
            continue
        gasite.extend((linie, pas, expr) for pas in pasi_pozitionali(expr))
    return gasite


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true", help="iesire 1 daca exista xpath-uri pozitionale")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    total = 0
    for cale in args.files:
        try:
            with open(cale, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"{cale}: nu s-a putut citi ({e})", file=sys.stderr)
            continue
        for linie, pas, expr in verifica_text(text):
            print(f'{cale}:{linie}: xpath pozițional {pas} în "{expr}": {SFAT}')
            total += 1
    return 1 if (args.strict and total) else 0


def cli():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    cli()
