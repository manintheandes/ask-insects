import tempfile
import unittest
from pathlib import Path

from askinsects.sources.aedes_olfaction_literature import fetch_aedes_olfaction_literature_records


ESEARCH = {"esearchresult": {"idlist": ["42063565", "40197710"], "count": "2"}}
ESUMMARY = {
    "result": {
        "uids": ["42063565", "40197710"],
        "42063565": {
            "uid": "42063565",
            "title": "Cyphers and cycles - A chemical basis for mosquito attraction",
            "fulljournalname": "iScience",
            "pubdate": "2026 Jan 16",
            "authors": [{"name": "Example A"}, {"name": "Example B"}],
            "articleids": [{"idtype": "doi", "value": "10.1016/j.isci.2026.115575"}],
        },
        "40197710": {
            "uid": "40197710",
            "title": "Identification of mosquito olfactory receptors",
            "source": "Insect Sci",
            "pubdate": "2025 Apr",
            "authors": [{"name": "Example C"}],
            "articleids": [{"idtype": "doi", "value": "10.1111/1744-7917.70041"}],
        },
    }
}


class AedesOlfactionLiteratureSourceTests(unittest.TestCase):
    def test_fetch_builds_pubmed_audit_records_with_coverage_status(self):
        calls = []

        def fake_fetch_json(url):
            calls.append(url)
            if "esearch.fcgi" in url:
                return ESEARCH
            if "esummary.fcgi" in url:
                return ESUMMARY
            raise AssertionError(url)

        existing_rows = [
            {
                "record_id": "literature:openalex:W123",
                "source": "aedes_literature_openalex",
                "title": "Identification of mosquito olfactory receptors",
                "url": "https://doi.org/10.1111/1744-7917.70041",
                "payload": {"doi": "10.1111/1744-7917.70041"},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_olfaction_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                existing_literature_rows=existing_rows,
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=20,
                page_size=10,
                include_fulltext=False,
            )
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

        self.assertEqual(result.source_id, "aedes_olfaction_literature")
        self.assertEqual(result.reported_total_count, 2)
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.canonical_literature_row_count, 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.gaps, [])
        statuses = {record.payload["pmid"]: record.payload["coverage_status"] for record in result.records}
        self.assertEqual(statuses["40197710"], "already_indexed")
        self.assertEqual(statuses["42063565"], "pubmed_metadata_ingested")
        missing = next(record for record in result.records if record.payload["pmid"] == "42063565")
        self.assertEqual(missing.record_id, "aedes_olfaction_literature:pubmed:42063565")
        self.assertEqual(missing.lane, "literature")
        self.assertEqual(missing.source, "aedes_olfaction_literature")
        self.assertEqual(missing.species, "Aedes aegypti")
        self.assertIn("coverage_status=pubmed_metadata_ingested", missing.text)
        self.assertIn("pubmed_esummary_0001.json#result/42063565", missing.provenance.locator)
        self.assertEqual(len(calls), 2)

    def test_fetch_reports_limit_applied_gap(self):
        def fake_fetch_json(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["1"], "count": "3"}}
            return {"result": {"uids": ["1"], "1": {"title": "Aedes aegypti olfactory test", "pubdate": "2025"}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_olfaction_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=1,
                page_size=1,
                include_fulltext=False,
            )

        self.assertIn("aedes_olfaction_result_limit_applied", {gap["reason"] for gap in result.gaps})
        self.assertIn("aedes_olfaction_no_canonical_literature_rows", {gap["reason"] for gap in result.gaps})

    def test_fetch_ingests_legal_open_fulltext_and_figure_captions(self):
        def fake_fetch_json(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["42063565"], "count": "1"}}
            if "esummary.fcgi" in url:
                return {
                    "result": {
                        "uids": ["42063565"],
                        "42063565": ESUMMARY["result"]["42063565"],
                    }
                }
            if "api.unpaywall.org" in url:
                return {
                    "doi": "10.1016/j.isci.2026.115575",
                    "best_oa_location": {
                        "url_for_xml": "https://example.org/open/aedes-olfaction.xml",
                        "license": "cc-by",
                    },
                }
            raise AssertionError(url)

        def fake_fetch_bytes(url):
            self.assertEqual(url, "https://example.org/open/aedes-olfaction.xml")
            return (
                b"""
                <article><body>
                  <sec><title>Results</title><p>Aedes aegypti Orco neurons encode host odor blends.</p></sec>
                  <fig id="f1"><caption><p>Figure 1. Antennal lobe response to human odor.</p></caption></fig>
                </body></article>
                """,
                "application/xml",
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_olfaction_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                fetch_bytes=fake_fetch_bytes,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=1,
                page_size=1,
                unpaywall_email="sources@openinsects.org",
                delay_seconds=0,
            )

        self.assertEqual(result.open_fulltext_count, 1)
        self.assertEqual(result.unpaywall_queried_count, 1)
        self.assertGreaterEqual(result.fulltext_unit_count, 2)
        self.assertEqual(result.figure_caption_unit_count, 1)
        record = result.records[0]
        self.assertEqual(record.payload["fulltext_status"], "open_fulltext_ingested")
        self.assertEqual(record.payload["open_fulltext_license"], "cc-by")
        self.assertEqual(result.fulltext_units[0].source, "aedes_olfaction_literature")
        self.assertIn("Orco neurons encode host odor", result.fulltext_units[0].text)
        figure_units = [unit for unit in result.fulltext_units if "figure-caption" in unit.unit_id]
        self.assertEqual(len(figure_units), 1)
        self.assertIn("Antennal lobe response", figure_units[0].text)

    def test_fetch_extracts_figure_captions_from_pdf_text(self):
        def fake_fetch_json(url):
            if "esearch.fcgi" in url:
                return {"esearchresult": {"idlist": ["42063565"], "count": "1"}}
            if "esummary.fcgi" in url:
                return {
                    "result": {
                        "uids": ["42063565"],
                        "42063565": ESUMMARY["result"]["42063565"],
                    }
                }
            if "api.unpaywall.org" in url:
                return {
                    "best_oa_location": {
                        "url_for_pdf": "https://example.org/open/aedes-olfaction.pdf",
                        "license": "cc-by",
                    },
                }
            raise AssertionError(url)

        def fake_fetch_bytes(url):
            return (b"%PDF-1.4 fake", "application/pdf")

        def fake_pdf_parser(path):
            return (
                "Aedes aegypti olfactory receptors respond to odor. "
                "Figure 3. Antennal neuron responses to human odor blends across Orco mutants. "
                "References"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_aedes_olfaction_literature_records(
                raw_dir=Path(tmpdir) / "raw",
                fetch_json=fake_fetch_json,
                fetch_bytes=fake_fetch_bytes,
                pdf_parser=fake_pdf_parser,
                retrieved_at="2026-05-25T00:00:00Z",
                max_results=1,
                page_size=1,
                unpaywall_email="sources@openinsects.org",
                delay_seconds=0,
            )

        self.assertEqual(result.open_fulltext_count, 1)
        self.assertEqual(result.figure_caption_unit_count, 1)
        figure_unit = next(unit for unit in result.fulltext_units if "figure-caption" in unit.unit_id)
        self.assertIn("Antennal neuron responses", figure_unit.text)


if __name__ == "__main__":
    unittest.main()
