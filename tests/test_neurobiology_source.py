import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.neurobiology import NEUROBIOLOGY_SOURCE_ID, fetch_neurobiology_records


class NeurobiologySourceTests(unittest.TestCase):
    def test_fetch_neurobiology_records_returns_brain_atoms_with_provenance(self):
        result = fetch_neurobiology_records(retrieved_at="2026-05-23T00:00:00Z")

        self.assertEqual(result.source_id, NEUROBIOLOGY_SOURCE_ID)
        self.assertEqual(result.gaps, [])
        self.assertGreaterEqual(len(result.records), 6)

        lanes = {record.lane for record in result.records}
        self.assertEqual(lanes, {"neurobiology"})

        atlas = next(record for record in result.records if record.record_id == "neuro:mosquitobrains:female-brain-atlas")
        self.assertEqual(atlas.species, "Aedes aegypti")
        self.assertIn("female Aedes aegypti brain", atlas.text)
        self.assertEqual(atlas.provenance.source_id, NEUROBIOLOGY_SOURCE_ID)
        self.assertIn("mosquitobrains.org", atlas.provenance.source_url)
        self.assertEqual(atlas.payload["record_type"], "brain_atlas")

        geo = next(record for record in result.records if record.record_id == "neuro:geo:GSE160740")
        self.assertIn("single-nucleus", geo.text)
        self.assertEqual(geo.payload["accession"], "GSE160740")

    def test_neurobiology_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            result = fetch_neurobiology_records(retrieved_at="2026-05-23T00:00:00Z")

            index.upsert_records(result.records)
            rows = index.sql(
                "select record_id, source, lane, payload_json from record_payloads "
                "where source = 'aedes_neurobiology_sources' order by record_id",
                limit=20,
            )

            self.assertEqual(len(rows), len(result.records))
            self.assertTrue(any(row["record_id"] == "neuro:geo:GSE160740" for row in rows))


if __name__ == "__main__":
    unittest.main()
