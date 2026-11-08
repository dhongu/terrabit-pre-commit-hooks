#!/usr/bin/env python
"""Teste pentru tb_gen_index.py: eticheta de găzduire din antetul paginii Apps Store.

Rulează din rădăcina repo-ului de hook-uri:

    python3 -m unittest tests/test_tb_gen_index.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrabit_pre_commit_hooks import tb_gen_index  # noqa: E402

MANIFEST = {"version": "19.0.1.0.0", "category": "Tools", "license": "OPL-1"}


class TestHostingBadge(unittest.TestCase):
    def _addon(self, with_init):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp))
        with open(os.path.join(tmp, "__manifest__.py"), "w", encoding="utf-8") as handle:
            handle.write(repr(MANIFEST))
        if with_init:
            open(os.path.join(tmp, "__init__.py"), "w", encoding="utf-8").close()
        return tmp

    def test_python_addon_is_not_online(self):
        addon = self._addon(with_init=True)
        self.assertFalse(tb_gen_index.is_data_only(addon))
        badges = tb_gen_index.build_badges(MANIFEST, "en", data_only=tb_gen_index.is_data_only(addon))
        self.assertIn("Odoo.sh &bull; On-premise", badges)
        self.assertNotIn("Odoo Online", badges)

    def test_data_only_addon_is_online(self):
        addon = self._addon(with_init=False)
        self.assertTrue(tb_gen_index.is_data_only(addon))
        for lang in ("en", "ro"):
            badges = tb_gen_index.build_badges(MANIFEST, lang, data_only=True)
            self.assertIn("Odoo Online &bull; Odoo.sh", badges)


if __name__ == "__main__":
    unittest.main()
