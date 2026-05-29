from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_ensembl_metazoa_orthology import (
    DMEL_HOMOLOG_FILE,
    DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
    GENEID_XREF_FILE,
    GENE_ARCHIVE_FILE,
    GENE_MAIN_FILE,
    MAPPING_SESSION_FILE,
    STABLE_ID_EVENT_FILE,
    fetch_drosophila_suzukii_ensembl_metazoa_orthology_records,
)


def _gz(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


class DrosophilaSuzukiiEnsemblMetazoaOrthologySourceTests(unittest.TestCase):
    def test_fetch_builds_current_gene_homolog_xref_and_history_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)

            def fetch(url: str, max_bytes: int) -> bytes:
                filename = url.rsplit("/", 1)[-1]
                if filename == GENE_MAIN_FILE:
                    return _gz(
                        "2\tprotein_coding\t\\N\t56.44\tEnsembl Metazoa\tGeneID_108018010\tDpit47\tRefSeq\t16534757\tDNA polymerase interacting tpr containing protein of 47kD\tNC_089020.1\t-1\t16533445\t1\t\\N\t1\t1\t1\n"
                    )
                if filename == GENEID_XREF_FILE:
                    return _gz("2\t\\N\t108018010\t108018010\n")
                if filename == DMEL_HOMOLOG_FILE:
                    return _gz("2R\t2\t6662118\t6660645\tortholog_one2one\tmelanogaster group\t91.1616\t100\tFBgn0266518\tFBpp0085479\tXP_016940857.2\tDpit47\t91.1616\t1\n")
                if filename in {GENE_ARCHIVE_FILE, STABLE_ID_EVENT_FILE, MAPPING_SESSION_FILE}:
                    return _gz("")
                raise AssertionError(url)

            result = fetch_drosophila_suzukii_ensembl_metazoa_orthology_records(
                artifact_dir=artifact_dir,
                fetch_bytes=fetch,
                retrieved_at="2026-05-29T00:00:00Z",
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID)
        self.assertEqual(result.current_gene_count, 1)
        self.assertEqual(result.geneid_xref_count, 1)
        self.assertEqual(result.dmel_homolog_count, 1)
        self.assertEqual(result.stable_id_event_count, 0)
        self.assertEqual(result.gene_archive_count, 0)
        self.assertEqual(result.homolog_relationship_counts, {"ortholog_one2one": 1})
        self.assertEqual(
            {record.payload["atom_type"] for record in result.records},
            {
                "ensembl_metazoa_current_gene",
                "ensembl_metazoa_geneid_xref",
                "ensembl_metazoa_dmel_homolog",
                "ensembl_metazoa_stable_id_history_gap",
            },
        )
        self.assertEqual({gap["reason"] for gap in result.gaps}, {"swd_ensembl_metazoa_stable_id_event_empty", "swd_ensembl_metazoa_gene_archive_empty"})
        self.assertEqual(len([record for record in result.records if record.payload["atom_type"] == "ensembl_metazoa_stable_id_history_gap"]), 2)
        homolog = [record for record in result.records if record.payload["atom_type"] == "ensembl_metazoa_dmel_homolog"][0]
        self.assertIn("FBgn0266518", homolog.text)
        self.assertEqual(homolog.payload["relationship"], "ortholog_one2one")

    def test_download_failure_becomes_fatal_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_drosophila_suzukii_ensembl_metazoa_orthology_records(
                artifact_dir=Path(tmp),
                fetch_bytes=lambda url, max_bytes: (_ for _ in ()).throw(RuntimeError("boom")),
                retrieved_at="2026-05-29T00:00:00Z",
            )
        self.assertEqual(result.records, [])
        self.assertGreaterEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0]["reason"], "swd_ensembl_metazoa_download_failed")


if __name__ == "__main__":
    unittest.main()
