import json
import subprocess
import sys
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "askinsects", *args],
            capture_output=True,
            text=True,
        )

    def test_health_summary_sources_and_ask(self):
        subprocess.run([sys.executable, "scripts/build_source_index.py", "--fixtures"], check=True)

        health = subprocess.check_output([sys.executable, "-m", "askinsects", "health"], text=True)
        self.assertTrue(json.loads(health)["ok"])

        summary = subprocess.check_output([sys.executable, "-m", "askinsects", "summary"], text=True)
        self.assertGreater(json.loads(summary)["record_count"], 0)

        sources = subprocess.check_output([sys.executable, "-m", "askinsects", "sources"], text=True)
        self.assertIn("mosquito_v1_fixtures", sources)

        answer = subprocess.check_output(
            [sys.executable, "-m", "askinsects", "ask", "what do we know about Aedes aegypti?", "--json"],
            text=True,
        )
        payload = json.loads(answer)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["evidence"])

    def test_missing_index_commands_return_structured_errors(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            cases = [
                ("summary",),
                ("search", "taxonomy", "Aedes"),
                ("sql", "select * from records"),
                ("ask", "what do we know about Aedes aegypti?", "--json"),
            ]
            for args in cases:
                with self.subTest(args=args):
                    result = self.run_cli("--artifact-dir", artifact_dir, *args)

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr, "")
                    payload = json.loads(result.stdout)
                    self.assertFalse(payload["ok"])
                    self.assertIn("error", payload)
                    self.assertIn("mosquito_v1", payload["source_gap"]["reason"])

    def test_invalid_write_sql_returns_structured_error(self):
        subprocess.run([sys.executable, "scripts/build_source_index.py", "--fixtures"], check=True)

        result = self.run_cli("sql", "delete from records")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)
        self.assertEqual(payload["source_gap"]["lane"], "sql")


if __name__ == "__main__":
    unittest.main()
