import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.server import dispatch_request


class ServerTests(unittest.TestCase):
    def test_auth_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            response = dispatch_request(
                "GET",
                "/health",
                None,
                headers={},
                artifact_dir=Path(tmpdir),
                token="secret",
            )

            self.assertEqual(response.status, 401)
            self.assertFalse(response.payload["ok"])

    def test_health_summary_sources_ask_and_sql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            headers = {"Authorization": "Bearer secret"}

            health = dispatch_request("GET", "/health", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertTrue(health.payload["ok"])
            self.assertEqual(health.payload["db_path"], str(artifact_dir / "source_index.sqlite"))

            summary = dispatch_request("GET", "/summary", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertEqual(summary.payload["record_count"], 7)

            sources = dispatch_request("GET", "/sources", None, headers=headers, artifact_dir=artifact_dir, token="secret")
            self.assertIn("mosquito_v1_fixtures", sources.payload["sources"])

            answer = dispatch_request(
                "POST",
                "/ask",
                {"question": "what do we know about Aedes aegypti?", "limit": 2},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
            )
            self.assertTrue(answer.payload["ok"])
            self.assertTrue(answer.payload["evidence"])

            sql = dispatch_request(
                "POST",
                "/sql",
                {"sql": "select source, count(*) as n from records group by source"},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
            )
            self.assertTrue(sql.payload["ok"])
            self.assertEqual(sql.payload["rows"][0]["n"], 7)

    def test_ingest_inaturalist_uses_staging_then_activates(self):
        calls = []

        def fake_builder(**kwargs):
            calls.append(kwargs)
            artifact_dir = kwargs["artifact_dir"]
            build_fixture_index(artifact_dir=artifact_dir)
            return {"ok": True, "record_count": 7}

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            headers = {"Authorization": "Bearer secret"}
            response = dispatch_request(
                "POST",
                "/ingest/inaturalist",
                {"species": ["Aedes aegypti"], "observation_limit": 10, "page_size": 10, "delay_seconds": 0},
                headers=headers,
                artifact_dir=artifact_dir,
                token="secret",
                build_source_index_fn=fake_builder,
            )

            self.assertEqual(response.status, 200)
            self.assertTrue(response.payload["ok"])
            self.assertEqual(calls[0]["inaturalist_species"], ["Aedes aegypti"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
            self.assertFalse((artifact_dir.parent / ".mosquito-v1.staging").exists())


if __name__ == "__main__":
    unittest.main()
