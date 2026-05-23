import json
import unittest

from askinsects.records import EvidenceRecord, Provenance


class RecordTests(unittest.TestCase):
    def test_record_round_trip_preserves_provenance(self):
        record = EvidenceRecord(
            record_id="taxon:aedes_aegypti",
            lane="taxonomy",
            source="mosquito_v1_fixtures",
            title="Aedes aegypti",
            text="Aedes aegypti is a mosquito species.",
            species="Aedes aegypti",
            url="https://example.org/aedes",
            media_url=None,
            provenance=Provenance(
                source_id="mosquito_v1_fixtures",
                locator="data/fixtures/mosquito_records.json#taxon:aedes_aegypti",
                retrieved_at="2026-05-23T00:00:00Z",
                license="CC0",
            ),
        )

        payload = record.to_row()
        self.assertEqual(payload["record_id"], "taxon:aedes_aegypti")
        self.assertEqual(payload["provenance_json"], json.dumps(record.provenance.to_dict(), sort_keys=True))

        restored = EvidenceRecord.from_row(payload)
        self.assertEqual(restored.species, "Aedes aegypti")
        self.assertEqual(restored.provenance.locator, "data/fixtures/mosquito_records.json#taxon:aedes_aegypti")


if __name__ == "__main__":
    unittest.main()
