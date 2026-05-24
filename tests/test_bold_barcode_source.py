import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.bold_barcodes import BOLD_SOURCE_ID, fetch_bold_barcode_records


FAKE_BOLD_TSV = """processid\tsampleid\trecordID\tcatalognum\tfieldnum\tinstitution_storing\tbin_uri\tphylum_taxID\tphylum_name\tclass_taxID\tclass_name\torder_taxID\torder_name\tfamily_taxID\tfamily_name\tsubfamily_taxID\tsubfamily_name\tgenus_taxID\tgenus_name\tspecies_taxID\tspecies_name\tsubspecies_taxID\tsubspecies_name\tidentification_provided_by\tvoucher_type\ttissue_type\tcollectors\tcollectiondate\tlifestage\tsex\treproduction\textrainfo\tnotes\tlat\tlon\tcoord_source\tcoord_accuracy\tcountry\tprovince\tregion\texactsite\tsequenceID\tmarkercode\tgenbank_accession\tnucleotides\t\nimage_ids\timage_urls\tcopyright_licenses\ttrace_ids\ttrace_links\trun_dates\tsequencing_centers\tdirections\tseq_primers\tmarker_codes\nBOLD1\tS1\tR1\tC1\t\tMuseum\tBOLD:AAA1111\t20\tArthropoda\t82\tInsecta\t127\tDiptera\t1730\tCulicidae\t2142\tCulicinae\t6438\tAedes\t14137\tAedes aegypti\t\t\tExpert\t\t\tCollector\t2020-01-01\tAdult\tF\t\t\t\t1.0\t2.0\tGPS\t\tBrazil\tRio de Janeiro\t\tSite\tSEQ1\tCOI-5P\tMN000001\tATGCATGC\nBOLD2\tS2\tR2\tC2\t\tMuseum\t\t20\tArthropoda\t82\tInsecta\t127\tDiptera\t1730\tCulicidae\t2142\tCulicinae\t6438\tAedes\t14137\tAedes aegypti\t\t\tExpert\t\t\tCollector\t2020-01-02\tAdult\tM\t\t\t\t3.0\t4.0\tGPS\t\tKenya\t\t\tSite\tSEQ2\tCOI-5P\t\tATGC\n"""


class BoldBarcodeSourceTests(unittest.TestCase):
    def test_fetch_bold_barcode_records_normalizes_public_tsv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_bold_barcode_records(
                species="Aedes aegypti",
                raw_dir=Path(tmpdir) / "raw" / "bold",
                limit=1,
                fetch_text=lambda url: FAKE_BOLD_TSV,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            self.assertEqual(result.source_id, BOLD_SOURCE_ID)
            self.assertEqual(result.fetched_row_count, 2)
            self.assertEqual(len(result.records), 1)
            self.assertTrue(any(gap["reason"] == "bold_limit_applied" for gap in result.gaps))
            record = result.records[0]
            self.assertEqual(record.record_id, "bold:barcode:BOLD1")
            self.assertEqual(record.lane, "dna_barcodes")
            self.assertEqual(record.source, BOLD_SOURCE_ID)
            self.assertEqual(record.species, "Aedes aegypti")
            self.assertIn("COI-5P", record.text)
            self.assertEqual(record.payload["sequence_length"], 8)
            self.assertEqual(record.payload["country"], "Brazil")
            self.assertTrue(result.raw_artifacts)

    def test_bold_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_bold_barcode_records(
                species="Aedes aegypti",
                raw_dir=Path(tmpdir) / "raw" / "bold",
                limit=2,
                fetch_text=lambda url: FAKE_BOLD_TSV,
                retrieved_at="2026-05-24T00:00:00Z",
            )
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)

            rows = index.sql(
                """
                select record_id, json_extract(payload_json, '$.marker_code') as marker
                from record_payloads
                where source='bold_api'
                order by record_id
                """
            )

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["marker"], "COI-5P")

    def test_duplicate_process_ids_still_become_distinct_records(self):
        duplicate_tsv = FAKE_BOLD_TSV + (
            "BOLD1\tS3\tR3\tC3\t\tMuseum\t\t20\tArthropoda\t82\tInsecta\t127\tDiptera\t1730\tCulicidae\t2142\tCulicinae\t6438\tAedes\t14137\tAedes aegypti\t\t\tExpert\t\t\tCollector\t2020-01-03\tAdult\tF\t\t\t\t5.0\t6.0\tGPS\t\tMexico\t\t\tSite\tSEQ3\tITS2\t\tATGC\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_bold_barcode_records(
                species="Aedes aegypti",
                raw_dir=Path(tmpdir) / "raw" / "bold",
                limit=10,
                fetch_text=lambda url: duplicate_tsv,
                retrieved_at="2026-05-24T00:00:00Z",
            )

            record_ids = [record.record_id for record in result.records]

            self.assertEqual(len(record_ids), 3)
            self.assertEqual(len(set(record_ids)), 3)
            self.assertTrue(any(record_id.startswith("bold:barcode:BOLD1:row:") for record_id in record_ids))


if __name__ == "__main__":
    unittest.main()
