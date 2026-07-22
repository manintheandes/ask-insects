import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.anopheles_gbif import (
    ANOPHELES_GBIF_RECORD_PREFIX,
    ANOPHELES_GBIF_SOURCE_ID,
    fetch_anopheles_gbif_records,
)


class FakeAnophelesGBIFFetcher:
    def __call__(self, url):
        if "/v1/species/match" in url:
            return {
                "usageKey": 12345,
                "canonicalName": "Anopheles stephensi",
                "rank": "SPECIES",
                "status": "ACCEPTED",
                "family": "Culicidae",
                "genus": "Anopheles",
                "species": "Anopheles stephensi",
            }
        if "/v1/occurrence/search" in url:
            return {
                "count": 1,
                "results": [
                    {
                        "key": 777,
                        "species": "Anopheles stephensi",
                        "scientificName": "Anopheles stephensi Liston, 1901",
                        "country": "India",
                        "eventDate": "2026-02-03",
                        "datasetName": "Example Anopheles surveillance dataset",
                        "license": "CC_BY_4_0",
                    }
                ],
            }
        raise AssertionError(f"unexpected URL: {url}")


class AnophelesGBIFTests(unittest.TestCase):
    def test_fetches_anopheles_gbif_with_distinct_source_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_anopheles_gbif_records(
                raw_dir=Path(tmpdir) / "raw" / "anopheles_gbif",
                species_names=["Anopheles stephensi"],
                occurrence_limit=1,
                fetch_json=FakeAnophelesGBIFFetcher(),
                retrieved_at="2026-07-22T00:00:00Z",
            )

            self.assertEqual(result.source_id, ANOPHELES_GBIF_SOURCE_ID)
            self.assertEqual(result.taxon_keys["Anopheles stephensi"], 12345)
            self.assertEqual(len(result.records), 2)
            taxonomy = next(record for record in result.records if record.lane == "taxonomy")
            self.assertEqual(taxonomy.record_id, f"{ANOPHELES_GBIF_RECORD_PREFIX}:taxon:12345")
            self.assertEqual(taxonomy.source, ANOPHELES_GBIF_SOURCE_ID)
            self.assertEqual(taxonomy.provenance.source_id, ANOPHELES_GBIF_SOURCE_ID)
            occurrence = next(record for record in result.records if record.lane == "observations")
            self.assertEqual(occurrence.record_id, f"{ANOPHELES_GBIF_RECORD_PREFIX}:occurrence:777")
            self.assertEqual(occurrence.source, ANOPHELES_GBIF_SOURCE_ID)
            self.assertEqual(occurrence.species, "Anopheles stephensi")
            self.assertIn("India", occurrence.text)
            self.assertIn("Anopheles_stephensi_match.json", result.raw_artifacts[0])

    def test_anopheles_gbif_question_prefers_anopheles_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="aedes:taxonomy",
                        lane="taxonomy",
                        source="aedes_taxonomy_authorities",
                        title="Aedes aegypti taxonomy authority",
                        text="Aedes aegypti taxonomy authority record.",
                        species="Aedes aegypti",
                        url=None,
                        media_url=None,
                        provenance=Provenance(source_id="aedes_taxonomy_authorities", locator="aedes#taxonomy", retrieved_at="2026-07-22T00:00:00Z"),
                    ),
                    EvidenceRecord(
                        record_id="anopheles_gbif:taxon:12345",
                        lane="taxonomy",
                        source=ANOPHELES_GBIF_SOURCE_ID,
                        title="Anopheles stephensi",
                        text="GBIF accepted species match for Anopheles stephensi.",
                        species="Anopheles stephensi",
                        url="https://www.gbif.org/species/12345",
                        media_url=None,
                        provenance=Provenance(
                            source_id=ANOPHELES_GBIF_SOURCE_ID,
                            locator="raw/anopheles_gbif/Anopheles_stephensi_match.json#species/match?name=Anopheles stephensi",
                            retrieved_at="2026-07-22T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="anopheles_gbif:occurrence:777",
                        lane="observations",
                        source=ANOPHELES_GBIF_SOURCE_ID,
                        title="Anopheles stephensi occurrence 777",
                        text="GBIF occurrence record for Anopheles stephensi in India, event date 2026-02-03.",
                        species="Anopheles stephensi",
                        url="https://www.gbif.org/occurrence/777",
                        media_url=None,
                        provenance=Provenance(
                            source_id=ANOPHELES_GBIF_SOURCE_ID,
                            locator="raw/anopheles_gbif/Anopheles_stephensi_occurrences_offset_000000.json#occurrence/777",
                            retrieved_at="2026-07-22T00:00:00Z",
                        ),
                    ),
                    EvidenceRecord(
                        record_id="anopheles_gbif:occurrence:888",
                        lane="observations",
                        source=ANOPHELES_GBIF_SOURCE_ID,
                        title="Anopheles stephensi occurrence 888",
                        text="GBIF occurrence record for Anopheles stephensi in Niger, event date 2026-02-04.",
                        species="Anopheles stephensi",
                        url="https://www.gbif.org/occurrence/888",
                        media_url=None,
                        provenance=Provenance(
                            source_id=ANOPHELES_GBIF_SOURCE_ID,
                            locator="raw/anopheles_gbif/Anopheles_stephensi_occurrences_offset_000000.json#occurrence/888",
                            retrieved_at="2026-07-22T00:00:00Z",
                        ),
                    ),
                ]
            )

            occurrence_answer = answer_question("show Anopheles stephensi GBIF occurrence records in India", artifact_dir=artifact_dir)
            self.assertTrue(occurrence_answer["ok"])
            self.assertEqual(occurrence_answer["evidence"][0]["source"], ANOPHELES_GBIF_SOURCE_ID)
            self.assertEqual(occurrence_answer["evidence"][0]["record_id"], "anopheles_gbif:occurrence:777")
            self.assertEqual(len(occurrence_answer["evidence"]), 1)

            taxonomy_answer = answer_question("show Anopheles stephensi taxonomy from GBIF", artifact_dir=artifact_dir)
            self.assertTrue(taxonomy_answer["ok"])
            self.assertEqual(taxonomy_answer["evidence"][0]["source"], ANOPHELES_GBIF_SOURCE_ID)
            self.assertEqual(taxonomy_answer["evidence"][0]["record_id"], "anopheles_gbif:taxon:12345")


if __name__ == "__main__":
    unittest.main()
