import json
import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
