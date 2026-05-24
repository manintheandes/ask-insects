from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit, LITERATURE_SOURCE_ID
from scripts.relocate_artifact_paths import relocate_artifact_paths


class RelocateArtifactPathsTests(unittest.TestCase):
    def test_rewrites_sqlite_and_top_level_json_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact = root / "mosquito-v1"
            artifact.mkdir()
            old_path = "/tmp/ask-insects-local-rebuild"
            new_path = artifact.as_posix()

            index = SourceIndex(artifact / "source_index.sqlite")
            index.initialize()
            record = EvidenceRecord(
                record_id="openalex:W1",
                lane="literature",
                source=LITERATURE_SOURCE_ID,
                title="Aedes aegypti paper",
                text="Aedes aegypti paper text",
                species="Aedes aegypti",
                url="https://openalex.org/W1",
                media_url=None,
                provenance=Provenance(
                    source_id=LITERATURE_SOURCE_ID,
                    locator=f"{old_path}/raw/literature/page.json#works/W1",
                    retrieved_at="2026-05-23T00:00:00Z",
                ),
                payload={"raw_path": f"{old_path}/raw/literature/page.json"},
            )
            unit = FullTextUnit(
                unit_id="openalex:W1:fulltext:0",
                record_id="openalex:W1",
                source=LITERATURE_SOURCE_ID,
                unit_index=0,
                text="full text",
                url="https://example.org/fulltext",
                license="cc-by",
                provenance=record.provenance,
            )
            index.upsert_records_and_fulltext_units([record], [unit])
            (artifact / "source_status.json").write_text(
                json.dumps({"artifact_dir": old_path, "gaps_path": f"{old_path}/gaps.json"}),
                encoding="utf-8",
            )
            (artifact / "gaps.json").write_text(
                json.dumps([{"raw_path": f"{old_path}/raw/literature/page.json"}]),
                encoding="utf-8",
            )

            result = relocate_artifact_paths(artifact, old_path, new_path)

            self.assertTrue(result["ok"])
            rows = index.sql(
                """
                select r.provenance_json, p.payload_json, p.provenance_json as payload_provenance, f.provenance_json as fulltext_provenance
                from records r
                join record_payloads p using (record_id)
                join literature_fulltext_units f using (record_id)
                where r.record_id='openalex:W1'
                """
            )
            serialized = json.dumps(rows)
            self.assertNotIn(old_path, serialized)
            self.assertIn(new_path, serialized)
            self.assertNotIn(old_path, (artifact / "source_status.json").read_text(encoding="utf-8"))
            self.assertIn(new_path, (artifact / "gaps.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
