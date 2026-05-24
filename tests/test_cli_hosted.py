import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from askinsects.cli import main


class HostedCliTests(unittest.TestCase):
    def run_cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(list(args))
        return code, output.getvalue()

    def test_configure_writes_hosted_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            with patch("askinsects.cli.HOSTED_CONFIG_PATH", path):
                code, output = self.run_cli("configure", "--url", "https://ask-insects.example", "--token", "secret")

            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            self.assertTrue(path.exists())

    def test_hosted_health_uses_remote_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((config.url, method, path, payload))
            return {"ok": True, "hosted": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("health", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("https://ask-insects.example", "GET", "/health", None))
        self.assertTrue(json.loads(output)["hosted"])

    def test_hosted_ingest_sends_species_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 4}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-inaturalist",
                "--hosted",
                "--species",
                "Aedes aegypti",
                "--observation-limit",
                "10",
                "--page-size",
                "10",
                "--delay-seconds",
                "0",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/inaturalist")
        self.assertEqual(calls[0][2]["species"], ["Aedes aegypti"])
        self.assertEqual(calls[0][2]["observation_limit"], 10)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_gbif_ingest_sends_deep_species_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 82238}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-gbif",
                "--hosted",
                "--species",
                "Aedes aegypti",
                "--occurrence-limit",
                "82237",
                "--occurrence-page-size",
                "300",
                "--occurrence-workers",
                "6",
                "--delay-seconds",
                "0",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/gbif")
        self.assertEqual(calls[0][2]["species"], ["Aedes aegypti"])
        self.assertEqual(calls[0][2]["occurrence_limit"], 82237)
        self.assertEqual(calls[0][2]["occurrence_page_size"], 300)
        self.assertEqual(calls[0][2]["occurrence_workers"], 6)
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])


if __name__ == "__main__":
    unittest.main()
