import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_aedes_olfaction_literature import ingest_aedes_olfaction_literature
from tests.test_aedes_olfaction_literature_source import ESEARCH, ESUMMARY


class IngestAedesOlfactionLiteratureTests(unittest.TestCase):
    def test_ingest_updates_audit_lane_without_removing_other_literature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="literature:openalex:W123",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Identification of mosquito olfactory receptors",
                        text="Aedes aegypti olfactory receptor paper doi 10.1111/1744-7917.70041",
                        species="Aedes aegypti",
                        url="https://doi.org/10.1111/1744-7917.70041",
                        media_url=None,
                        provenance=Provenance(
                            source_id="aedes_literature_openalex",
                            locator="openalex#W123",
                            retrieved_at="2026-05-25T00:00:00Z",
                        ),
                        payload={"doi": "10.1111/1744-7917.70041"},
                    )
                ]
            )

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                raise AssertionError(url)

            result = ingest_aedes_olfaction_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=20,
                page_size=10,
                include_fulltext=False,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["source"], "aedes_olfaction_literature")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["canonical_literature_row_count"], 1)
            self.assertEqual(result["already_indexed_count"], 1)
            self.assertEqual(result["pubmed_metadata_ingested_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, lane, count(*) as n from records group by source, lane order by source, lane",
                limit=100,
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("aedes_literature_openalex", "literature")], 1)
            self.assertEqual(counts[("aedes_olfaction_literature", "literature")], 2)
            receipt = (artifact_dir / "source_receipt.json").read_text(encoding="utf-8")
            self.assertIn("aedes_olfaction_literature", receipt)
            self.assertIn("already_indexed_count", receipt)

    def test_failed_refresh_preserves_existing_audit_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return ESEARCH
                if "esummary.fcgi" in url:
                    return ESUMMARY
                raise AssertionError(url)

            ingest_aedes_olfaction_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                include_fulltext=False,
            )
            failed = ingest_aedes_olfaction_literature(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-25T01:00:00Z",
                include_fulltext=False,
            )

            self.assertFalse(failed["ok"])
            self.assertTrue(failed["preserved_existing"])
            self.assertEqual(failed["record_count"], 2)

    def test_ingest_writes_legal_olfaction_fulltext_units(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            def fake_fetch_json(url):
                if "esearch.fcgi" in url:
                    return {"esearchresult": {"idlist": ["42063565"], "count": "1"}}
                if "esummary.fcgi" in url:
                    return {
                        "result": {
                            "uids": ["42063565"],
                            "42063565": ESUMMARY["result"]["42063565"],
                        }
                    }
                if "api.unpaywall.org" in url:
                    return {
                        "best_oa_location": {
                            "url_for_xml": "https://example.org/open/aedes-olfaction.xml",
                            "license": "cc-by",
                        }
                    }
                raise AssertionError(url)

            def fake_fetch_bytes(url):
                return (
                    b"<article><body><p>Aedes aegypti olfactory receptors respond to odor.</p>"
                    b"<fig><caption><p>Figure 2. Receptor response map.</p></caption></fig></body></article>",
                    "application/xml",
                )

            result = ingest_aedes_olfaction_literature(
                artifact_dir=artifact_dir,
                fetch_json=fake_fetch_json,
                fetch_bytes=fake_fetch_bytes,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=1,
                page_size=1,
                unpaywall_email="sources@openinsects.org",
                delay_seconds=0,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["open_fulltext_count"], 1)
            self.assertEqual(result["figure_caption_unit_count"], 1)
            rows = SourceIndex(artifact_dir / "source_index.sqlite").sql(
                "select source, text from literature_fulltext_units order by unit_index",
                limit=10,
            )
            self.assertEqual({row["source"] for row in rows}, {"aedes_olfaction_literature"})
            self.assertTrue(any("olfactory receptors respond" in row["text"] for row in rows))
            self.assertTrue(any("Figure 2" in row["text"] for row in rows))


if __name__ == "__main__":
    unittest.main()
