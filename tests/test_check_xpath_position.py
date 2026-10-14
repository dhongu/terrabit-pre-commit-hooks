#!/usr/bin/env python
"""Teste pentru hook-ul check_xpath_position.py.

Ruleaza din radacina repo-ului de hook-uri:

    python3 -m unittest discover -s tests -p "test_check_xpath_position.py"
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "terrabit_pre_commit_hooks", "check_xpath_position.py"
)

VEDERE = """<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <template id="t" inherit_id="portal.x">
{corp}
    </template>
</odoo>
"""


class TestCheckXpathPosition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def ruleaza(self, corp, *args):
        cale = os.path.join(self.tmp, "views.xml")
        with open(cale, "w", encoding="utf-8") as f:
            f.write(VEDERE.format(corp=corp))
        return subprocess.run(
            [sys.executable, SCRIPT, *args, "views.xml"], cwd=self.tmp, capture_output=True, text=True
        )

    def semnalate(self, corp):
        rezultat = self.ruleaza(corp)
        self.assertEqual(rezultat.returncode, 0, rezultat.stderr)
        return [linie for linie in rezultat.stdout.splitlines() if "xpath pozițional" in linie]

    def test_index_simplu(self):
        linii = self.semnalate("""        <xpath expr="//t[@t-foreach='orders']/tr/td[2]" position="after"/>""")
        self.assertEqual(len(linii), 1)
        self.assertEqual(
            linii[0],
            "views.xml:4: xpath pozițional td[2] în \"//t[@t-foreach='orders']/tr/td[2]\": un alt modul care "
            "inserează un element înainte îl deplasează; ancorează pe @name/@id/@t-field/hasclass(...)",
        )

    def test_mai_multi_pasi_pozitionali(self):
        linii = self.semnalate("""        <xpath expr="//tr/td[2]/span[1]" position="replace"/>""")
        self.assertEqual(len(linii), 2)
        self.assertIn("pozițional td[2]", linii[0])
        self.assertIn("pozițional span[1]", linii[1])

    def test_last(self):
        linii = self.semnalate("""        <xpath expr="//thead//tr[hasclass('active')]/th[last()]" position="after"/>""")
        self.assertEqual(len(linii), 1)
        self.assertIn("pozițional th[last()]", linii[0])

    def test_last_minus(self):
        linii = self.semnalate("""        <xpath expr="//tr/td[last() - 1]" position="before"/>""")
        self.assertEqual(len(linii), 1)
        self.assertIn("pozițional td[last() - 1]", linii[0])

    def test_position(self):
        linii = self.semnalate("""        <xpath expr="//group/field[position() &gt; 1]" position="before"/>""")
        self.assertEqual(len(linii), 1)
        self.assertIn('field[position() > 1] în "//group/field[position() > 1]"', linii[0])

    def test_index_dupa_filtru_nesemnalat(self):
        self.assertEqual(
            self.semnalate(
                """        <xpath expr="//span[@t-field='order.date_order'][1]" position="after"/>
        <xpath expr="//field[@name='x'][2]" position="after"/>
        <xpath expr="//div[hasclass('o_portal')][last()]" position="inside"/>"""
            ),
            [],
        )

    def test_index_inainte_de_filtru_semnalat(self):
        """`td[2][@class='x']` alege a doua celula si abia apoi filtreaza."""
        linii = self.semnalate("""        <xpath expr="//tr/td[2][@class='x']" position="after"/>""")
        self.assertEqual(len(linii), 1)

    def test_pas_fara_index_nesemnalat(self):
        self.assertEqual(
            self.semnalate(
                """        <xpath expr="//t[@t-foreach='orders']/tr/td" position="after"/>
        <xpath expr="//thead/tr" position="inside"/>
        <xpath expr="." position="inside"/>"""
            ),
            [],
        )

    def test_comentariu_exceptie(self):
        self.assertEqual(
            self.semnalate(
                """        <!-- xpath-position: ok -->
        <xpath expr="//tr/td[last()]" position="after"/>"""
            ),
            [],
        )

    def test_comentariu_exceptie_doar_pe_linia_dinainte(self):
        linii = self.semnalate(
            """        <!-- xpath-position: ok -->
        <xpath expr="//tr/td[1]" position="after"/>
        <xpath expr="//tr/td[3]" position="after"/>"""
        )
        self.assertEqual(len(linii), 1)
        self.assertIn("td[3]", linii[0])

    def test_xpath_comentat_ignorat(self):
        self.assertEqual(self.semnalate("""        <!-- <xpath expr="//tr/td[2]" position="after"/> -->"""), [])

    def test_entitati(self):
        linii = self.semnalate(
            """        <xpath expr="//t[@t-foreach=&quot;orders&quot;]/tr/td[&#50;]" position="after"/>
        <xpath expr="//span[@t-field=&#39;o.name&#39;][1]" position="after"/>"""
        )
        self.assertEqual(len(linii), 1)
        self.assertIn('td[2] în "//t[@t-foreach="orders"]/tr/td[2]"', linii[0])

    def test_ghilimele_simple_pe_atribut(self):
        linii = self.semnalate("""        <xpath expr='//div[@t-if="x"]/group[1]' position="inside"/>""")
        self.assertEqual(len(linii), 1)
        self.assertIn("pozițional group[1]", linii[0])

    def test_index_in_string_sau_predicat_nesemnalat(self):
        self.assertEqual(
            self.semnalate(
                """        <xpath expr="//div[@t-if='lines[0]']" position="inside"/>
        <xpath expr='//t[@t-set="a/b[1]"]' position="inside"/>
        <xpath expr="//div[span[2]]" position="inside"/>"""
            ),
            [],
        )

    def test_paranteze(self):
        linii = self.semnalate(
            """        <xpath expr="(//label[@for='method_progress_factor'])[2]" position="replace"/>
        <xpath expr="(//div[field[@name='x']])[1]" position="replace"/>
        <xpath expr="(//tr/td)[2]" position="after"/>
        <xpath expr="(//tr/td[3])[1]" position="after"/>"""
        )
        self.assertEqual(len(linii), 2)
        self.assertIn("pozițional (//tr/td)[2]", linii[0])
        self.assertIn("pozițional td[3]", linii[1])

    def test_atribute_multilinie(self):
        linii = self.semnalate(
            """        <xpath
            position="after"
            expr="//group[@name='first']//group[1]"
        >
            <field name="x"/>
        </xpath>"""
        )
        self.assertEqual(len(linii), 1)
        self.assertTrue(linii[0].startswith("views.xml:4:"), linii[0])

    def test_strict(self):
        corp = """        <xpath expr="//tr/td[2]" position="after"/>"""
        self.assertEqual(self.ruleaza(corp).returncode, 0)
        rezultat = self.ruleaza(corp, "--strict")
        self.assertEqual(rezultat.returncode, 1)
        self.assertIn("td[2]", rezultat.stdout)

    def test_strict_fara_probleme(self):
        rezultat = self.ruleaza("""        <xpath expr="//field[@name='x']" position="after"/>""", "--strict")
        self.assertEqual(rezultat.returncode, 0)
        self.assertEqual(rezultat.stdout, "")


if __name__ == "__main__":
    unittest.main()
