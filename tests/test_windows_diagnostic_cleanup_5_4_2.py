from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsDiagnosticCleanup542Tests(unittest.TestCase):
    def test_cloud_diagnostic_explicitly_closes_raw_sqlite_connection(self):
        source = (ROOT / "diagnostico.py").read_text(encoding="utf-8")
        self.assertIn("from contextlib import closing", source)
        self.assertIn("with closing(sqlite3.connect(temp_db_path, timeout=3)) as check:", source)
        self.assertNotIn("with sqlite3.connect(temp_db_path) as check:", source)

    def test_diagnostic_has_no_with_sqlite_connect_context_that_relies_on_nonclosing_exit(self):
        tree = ast.parse((ROOT / "diagnostico.py").read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            for item in node.items:
                call = item.context_expr
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "sqlite3" and func.attr == "connect":
                        offenders.append(getattr(node, "lineno", -1))
        self.assertEqual(offenders, [], f"sqlite3.connect usado diretamente em with nas linhas {offenders}; use closing(...)")


if __name__ == "__main__":
    unittest.main()
