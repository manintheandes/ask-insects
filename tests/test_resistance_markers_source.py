from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit
from askinsects.sources.resistance_markers import (
    RESISTANCE_MARKER_SOURCE_ID,
    build_resistance_marker_records,
)


def write_resistance_marker_fixture(artifact_dir: Path) -> None:
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    index.initialize()
    literature = EvidenceRecord(
        record_id="openalex:WRM1",
        lane="literature",
        source="aedes_literature_openalex",
        title="Pyrethroid resistance and kdr mutations in Aedes aegypti",
        text="Aedes aegypti pyrethroid resistance study measuring V1016G, F1534C and CYP9J32.",
        species="Aedes aegypti",
        url="https://example.org/resistance-marker",
        media_url=None,
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/literature/page.json#WRM1",
            retrieved_at="2026-05-24T00:00:00Z",
            license="open metadata",
            source_url="https://example.org/resistance-marker",
        ),
    )
    unit = FullTextUnit(
        unit_id="openalex:WRM1:fulltext:0",
        record_id="openalex:WRM1",
        source="aedes_literature_openalex",
        unit_index=0,
        text=(
            "Aedes aegypti showed pyrethroid resistance after permethrin bioassay exposure. "
            "The VGSC kdr mutations V1016G and F1534C co-occurred with metabolic resistance "
            "and overexpression of CYP9J32 detoxification genes."
        ),
        url="https://example.org/resistance-marker/fulltext",
        license="CC-BY",
        provenance=Provenance(
            source_id="aedes_literature_openalex",
            locator="raw/fulltext/WRM1.txt#chunk/0",
            retrieved_at="2026-05-24T00:00:00Z",
            license="CC-BY",
            source_url="https://example.org/resistance-marker/fulltext",
        ),
    )
    index.upsert_records_and_fulltext_units([literature], [unit])


class ResistanceMarkerSourceTests(unittest.TestCase):
    def test_build_resistance_marker_records_extracts_kdr_and_metabolic_markers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            write_resistance_marker_fixture(artifact_dir)

            result = build_resistance_marker_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.source_id, RESISTANCE_MARKER_SOURCE_ID)
            marker_ids = {record.payload["marker_id"] for record in result.records}
            self.assertIn("V1016G", marker_ids)
            self.assertIn("F1534C", marker_ids)
            self.assertIn("CYP9J32", marker_ids)
            self.assertGreaterEqual(result.marker_counts["V1016G"], 1)
            record = next(record for record in result.records if record.payload["marker_id"] == "V1016G")
            self.assertEqual(record.source, RESISTANCE_MARKER_SOURCE_ID)
            self.assertEqual(record.lane, "resistance")
            self.assertEqual(record.payload["marker_class"], "target_site")
            self.assertIn("permethrin", record.payload["insecticide_terms"])
            self.assertIn("literature_fulltext_units#openalex:WRM1:fulltext:0", record.provenance.locator)

    def test_build_resistance_marker_records_records_gap_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            SourceIndex(artifact_dir / "source_index.sqlite").initialize()

            result = build_resistance_marker_records(artifact_dir, retrieved_at="2026-05-24T00:00:00Z")

            self.assertEqual(result.records, [])
            self.assertEqual(result.gaps[0]["source"], RESISTANCE_MARKER_SOURCE_ID)


if __name__ == "__main__":
    unittest.main()
