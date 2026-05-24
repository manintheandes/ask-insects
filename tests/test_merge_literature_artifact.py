from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit, LITERATURE_SOURCE_ID
from scripts.merge_literature_artifact import merge_literature_artifact


class MergeLiteratureArtifactTests(unittest.TestCase):
    def test_merges_literature_without_removing_existing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "mosquito-v1"
            literature = root / "aedes-literature-2020"
            target.mkdir()
            literature.mkdir()

            target_index = SourceIndex(target / "source_index.sqlite")
            target_index.initialize()
            target_index.upsert_records(
                [
                    EvidenceRecord(
                        record_id="gbif:1",
                        lane="observations",
                        source="gbif_api",
                        title="GBIF observation",
                        text="Aedes aegypti observed",
                        species="Aedes aegypti",
                        url="https://example.org/gbif",
                        media_url=None,
                        provenance=Provenance(
                            source_id="gbif_api",
                            locator=f"{target}/raw/gbif/page.json#1",
                            retrieved_at="2026-05-23T00:00:00Z",
                        ),
                    )
                ]
            )
            (target / "source_status.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "source_id": "gbif_api",
                        "sources": ["gbif_api"],
                        "source_counts": {"gbif_api": 1},
                        "boundary": "mosquitoes first",
                        "generated_at": "2026-05-23T00:00:00Z",
                        "fully_parsed": True,
                        "record_count": 1,
                        "species_count": 1,
                        "lanes": {"observations": 1},
                        "gap_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            (target / "source_receipt.json").write_text(json.dumps({"sources": {"gbif_api": {"record_count": 1}}}), encoding="utf-8")
            (target / "gaps.json").write_text("[]", encoding="utf-8")

            literature_index = SourceIndex(literature / "source_index.sqlite")
            literature_index.initialize()
            lit_record = EvidenceRecord(
                record_id="openalex:W1",
                lane="literature",
                source=LITERATURE_SOURCE_ID,
                title="Aedes aegypti paper",
                text="Aedes aegypti Wolbachia study",
                species="Aedes aegypti",
                url="https://openalex.org/W1",
                media_url=None,
                provenance=Provenance(
                    source_id=LITERATURE_SOURCE_ID,
                    locator=f"{literature}/raw/literature/page.json#W1",
                    retrieved_at="2026-05-24T00:00:00Z",
                ),
                payload={"raw_path": f"{literature}/raw/literature/page.json"},
            )
            unit = FullTextUnit(
                unit_id="openalex:W1:fulltext:0",
                record_id="openalex:W1",
                source=LITERATURE_SOURCE_ID,
                unit_index=0,
                text="full text chunk about Aedes aegypti",
                url="https://example.org/fulltext",
                license="cc-by",
                provenance=lit_record.provenance,
            )
            literature_index.upsert_records_and_fulltext_units([lit_record], [unit])
            (literature / "raw" / "literature").mkdir(parents=True)
            (literature / "raw" / "literature" / "page.json").write_text("{}", encoding="utf-8")
            (literature / "source_status.json").write_text(
                json.dumps(
                    {
                        "sources": [LITERATURE_SOURCE_ID],
                        "source_counts": {LITERATURE_SOURCE_ID: 1},
                        "record_count": 1,
                        "gap_count": 1,
                        "literature": {"record_count": 1, "source": LITERATURE_SOURCE_ID},
                    }
                ),
                encoding="utf-8",
            )
            (literature / "source_receipt.json").write_text(
                json.dumps({"literature": {"record_count": 1, "raw_artifacts": [f"{literature}/raw/literature/page.json"]}}),
                encoding="utf-8",
            )
            (literature / "literature_enrichment_receipt.json").write_text(
                json.dumps({"latest": {"artifact_dir": str(literature)}}),
                encoding="utf-8",
            )
            (literature / "gaps.json").write_text(
                json.dumps([{"source": LITERATURE_SOURCE_ID, "raw_path": f"{literature}/raw/literature/page.json"}]),
                encoding="utf-8",
            )

            result = merge_literature_artifact(target, literature)

            self.assertTrue(result["ok"])
            index = SourceIndex(target / "source_index.sqlite")
            counts = index.sql("select source, count(*) as n from records group by source order by source")
            self.assertEqual(counts, [{"source": LITERATURE_SOURCE_ID, "n": 1}, {"source": "gbif_api", "n": 1}])
            self.assertEqual(index.search("Wolbachia", lane="literature", limit=5)[0].record_id, "openalex:W1")
            self.assertEqual(
                index.sql("select count(*) as n from literature_fulltext_fts where literature_fulltext_fts match 'aegypti'")[0]["n"],
                1,
            )

            payload = index.sql("select payload_json, provenance_json from record_payloads where record_id='openalex:W1'")[0]
            self.assertIn(target.absolute().as_posix(), payload["payload_json"])
            self.assertIn(target.absolute().as_posix(), payload["provenance_json"])
            self.assertTrue((target / "raw" / "literature" / "page.json").exists())

            status = json.loads((target / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["source_counts"][LITERATURE_SOURCE_ID], 1)
            self.assertIn("gbif_api", status["sources"])
            self.assertIn(LITERATURE_SOURCE_ID, status["sources"])
            gaps = json.loads((target / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(gaps[0]["raw_path"], f"{target.absolute()}/raw/literature/page.json")


if __name__ == "__main__":
    unittest.main()
