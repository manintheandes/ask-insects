from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.prune_literature_gaps import prune_gaps


class PruneLiteratureGapsTests(unittest.TestCase):
    def test_prunes_stale_pubmed_skipped_and_updates_metadata_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            gaps = [
                {"source": "aedes_literature_openalex", "reason": "pubmed_skipped", "record_id": "openalex:W1"},
                {"source": "aedes_literature_openalex", "reason": "pubmed_missing_pmid", "record_id": "openalex:W2"},
                {"source": "aedes_neurobiology_sources", "reason": "connectome_dataset_not_public", "record_id": "neuro:1"},
            ]
            (artifact_dir / "gaps.json").write_text(json.dumps(gaps), encoding="utf-8")
            for name in ("source_status.json", "source_receipt.json"):
                (artifact_dir / name).write_text(
                    json.dumps(
                        {
                            "gap_count": len(gaps),
                            "generated_at": "2026-05-23T00:00:00Z",
                            "literature": {"gap_count": len(gaps), "gaps_path": "old"},
                        }
                    ),
                    encoding="utf-8",
                )

            result = prune_gaps(artifact_dir, {"pubmed_skipped"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["removed"], 1)
            kept = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual([gap["reason"] for gap in kept], ["pubmed_missing_pmid", "connectome_dataset_not_public"])
            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["gap_count"], 2)
            self.assertEqual(status["literature"]["gap_count"], 1)


if __name__ == "__main__":
    unittest.main()
