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
        self.assertIn("raw_sra_reanalysis_not_performed", {gap["reason"] for gap in result.gaps})
        self.assertGreaterEqual(len(result.raw_artifacts), 4)
        record_ids = {record.record_id for record in result.records}
        self.assertIn("expression:geo:GSE999999", record_ids)
        self.assertIn("expression:sra_run:SRR999001", record_ids)
        self.assertIn("expression:gap:raw_sra_reanalysis_not_performed", record_ids)
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

    def test_fetch_expression_omics_records_emits_queryable_analysis_scope_gaps(self):
        def fake_fetch_json(url):
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
            )

        gap_records = [record for record in result.records if record.record_id.startswith("expression:gap:")]
        self.assertGreaterEqual(len(gap_records), 2)
        self.assertTrue(any("count matrices" in record.text for record in gap_records))
        self.assertTrue(any("differential-expression outputs" in record.text for record in gap_records))
        self.assertTrue(all(record.payload["atom_type"] == "source_gap" for record in gap_records))

    def test_fetch_expression_omics_records_reports_empty_result_gaps(self):
        def fake_fetch_json(url):
            return {"esearchresult": {"idlist": [], "count": "0"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        self.assertFalse([record for record in result.records if not record.record_id.startswith("expression:gap:")])
        self.assertTrue(any(record.record_id == "expression:gap:raw_sra_reanalysis_not_performed" for record in result.records))
        self.assertTrue({"expression_omics_no_geo_results", "expression_omics_no_sra_results"}.issubset({gap["reason"] for gap in result.gaps}))

    def test_fetch_expression_omics_records_does_not_add_empty_gap_after_search_failure(self):
        def fake_fetch_json(url):
            if "db=gds" in url:
                raise RuntimeError("ncbi unavailable")
            return {"esearchresult": {"idlist": [], "count": "0"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-24T00:00:00Z",
            )

        gds_reasons = {gap["reason"] for gap in result.gaps if gap.get("db") == "gds"}
        self.assertEqual(gds_reasons, {"expression_omics_search_failed"})

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

    def test_fetch_expression_omics_records_paginates_search_and_batches_summaries(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "db=gds" in url and "esearch.fcgi" in url:
                if "retstart=0" in url:
                    return {"esearchresult": {"idlist": ["2001", "2002"], "count": "5"}}
                if "retstart=2" in url:
                    return {"esearchresult": {"idlist": ["2003", "2004"], "count": "5"}}
                if "retstart=4" in url:
                    return {"esearchresult": {"idlist": ["2005"], "count": "5"}}
            if "db=gds" in url and "esummary.fcgi" in url:
                ids = url.split("id=", 1)[1].split("&", 1)[0].split("%2C")
                return {
                    "result": {
                        "uids": ids,
                        **{
                            uid: {
                                "Accession": f"GSE{uid}",
                                "title": f"Aedes aegypti expression dataset {uid}",
                                "summary": "Paged expression metadata.",
                                "taxon": "Aedes aegypti",
                                "gdsType": "Expression profiling by high throughput sequencing",
                            }
                            for uid in ids
                        },
                    }
                }
            if "db=sra" in url and "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": [], "count": "0"}}
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_expression_omics_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                geo_limit=5,
                sra_limit=0,
                search_page_size=2,
                summary_batch_size=2,
            )

        data_records = [record for record in result.records if not record.record_id.startswith("expression:gap:")]
        self.assertEqual(len(data_records), 5)
        self.assertEqual({record.payload["accession"] for record in data_records}, {"GSE2001", "GSE2002", "GSE2003", "GSE2004", "GSE2005"})
        self.assertTrue(any("retstart=2" in call for call in calls))
        self.assertTrue(any("retstart=4" in call for call in calls))
        summary_calls = [call for call in calls if "db=gds" in call and "esummary.fcgi" in call]
        self.assertEqual(len(summary_calls), 3)
        self.assertTrue(any("id=2005" in call for call in summary_calls))


if __name__ == "__main__":
    unittest.main()
