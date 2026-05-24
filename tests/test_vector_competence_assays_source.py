from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit
from askinsects.sources.vector_competence_assays import (
    VECTOR_COMPETENCE_ASSAY_SOURCE_ID,
    build_vector_competence_assay_records,
)


def write_assay_literature_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    literature = EvidenceRecord(
        record_id="openalex:WVC1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Vector competence of Aedes aegypti for Zika virus",
        text="Aedes aegypti vector competence study with oral infection.",
        species="Aedes aegypti",
        url="https://example.org/vector-competence",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WVC1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="open metadata",
            source_url="https://example.org/vector-competence",
        ),
    )
    unit = FullTextUnit(
        unit_id="openalex:WVC1:fulltext:0",
        record_id="openalex:WVC1",
        source="aedes_literature_openalex",
        unit_index=0,
        text=(
            "Aedes aegypti mosquitoes were orally infected with ZIKV at 10^6 PFU in an artificial blood meal. "
            "At 28 C and 14 days post infection, midgut infection rate, dissemination rate in legs and wings, "
            "and transmission rate based on saliva samples were measured in the field population."
        ),
        url="https://example.org/vector-competence/fulltext",
        license="CC-BY",
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/fulltext/WVC1.txt#chunk/0",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/vector-competence/fulltext",
        ),
    )
    index.upsert_records_and_fulltext_units([literature], [unit])


class VectorCompetenceAssaySourceTests(unittest.TestCase):
    def test_build_vector_competence_assay_records_extracts_structured_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_assay_literature_fixture(artifact_dir)

            result = build_vector_competence_assay_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
            self.assertEqual(result.candidate_count, 1)
            self.assertEqual(result.source_record_count, 1)
            self.assertEqual(result.fulltext_unit_count, 1)
            record = result.records[0]
            self.assertEqual(record.source, VECTOR_COMPETENCE_ASSAY_SOURCE_ID)
            self.assertEqual(record.lane, "vector_competence")
            self.assertIn("Zika virus", record.title)
            self.assertIn("infection", record.payload["assay_fields"])
            self.assertIn("dissemination", record.payload["assay_fields"])
            self.assertIn("transmission", record.payload["assay_fields"])
            self.assertIn("dose", record.payload["assay_fields"])
            self.assertIn("temperature", record.payload["assay_fields"])
            self.assertIn("literature_fulltext_units#openalex:WVC1:fulltext:0", record.provenance.locator)

    def test_build_vector_competence_assay_records_records_gap_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_vector_competence_assay_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], VECTOR_COMPETENCE_ASSAY_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
