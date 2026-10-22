"""Spec NFR-01, NFR-02."""
import ast
import os
import sys
import unittest
from pathlib import Path

import actiontrack
from actiontrack.store import db_path


class NonFunctional(unittest.TestCase):
    def test_stdlib_only_NFR_01(self):
        for p in Path(actiontrack.__file__).parent.glob("*.py"):
            for node in ast.walk(ast.parse(p.read_text())):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    self.assertTrue(m in sys.stdlib_module_names or m == "actiontrack", f"{p.name} imports {m}")
        self.assertGreaterEqual(sys.version_info, (3, 10))

    def test_db_location_NFR_02(self):
        old = os.environ.pop("ACTIONTRACK_DB", None)
        try:
            self.assertEqual(db_path(None), Path(".actiontrack/actiontrack.db"))
            os.environ["ACTIONTRACK_DB"] = "/x/y.db"
            self.assertEqual(db_path(None), Path("/x/y.db"))
            self.assertEqual(db_path("/z.db"), Path("/z.db"))   # --db wins
        finally:
            os.environ.pop("ACTIONTRACK_DB", None)
            if old:
                os.environ["ACTIONTRACK_DB"] = old


class ClosedPipe(unittest.TestCase):
    def test_broken_pipe_is_quiet_NFR_04(self):
        import subprocess
        from tests.helpers import SAMPLES
        env = {**os.environ, "PYTHONPATH": str(Path(actiontrack.__file__).parent.parent),
               "ACTIONTRACK_DB": str(Path(__import__("tempfile").mkdtemp()) / "p.db")}
        cmd = f"{sys.executable} -m actiontrack ingest {SAMPLES} -v | head -1"
        r = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr)
