#!/usr/bin/env python
"""Teste pentru hook-ul tb_odoo_lint.py.

Ruleaza din radacina repo-ului de hook-uri:

    python3 -m unittest discover -s tests -p "test_tb_odoo_lint.py"
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "terrabit_pre_commit_hooks", "tb_odoo_lint.py"
)
_spec = importlib.util.spec_from_file_location("tb_odoo_lint", SCRIPT)
lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint)


class ModulTemporar(unittest.TestCase):
    """Un modul Odoo minimal intr-un director temporar."""

    versiune = "19.0.1.0.0"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.modul = os.path.join(self.tmp, "my_module")
        os.makedirs(self.modul)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def scrie(self, rel, text):
        cale = os.path.join(self.modul, rel)
        os.makedirs(os.path.dirname(cale), exist_ok=True)
        with open(cale, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(text).lstrip("\n"))
        return cale

    def manifest(self, data=(), extra=""):
        self.scrie(
            "__manifest__.py",
            f'{{"name": "M", "version": "{self.versiune}", "data": {list(data)!r}, {extra}}}\n',
        )

    def reguli(self, *cai):
        """Regulile semnalate, ca set de (id, severitate)."""
        constatari, _neincarcate = lint.ruleaza([], [self.tmp], "19")
        if cai:
            cai = {os.path.relpath(os.path.join(self.modul, c)) for c in cai}
            constatari = [c for c in constatari if c.cale in cai]
        return {(c.regula, c.severitate) for c in constatari}

    def python(self, cod, rel="models/m.py"):
        """Modul cu un singur fisier Python incarcat; intoarce regulile semnalate."""
        pachet, fisier = os.path.split(rel)
        self.manifest()
        self.scrie("__init__.py", f"from . import {pachet}\n")
        self.scrie(f"{pachet}/__init__.py", f"from . import {fisier[:-3]}\n")
        self.scrie(rel, cod)
        return {r for r, _s in self.reguli()}

    def xml(self, continut, rel="views/v.xml"):
        self.manifest([rel])
        self.scrie("__init__.py", "")
        self.scrie(rel, f'<?xml version="1.0"?>\n<odoo>\n{textwrap.dedent(continut)}\n</odoo>\n')
        return {r for r, _s in self.reguli()}


class TestFiltruIncarcate(ModulTemporar):
    def test_xml_nelistat_in_data_nu_se_verifica(self):
        self.manifest(["views/loaded.xml"], extra='"oca_data_manual": ["views/manual.xml"]')
        self.scrie("__init__.py", "")
        view = '<?xml version="1.0"?><odoo><record id="v" model="ir.ui.view"><field name="arch" type="xml"><tree/></field></record></odoo>'
        self.scrie("views/loaded.xml", view)
        self.scrie("views/manual.xml", view)
        self.scrie("views/orphan.xml", view)
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual({os.path.basename(c.cale) for c in constatari}, {"loaded.xml"})

    def test_import_comentat_scoate_fisierul(self):
        self.manifest()
        self.scrie("__init__.py", "from . import models\n")
        self.scrie("models/__init__.py", "from . import active\n# from . import dead\n")
        self.scrie("models/active.py", "x = product.uom_po_id\n")
        self.scrie("models/dead.py", "x = product.uom_po_id\n")
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual({os.path.basename(c.cale) for c in constatari}, {"active.py"})

    def test_from_pachet_import_submodul(self):
        self.manifest()
        self.scrie("__init__.py", "from .models import a\nfrom odoo.addons.my_module.wizard import w\n")
        self.scrie("models/__init__.py", "")
        self.scrie("models/a.py", "x = p.uom_po_id\n")
        self.scrie("wizard/__init__.py", "")
        self.scrie("wizard/w.py", "x = p.uom_po_id\n")
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual({os.path.basename(c.cale) for c in constatari}, {"a.py", "w.py"})

    def test_fisier_primit_neincarcat_e_raportat_separat(self):
        self.manifest()
        self.scrie("__init__.py", "")
        cale = self.scrie("models/dead.py", "x = p.uom_po_id\n")
        constatari, neincarcate = lint.ruleaza([cale], [], "19")
        self.assertEqual(constatari, [])
        self.assertEqual(neincarcate, [cale])

    def test_testele_coboara_la_avertisment(self):
        self.manifest()
        self.scrie("__init__.py", "")
        self.scrie("tests/__init__.py", "from . import test_a\n")
        self.scrie("tests/test_a.py", "x = p.uom_po_id\n")
        self.assertEqual(self.reguli(), {("O19-PY-03", "warn")})

    def test_migrations_nu_se_verifica(self):
        self.manifest()
        self.scrie("__init__.py", "from .migrations import m\n")
        self.scrie("migrations/__init__.py", "")
        self.scrie("migrations/m.py", "x = p.uom_po_id\n")
        self.assertEqual(self.reguli(), set())


class TestDezactivare(ModulTemporar):
    def test_pe_linie_si_deasupra(self):
        cod = """
        a = p.uom_po_id  # tb-lint: disable=O19-PY-03 motiv
        # tb-lint: disable=O19-PY-03
        b = p.uom_po_id
        c = p.uom_po_id
        """
        self.python(cod)
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual([c.linie for c in constatari], [4])

    def test_pe_fisier(self):
        self.assertEqual(self.python("# tb-lint: disable-file=O19-PY-03\nx = p.uom_po_id\n"), set())

    def test_pylint_sql_injection_acopera_py06(self):
        cod = """
        class R(models.Model):
            def init(self):
                # pylint: disable=E8103
                self.env.cr.execute(f"CREATE VIEW {self._table} AS (SELECT 1)")
        """
        self.assertEqual(self.python(cod), set())


class TestReguliPython(ModulTemporar):
    def test_underscore_doar_in_model(self):
        model = """
        from odoo import _, models
        class M(models.Model):
            _name = "x"
            def f(self):
                return _("a")
        """
        self.assertIn("O19-PY-01", self.python(model))

    def test_underscore_in_client_api_nu(self):
        client = """
        from odoo import _
        class Client:
            def f(self):
                return _("a")
        """
        self.assertNotIn("O19-PY-01", self.python(client))

    def test_sql_constraints(self):
        self.assertIn(
            "O19-PY-02", self.python('class M(models.Model):\n    _sql_constraints = [("a", "unique(a)", "m")]\n')
        )

    def test_campuri_eliminate(self):
        self.assertIn("O19-PY-03", self.python("x = product.uom_po_id.id\n"))
        self.assertIn("O19-PY-03", self.python('g = env["procurement.group"]\n'))

    def test_docstring_nu_da_alarma(self):
        cod = '''
        def f():
            """In 19 `uom_po_id` si `procurement.group` au disparut; scriem `.datas`."""
            # uom_po_id nu mai exista
            return 1
        '''
        self.assertEqual(self.python(cod), set())

    def test_product_uom_pe_linia_de_vanzare(self):
        cod = """
        class L(models.Model):
            _inherit = "sale.order.line"
            def f(self):
                return self.product_uom, move.product_uom
        """
        self.assertIn("O19-PY-04", self.python(cod))
        cod_move = """
        class M(models.Model):
            _inherit = "stock.move"
            def f(self):
                return self.product_uom
        """
        self.assertNotIn("O19-PY-04", self.python(cod_move))

    def test_product_uom_in_order_line(self):
        cod = 'so = env["sale.order"].create({"order_line": [(0, 0, {"product_id": 1, "product_uom": 2})]})\n'
        self.assertIn("O19-PY-04", self.python(cod))

    def test_create_api_model(self):
        cod = """
        class M(models.Model):
            @api.model
            def create(self, vals):
                return super().create(vals)
        """
        self.assertIn("O19-PY-05", self.python(cod))
        corect = cod.replace("@api.model\n", "@api.model_create_multi\n")
        self.assertNotIn("O19-PY-05", self.python(corect))

    def test_cr_execute_compus(self):
        compus = 'class M(models.Model):\n    def f(self):\n        self.env.cr.execute(f"SELECT {x}")\n'
        self.assertIn("O19-PY-06", self.python(compus))
        sigur = 'class M(models.Model):\n    def f(self):\n        self.env.cr.execute("SELECT %s", (x,))\n'
        self.assertNotIn("O19-PY-06", self.python(sigur))

    def test_name_search_args(self):
        self.assertIn(
            "O19-PY-07",
            self.python('class M(models.Model):\n    def name_search(self, name="", args=None):\n        pass\n'),
        )

    def test_route_json(self):
        self.assertIn(
            "O19-PY-08", self.python('@http.route("/x", type="json")\ndef f():\n    pass\n', "controllers/c.py")
        )

    def test_mobile_pazit_de_hasattr(self):
        self.assertIn("O19-PY-09", self.python("x = partner.mobile\n"))
        self.assertNotIn("O19-PY-09", self.python('x = hasattr(partner, "mobile") and partner.mobile\n'))


class TestReguliXml(ModulTemporar):
    def view(self, arch):
        return f'<record id="v" model="ir.ui.view"><field name="model">x</field><field name="arch" type="xml">{arch}</field></record>'

    def test_tree(self):
        self.assertIn("O19-XML-01", self.xml(self.view("<tree><field name='a'/></tree>")))

    def test_attrs_states(self):
        self.assertIn("O19-XML-02", self.xml(self.view("<form><field name='a' attrs=\"{'invisible': 1}\"/></form>")))

    def test_group_expand_in_search(self):
        search = "<search><group expand='0' string='Group By'><filter name='g' context=\"{'group_by': 'a'}\"/></group></search>"
        self.assertIn("O19-XML-03", self.xml(self.view(search)))

    def test_group_string_in_search_mostenit(self):
        mostenit = "<xpath expr='//search' position='inside'><group string='X'><filter name='g'/></group></xpath>"
        self.assertIn("O19-XML-03", self.xml(self.view(mostenit)))

    def test_group_string_in_form_e_valid(self):
        self.assertNotIn(
            "O19-XML-03", self.xml(self.view("<form><group string='Info'><field name='a'/></group></form>"))
        )

    def test_report_tag(self):
        self.assertIn("O19-XML-04", self.xml('<report id="r" model="x" name="x.r" string="R"/>'))

    def test_act_window(self):
        rec = '<record id="a" model="ir.actions.act_window"><field name="view_type">form</field><field name="target">inline</field></record>'
        self.assertIn("O19-XML-05", self.xml(rec))

    def test_ir_rule_allowed_company_ids(self):
        rec = '<record id="r" model="ir.rule"><field name="domain_force">[("company_id", "in", allowed_company_ids)]</field></record>'
        self.assertIn("O19-XML-06", self.xml(rec))
        bun = rec.replace("allowed_company_ids", "company_ids")
        self.assertNotIn("O19-XML-06", self.xml(bun))

    def test_grupuri_redenumite(self):
        rec = '<record id="g" model="res.groups"><field name="category_id" ref="base.x"/></record>'
        self.assertIn("O19-XML-07", self.xml(rec))
        meniu = '<record id="m" model="ir.ui.menu"><field name="groups_id" eval="[(4, ref(\'base.group_user\'))]"/></record>'
        self.assertIn("O19-XML-07", self.xml(meniu))

    def test_optiunea_format(self):
        self.assertIn(
            "O19-XML-08", self.xml(self.view("<list><field name='year' options=\"{'format': false}\"/></list>"))
        )

    def test_comentariile_nu_dau_alarma(self):
        self.assertEqual(self.xml("<!-- <report id='r'/> <tree/> -->"), set())

    def test_index_html_cu_declaratie_xml(self):
        self.manifest()
        self.scrie("__init__.py", "")
        self.scrie("static/description/index.html", '<?xml version="1.0"?>\n<section>x</section>\n')
        self.assertIn(("O19-XML-09", "block"), self.reguli())


class TestOdoo20(ModulTemporar):
    versiune = "20.0.1.0.0"

    def test_get_param_pe_config_parameter(self):
        cod = """
        class M(models.Model):
            def f(self):
                icp = self.env["ir.config_parameter"].sudo()
                a = icp.get_param("a")
                b = self.env["ir.config_parameter"].sudo().set_param("b", 1)
                c = message.get_param("charset")
        """
        self.python(cod)
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual(sorted(c.linie for c in constatari if c.regula == "O20-PY-01"), [4, 5])

    def test_datas_doar_pe_ir_attachment(self):
        self.assertIn("O20-PY-04", self.python('a = self.env["ir.attachment"].create({"name": "a", "datas": b})\n'))
        self.assertIn("O20-PY-04", self.python('v = {"name": "a", "datas": b, "res_model": "x"}\n'))
        self.assertNotIn("O20-PY-04", self.python('payload = {"name": "a", "datas": b}\n'))

    def test_b64encode_bytes_in_camp_binar(self):
        cod = """
        import base64
        class M(models.Model):
            def f(self, continut):
                self.write({"image_1920": base64.b64encode(continut)})
                self.pdf_file = base64.b64encode(continut)
                self.write({"image_1920": base64.b64encode(continut).decode()})
                self.write({"raw": continut, "file_name": base64.b64encode(continut)})
                payload = {"body": base64.b64encode(continut), "attachment_ids": base64.b64encode(continut)}
        """
        self.python(cod)
        constatari, _n = lint.ruleaza([], [self.tmp], "19")
        self.assertEqual(
            sorted((c.linie, c.severitate) for c in constatari if c.regula == "O20-PY-06"), [(4, "warn"), (5, "warn")]
        )

    def test_b64encode_nu_se_semnaleaza_pe_19(self):
        self.versiune = "19.0.1.0.0"
        self.assertNotIn("O20-PY-06", self.python('import base64\nv = {"image_1920": base64.b64encode(b"x")}\n'))

    def test_ir_rule_si_acl(self):
        self.manifest(["security/ir.model.access.csv", "security/rules.xml"])
        self.scrie("__init__.py", "")
        self.scrie("security/ir.model.access.csv", "id,name,model_id:id,group_id:id,perm_read\n")
        self.scrie("security/rules.xml", '<odoo><record id="r" model="ir.rule"/></odoo>')
        self.assertEqual({r for r, _s in self.reguli()}, {"O20-XML-01", "O20-XML-02"})

    def test_regulile_20_nu_se_aplica_pe_19(self):
        self.versiune = "19.0.1.0.0"
        self.assertNotIn("O20-PY-01", self.python('x = self.env["ir.config_parameter"].get_param("a")\n'))


class TestCli(ModulTemporar):
    def test_cod_iesire(self):
        self.manifest()
        self.scrie("__init__.py", "from . import m\n")
        cale = self.scrie("m.py", "x = p.uom_po_id\n")
        rezultat = subprocess.run([sys.executable, SCRIPT, cale], capture_output=True, text=True)
        self.assertEqual(rezultat.returncode, 1, rezultat.stdout + rezultat.stderr)
        self.assertIn("[O19-PY-03] block", rezultat.stdout)
        rezultat = subprocess.run([sys.executable, SCRIPT, "--warn-only", cale], capture_output=True, text=True)
        self.assertEqual(rezultat.returncode, 0)


if __name__ == "__main__":
    unittest.main()
