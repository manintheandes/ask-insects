import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from askinsects.cli import main
from askinsects.context_package import MAX_PACKAGE_BYTES


def generic_evidence_package_v2():
    return {
        "ok": True,
        "schema_version": "ask-insects-evidence-package.v2",
        "content_sha256": "abc123",
        "validation_contract": {
            "producer_linkage": "verified_in_read_only_source_index_during_build",
            "downstream_validation": "exported_snapshot_internal_consistency_only",
            "snapshot_authentication": "publisher_pinned_content_sha256",
        },
        "contexts": [
            {
                "id": "treated_area_contact_avoidance",
                "endpoint_family": "treated_area_occupancy",
                "exposure_routes": ["contact"],
            }
        ],
        "evidence_records": [
            {
                "record_id": "public:swd:1",
                "eligibility": {
                    "ruleset_version": "direct-semantic-evidence.v1",
                    "taxon": {
                        "status": "direct_focal_taxon",
                        "basis": [{"field_path": "payload.title"}],
                    },
                    "context": {
                        "status": "direct_context",
                        "basis": [{"field_path": "payload.abstract"}],
                    },
                },
            }
        ],
        "selector_results": [
            {
                "selector_id": "contact_swd_behavior",
                "candidate_count": 2,
                "selected_count": 1,
                "rejection_counts": {"taxon_not_directly_confirmed": 1},
            }
        ],
        "gaps": [],
    }


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

    def test_context_package_uses_the_hosted_read_surface_by_default(self):
        calls = []

        def fake_request(
            config, method, path, payload=None, timeout=120, max_response_bytes=None
        ):
            calls.append((config.url, method, path, payload, timeout, max_response_bytes))
            return generic_evidence_package_v2()

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ), patch("askinsects.cli.build_context_package") as local_build, patch(
            "askinsects.cli.validate_context_package"
        ) as validate_package:
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("context-package")

        self.assertEqual(code, 0)
        self.assertEqual(
            calls[0],
            (
                "https://ask-insects.example",
                "GET",
                "/context-package",
                None,
                120,
                MAX_PACKAGE_BYTES,
            ),
        )
        local_build.assert_not_called()
        validate_package.assert_called_once()
        payload = json.loads(output)
        self.assertEqual(payload["schema_version"], "ask-insects-evidence-package.v2")
        self.assertEqual(payload["contexts"][0]["endpoint_family"], "treated_area_occupancy")
        self.assertEqual(payload["contexts"][0]["exposure_routes"], ["contact"])
        self.assertEqual(
            payload["validation_contract"]["producer_linkage"],
            "verified_in_read_only_source_index_during_build",
        )
        self.assertEqual(
            payload["evidence_records"][0]["eligibility"]["taxon"]["status"],
            "direct_focal_taxon",
        )
        self.assertEqual(
            payload["evidence_records"][0]["eligibility"]["context"]["status"],
            "direct_context",
        )
        self.assertEqual(
            payload["selector_results"][0]["rejection_counts"],
            {"taxon_not_directly_confirmed": 1},
        )
        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in ("consumer_id", "experiment_detail", "callback", "destination", "private_assay"):
            self.assertNotIn(forbidden, serialized)

    def test_context_package_hosted_failure_never_falls_back_to_local_generation(self):
        calls = []

        def fake_request(
            config, method, path, payload=None, timeout=120, max_response_bytes=None
        ):
            calls.append((method, path, payload, timeout, max_response_bytes))
            return {
                "ok": False,
                "error": {
                    "code": "evidence_package_generation_failed",
                    "message": "The generic public evidence package could not be generated.",
                },
            }

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ), patch("askinsects.cli.build_context_package") as local_build:
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("context-package")

        self.assertEqual(code, 2)
        self.assertEqual(
            calls,
            [("GET", "/context-package", None, 120, MAX_PACKAGE_BYTES)],
        )
        local_build.assert_not_called()
        self.assertEqual(
            json.loads(output)["error"]["code"],
            "evidence_package_generation_failed",
        )

    def test_context_package_hosted_failure_is_rebuilt_without_untrusted_error_text(self):
        leaked = "/Users/josh/private/source.json Authorization: Bearer secret-token " + "x" * 5000

        def fake_request(
            config, method, path, payload=None, timeout=120, max_response_bytes=None
        ):
            return {
                "ok": False,
                "error": {
                    "code": "evidence_package_generation_failed",
                    "message": leaked,
                    "debug": leaked,
                },
            }

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ), patch("askinsects.cli.build_context_package") as local_build:
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("context-package")

        self.assertEqual(code, 2)
        local_build.assert_not_called()
        self.assertEqual(
            json.loads(output),
            {
                "ok": False,
                "error": {
                    "code": "evidence_package_generation_failed",
                    "message": "The generic public evidence package could not be generated.",
                },
            },
        )
        self.assertLess(len(output), 256)
        self.assertNotIn(leaked, output)
        self.assertNotIn("/Users/josh", output)
        self.assertNotIn("secret-token", output)

    def test_context_package_rejects_invalid_hosted_success_without_echoing_it(self):
        leaked = "/Users/josh/private/package.json Authorization: Bearer secret-token"

        def fake_request(
            config, method, path, payload=None, timeout=120, max_response_bytes=None
        ):
            return {
                "ok": True,
                "schema_version": "ask-insects-evidence-package.v2",
                "objective": leaked,
            }

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ), patch(
            "askinsects.cli.validate_context_package",
            side_effect=ValueError(leaked),
        ):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("context-package")

        self.assertEqual(code, 2)
        payload = json.loads(output)
        self.assertEqual(payload["error"]["code"], "evidence_package_invalid")
        self.assertLess(len(output), 256)
        self.assertNotIn("/Users/josh", output)
        self.assertNotIn("secret-token", output)

    def test_context_package_rejects_a_legacy_hosted_success_without_local_fallback(self):
        calls = []

        def fake_request(
            config, method, path, payload=None, timeout=120, max_response_bytes=None
        ):
            calls.append((method, path, payload, timeout, max_response_bytes))
            return {
                "ok": True,
                "schema_version": "ask-insects-context-package.v1",
                "content_sha256": "legacy-hash",
            }

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ), patch("askinsects.cli.build_context_package") as local_build:
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("context-package")

        self.assertEqual(code, 2)
        self.assertEqual(
            calls,
            [("GET", "/context-package", None, 120, MAX_PACKAGE_BYTES)],
        )
        local_build.assert_not_called()
        payload = json.loads(output)
        self.assertEqual(payload["error"]["code"], "evidence_package_schema_mismatch")
        self.assertIn("ask-insects-evidence-package.v2", payload["error"]["message"])
        self.assertNotIn("legacy-hash", output)

    def test_context_package_help_names_the_generic_v2_contract_without_private_parameters(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["context-package", "--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("generic public insect evidence package", help_text)
        self.assertIn("ask-insects-evidence-package.v2", help_text)
        for forbidden_option in ("--consumer", "--experiment", "--callback", "--destination"):
            self.assertNotIn(forbidden_option, help_text)

    def test_compact_hosted_ask_keeps_answer_and_exact_provenance_without_duplicate_rows(self):
        calls = []
        hosted_payload = {
            "ok": True,
            "answer_shape": "repellency_comparison",
            "answer": "Ask Insects cannot support the comparison claim.",
            "claim": {"status": "insufficient_evidence", "reasons": []},
            "coverage": {
                "deduplicated_papers": 10,
                "unresolved_source_gaps": 1,
                "source_gaps": [{"detail": "large duplicate detail"}],
            },
            "comparison": {
                "target": {"species": "Culicidae"},
                "dimensions": ["species", "assay"],
                "directly_comparable_record_ids": [],
                "comparable_pair_record_ids": [],
                "rows": [{"evidence_text": "large duplicate detail"}],
            },
            "evidence": [
                {
                    "record_id": "fact:1",
                    "source": "mosquito_repellent_external_discovery_extracted_facts",
                    "species": "Culicidae",
                    "title": "Candidate assay fact",
                    "text": "large duplicate detail",
                    "provenance": {
                        "source_id": "mosquito_repellent_external_discovery_extracted_facts",
                        "locator": "records#mosquito_repellent_external_discovery:fact:1",
                    },
                }
            ],
        }

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload))
            return hosted_payload

        with patch("askinsects.cli.load_config") as load_config, patch(
            "askinsects.cli.hosted_request", fake_request
        ):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ask",
                "Does anything in the literature beat this result?",
                "--json",
                "--compact",
            )

        self.assertEqual(code, 0)
        self.assertEqual(
            calls[0],
            (
                "POST",
                "/ask",
                {"question": "Does anything in the literature beat this result?", "limit": 5},
            ),
        )
        payload = json.loads(output)
        self.assertEqual(
            set(payload),
            {"ok", "answer_shape", "final_answer"},
        )
        self.assertIn(hosted_payload["answer"], payload["final_answer"])
        self.assertIn("mosquito_repellent_external_discovery_extracted_facts", payload["final_answer"])
        self.assertIn(
            "records#mosquito_repellent_external_discovery:fact:1",
            payload["final_answer"],
        )
        self.assertNotIn("large duplicate detail", payload["final_answer"])

    def test_hosted_insect_intelligence_ingest_sends_program_ledger(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 99}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-insect-intelligence-programs",
                "--hosted",
                "--program-path",
                "config/insect-intelligence-programs.json",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/insect-intelligence-programs")
        self.assertEqual(calls[0][2], {"program_path": "config/insect-intelligence-programs.json"})
        self.assertEqual(calls[0][3], 120)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_literature_depth_ingest_sends_profile_and_bounds(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "results": []}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-literature-depth",
                "--hosted",
                "--profile",
                "mosquito_repellent_literature_extracted_facts",
                "--max-fulltext-units",
                "25",
                "--discover-supplements",
                "--max-supplement-files",
                "7",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/literature-depth")
        self.assertEqual(calls[0][2]["profile"], "mosquito_repellent_literature_extracted_facts")
        self.assertEqual(calls[0][2]["max_fulltext_units"], 25)
        self.assertTrue(calls[0][2]["discover_supplements"])
        self.assertEqual(calls[0][2]["max_supplement_files"], 7)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

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

    def test_hosted_aedes_olfaction_literature_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 183}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-aedes-olfaction-literature",
                "--hosted",
                "--max-results",
                "250",
                "--page-size",
                "50",
                "--unpaywall-email",
                "sources@openinsects.org",
                "--fulltext-limit",
                "25",
                "--delay-seconds",
                "0",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/aedes-olfaction-literature")
        self.assertEqual(calls[0][2]["max_results"], 250)
        self.assertEqual(calls[0][2]["page_size"], 50)
        self.assertTrue(calls[0][2]["include_fulltext"])
        self.assertEqual(calls[0][2]["unpaywall_email"], "sources@openinsects.org")
        self.assertEqual(calls[0][2]["fulltext_limit"], 25)
        self.assertEqual(calls[0][2]["delay_seconds"], 0)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_crossref_literature_audit_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 200}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-crossref-literature-audit",
                "--hosted",
                "--max-results",
                "250",
                "--page-size",
                "50",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/crossref-literature-audit")
        self.assertEqual(calls[0][2]["max_results"], 250)
        self.assertEqual(calls[0][2]["page_size"], 50)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_mosquito_repellent_literature_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 300}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-mosquito-repellent-literature",
                "--hosted",
                "--pubmed-max-results",
                "250",
                "--crossref-max-results",
                "350",
                "--page-size",
                "50",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/mosquito-repellent-literature")
        self.assertEqual(calls[0][2]["pubmed_max_results"], 250)
        self.assertEqual(calls[0][2]["crossref_max_results"], 350)
        self.assertEqual(calls[0][2]["page_size"], 50)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_mosquito_repellent_external_discovery_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 120}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-mosquito-repellent-external-discovery",
                "--hosted",
                "--max-results-per-source",
                "25",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/mosquito-repellent-external-discovery")
        self.assertEqual(calls[0][2]["max_results_per_source"], 25)
        self.assertEqual(calls[0][3], 3600)
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

    def test_hosted_who_malaria_threats_resistance_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 2}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-who-malaria-threats-resistance",
                "--hosted",
                "--species",
                "Aedes aegypti",
                "--sample-limit",
                "3",
                "--aedes-limit",
                "50",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/who-malaria-threats-resistance")
        self.assertEqual(calls[0][2]["species"], "Aedes aegypti")
        self.assertEqual(calls[0][2]["sample_limit"], 3)
        self.assertEqual(calls[0][2]["aedes_limit"], 50)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_harvard_dataverse_suitability_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 2}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-harvard-dataverse-suitability",
                "--hosted",
                "--query",
                '"Aedes aegypti" suitability',
                "--per-page",
                "10",
                "--dataset-limit",
                "3",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/harvard-dataverse-suitability")
        self.assertEqual(calls[0][2]["queries"], ['"Aedes aegypti" suitability'])
        self.assertEqual(calls[0][2]["per_page"], 10)
        self.assertEqual(calls[0][2]["dataset_limit"], 3)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_observation_climate_join_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 2}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-observation-climate-join",
                "--hosted",
                "--limit",
                "25",
                "--input-source",
                "gbif_api",
                "--input-source",
                "inaturalist_api",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/observation-climate-join")
        self.assertEqual(calls[0][2]["limit"], 25)
        self.assertEqual(calls[0][2]["input_sources"], ["gbif_api", "inaturalist_api"])
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

    def test_hosted_cdc_dengue_surveillance_ingest_sends_source_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 8}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-cdc-dengue-surveillance",
                "--hosted",
                "--source-url",
                "https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/cdc-dengue-surveillance")
        self.assertEqual(calls[0][2]["source_urls"], ["https://www.cdc.gov/dengue/data-research/facts-stats/current-data.html"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_ncvbdc_dengue_surveillance_ingest_sends_source_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 221}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-ncvbdc-dengue-surveillance",
                "--hosted",
                "--source-url",
                "https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/ncvbdc-dengue-surveillance")
        self.assertEqual(calls[0][2]["source_urls"], ["https://ncvbdc.mohfw.gov.in/index4.php?lang=1&level=0&lid=3715&linkid=431&theme=Green"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_opendatasus_dengue_surveillance_ingest_sends_years_and_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 9}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-opendatasus-dengue-surveillance",
                "--hosted",
                "--year",
                "2025",
                "--file-url",
                "https://opendatasus.example/DENGBR25.csv.zip",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/opendatasus-dengue-surveillance")
        self.assertEqual(calls[0][2]["years"], [2025])
        self.assertEqual(calls[0][2]["file_urls"], ["https://opendatasus.example/DENGBR25.csv.zip"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_who_dengue_surveillance_ingest_sends_source_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 8}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-who-dengue-surveillance",
                "--hosted",
                "--source-url",
                "https://www.who.int/publications/i/item/who-wer10052-665-678",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/who-dengue-surveillance")
        self.assertEqual(calls[0][2]["source_urls"], ["https://www.who.int/publications/i/item/who-wer10052-665-678"])
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
                "--cds-url",
                "https://vectorbase.org/cds.fasta",
                "--transcript-url",
                "https://vectorbase.org/transcripts.fasta",
                "--go-url",
                "https://vectorbase.org/go.gaf.gz",
                "--codon-usage-url",
                "https://vectorbase.org/codon.txt",
                "--id-events-url",
                "https://vectorbase.org/id-events.tab",
                "--ncbi-linkout-url",
                "https://vectorbase.org/linkout.xml",
                "--orthologs-url",
                "https://orthomcl.org/orthologs.txt.gz",
                "--coorthologs-url",
                "https://orthomcl.org/coorthologs.txt.gz",
                "--inparalogs-url",
                "https://orthomcl.org/inparalogs.txt.gz",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vectorbase-genomics")
        self.assertEqual(calls[0][2]["file_urls"]["gff"], "https://vectorbase.org/gff")
        self.assertEqual(calls[0][2]["file_urls"]["proteins"], "https://vectorbase.org/proteins")
        self.assertEqual(calls[0][2]["file_urls"]["cds"], "https://vectorbase.org/cds.fasta")
        self.assertEqual(calls[0][2]["file_urls"]["transcript_sequences"], "https://vectorbase.org/transcripts.fasta")
        self.assertEqual(calls[0][2]["file_urls"]["go"], "https://vectorbase.org/go.gaf.gz")
        self.assertEqual(calls[0][2]["file_urls"]["codon_usage"], "https://vectorbase.org/codon.txt")
        self.assertEqual(calls[0][2]["file_urls"]["id_events"], "https://vectorbase.org/id-events.tab")
        self.assertEqual(calls[0][2]["file_urls"]["ncbi_linkout"], "https://vectorbase.org/linkout.xml")
        self.assertEqual(calls[0][2]["file_urls"]["orthologs"], "https://orthomcl.org/orthologs.txt.gz")
        self.assertEqual(calls[0][2]["file_urls"]["coorthologs"], "https://orthomcl.org/coorthologs.txt.gz")
        self.assertEqual(calls[0][2]["file_urls"]["inparalogs"], "https://orthomcl.org/inparalogs.txt.gz")
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_expression_omics_ingest_sends_limits(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 20}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-expression-omics",
                "--hosted",
                "--geo-limit",
                "7",
                "--sra-limit",
                "9",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/expression-omics")
        self.assertEqual(calls[0][2]["geo_limit"], 7)
        self.assertEqual(calls[0][2]["sra_limit"], 9)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_uniprot_proteins_ingest_sends_limits(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 250}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-uniprot-proteins",
                "--hosted",
                "--protein-limit",
                "12",
                "--proteome-limit",
                "3",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/uniprot-proteins")
        self.assertEqual(calls[0][2]["protein_limit"], 12)
        self.assertEqual(calls[0][2]["proteome_limit"], 3)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_wolbachia_interventions_ingest_sends_source_urls(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 5}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-wolbachia-interventions",
                "--hosted",
                "--source-url",
                "https://www.worldmosquitoprogram.org/example",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/wolbachia-interventions")
        self.assertEqual(calls[0][2]["source_urls"], ["https://www.worldmosquitoprogram.org/example"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_vectorbyte_traits_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 42}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-vectorbyte-traits",
                "--hosted",
                "--query",
                "Aedes aegypti",
                "--dataset-limit",
                "3",
                "--row-limit",
                "250",
                "--search-limit",
                "25",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vectorbyte-traits")
        self.assertEqual(
            calls[0][2],
            {
                "query": "Aedes aegypti",
                "dataset_limit": 3,
                "row_limit": 250,
                "search_limit": 25,
            },
        )
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_vectorbyte_abundance_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 42}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-vectorbyte-abundance",
                "--hosted",
                "--query",
                "Aedes aegypti",
                "--dataset-limit",
                "2",
                "--row-limit",
                "250",
                "--search-page-limit",
                "1",
                "--dataset-page-limit",
                "10",
                "--dataset-id",
                "27006",
                "--dataset-id",
                "220",
                "--merge-existing",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vectorbyte-abundance")
        self.assertEqual(
            calls[0][2],
            {
                "query": "Aedes aegypti",
                "dataset_limit": 2,
                "row_limit": 250,
                "search_page_limit": 1,
                "dataset_page_limit": 10,
                "dataset_ids": ["27006", "220"],
                "merge_existing": True,
            },
        )
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_vectorbyte_abundance_ingest_reads_dataset_id_file(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 42}

        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_file = Path(tmpdir) / "vecdyn-datasets.txt"
            dataset_file.write_text("27006\n220, 221\n220\n", encoding="utf-8")
            with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
                load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
                code, output = self.run_cli(
                    "ingest-vectorbyte-abundance",
                    "--hosted",
                    "--dataset-id-file",
                    str(dataset_file),
                    "--dataset-id",
                    "222",
                    "--dataset-limit",
                    "4",
                )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][1], "/ingest/vectorbyte-abundance")
        self.assertEqual(calls[0][2]["dataset_ids"], ["222", "27006", "220", "221"])
        self.assertEqual(calls[0][2]["dataset_limit"], 4)
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

    def test_hosted_vectornet_surveillance_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 546}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-vectornet-surveillance",
                "--hosted",
                "--species",
                "Aedes aegypti",
                "--archive-url",
                "https://ipt.gbif.org/archive.do?r=vndatabase",
                "--max-records",
                "10",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/vectornet-surveillance")
        self.assertEqual(calls[0][2]["species"], "Aedes aegypti")
        self.assertEqual(calls[0][2]["archive_url"], "https://ipt.gbif.org/archive.do?r=vndatabase")
        self.assertEqual(calls[0][2]["max_records"], 10)
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

    def test_hosted_zenodo_aedes_video_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-zenodo-aedes-videos",
                "--hosted",
                "--query",
                '"Aedes aegypti" mp4',
                "--size",
                "7",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/zenodo-aedes-videos")
        self.assertEqual(calls[0][2]["query"], '"Aedes aegypti" mp4')
        self.assertEqual(calls[0][2]["size"], 7)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_figshare_aedes_video_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-figshare-aedes-videos",
                "--hosted",
                "--query",
                "Aedes aegypti mp4",
                "--page-size",
                "7",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/figshare-aedes-videos")
        self.assertEqual(calls[0][2]["query"], "Aedes aegypti mp4")
        self.assertEqual(calls[0][2]["page_size"], 7)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_pmc_video_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-pmc-videos",
                "--hosted",
                "--article-url",
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
                "--retrieved-at",
                "2026-05-25T00:00:00Z",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/pmc-videos")
        self.assertEqual(calls[0][2]["article_urls"], ["https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"])
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-25T00:00:00Z")
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

    def test_hosted_ncbi_snp_variation_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-ncbi-snp-variation",
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
        self.assertEqual(calls[0][1], "/ingest/ncbi-snp-variation")
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
                "--max-supplement-discovery-records",
                "34",
                "--max-repository-supplement-discovery-records",
                "7",
                "--max-supplement-files",
                "12",
                "--max-supplement-bytes",
                "3456",
                "--max-pdf-supplement-files",
                "2",
                "--source-record-id",
                "openalex:WFACT1",
                "--merge-existing",
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
                "max_supplement_discovery_records": 34,
                "max_repository_supplement_discovery_records": 7,
                "max_supplement_files": 12,
                "max_supplement_bytes": 3456,
                "max_pdf_supplement_files": 2,
                "source_record_ids": ["openalex:WFACT1"],
                "merge_existing": True,
            },
        )
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_video_atoms_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 7}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-video-atoms",
                "--hosted",
                "--max-video-bytes",
                "12345",
                "--mirror-videos",
                "--generate-artifacts",
                "--discover-sources",
                "--allow-unclear-license",
                "--allowed-licenses",
                "CC-BY,Creative Commons Attribution License",
                "--motion-table",
                "raw/video_atoms/motion.csv",
                "--discovery-repository",
                "dryad",
                "--merge-existing",
                "--skip-motion-rows",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/video-atoms")
        self.assertEqual(
            calls[0][2],
            {
                "max_video_bytes": 12345,
                "mirror_videos": True,
                "generate_artifacts": True,
                "discover_sources": True,
                "allow_unclear_license": True,
                "allowed_licenses": ["CC-BY", "Creative Commons Attribution License"],
                "motion_table_paths": ["raw/video_atoms/motion.csv"],
                "max_discovery_results": 1000,
                "discovery_repositories": ["dryad"],
                "merge_existing": True,
                "parse_motion_rows": False,
            },
        )
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_image_atoms_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 7}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli(
                "ingest-image-atoms",
                "--hosted",
                "--mirror-images",
                "--max-image-bytes",
                "1234",
                "--max-image-mirrors",
                "5",
                "--allow-unclear-license",
                "--allowed-licenses",
                "cc-by,CC0",
            )

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/image-atoms")
        self.assertEqual(
            calls[0][2],
            {
                "mirror_images": True,
                "max_image_bytes": 1234,
                "max_image_mirrors": 5,
                "allow_unclear_license": True,
                "allowed_licenses": ["cc-by", "CC0"],
            },
        )
        self.assertEqual(calls[0][3], 7200)
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

    def test_hosted_drosophila_suzukii_occurrence_ecology_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 12}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-drosophila-suzukii-occurrence-ecology", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-occurrence-ecology")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_resistance_table_rows_ingest_sends_request(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True, "record_count": 1}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = SimpleNamespace(url="https://ask-insects.example", token="secret")
            code, output = self.run_cli("ingest-resistance-table-rows", "--hosted")

        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/resistance-table-rows")
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_aedes_deep_sources_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-aedes-deep-sources",
                "--hosted",
                "--compendium-row-limit",
                "25",
                "--bioproject-limit",
                "7",
                "--worldclim-sample-limit",
                "3",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/aedes-deep-sources")
        self.assertEqual(calls[0][2]["compendium_row_limit"], 25)
        self.assertEqual(calls[0][2]["bioproject_limit"], 7)
        self.assertEqual(calls[0][2]["worldclim_sample_limit"], 3)
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii",
                "--hosted",
                "--gbif-occurrence-limit",
                "11",
                "--inaturalist-observation-limit",
                "12",
                "--literature-max-works",
                "13",
                "--bold-limit",
                "14",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii")
        self.assertEqual(calls[0][2]["gbif_occurrence_limit"], 11)
        self.assertEqual(calls[0][2]["inaturalist_observation_limit"], 12)
        self.assertEqual(calls[0][2]["literature_max_works"], 13)
        self.assertEqual(calls[0][2]["bold_limit"], 14)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_deep_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-deep-sources",
                "--hosted",
                "--ncbi-limit",
                "15",
                "--protein-limit",
                "16",
                "--proteome-limit",
                "17",
                "--repository-limit",
                "18",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-deep-sources")
        self.assertEqual(calls[0][2]["ncbi_limit"], 15)
        self.assertEqual(calls[0][2]["protein_limit"], 16)
        self.assertEqual(calls[0][2]["proteome_limit"], 17)
        self.assertEqual(calls[0][2]["repository_limit"], 18)
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_genome_files_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-genome-files",
                "--hosted",
                "--assembly-accession",
                "GCF_043229965.1",
                "--max-download-bytes",
                "12345",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-genome-files")
        self.assertEqual(calls[0][2]["assembly_accession"], "GCF_043229965.1")
        self.assertEqual(calls[0][2]["max_download_bytes"], 12345)
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_extracted_facts_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-extracted-facts",
                "--hosted",
                "--discover-supplements",
                "--download-supplements",
                "--max-supplement-discovery-records",
                "19",
                "--max-supplement-files",
                "20",
                "--source-record-id",
                "swd:openalex:W1",
                "--merge-existing",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-extracted-facts")
        self.assertTrue(calls[0][2]["discover_supplements"])
        self.assertTrue(calls[0][2]["download_supplements"])
        self.assertEqual(calls[0][2]["max_supplement_discovery_records"], 19)
        self.assertEqual(calls[0][2]["max_supplement_files"], 20)
        self.assertEqual(calls[0][2]["source_record_ids"], ["swd:openalex:W1"])
        self.assertTrue(calls[0][2]["merge_existing"])
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_literature_fulltext_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-literature-fulltext",
                "--hosted",
                "--email",
                "sources@openinsects.org",
                "--limit",
                "30",
                "--delay-seconds",
                "0",
                "--max-fulltext-bytes",
                "12345",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-literature-fulltext")
        self.assertEqual(calls[0][2]["email"], "sources@openinsects.org")
        self.assertEqual(calls[0][2]["limit"], 30)
        self.assertEqual(calls[0][2]["delay_seconds"], 0)
        self.assertEqual(calls[0][2]["max_fulltext_bytes"], 12345)
        self.assertTrue(calls[0][2]["include_unpaywall"])
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ncbi_nucleotide_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-ncbi-nucleotide",
                "--hosted",
                "--max-results",
                "31",
                "--page-size",
                "32",
                "--delay-seconds",
                "0",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-ncbi-nucleotide")
        self.assertEqual(calls[0][2]["max_results"], 31)
        self.assertEqual(calls[0][2]["page_size"], 32)
        self.assertEqual(calls[0][2]["delay_seconds"], 0)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ncbi_snp_variation_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-ncbi-snp-variation",
                "--hosted",
                "--limit",
                "33",
                "--page-size",
                "34",
                "--delay-seconds",
                "0",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-ncbi-snp-variation")
        self.assertEqual(calls[0][2]["limit"], 33)
        self.assertEqual(calls[0][2]["page_size"], 34)
        self.assertEqual(calls[0][2]["delay_seconds"], 0)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ncbi_marker_review_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-ncbi-marker-review",
                "--hosted",
                "--max-results",
                "35",
                "--page-size",
                "36",
                "--delay-seconds",
                "0",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-ncbi-marker-review")
        self.assertEqual(calls[0][2]["max_results"], 35)
        self.assertEqual(calls[0][2]["page_size"], 36)
        self.assertEqual(calls[0][2]["delay_seconds"], 0)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_extension_guidance_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-extension-guidance",
                "--hosted",
                "--source-url",
                "https://extension.example/swd",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-extension-guidance")
        self.assertEqual(calls[0][2]["source_urls"], ["https://extension.example/swd"])
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_jki_drosomon_trap_captures_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-jki-drosomon-trap-captures",
                "--hosted",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-jki-drosomon-trap-captures")
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_osu_trap_reports_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-osu-trap-reports",
                "--hosted",
                "--retrieved-at",
                "2026-05-30T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-osu-trap-reports")
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-30T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_dryad_landscape_monitoring_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-dryad-landscape-monitoring",
                "--hosted",
                "--retrieved-at",
                "2026-05-30T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-dryad-landscape-monitoring")
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-30T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_plos_climate_suitability_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-plos-climate-suitability",
                "--hosted",
                "--retrieved-at",
                "2026-05-30T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-plos-climate-suitability")
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-30T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_umn_flight_assay_rows_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-umn-flight-assay-rows",
                "--hosted",
                "--max-download-bytes",
                "123456",
                "--max-rows",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-umn-flight-assay-rows")
        self.assertEqual(calls[0][2]["max_download_bytes"], 123456)
        self.assertEqual(calls[0][2]["max_rows"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ncbi_gene_orthologs_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-ncbi-gene-orthologs",
                "--hosted",
                "--max-download-bytes",
                "123456",
                "--max-rows",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-ncbi-gene-orthologs")
        self.assertEqual(calls[0][2]["max_download_bytes"], 123456)
        self.assertEqual(calls[0][2]["max_rows"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_ensembl_metazoa_orthology_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-ensembl-metazoa-orthology",
                "--hosted",
                "--max-download-bytes",
                "123456",
                "--max-rows-per-file",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-ensembl-metazoa-orthology")
        self.assertEqual(calls[0][2]["max_download_bytes"], 123456)
        self.assertEqual(calls[0][2]["max_rows_per_file"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_geo_expression_matrices_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-geo-expression-matrices",
                "--hosted",
                "--max-download-bytes",
                "123456",
                "--max-rows-per-file",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-geo-expression-matrices")
        self.assertEqual(calls[0][2]["max_download_bytes"], 123456)
        self.assertEqual(calls[0][2]["max_rows_per_file"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_figshare_mk_selection_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-figshare-mk-selection",
                "--hosted",
                "--max-download-bytes",
                "123456",
                "--max-rows",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-figshare-mk-selection")
        self.assertEqual(calls[0][2]["max_download_bytes"], 123456)
        self.assertEqual(calls[0][2]["max_rows"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_population_genomics_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-population-genomics",
                "--hosted",
                "--limit",
                "42",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-population-genomics")
        self.assertEqual(calls[0][2]["limit"], 42)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_dryad_population_variants_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-dryad-population-variants",
                "--hosted",
                "--max-mirror-bytes",
                "123456",
                "--retrieved-at",
                "2026-05-29T00:00:00Z",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-dryad-population-variants")
        self.assertEqual(calls[0][2]["max_mirror_bytes"], 123456)
        self.assertEqual(calls[0][2]["retrieved_at"], "2026-05-29T00:00:00Z")
        self.assertEqual(calls[0][3], 3600)
        self.assertTrue(json.loads(output)["ok"])

    def test_hosted_drosophila_suzukii_video_atoms_ingest_sends_options(self):
        calls = []

        def fake_request(config, method, path, payload=None, timeout=120):
            calls.append((method, path, payload, timeout))
            return {"ok": True}

        with patch("askinsects.cli.load_config") as load_config, patch("askinsects.cli.hosted_request", fake_request):
            load_config.return_value = object()
            code, output = self.run_cli(
                "ingest-drosophila-suzukii-video-atoms",
                "--hosted",
                "--mirror-videos",
                "--generate-artifacts",
                "--max-video-bytes",
                "1234",
                "--allow-unclear-license",
                "--allowed-licenses",
                "CC BY,CC0",
            )

        self.assertEqual(code, 0, output)
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "/ingest/drosophila-suzukii-video-atoms")
        self.assertTrue(calls[0][2]["mirror_videos"])
        self.assertTrue(calls[0][2]["generate_artifacts"])
        self.assertEqual(calls[0][2]["max_video_bytes"], 1234)
        self.assertTrue(calls[0][2]["allow_unclear_license"])
        self.assertEqual(calls[0][2]["allowed_licenses"], ["CC BY", "CC0"])
        self.assertEqual(calls[0][3], 7200)
        self.assertTrue(json.loads(output)["ok"])


if __name__ == "__main__":
    unittest.main()
