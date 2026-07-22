from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from askinsects.answer import answer_question
from askinsects.sources.anopheles_ncbi_assemblies import fetch_anopheles_ncbi_assemblies
from scripts.ingest_anopheles_ncbi_assemblies import ingest_anopheles_ncbi_assemblies


class AnophelesNCBIAssembliesTests(unittest.TestCase):
    def test_builds_atomic_assembly_record_with_exact_locator(self):
        def fetch_json(url: str):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "2", "idlist": ["123"]}}
            return {"result": {"uids": ["123"], "123": {
                "assemblyaccession": "GCF_000005575.2",
                "assemblyname": "AgamP4",
                "speciesname": "Anopheles gambiae",
                "organism": "Anopheles gambiae (African malaria mosquito)",
                "assemblystatus": "Chromosome",
                "assemblytype": "haploid",
                "biosampleaccn": "SAMN02953639",
                "coverage": "9x",
                "asmreleasedate_refseq": "2014/02/11 00:00",
                "submitterorganization": "VectorBase",
                "refseq_category": "reference genome",
                "contign50": 777000,
                "scaffoldn50": 49300000,
                "gb_bioprojects": [{"bioprojectaccn": "PRJNA168"}],
                "rs_bioprojects": [],
                "propertylist": ["has-chromosome", "reference"],
                "ftppath_refseq": "ftp://example/refseq",
                "ftppath_genbank": "ftp://example/genbank",
                "ftppath_assembly_rpt": "ftp://example/report",
            }}}

        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_anopheles_ncbi_assemblies(
                raw_dir=Path(tmp), target_taxa=["Anopheles gambiae"], limit_per_taxon=1,
                delay_seconds=0, fetch_json=fetch_json, retrieved_at="2026-07-22T00:00:00Z",
            )
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.record_id, "anopheles_ncbi:assembly:GCF_000005575.2")
        self.assertEqual(record.payload["assembly_level"], "Chromosome")
        self.assertEqual(record.payload["bioprojects"], ["PRJNA168"])
        self.assertEqual(record.payload["biosample"], "SAMN02953639")
        self.assertIn("#result/123", record.provenance.locator)
        self.assertEqual(result.reported_total_counts["Anopheles gambiae"], 2)
        self.assertTrue(any(gap["reason"] == "assembly_limit_applied" for gap in result.gaps))

    def test_records_fetch_failure_as_gap(self):
        def fail(_url: str):
            raise RuntimeError("offline")

        with tempfile.TemporaryDirectory() as tmp:
            result = fetch_anopheles_ncbi_assemblies(
                raw_dir=Path(tmp), target_taxa=["Anopheles stephensi"], delay_seconds=0, fetch_json=fail,
            )
        self.assertEqual(result.records, [])
        self.assertTrue(any(gap["reason"] == "assembly_fetch_failed" for gap in result.gaps))

    def test_normal_question_returns_only_requested_species_and_level(self):
        def fetch_json(url: str):
            if "esearch.fcgi" in url:
                species = "Anopheles stephensi" if "stephensi" in url else "Anopheles gambiae"
                uid = "2" if species.endswith("stephensi") else "1"
                return {"esearchresult": {"count": "1", "idlist": [uid]}}
            uid = "2" if "id=2" in url else "1"
            species = "Anopheles stephensi" if uid == "2" else "Anopheles gambiae"
            accession = "GCA_999999999.1" if uid == "2" else "GCF_000005575.2"
            return {"result": {"uids": [uid], uid: {
                "assemblyaccession": accession, "assemblyname": "test", "speciesname": species,
                "organism": species, "assemblystatus": "Chromosome" if uid == "1" else "Scaffold",
                "gb_bioprojects": [], "rs_bioprojects": [], "propertylist": [],
            }}}

        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            outcome = ingest_anopheles_ncbi_assemblies(
                artifact_dir=artifact_dir, target_taxa=["Anopheles gambiae", "Anopheles stephensi"],
                limit_per_taxon=1, delay_seconds=0, fetch_json=fetch_json, retrieved_at="2026-07-22T00:00:00Z",
            )
            self.assertTrue(outcome["ok"])
            answer = answer_question("show chromosome-level Anopheles gambiae assemblies", artifact_dir=artifact_dir)
            missing = answer_question("show chromosome-level Anopheles stephensi assemblies", artifact_dir=artifact_dir)
        self.assertTrue(answer["ok"])
        self.assertIn("GCF_000005575.2", answer["answer"])
        self.assertNotIn("GCA_999999999.1", answer["answer"])
        self.assertFalse(missing["ok"])
        self.assertIn("No indexed chromosome-level", missing["source_gap"]["reason"])


if __name__ == "__main__":
    unittest.main()
