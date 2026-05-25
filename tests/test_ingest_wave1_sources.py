import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from scripts.ingest_expression_omics import ingest_expression_omics
from scripts.ingest_uniprot_proteins import ingest_uniprot_proteins
from scripts.ingest_wolbachia_interventions import ingest_wolbachia_interventions
from tests.test_expression_omics_source import GEO_ESEARCH, GEO_ESUMMARY, SRA_ESEARCH, SRA_ESUMMARY
from tests.test_uniprot_proteins_source import PROTEOME_PAYLOAD, UNIPROTKB_PAYLOAD
from tests.test_wolbachia_interventions_source import HTML


class IngestWave1SourceTests(unittest.TestCase):
    def test_ingests_update_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def expression_fetch(url):
                if "db=gds" in url and "esearch.fcgi" in url:
                    return GEO_ESEARCH
                if "db=gds" in url and "esummary.fcgi" in url:
                    return GEO_ESUMMARY
                if "db=sra" in url and "esearch.fcgi" in url:
                    return SRA_ESEARCH
                if "db=sra" in url and "esummary.fcgi" in url:
                    return SRA_ESUMMARY
                raise AssertionError(url)

            expression = ingest_expression_omics(
                artifact_dir=artifact_dir,
                fetch_json=expression_fetch,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            uniprot = ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: UNIPROTKB_PAYLOAD if "/uniprotkb/search" in url else PROTEOME_PAYLOAD,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            wolbachia = ingest_wolbachia_interventions(
                artifact_dir=artifact_dir,
                source_urls=["https://www.worldmosquitoprogram.org/example-yogyakarta"],
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(expression["ok"])
            self.assertTrue(uniprot["ok"])
            self.assertTrue(wolbachia["ok"])
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                (row["source"], row["lane"]): row["n"]
                for row in index.sql(
                    "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                    limit=100,
                )
            }
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 4)
            self.assertEqual(counts[("aedes_expression_omics", "expression")], 2)
            self.assertEqual(counts[("aedes_uniprot_proteins", "proteins")], 2)
            self.assertEqual(counts[("aedes_wolbachia_interventions", "public_health")], 1)
            sources_status = (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            self.assertIn("aedes_expression_omics", sources_status)
            self.assertIn("aedes_uniprot_proteins", sources_status)
            self.assertIn("aedes_wolbachia_interventions", sources_status)

    def test_failed_refreshes_preserve_existing_wave1_source_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def expression_fetch(url):
                if "db=gds" in url and "esearch.fcgi" in url:
                    return GEO_ESEARCH
                if "db=gds" in url and "esummary.fcgi" in url:
                    return GEO_ESUMMARY
                if "db=sra" in url and "esearch.fcgi" in url:
                    return SRA_ESEARCH
                if "db=sra" in url and "esummary.fcgi" in url:
                    return SRA_ESUMMARY
                raise AssertionError(url)

            ingest_expression_omics(
                artifact_dir=artifact_dir,
                fetch_json=expression_fetch,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: UNIPROTKB_PAYLOAD if "/uniprotkb/search" in url else PROTEOME_PAYLOAD,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            ingest_wolbachia_interventions(
                artifact_dir=artifact_dir,
                source_urls=["https://www.worldmosquitoprogram.org/example-yogyakarta"],
                fetch_text=lambda url: HTML,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            expression = ingest_expression_omics(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T01:00:00Z",
            )
            uniprot = ingest_uniprot_proteins(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T01:00:00Z",
            )
            wolbachia = ingest_wolbachia_interventions(
                artifact_dir=artifact_dir,
                source_urls=["https://www.worldmosquitoprogram.org/example-yogyakarta"],
                fetch_text=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-24T01:00:00Z",
            )

            self.assertFalse(expression["ok"])
            self.assertFalse(uniprot["ok"])
            self.assertFalse(wolbachia["ok"])
            self.assertTrue(expression["preserved_existing"])
            self.assertTrue(uniprot["preserved_existing"])
            self.assertTrue(wolbachia["preserved_existing"])
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            counts = {
                row["source"]: row["n"]
                for row in index.sql(
                    "select source, count(*) as n from records group by source order by source",
                    limit=100,
                )
            }
            self.assertEqual(counts["aedes_expression_omics"], 2)
            self.assertEqual(counts["aedes_uniprot_proteins"], 2)
            self.assertEqual(counts["aedes_wolbachia_interventions"], 1)


if __name__ == "__main__":
    unittest.main()
