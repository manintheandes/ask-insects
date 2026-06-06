import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from askinsects.cli import main


class HostedDefaultReadTests(unittest.TestCase):
    """ask-insects answers ONLY from the hosted plane: read commands route to hosted
    by default; --local is a loud, explicit dev escape."""

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_sql_defaults_to_hosted_without_flag(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path))
            return {"ok": True, "rows": [{"n": 1}]}

        with patch("askinsects.cli.load_config"), patch("askinsects.cli.hosted_request", fake_request):
            code, out, err = self._run("sql", "select 1 as n")

        self.assertEqual(code, 0)
        self.assertEqual(calls, [("POST", "/sql")])  # went to hosted, not local
        self.assertIn('"n": 1', out)

    def test_search_and_ask_and_summary_default_to_hosted(self):
        seen = []

        def fake_request(config, method, path, payload=None, timeout=120):
            seen.append(path)
            return {"ok": True, "rows": [], "answer": "x"}

        with patch("askinsects.cli.load_config"), patch("askinsects.cli.hosted_request", fake_request):
            self._run("search", "literature", "Drosophila suzukii")
            self._run("ask", "what is known?", "--json")
            self._run("summary")
        self.assertIn("/search", seen)
        self.assertIn("/ask", seen)
        self.assertIn("/summary", seen)

    def test_local_flag_does_not_hit_hosted_and_warns(self):
        hit = {"hosted": False}

        def fake_request(config, method, path, payload=None, timeout=120):
            hit["hosted"] = True
            return {"ok": True, "rows": []}

        with tempfile.TemporaryDirectory() as tmp:
            with patch("askinsects.cli.load_config"), patch("askinsects.cli.hosted_request", fake_request):
                code, out, err = self._run("--artifact-dir", str(Path(tmp) / "mosquito-v1"), "sql", "select 1", "--local")

        self.assertFalse(hit["hosted"])  # --local never touches the hosted plane (reads local)


if __name__ == "__main__":
    unittest.main()
