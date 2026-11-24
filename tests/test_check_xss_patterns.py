#!/usr/bin/env python
"""Teste pentru hook-ul check_xss_patterns.py.

Cazurile reale sunt cele reparate dupa CVE-2026-130029 (deltatech_maintenance, deltatech_mcp,
agroamat_blog, agroamat_marketing, deltatech_mail_client). Ruleaza din radacina repo-ului:

    python3 -m unittest discover -s tests -p "test_check_xss_patterns.py"
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
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "terrabit_pre_commit_hooks",
    "check_xss_patterns.py",
)
_spec = importlib.util.spec_from_file_location("check_xss_patterns", SCRIPT)
xss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xss)


def reguli(cale, text):
    return [c.regula for c in xss.verifica_text(cale, textwrap.dedent(text))]


class TestPython(unittest.TestCase):
    def py(self, text):
        return reguli("my_module/models/x.py", text)

    # --- cazurile reale, inainte de fix

    def test_deltatech_maintenance_fstring(self):
        self.assertEqual(
            self.py(
                """
                picking.message_post(
                    body=Markup(f"Created stock picking {link} for this maintenance request."),
                )
                """
            ),
            ["XSS-PY-01"],
        )

    def test_deltatech_mcp_mail_bot(self):
        self.assertEqual(
            self.py('return Markup(f"{text}<br/>{link}")\n'), ["XSS-PY-01"]
        )

    def test_agroamat_blog_json_dumps(self):
        self.assertEqual(
            self.py(
                'values = {"ld": Markup(json.dumps(art._date_structurate(), ensure_ascii=False))}\n'
            ),
            ["XSS-PY-05"],
        )

    def test_agroamat_blog_sanitize_false(self):
        self.assertEqual(
            self.py('continut = fields.Html("Continut", sanitize=False)\n'),
            ["XSS-PY-06"],
        )

    def test_agroamat_blog_cuprins_procent(self):
        self.assertEqual(
            self.py("""a.cuprins = Markup('<ol class="mb-0">%s</ol>' % randuri)\n"""),
            ["XSS-PY-03"],
        )

    def test_agroamat_marketing_preview_fara_csp(self):
        text = """
            class Ctrl(http.Controller):
                @http.route("/preview/<int:sid>", auth="user")
                def preview(self, sid):
                    s = request.env["x"].browse(sid)
                    return request.make_response(
                        s.randeaza(), headers=[("Content-Type", "text/html; charset=utf-8")]
                    )
            """
        self.assertEqual(self.py(text), ["XSS-PY-07"])

    def test_agroamat_marketing_dupa_fix(self):
        text = """
            ANTETE_PREVIZUALIZARE = [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Security-Policy", "sandbox"),
            ]

            class Ctrl(http.Controller):
                def preview(self, sid):
                    return request.make_response(s.randeaza(), headers=ANTETE_PREVIZUALIZARE)
            """
        self.assertEqual(self.py(text), [])

    # --- celelalte forme gresite

    def test_concatenare_in_markup(self):
        self.assertEqual(
            self.py('body = Markup("<b>" + name + "</b>")\n'), ["XSS-PY-02"]
        )

    def test_markup_variabila_plus(self):
        self.assertEqual(
            self.py('body = header + Markup(content["body"])\n'), ["XSS-PY-02"]
        )

    def test_format_inainte_de_markup(self):
        self.assertEqual(
            self.py('body = Markup("<b>{}</b>".format(name))\n'), ["XSS-PY-04"]
        )

    def test_traducere_cu_procent_inainte(self):
        self.assertEqual(
            self.py('body = Markup(_("Hello <b>%s</b>") % name)\n'), ["XSS-PY-03"]
        )

    def test_sanitize_attributes_si_tags(self):
        text = """
            description = fields.Html(
                sanitize_tags=False,
                sanitize_attributes=False,
            )
            """
        self.assertEqual(self.py(text), ["XSS-PY-06", "XSS-PY-06"])

    def test_html_calculat_editabil(self):
        text = 'x = fields.Html(compute="_c", readonly=False, sanitize=False)\n'
        self.assertEqual(self.py(text), ["XSS-PY-06"])

    def test_markupsafe_atribut(self):
        self.assertEqual(
            self.py('x = markupsafe.Markup(f"<i>{y}</i>")\n'), ["XSS-PY-01"]
        )

    # --- corect, nu se raporteaza

    def test_corect_procent_dupa_markup(self):
        self.assertEqual(self.py('body = Markup("<b>%s</b>") % name\n'), [])

    def test_corect_format_dupa_markup(self):
        self.assertEqual(self.py('body = Markup("{}<br/>{}").format(text, link)\n'), [])

    def test_corect_fix_maintenance(self):
        text = """
            link = Markup('<a href="#" data-oe-id="{}">{}</a>').format(p.id, p.display_name)
            body = Markup("Created stock picking {} for this maintenance request.").format(link)
            """
        self.assertEqual(self.py(text), [])

    def test_corect_markup_literal_plus(self):
        self.assertEqual(self.py('body = Markup("<br/>") + name\n'), [])

    def test_corect_literale(self):
        text = """
            a = Markup("<b>" + "x" + "</b>")
            b = Markup(f"<b>fix</b>")
            c = Markup(_("<b>Done</b>"))
            d = Markup("<b>%s</b>" % "x")
            e = Markup("").join(parts)
            """
        self.assertEqual(self.py(text), [])

    def test_corect_html_calculat(self):
        text = 'explanation_html = fields.Html(compute="_compute_explanation_html", sanitize=False)\n'
        self.assertEqual(self.py(text), [])

    def test_corect_sanitize_overridable(self):
        self.assertEqual(
            self.py('continut = fields.Html("Continut", sanitize_overridable=True)\n'),
            [],
        )

    def test_corect_fragment_qweb(self):
        text = """
            def children(self):
                content = request.env["ir.ui.view"]._render_template("m.t", {})
                return request.make_response(content, headers=[("Content-Type", "text/html")])

            def gol(self):
                return request.make_response("", headers=[("Content-Type", "text/html")])
            """
        self.assertEqual(self.py(text), [])

    def test_corect_make_response_json(self):
        text = 'return request.make_response(data, headers=[("Content-Type", "application/json")])\n'
        self.assertEqual(self.py(text), [])

    def test_comentariu_si_docstring(self):
        text = '''
            def f():
                """Nu scrie Markup(f"{x}")."""
                # Markup(f"{x}")
            '''
        self.assertEqual(self.py(text), [])

    def test_sintaxa_gresita_nu_crapa(self):
        self.assertEqual(self.py("def (:\n"), [])


class TestJs(unittest.TestCase):
    def js(self, text):
        return reguli("my_module/static/src/js/x.esm.js", text)

    def test_inner_html(self):
        self.assertEqual(self.js("el.innerHTML = data.html;\n"), ["XSS-JS-01"])

    def test_inner_html_template_cu_valori(self):
        self.assertEqual(
            self.js("label.innerHTML = `Locker: <span>${name}</span>`;\n"),
            ["XSS-JS-01"],
        )

    def test_insert_adjacent(self):
        self.assertEqual(
            self.js('el.insertAdjacentHTML("beforeend", result.html);\n'), ["XSS-JS-02"]
        )

    def test_jquery_html(self):
        self.assertEqual(
            self.js("$(alert).html('<p>' + data.error + '</p>');\n"), ["XSS-JS-03"]
        )

    def test_owl_markup(self):
        self.assertEqual(
            self.js("content: markup(compose.initialHtml),\n"), ["XSS-JS-04"]
        )

    def test_corect_literale(self):
        text = """
            el.innerHTML = "";
            el.innerHTML = `<p>fix</p>`;
            el.insertAdjacentHTML("beforeend", "<br/>");
            $(el).html("<b>x</b>");
            const h = $(el).html();
            $(el).html($message);
            const t = markup("<b>x</b>");
            if (el.innerHTML === x) {}
            el.textContent = x;
            """
        self.assertEqual(self.js(text), [])

    def test_corect_comentariu_si_import(self):
        text = """
            import { markup } from "@odoo/owl";
            // el.innerHTML = x;
            /*
             * $(x).html(y);
             */
            """
        self.assertEqual(self.js(text), [])

    def test_iframe_in_js(self):
        text = 'const f = `<iframe sandbox="allow-scripts allow-same-origin" src="${u}"></iframe>`;\n'
        self.assertEqual(self.js(text), ["XSS-XML-02"])


class TestXml(unittest.TestCase):
    def xml(self, text):
        return reguli("my_module/views/x.xml", text)

    def test_t_raw_avertisment(self):
        gasite = xss.verifica_text("v.xml", '<t t-raw="doc.note"/>\n')
        self.assertEqual([c.regula for c in gasite], ["XSS-XML-01"])
        self.assertEqual(gasite[0].severitate, xss.AVERTISMENT)

    def test_iframe_sandbox_periculos(self):
        text = """
            <iframe src="/preview"
                    sandbox="allow-same-origin allow-scripts"/>
            """
        gasite = xss.verifica_text("v.xml", textwrap.dedent(text))
        self.assertEqual([(c.regula, c.linie) for c in gasite], [("XSS-XML-02", 3)])

    def test_corect(self):
        text = """
            <t t-out="doc.note"/>
            <iframe sandbox="allow-scripts" src="/p"/>
            <iframe sandbox="" src="/p"/>
            <!-- <t t-raw="x"/> -->
            """
        self.assertEqual(self.xml(text), [])


class TestExceptii(unittest.TestCase):
    def test_xss_ok_cu_motiv_pe_linie(self):
        text = 'x = Markup(f"<b>{n}</b>")  # xss-ok: n este int\n'
        self.assertEqual(reguli("m/models/x.py", text), [])

    def test_xss_ok_pe_linia_de_deasupra(self):
        text = """
            // xss-ok: html trece prin DOMPurify.sanitize
            el.innerHTML = this._mdToHtml(md);
            """
        self.assertEqual(reguli("m/static/src/x.js", text), [])

    def test_xss_ok_pe_apel_pe_mai_multe_linii(self):
        text = """
            body = Markup(  # xss-ok: valorile sunt numere
                f"<b>{n}</b>"
            )
            """
        self.assertEqual(reguli("m/models/x.py", text), [])

    def test_xss_ok_xml(self):
        text = '<!-- xss-ok: raport vechi, camp sanitizat -->\n<t t-raw="doc.note"/>\n'
        self.assertEqual(reguli("m/views/x.xml", text), [])

    def test_xss_ok_fara_motiv(self):
        text = 'x = Markup(f"<b>{n}</b>")  # xss-ok\n'
        self.assertEqual(reguli("m/models/x.py", text), ["XSS-OK-00", "XSS-PY-01"])

    def test_xss_ok_doua_puncte_fara_motiv(self):
        self.assertEqual(
            reguli("m/views/x.xml", '<t t-raw="x"/> <!-- xss-ok: -->\n'),
            ["XSS-OK-00", "XSS-XML-01"],
        )


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def scrie(self, rel, text):
        cale = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(cale), exist_ok=True)
        with open(cale, "w", encoding="utf-8") as f:
            f.write(text)
        return rel

    def ruleaza(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            cwd=self.tmp,
            capture_output=True,
            text=True,
        )

    def test_format_si_cod_iesire(self):
        f = self.scrie("m/models/x.py", 'body = Markup(f"{text}<br/>{link}")\n')
        r = self.ruleaza(f)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(
            r.stdout.startswith("m/models/x.py:1: [XSS-PY-01] Markup(f"), r.stdout
        )

    def test_avertismentul_nu_opreste(self):
        f = self.scrie("m/views/x.xml", '<t t-raw="x"/>\n')
        r = self.ruleaza(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn("[XSS-XML-01] avertisment:", r.stdout)

    def test_warn_only(self):
        f = self.scrie("m/models/x.py", 'body = Markup(f"{x}")\n')
        self.assertEqual(self.ruleaza("--warn-only", f).returncode, 0)

    def test_fisiere_excluse(self):
        text = 'body = Markup(f"{x}")\n'
        fisiere = [
            self.scrie("m/tests/test_x.py", text),
            self.scrie("m/migrations/18.0.1.0.1/post-migrate.py", text),
            self.scrie("m/static/lib/foo/foo.js", "el.innerHTML = x;\n"),
            self.scrie("m/static/src/js/foo.min.js", "el.innerHTML = x;\n"),
        ]
        r = self.ruleaza(*fisiere)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_summary(self):
        f = self.scrie("m/models/x.py", 'a = Markup(f"{x}")\nb = Markup(f"{y}")\n')
        self.assertIn("XSS-PY-01\t2", self.ruleaza("--summary", f).stdout)


if __name__ == "__main__":
    unittest.main()
