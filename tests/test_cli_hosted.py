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

    def test_setup_saves_config_and_reports_ready_after_health_check(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((config.url, config.token, method, path, payload, timeout))
            return {"ok": True, "record_count": 436182}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            with patch("askinsects.cli.HOSTED_CONFIG_PATH", path), patch("askinsects.cli.hosted_request", fake_request):
                code, output = self.run_cli("setup", "--url", "https://ask-insects.example", "--token", "secret")

            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["url"], "https://ask-insects.example")
            self.assertEqual(payload["record_count"], 436182)
            self.assertNotIn("secret", output)
            self.assertEqual(calls[0], ("https://ask-insects.example", "secret", "GET", "/health", None, 120))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["url"], "https://ask-insects.example")

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

    def test_hosted_irmapper_ingest_sends_species_option(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 16708}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-irmapper",
                "--hosted",
                "--species",
                "Aedes aegypti",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/irmapper")
        self.assertEqual(calls[0][2]["species"], "Aedes aegypti")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_public_health_ingest_sends_source_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 8}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-public-health",
                "--hosted",
                "--source-url",
                "https://www.cdc.gov/example",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/public-health")
        self.assertEqual(calls[0][2]["source_urls"], ["https://www.cdc.gov/example"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_paho_dengue_surveillance_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 8}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-paho-dengue-surveillance",
                "--hosted",
                "--report-url",
                "https://ais.paho.org/example",
                "--dashboard-page",
                "https://www.paho.org/dashboard",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/paho-dengue-surveillance")
        self.assertEqual(calls[0][2]["report_urls"], ["https://ais.paho.org/example"])
        self.assertEqual(calls[0][2]["dashboard_pages"], ["https://www.paho.org/dashboard"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_vectorbase_genomics_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 4}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-vectorbase-genomics",
                "--hosted",
                "--gff-url",
                "https://vectorbase.org/gff",
                "--protein-url",
                "https://vectorbase.org/proteins",
                "--go-url",
                "https://vectorbase.org/go.gaf.gz",
                "--codon-usage-url",
                "https://vectorbase.org/codon.txt",
                "--id-events-url",
                "https://vectorbase.org/id-events.tab",
                "--ncbi-linkout-url",
                "https://vectorbase.org/linkout.xml",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vectorbase-genomics")
        self.assertEqual(calls[0][2]["file_urls"]["gff"], "https://vectorbase.org/gff")
        self.assertEqual(calls[0][2]["file_urls"]["proteins"], "https://vectorbase.org/proteins")
        self.assertEqual(calls[0][2]["file_urls"]["go"], "https://vectorbase.org/go.gaf.gz")
        self.assertEqual(calls[0][2]["file_urls"]["codon_usage"], "https://vectorbase.org/codon.txt")
        self.assertEqual(calls[0][2]["file_urls"]["id_events"], "https://vectorbase.org/id-events.tab")
        self.assertEqual(calls[0][2]["file_urls"]["ncbi_linkout"], "https://vectorbase.org/linkout.xml")
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_mosquito_alert_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 140}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-mosquito-alert",
                "--hosted",
                "--occurrence-limit",
                "70",
                "--occurrence-page-size",
                "30",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/mosquito-alert")
        self.assertEqual(calls[0][2]["occurrence_limit"], 70)
        self.assertEqual(calls[0][2]["occurrence_page_size"], 30)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_dryad_behavior_video_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 30}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-dryad-behavior-videos",
                "--hosted",
                "--doi",
                "10.5061/dryad.example",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/dryad-behavior-videos")
        self.assertEqual(calls[0][2]["dois"], ["10.5061/dryad.example"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_osf_flighttrackai_video_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 21}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-osf-flighttrackai-videos", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/osf-flighttrackai-videos")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_mendeley_behavior_media_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 5}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-mendeley-behavior-media",
                "--hosted",
                "--dataset",
                "6gvs94p6r2:1",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/mendeley-behavior-media")
        self.assertEqual(calls[0][2]["datasets"], ["6gvs94p6r2:1"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_pathogen_taxonomy_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 6}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-pathogen-taxonomy", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/pathogen-taxonomy")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_ncbi_biosamples_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1000}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-ncbi-biosamples",
                "--hosted",
                "--species",
                "Aedes aegypti",
                "--limit",
                "500",
                "--page-size",
                "100",
                "--delay-seconds",
                "0",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/ncbi-biosamples")
        self.assertEqual(calls[0][2]["species"], "Aedes aegypti")
        self.assertEqual(calls[0][2]["limit"], 500)
        self.assertEqual(calls[0][2]["page_size"], 100)
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_vector_competence_assay_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 4}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-vector-competence-assays", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vector-competence-assays")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_resistance_marker_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 12}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-resistance-markers", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/resistance-markers")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_extracted_facts_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 18}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-extracted-facts",
                "--hosted",
                "--max-fulltext-units",
                "25",
                "--discover-supplements",
                "--download-supplements",
                "--max-supplement-files",
                "12",
                "--max-supplement-bytes",
                "3456",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/extracted-facts")
        self.assertEqual(
            calls[0][2],
            {
                "max_fulltext_units": 25,
                "discover_supplements": True,
                "download_supplements": True,
                "max_supplement_files": 12,
                "max_supplement_bytes": 3456,
            },
        )
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_occurrence_ecology_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 12}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-occurrence-ecology", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/occurrence-ecology")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])


if __name__ == "__main__":
    unittest.main()
