import json
import tempfile
import unittest
import io
import zipfile
from pathlib import Path

from PIL import Image

from askinsects.sources.aedes_deep_sources import (
    AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
    AEDES_POPULATION_GENOMICS_SOURCE_ID,
    AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
    AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
    AEDES_WORLDCLIM_SOURCE_ID,
    DEFAULT_COMPENDIUM_API_URL,
    DEFAULT_NCBI_BIOPROJECT_SEARCH_URL,
    DEFAULT_TAXONOMY_SOURCES,
    DEFAULT_WHO_RESISTANCE_SOURCES,
    DEFAULT_WORLDCLIM_BIOCLIM_10M_URL,
    DEFAULT_WORLDCLIM_SOURCES,
    fetch_aedes_deep_source_records,
)


def fake_worldclim_zip() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for filename, value in (("wc2.1_10m_bio_1.tif", 24), ("wc2.1_10m_bio_12.tif", 1432)):
            image_bytes = io.BytesIO()
            Image.new("I", (4, 2), color=value).save(image_bytes, format="TIFF")
            archive.writestr(filename, image_bytes.getvalue())
    return payload.getvalue()


class AedesDeepSourcesTests(unittest.TestCase):
    def test_fetch_aedes_deep_source_records_normalizes_all_five_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_dir = Path(tmpdir)

            def fake_text(url):
                if url == DEFAULT_TAXONOMY_SOURCES[0]["url"]:
                    return "<html><h1>Aedes aegypti factsheet</h1><p>Species name/classification: Aedes (Stegomyia) aegypti. Synonyms and other name in use: Stegomyia aegypti. Hazards associated with mosquito species.</p></html>"
                if url == DEFAULT_TAXONOMY_SOURCES[3]["url"]:
                    return "<html><h1>Taxonomy browser Taxonomy Browser (Aedes aegypti)</h1><p>Taxonomy ID: 7159. Current name Aedes aegypti. Homotypic synonym Stegomyia aegypti. Heterotypic synonym Culex aegypti. Diptera Culicidae Aedes Stegomyia.</p></html>"
                if url == DEFAULT_TAXONOMY_SOURCES[4]["url"]:
                    return "<html><h1>NALT Full</h1><p>Aedes aegypti. Synonyms: Stegomyia aegypti. Broader terms: Aedes, Culicidae, Diptera.</p></html>"
                if url == DEFAULT_WORLDCLIM_SOURCES[0]["url"]:
                    return "<html><h1>Historical climate data</h1><p>WorldClim version 2.1 climate data for 1970-2000. Each download is a zip file containing 12 GeoTiff files, one for each month. Average temperature and precipitation are available.</p></html>"
                if url == DEFAULT_WORLDCLIM_SOURCES[1]["url"]:
                    return "<html><h1>Historical monthly weather data</h1><p>Historical monthly weather data for 1950-2024 includes tmin, tmax, and prec zip files.</p></html>"
                if url == DEFAULT_WHO_RESISTANCE_SOURCES[0]["url"]:
                    return "<html><h1>Monitoring and managing insecticide resistance in Aedes mosquito populations</h1><p>This document summarizes WHO test procedures for detection of insecticide resistance in Aedes larvae and adults including insect growth regulators and Bti products.</p><a href='https://iris.who.int/example-aedes.pdf'>PDF</a></html>"
                if url == DEFAULT_WHO_RESISTANCE_SOURCES[1]["url"]:
                    return "<html><h1>Determining discriminating concentrations</h1><p>WHO established and validated 17 new insecticide discriminating concentrations for Aedes spp. in filter paper and bottle bioassays.</p></html>"
                raise AssertionError(url)

            def fake_json(url):
                if url == DEFAULT_COMPENDIUM_API_URL:
                    return {
                        "metadata": {"title": "Data from: The global compendium of Aedes aegypti and Ae. albopictus occurrence"},
                        "files": [
                            {
                                "key": "aegypti_albopictus.csv",
                                "links": {"self": "https://zenodo.org/api/records/4946792/files/aegypti_albopictus.csv/content"},
                            }
                        ],
                    }
                if url == DEFAULT_NCBI_BIOPROJECT_SEARCH_URL:
                    return {"esearchresult": {"count": "2", "idlist": ["1090933", "985220"]}}
                if "esummary.fcgi" in url:
                    return {
                        "result": {
                            "uids": ["1090933", "985220"],
                            "1090933": {
                                "uid": "1090933",
                                "taxid": 7159,
                                "project_acc": "PRJNA1090933",
                                "project_title": "Aedes aegypti population genomics",
                                "project_description": "Spatial and temporal distribution of genome divergence among Florida and Caribbean populations of Aedes aegypti.",
                                "project_data_type": "Genome sequencing",
                                "project_target_scope": "Multiisolate",
                                "submitter_organization": "University of Florida",
                                "registration_date": "2024/03/22 00:00",
                            },
                            "985220": {
                                "uid": "985220",
                                "project_acc": "PRJNA985220",
                                "project_title": "Florida Aedes aegypti genomes",
                                "project_description": "fine-scale mapping of introgression and insecticide locus duplication trajectories",
                                "project_data_type": "Raw sequence reads",
                                "project_target_scope": "Multispecies",
                                "submitter_organization": "Florida International University",
                                "registration_date": "2023/06/19 00:00",
                            },
                        }
                    }
                raise AssertionError(url)

            def fake_bytes(url):
                if url in {DEFAULT_TAXONOMY_SOURCES[1]["url"], DEFAULT_TAXONOMY_SOURCES[2]["url"]}:
                    return b"%PDF-1.4\n% fake authority PDF for fallback text extraction tests\n"
                if url == DEFAULT_WORLDCLIM_BIOCLIM_10M_URL:
                    return fake_worldclim_zip()
                self.assertIn("aegypti_albopictus.csv", url)
                return (
                    "species,COUNTRY,latitude,longitude,year,status\n"
                    "Aedes aegypti,Brazil,-12.1,-44.2,2014,presence\n"
                    "Aedes albopictus,France,43.2,5.4,2014,presence\n"
                    "Ae. aegypti,Thailand,13.7,100.5,2012,presence\n"
                ).encode("utf-8")

            result = fetch_aedes_deep_source_records(
                raw_dir=raw_dir,
                fetch_text=fake_text,
                fetch_json=fake_json,
                fetch_bytes=fake_bytes,
                retrieved_at="2026-05-25T00:00:00Z",
                compendium_row_limit=10,
                bioproject_limit=5,
                worldclim_sample_limit=2,
            )

        source_ids = {record.source for record in result.records}
        self.assertEqual(
            source_ids,
            {
                AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID,
                AEDES_WORLDCLIM_SOURCE_ID,
                AEDES_GLOBAL_COMPENDIUM_SOURCE_ID,
                AEDES_POPULATION_GENOMICS_SOURCE_ID,
                AEDES_WHO_RESISTANCE_GUIDANCE_SOURCE_ID,
            },
        )
        self.assertEqual(result.gaps, [])
        self.assertEqual(result.source_record_counts[AEDES_TAXONOMY_AUTHORITIES_SOURCE_ID], len(DEFAULT_TAXONOMY_SOURCES))
        self.assertEqual(result.source_record_counts[AEDES_GLOBAL_COMPENDIUM_SOURCE_ID], 2)
        self.assertEqual(result.source_record_counts[AEDES_WORLDCLIM_SOURCE_ID], 4)
        self.assertEqual(result.source_record_counts[AEDES_POPULATION_GENOMICS_SOURCE_ID], 2)
        self.assertTrue(any(record.lane == "taxonomy" and "Stegomyia" in record.text for record in result.records))
        self.assertTrue(any(record.lane == "ecology" and "WorldClim" in record.text for record in result.records))
        self.assertTrue(any(record.record_id.startswith("ecology:worldclim:sample:") and "24.0 deg C" in record.text for record in result.records))
        self.assertTrue(any(record.lane == "observations" and "Brazil" in record.text for record in result.records))
        self.assertTrue(any(record.lane == "genome_features" and "PRJNA1090933" in record.text for record in result.records))
        self.assertTrue(any(record.lane == "resistance" and "WHO" in record.text for record in result.records))
        self.assertGreaterEqual(len(result.raw_artifacts), 6)


if __name__ == "__main__":
    unittest.main()
