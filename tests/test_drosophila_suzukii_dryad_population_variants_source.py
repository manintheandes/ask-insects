import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_dryad_population_variants import (
    DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
    fetch_drosophila_suzukii_dryad_population_variants_records,
)


class DrosophilaSuzukiiDryadPopulationVariantsSourceTests(unittest.TestCase):
    def test_fetch_builds_manifest_and_gap_records(self):
        def fake_fetch(url: str):
            if "/datasets/" in url:
                return {
                    "identifier": "doi:10.25338/B89P86",
                    "id": 64736,
                    "storageSize": 18752579970,
                    "title": "Population structure of Drosophila suzukii and signals of multiple invasions",
                    "abstract": "We sequenced whole genomes of 237 individual flies.",
                    "methods": "Illumina sequencing libraries were prepared.",
                    "license": "https://spdx.org/licenses/CC0-1.0.html",
                    "_links": {"stash:version": {"href": "/api/v2/versions/110476"}},
                }
            if "/versions/110476/files" in url:
                return {
                    "count": 2,
                    "total": 2,
                    "_embedded": {
                        "stash:files": [
                            {
                                "id": 620084,
                                "path": "README",
                                "size": 95,
                                "digest": "readme-sha",
                                "digestType": "sha-256",
                                "_links": {"stash:download": {"href": "/api/v2/files/620084/download"}},
                            },
                            {
                                "id": 620083,
                                "path": "SNPs-q30-original-SWD.vcf.gz",
                                "size": 18752495016,
                                "mimeType": "text/vcard",
                                "digest": "2b8328db94a71e66b89e67e62a9d9b88407e0d4f705e87ff26be05c6379675a2",
                                "digestType": "sha-256",
                                "_links": {"stash:download": {"href": "/api/v2/files/620083/download"}},
                            },
                        ]
                    },
                }
            if "/versions/110476" in url:
                return {"id": 110476, "versionNumber": 1}
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_dryad_population_variants_records(
                raw_dir=Path(tmpdir),
                retrieved_at="2026-05-29T00:00:00Z",
                fetch_json=fake_fetch,
                max_mirror_bytes=1_000_000_000,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID)
        self.assertEqual(result.file_count, 2)
        self.assertEqual(result.gaps, [])
        self.assertEqual(result.records[0].payload["atom_type"], "dryad_variant_dataset")
        reasons = {record.payload.get("reason") for record in result.records if record.payload.get("atom_type") == "source_gap"}
        self.assertIn("dryad_variant_file_too_large", reasons)
        self.assertIn("dryad_variant_rows_not_mirrored", reasons)
        self.assertIn("dryad_variant_header_not_indexed", reasons)
        self.assertIn("dryad_variant_checksum_unverified", reasons)
        vcf = [record for record in result.records if record.payload.get("atom_type") == "dryad_variant_file_manifest" and record.payload.get("is_vcf")][0]
        self.assertEqual(vcf.payload["byte_size"], 18752495016)
        self.assertIn("#files/2", vcf.provenance.locator)


if __name__ == "__main__":
    unittest.main()
