import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from askinsects.index import SourceIndex
from askinsects.sources.drosophila_suzukii_deep_sources import (
    DROSOPHILA_SUZUKII_DEEP_SOURCE_ID,
    fetch_drosophila_suzukii_deep_records,
)


def fake_fetch_json(url: str):
    if "db=assembly" in url and "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["1"]}}
    if "db=assembly" in url and "esummary.fcgi" in url:
        return {
            "result": {
                "uids": ["1"],
                "1": {
                    "assemblyaccession": "GCF_013340165.1",
                    "assemblyname": "ASM1334016v1",
                    "organism": "Drosophila suzukii",
                    "assemblystatus": "Chromosome",
                    "bioprojectaccn": "PRJNA1",
                    "biosampleaccn": "SAMN1",
                },
            }
        }
    if "db=bioproject" in url and "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["2"]}}
    if "db=bioproject" in url and "esummary.fcgi" in url:
        return {"result": {"uids": ["2"], "2": {"project_acc": "PRJNA2", "title": "SWD population genomics", "description": "Drosophila suzukii genomes"}}}
    if "db=biosample" in url and "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["3"]}}
    if "db=biosample" in url and "esummary.fcgi" in url:
        return {"result": {"uids": ["3"], "3": {"accession": "SAMN3", "title": "Drosophila suzukii adult sample", "organism": "Drosophila suzukii"}}}
    if "db=sra" in url and "esearch.fcgi" in url:
        return {"esearchresult": {"count": "1", "idlist": ["4"]}}
    if "db=sra" in url and "esummary.fcgi" in url:
        return {
            "result": {
                "uids": ["4"],
                "4": {
                    "Title": "Drosophila suzukii RNA-seq",
                    "Accession": "SRX4",
                    "ExpXml": "<Experiment acc=\"SRX4\"><Title>Drosophila suzukii RNA-seq</Title><Bioproject>PRJNA4</Bioproject><Biosample>SAMN4</Biosample><Platform instrument_model=\"Illumina NovaSeq\"/></Experiment>",
                    "Runs": "<Run acc=\"SRR4\" total_spots=\"100\" total_bases=\"1000\"/>",
                },
            }
        }
    if "rest.uniprot.org/uniprotkb" in url:
        return {"results": [{"primaryAccession": "A0A0S1", "uniProtkbId": "A0A0S1_DROSU", "proteinDescription": {"recommendedName": {"fullName": {"value": "test protein"}}}}]}
    if "rest.uniprot.org/proteomes" in url:
        return {"results": [{"id": "UP000000001", "taxonomy": {"scientificName": "Drosophila suzukii"}}]}
    if "zenodo.org/api/records" in url:
        return {
            "hits": {
                "hits": [
                    {
                        "id": 10,
                        "metadata": {"title": "Drosophila suzukii behavior video", "description": "tracking videos"},
                        "links": {"html": "https://zenodo.org/records/10"},
                        "files": [{"key": "swd.mp4", "links": {"self": "https://zenodo.org/api/files/swd.mp4"}, "size": 10}],
                    }
                ]
            }
        }
    if "api.figshare.com/v2/articles/search" in url:
        return [{"id": 20, "title": "Drosophila suzukii movie"}]
    if "api.figshare.com/v2/articles/20" in url:
        return {
            "id": 20,
            "title": "Drosophila suzukii movie",
            "description": "video data",
            "url_public_html": "https://figshare.com/articles/20",
            "files": [{"id": 21, "name": "swd.mov", "download_url": "https://figshare.com/ndownloader/files/21", "size": 20}],
        }
    if "datadryad.org/api/v2/search" in url:
        return {"_embedded": {"stash:datasets": [{"identifier": "doi:10.5061/test", "title": "Drosophila suzukii behavior data", "abstract": "Drosophila suzukii", "sharingLink": "https://datadryad.org/stash/dataset/doi:10.5061/test"}]}}
    raise AssertionError(f"unexpected URL: {url}")


def fake_fetch_json_no_video(url: str):
    if "zenodo.org/api/records" in url:
        return {"hits": {"hits": []}}
    if "api.figshare.com/v2/articles/search" in url:
        return []
    return fake_fetch_json(url)


class DrosophilaSuzukiiDeepSourceTests(unittest.TestCase):
    def test_fetch_builds_deep_source_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_deep_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii_deep_sources",
                retrieved_at="2026-05-28T00:00:00Z",
                fetch_json=fake_fetch_json,
                ncbi_limit=1,
                protein_limit=1,
                proteome_limit=1,
                repository_limit=1,
            )

            self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_DEEP_SOURCE_ID)
            lanes = {record.lane for record in result.records}
            self.assertIn("genome_assemblies", lanes)
            self.assertIn("genome_features", lanes)
            self.assertIn("biosamples", lanes)
            self.assertIn("expression", lanes)
            self.assertIn("proteins", lanes)
            self.assertIn("media", lanes)
            self.assertIn("behavior", lanes)
            self.assertIn("resistance", lanes)
            self.assertTrue(all(record.source == DROSOPHILA_SUZUKII_DEEP_SOURCE_ID for record in result.records))
            self.assertTrue(result.raw_artifacts)
            requested = "\n".join(unquote(url).replace("+", " ") for url in result.requested_urls)
            self.assertIn("Drosophila suzukii oviposition", requested)
            self.assertIn("spotted wing drosophila video", requested)

    def test_deep_records_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_deep_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii_deep_sources",
                retrieved_at="2026-05-28T00:00:00Z",
                fetch_json=fake_fetch_json,
                ncbi_limit=1,
                protein_limit=1,
                proteome_limit=1,
                repository_limit=1,
            )
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)

            rows = index.search("Drosophila suzukii SRA", lane="expression", limit=5)

            self.assertTrue(rows)
            self.assertEqual(rows[0].source, DROSOPHILA_SUZUKII_DEEP_SOURCE_ID)

    def test_missing_repository_videos_are_explicit_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_deep_records(
                raw_dir=Path(tmpdir) / "raw" / "drosophila_suzukii_deep_sources",
                retrieved_at="2026-05-28T00:00:00Z",
                fetch_json=fake_fetch_json_no_video,
                ncbi_limit=1,
                protein_limit=1,
                proteome_limit=1,
                repository_limit=1,
            )

            reasons = {str(gap.get("reason")) for gap in result.gaps}
            self.assertIn("zenodo_no_queryable_video_files", reasons)
            self.assertIn("figshare_no_queryable_video_files", reasons)


if __name__ == "__main__":
    unittest.main()
