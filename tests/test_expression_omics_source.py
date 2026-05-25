import tempfile
import unittest
from pathlib import Path

from askinsects.sources.expression_omics import fetch_expression_omics_records


GEO_ESEARCH = {"esearchresult": {"idlist": ["200000001"], "count": "1"}}
GEO_ESUMMARY = {
    "result": {
        "uids": ["200000001"],
        "200000001": {
            "Accession": "GSE999999",
            "title": "Aedes aegypti midgut RNA-seq after dengue exposure",
            "summary": "Expression profiling by high throughput sequencing in infected and control midguts.",
            "taxon": "Aedes aegypti",
            "gdsType": "Expression profiling by high throughput sequencing",
            "n_samples": "12",
            "GPL": "GPL24265",
        },
    }
}
SRA_ESEARCH = {"esearchresult": {"idlist": ["44630001"], "count": "1"}}
SRA_ESUMMARY = {
    "result": {
        "uids": ["44630001"],
        "44630001": {
            "Title": "Aedes aegypti ovary transcriptome RNA-Seq",
            "ExpXml": """
                <Summary><Title>Aedes aegypti ovary transcriptome RNA-Seq</Title></Summary>
                <Bioproject>PRJNA999999</Bioproject>
                <Biosample>SAMN999999</Biosample>
                <Platform instrument_model="Illumina NovaSeq 6000">ILLUMINA</Platform>
            """,
            "Runs": '<Run acc="SRR999001" total_spots="1000" total_bases="150000" />',
        },
    }
}
LOWERCASE_GEO_ESUMMARY = {
    "result": {
        "uids": ["200291647"],
        "200291647": {
            "accession": "GSE291647",
            "title": "Aedes aegypti infected midgut RNA-seq",
            "summary": "Live NCBI-style lowercase GEO summary.",
            "taxon": "Aedes aegypti",
            "gdstype": "Expression profiling by high throughput sequencing",
            "n_samples": "8",
            "gpl": "GPL24265",
        },
    }
}
LOWERCASE_SRA_ESUMMARY = {
    "result": {
        "uids": ["44630002"],
        "44630002": {
            "title": "Aedes aegypti live SRA RNA-seq",
            "expxml": """
                <Summary><Title>Aedes aegypti live SRA RNA-seq</Title></Summary>
                <Bioproject>PRJNA888888</Bioproject>
                <Biosample>SAMN888888</Biosample>
                <Experiment acc="SRX888888" />
                <Platform instrument_model="Illumina NovaSeq 6000">ILLUMINA</Platform>
            """,
            "runs": '<Run acc="SRR888001" total_spots="2000" total_bases="300000" />',
        },
    }
}


class ExpressionOmicsSourceTests(unittest.TestCase):
    def test_fetch_expression_omics_records_indexes_geo_and_sra_atoms(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "db=gds" in url and "esearch.fcgi" in url:
                return GEO_ESEARCH
            if "db=gds" in url and "esummary.fcgi" in url:
                return GEO_ESUMMARY
            if "db=sra" in url and "esearch.fcgi" in url:
                return SRA_ESEARCH
            if "db=sra" in url and "esummary.fcgi" in url:
                return SRA_ESUMMARY
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
                geo_limit=5,
                sra_limit=5,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "aedes_expression_omics")
        self.assertEqual(result.gaps, [])
        self.assertEqual(len(result.raw_artifacts), 4)
        record_ids = {record.record_id for record in result.records}
        self.assertIn("expression:geo:GSE999999", record_ids)
        self.assertIn("expression:sra_run:SRR999001", record_ids)
        geo_record = next(record for record in result.records if record.record_id == "expression:geo:GSE999999")
        self.assertEqual(geo_record.lane, "expression")
        self.assertEqual(geo_record.source, "aedes_expression_omics")
        self.assertEqual(geo_record.species, "Aedes aegypti")
        self.assertIn("midgut RNA-seq", geo_record.text)
        self.assertEqual(geo_record.payload["sample_count"], "12")
        run_record = next(record for record in result.records if record.record_id == "expression:sra_run:SRR999001")
        self.assertIn("PRJNA999999", run_record.text)
        self.assertEqual(run_record.payload["run_accession"], "SRR999001")
        self.assertEqual(len(calls), 4)

    def test_fetch_expression_omics_records_reports_empty_result_gaps(self):
        def fake_fetch_json(url):
            return {"esearchresult": {"idlist": [], "count": "0"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertFalse(result.records)
        self.assertEqual({gap["reason"] for gap in result.gaps}, {"expression_omics_no_geo_results", "expression_omics_no_sra_results"})

    def test_fetch_expression_omics_records_accepts_live_lowercase_esummary_keys(self):
        def fake_fetch_json(url):
            if "db=gds" in url and "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["200291647"], "count": "2"}}
            if "db=gds" in url and "esummary.fcgi" in url:
                return LOWERCASE_GEO_ESUMMARY
            if "db=sra" in url and "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["44630002"], "count": "1"}}
            if "db=sra" in url and "esummary.fcgi" in url:
                return LOWERCASE_SRA_ESUMMARY
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
                geo_limit=1,
                sra_limit=1,
            )

        record_ids = {record.record_id for record in result.records}
        self.assertIn("expression:geo:GSE291647", record_ids)
        self.assertIn("expression:sra_run:SRR888001", record_ids)
        geo = next(record for record in result.records if record.record_id == "expression:geo:GSE291647")
        self.assertIn("acc=GSE291647", geo.url)
        self.assertEqual(geo.payload["platform"], "GPL24265")
        self.assertIn("expression_omics_limit_applied", {gap["reason"] for gap in result.gaps})

    def test_fetch_expression_omics_records_gaps_sra_without_run_accessions(self):
        def fake_fetch_json(url):
            if "db=gds" in url and "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": [], "count": "0"}}
            if "db=sra" in url and "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["44630003"], "count": "1"}}
            if "db=sra" in url and "esummary.fcgi" in url:
                return {"result": {"uids": ["44630003"], "44630003": {"title": "No runs", "expxml": "<Experiment acc=\"SRX1\" />"}}}
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertNotIn("expression:sra_run:44630003", {record.record_id for record in result.records})
        self.assertIn("expression_omics_sra_runs_missing", {gap["reason"] for gap in result.gaps})


if __name__ == "__main__":
    unittest.main()
