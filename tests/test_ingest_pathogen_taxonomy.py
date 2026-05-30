import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from scripts.ingest_pathogen_taxonomy import ingest_pathogen_taxonomy
from tests.test_pathogen_taxonomy_source import taxonomy_payload


class IngestPathogenTaxonomyTests(unittest.TestCase):
    def test_ingest_updates_existing_artifact_without_removing_other_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="fixture:taxonomy:aedes",
                        lane="taxonomy",
                        source="mosquito_v1_fixtures",
                        title="Aedes aegypti",
                        text="Aedes aegypti taxonomy fixture.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(
                            source_id="mosquito_v1_fixtures",
                            locator="fixture#taxonomy",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )

            result = ingest_pathogen_taxonomy(
                artifact_dir=artifact_dir,
                fetch_json=lambda url: taxonomy_payload(),
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertTrue(result["ok"])
            queried = SourceIndex(artifact_dir / "source_index.sqlite")
            # Source gaps are now persisted as queryable source_gap records, so
            # exclude them when counting the substantive (non-gap) records.
            non_gap_filter = (
                "record_id not in (select record_id from record_payloads "
                "where json_extract(payload_json, '$.atom_type') = 'source_gap')"
            )
            rows = queried.sql(
                "select source, lane, count(*) as n from records "
                f"where {non_gap_filter} group by source, lane"
            )
            counts = {(row["source"], row["lane"]): row["n"] for row in rows}
            self.assertEqual(counts[("mosquito_v1_fixtures", "taxonomy")], 1)
            self.assertEqual(counts[("aedes_pathogen_taxonomy", "vector_competence")], 2)
            payload_rows = queried.sql(
                "select count(*) as n from record_payloads "
                "where source='aedes_pathogen_taxonomy' "
                "and coalesce(json_extract(payload_json, '$.atom_type'), '') != 'source_gap'"
            )
            self.assertEqual(payload_rows[0]["n"], 2)
            # Gaps are now queryable as source_gap records in the index.
            gap_rows = queried.sql(
                "select count(*) as n from record_payloads "
                "where source='aedes_pathogen_taxonomy' "
                "and json_extract(payload_json, '$.atom_type') = 'source_gap'"
            )
            self.assertEqual(gap_rows[0]["n"], result["gap_count"])


if __name__ == "__main__":
    unittest.main()
