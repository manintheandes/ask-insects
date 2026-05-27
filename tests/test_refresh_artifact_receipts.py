import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.refresh_artifact_receipts import refresh_receipts


class RefreshArtifactReceiptsTests(unittest.TestCase):
    def test_refreshes_counts_from_sqlite_and_records_vectorbase_sequences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            artifact_dir.mkdir()
            with sqlite3.connect(artifact_dir / "source_index.sqlite") as conn:
                conn.executescript(
                    """
                    create table records (
                      record_id text primary key,
                      lane text not null,
                      source text not null,
                      title text not null,
                      text text not null,
                      species text,
                      url text,
                      media_url text,
                      provenance_json text not null
                    );
                    insert into records values ('vectorbase:cds:AAEL000001-RA', 'genome_features', 'vectorbase_aedes_genomics', 'cds', 'cds', 'Aedes aegypti', null, null, '{}');
                    insert into records values ('vectorbase:transcript_sequence:AAEL000001-RA', 'transcripts', 'vectorbase_aedes_genomics', 'tx', 'tx', 'Aedes aegypti', null, null, '{}');
                    insert into records values ('fixture:taxon:aedes', 'taxonomy', 'mosquito_v1_fixtures', 'taxon', 'taxon', 'Aedes aegypti', null, null, '{}');
                    """
                )
            raw_dir = artifact_dir / "raw" / "vectorbase_genomics"
            raw_dir.mkdir(parents=True)
            (raw_dir / "VectorBase-68_AaegyptiLVP_AGWG_AnnotatedCDSs.fasta").write_text(">x\nATG\n", encoding="utf-8")
            stale = {
                "record_count": 1,
                "source_counts": {"vectorbase_aedes_genomics": 1},
                "mosquito_v1_fixtures": {"record_count": 99},
                "sources": {"mosquito_v1_fixtures": {"record_count": 99}},
            }
            (artifact_dir / "source_status.json").write_text(json.dumps(stale), encoding="utf-8")
            (artifact_dir / "source_receipt.json").write_text(json.dumps(stale), encoding="utf-8")
            (artifact_dir / "gaps.json").write_text(
                json.dumps(
                    [
                        {"source": "a", "lane": "x", "reason": "missing", "record_id": "1", "locator": "row/1"},
                        {"source": "a", "lane": "x", "reason": "missing", "record_id": "1", "locator": "row/1"},
                        {"source": "a", "lane": "x", "reason": "missing", "record_id": "2", "locator": "row/2"},
                    ]
                ),
                encoding="utf-8",
            )

            result = refresh_receipts(artifact_dir, include_vectorbase_sequence_refresh=True)

            self.assertTrue(result["ok"])
            self.assertEqual(result["record_count"], 3)
            self.assertEqual(result["deduped_gap_count"], 1)
            self.assertEqual(len(json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))), 2)
            for filename in ("source_status.json", "source_receipt.json"):
                payload = json.loads((artifact_dir / filename).read_text(encoding="utf-8"))
                self.assertEqual(payload["record_count"], 3)
                self.assertEqual(payload["gap_count"], 2)
                self.assertEqual(payload["source_counts"]["vectorbase_aedes_genomics"], 2)
                self.assertEqual(payload["mosquito_v1_fixtures"]["record_count"], 1)
                self.assertEqual(payload["sources"]["mosquito_v1_fixtures"]["record_count"], 1)
                self.assertEqual(payload["vectorbase_genomics"]["record_count"], 2)
                refresh = payload["vectorbase_sequence_atom_refresh"]
                self.assertEqual(refresh["cds_live_count"], 1)
                self.assertEqual(refresh["transcript_sequence_live_count"], 1)

    def test_backfills_missing_literature_fulltext_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            artifact_dir.mkdir()
            payload = {
                "unpaywall": {
                    "is_oa": True,
                    "best_oa_location": {"url_for_pdf": "https://example.org/paper.pdf"},
                }
            }
            with sqlite3.connect(artifact_dir / "source_index.sqlite") as conn:
                conn.executescript(
                    """
                    create table records (
                      record_id text primary key,
                      lane text not null,
                      source text not null,
                      title text not null,
                      text text not null,
                      species text,
                      url text,
                      media_url text,
                      provenance_json text not null
                    );
                    create table record_payloads (
                      record_id text primary key,
                      source text not null,
                      lane text not null,
                      payload_json text not null,
                      provenance_json text not null
                    );
                    create table literature_fulltext_units (
                      record_id text not null,
                      unit_index integer not null,
                      text text not null,
                      source_url text,
                      license text,
                      retrieved_at text,
                      primary key (record_id, unit_index)
                    );
                    insert into records values ('openalex:W1', 'literature', 'aedes_literature_openalex', 'paper', 'paper', 'Aedes aegypti', null, null, '{}');
                    """
                )
                conn.execute(
                    "insert into record_payloads values ('openalex:W1', 'aedes_literature_openalex', 'literature', ?, '{}')",
                    (json.dumps(payload),),
                )
            (artifact_dir / "source_status.json").write_text(json.dumps({}), encoding="utf-8")
            (artifact_dir / "source_receipt.json").write_text(json.dumps({}), encoding="utf-8")
            (artifact_dir / "gaps.json").write_text("[]", encoding="utf-8")

            result = refresh_receipts(artifact_dir)

            self.assertEqual(result["literature_fulltext_gap_backfill_count"], 1)
            gaps = json.loads((artifact_dir / "gaps.json").read_text(encoding="utf-8"))
            self.assertEqual(len(gaps), 1)
            self.assertEqual(gaps[0]["reason"], "fulltext_fetch_failed")
            self.assertEqual(gaps[0]["record_id"], "openalex:W1")


if __name__ == "__main__":
    unittest.main()
