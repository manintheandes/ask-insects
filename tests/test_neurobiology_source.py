import tempfile
import gzip
import h5py
import io
import json
import struct
import tarfile
import unittest
import zipfile
from pathlib import Path

from askinsects.index import SourceIndex
from askinsects.sources.neurobiology import NEUROBIOLOGY_SOURCE_ID, fetch_neurobiology_records
from askinsects.voxels import read_voxel_value


def write_fake_neurobiology_artifacts(root: Path) -> Path:
    artifact_dir = root / "neurobiology"
    geo_dir = artifact_dir / "geo" / "GSE160740"
    geo_dir.mkdir(parents=True)
    tar_path = geo_dir / "GSE160740_RAW.tar"
    with tarfile.open(tar_path, "w") as tar:
        members = {
            "GSM1_male_barcodes.tsv.gz": "cell-1\ncell-2\n",
            "GSM1_male_features.tsv.gz": "AAEL000001\torco\tGene Expression\nAAEL000002\tdsx\tGene Expression\n",
            "GSM1_male_matrix.mtx.gz": "%%MatrixMarket matrix coordinate integer general\n%\n2 2 3\n1 1 5\n2 1 7\n2 2 9\n",
        }
        for name, text in members.items():
            payload = gzip.compress(text.encode("utf-8"))
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

    zenodo_dir = artifact_dir / "zenodo" / "14890013"
    zenodo_dir.mkdir(parents=True)
    (zenodo_dir / "record.json").write_text(
        json.dumps(
            {
                "id": 14890013,
                "metadata": {"title": "Mosquito Cell Atlas", "license": {"id": "cc-by-4.0"}},
                "files": [
                    {
                        "key": "00_README.txt",
                        "size": 42,
                        "checksum": "md5:abc",
                        "links": {"self": "https://zenodo.org/api/records/14890013/files/00_README.txt/content"},
                    },
                    {
                        "key": "09_tables.xlsx",
                        "size": 100,
                        "checksum": "md5:def",
                        "links": {"self": "https://zenodo.org/api/records/14890013/files/09_tables.xlsx/content"},
                    },
                    {
                        "key": "04_H5ADs.zip",
                        "size": 256,
                        "checksum": "md5:ghi",
                        "links": {"self": "https://zenodo.org/api/records/14890013/files/04_H5ADs.zip/content"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with zipfile.ZipFile(zenodo_dir / "09_tables.xlsx", "w") as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>'
            '<sheet name="Brain cells" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            "</sheets></workbook>",
        )
    with zipfile.ZipFile(zenodo_dir / "04_H5ADs.zip", "w") as archive:
        h5ad_path = root / "female_brain.h5ad"
        with h5py.File(h5ad_path, "w") as h5:
            h5.create_dataset("X", data=[[1, 0, 3], [0, 2, 4]])
            h5["X"].attrs["shape"] = [2, 3]
            obs = h5.create_group("obs")
            obs.create_dataset("_index", data=[b"cell-1", b"cell-2"])
            obs.create_dataset("cell_type", data=[b"Kenyon cell", b"projection neuron"])
            var = h5.create_group("var")
            var.create_dataset("_index", data=[b"AAEL000001", b"AAEL000002", b"AAEL000003"])
            var.create_dataset("gene_symbol", data=[b"orco", b"dsx", b"nix"])
            uns = h5.create_group("uns")
            uns.create_dataset("dataset_name", data=b"fake brain atlas")
        archive.write(h5ad_path, "brain/female_brain.h5ad")

    sra_dir = artifact_dir / "geo"
    (sra_dir / "SRP290992_runinfo.csv").write_text(
        "Run,Experiment,Sample,BioSample,SampleName,LibraryStrategy,LibraryLayout,spots,bases,size_MB,download_path,ScientificName\n"
        "SRR1,SRX1,SRS1,SAMN1,GSM1_male,RNA-Seq,PAIRED,10,1340,1,https://example.test/SRR1.lite.1,Aedes aegypti\n",
        encoding="utf-8",
    )

    mosquito_dir = artifact_dir / "mosquitobrains"
    mosquito_dir.mkdir()
    (mosquito_dir / "downloads-and-links.html").write_text(
        '<a href="https://www.dropbox.com/sh/reference?dl=0">Aedes Reference Brain</a>'
        '<a href="https://www.dropbox.com/sh/segmentations?dl=0">Segmentation Files</a>',
        encoding="utf-8",
    )
    download_dir = mosquito_dir / "downloads"
    download_dir.mkdir()
    with zipfile.ZipFile(download_dir / "Aedes-Reference-Brain.zip", "w") as archive:
        nested = io.BytesIO()
        with zipfile.ZipFile(nested, "w") as inner:
            inner.writestr(
                "female_reference_brain/female_reference_brain.mhd",
                "ObjectType = Image\nNDims = 3\nDimSize = 2 2 2\nElementSpacing = 0.001 0.001 0.001\nElementType = MET_SHORT\nElementDataFile = female_reference_brain.raw\n",
            )
            inner.writestr("female_reference_brain/female_reference_brain.raw", struct.pack("<8h", 10, 11, 12, 13, 14, 15, 16, 17))
        archive.writestr("female_reference_brain.zip", nested.getvalue())
    with zipfile.ZipFile(download_dir / "Segmentation-Files.zip", "w") as archive:
        archive.writestr(
            "individual_brain_regions/Individual_Brain_regions.mha",
            b"ObjectType = Image\nNDims = 3\nDimSize = 2 2 2\nElementSpacing = 0.001 0.001 0.001\nElementType = MET_USHORT\nElementDataFile = LOCAL\n"
            + struct.pack("<8H", 1, 2, 3, 4, 5, 6, 7, 8),
        )
        archive.writestr(
            "individual_brain_regions/Label_Descriptions_BrainRegions.txt",
            '    1   255    0    0        1  1  1    "Lamina"\n'
            '    2    38  255    0        1  1  1    "Medulla"\n',
        )

    connectome_dir = artifact_dir / "connectome" / "aedes_public" / "csvs"
    connectome_dir.mkdir(parents=True)
    (connectome_dir.parent / "repo.json").write_text(
        json.dumps(
            {
                "full_name": "htem/aedes_public",
                "html_url": "https://github.com/htem/aedes_public",
                "description": "Public Aedes EM/CATMAID analysis repository",
                "license": {"spdx_id": "GPL-3.0"},
                "pushed_at": "2026-05-22T22:13:48Z",
            }
        ),
        encoding="utf-8",
    )
    (connectome_dir / "total_synapse_data.csv").write_text("class,total_synapses\nOSN,42\n", encoding="utf-8")
    return artifact_dir


class NeurobiologySourceTests(unittest.TestCase):
    def test_fetch_neurobiology_records_returns_brain_atoms_with_provenance(self):
        result = fetch_neurobiology_records(retrieved_at="2026-05-23T00:00:00Z")

        self.assertEqual(result.source_id, NEUROBIOLOGY_SOURCE_ID)
        self.assertEqual(result.gaps, [])
        self.assertGreaterEqual(len(result.records), 6)

        lanes = {record.lane for record in result.records}
        self.assertEqual(lanes, {"neurobiology"})

        atlas = next(record for record in result.records if record.record_id == "neuro:mosquitobrains:female-brain-atlas")
        self.assertEqual(atlas.species, "Aedes aegypti")
        self.assertIn("female Aedes aegypti brain", atlas.text)
        self.assertEqual(atlas.provenance.source_id, NEUROBIOLOGY_SOURCE_ID)
        self.assertIn("mosquitobrains.org", atlas.provenance.source_url)
        self.assertEqual(atlas.payload["record_type"], "brain_atlas")

        geo = next(record for record in result.records if record.record_id == "neuro:geo:GSE160740")
        self.assertIn("single-nucleus", geo.text)
        self.assertEqual(geo.payload["accession"], "GSE160740")

    def test_neurobiology_payloads_are_queryable_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            result = fetch_neurobiology_records(retrieved_at="2026-05-23T00:00:00Z")

            index.upsert_records(result.records)
            rows = index.sql(
                "select record_id, source, lane, payload_json from record_payloads "
                "where source = 'aedes_neurobiology_sources' order by record_id",
                limit=20,
            )

            self.assertEqual(len(rows), len(result.records))
            self.assertTrue(any(row["record_id"] == "neuro:geo:GSE160740" for row in rows))

    def test_fetch_neurobiology_records_ingests_local_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = write_fake_neurobiology_artifacts(Path(tmpdir))

            result = fetch_neurobiology_records(
                artifact_dir=artifact_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            record_ids = {record.record_id for record in result.records}
            self.assertIn("neuro:geo:GSE160740:GSM1_male:matrix", record_ids)
            self.assertIn("neuro:geo:GSE160740:GSM1_male:feature:AAEL000001", record_ids)
            self.assertIn("neuro:zenodo:14890013:file:00_README.txt", record_ids)
            self.assertIn("neuro:zenodo:14890013:workbook:09_tables.xlsx:sheet:Brain cells", record_ids)
            self.assertIn("neuro:zenodo:14890013:zip-member:04_H5ADs.zip:brain/female_brain.h5ad", record_ids)
            self.assertIn("neuro:zenodo:14890013:h5ad-summary:brain/female_brain.h5ad", record_ids)
            self.assertIn("neuro:zenodo:14890013:h5ad-dataset:brain/female_brain.h5ad:X", record_ids)
            self.assertIn("neuro:zenodo:14890013:h5ad-obs-column:brain/female_brain.h5ad:cell_type", record_ids)
            self.assertIn("neuro:zenodo:14890013:h5ad-var-column:brain/female_brain.h5ad:gene_symbol", record_ids)
            self.assertIn("neuro:sra:SRP290992:run:SRR1", record_ids)
            self.assertIn("neuro:sra:SRP290992:sample:GSM1_male", record_ids)
            self.assertIn("neuro:sra:SRP290992:raw-access", record_ids)
            self.assertIn("neuro:sra:SRP290992:reanalysis-workflow", record_ids)
            self.assertIn("neuro:mosquitobrains:dropbox:Aedes-Reference-Brain", record_ids)
            self.assertIn("neuro:mosquitobrains:file:Aedes-Reference-Brain.zip", record_ids)
            self.assertIn("neuro:mosquitobrains:zip-member:Aedes-Reference-Brain.zip:female_reference_brain.zip", record_ids)
            self.assertIn("neuro:mosquitobrains:volume:Aedes-Reference-Brain.zip:female_reference_brain.zip:female_reference_brain/female_reference_brain.mhd", record_ids)
            self.assertIn("neuro:mosquitobrains:volume:Segmentation-Files.zip:individual_brain_regions/Individual_Brain_regions.mha", record_ids)
            self.assertIn("neuro:mosquitobrains:label:Segmentation-Files.zip:individual_brain_regions/Label_Descriptions_BrainRegions.txt:1", record_ids)
            self.assertIn("neuro:connectome:aedes_public:repository", record_ids)
            self.assertIn("neuro:connectome:aedes_public:csv:total_synapse_data.csv", record_ids)
            self.assertIn("neuro:connectome:wellcome:source-gap", record_ids)

            gap_reasons = {gap["reason"] for gap in result.gaps}
            self.assertIn("whole_brain_connectome_download_not_public", gap_reasons)
            self.assertNotIn("h5ad_internal_matrix_not_parsed", gap_reasons)

            matrix = next(record for record in result.records if record.record_id == "neuro:geo:GSE160740:GSM1_male:matrix")
            self.assertEqual(matrix.payload["matrix"]["rows"], 2)
            self.assertEqual(matrix.payload["matrix"]["columns"], 2)
            self.assertEqual(matrix.payload["matrix"]["nonzero_entries"], 3)

            raw_access = next(record for record in result.records if record.record_id == "neuro:sra:SRP290992:raw-access")
            self.assertEqual(raw_access.payload["run_count"], 1)
            self.assertEqual(raw_access.payload["total_size_mb"], 1)
            self.assertEqual(raw_access.payload["runs"][0]["run"], "SRR1")

            workflow = next(record for record in result.records if record.record_id == "neuro:sra:SRP290992:reanalysis-workflow")
            self.assertIn("fasterq-dump", workflow.text)
            self.assertEqual(workflow.payload["execution_status"], "not_executed_by_source_index")

            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records(result.records)
            payload_rows = index.sql(
                "select record_id from record_payloads where record_id='neuro:zenodo:14890013:h5ad-dataset:brain/female_brain.h5ad:X'",
                limit=1,
            )
            self.assertEqual(len(payload_rows), 1)

            mha_value = read_voxel_value(
                index_path=Path(tmpdir) / "source_index.sqlite",
                record_id="neuro:mosquitobrains:volume:Segmentation-Files.zip:individual_brain_regions/Individual_Brain_regions.mha",
                x=1,
                y=0,
                z=1,
            )
            self.assertEqual(mha_value["value"], 6)
            self.assertEqual(mha_value["coordinate"], {"x": 1, "y": 0, "z": 1})

            mhd_value = read_voxel_value(
                index_path=Path(tmpdir) / "source_index.sqlite",
                record_id="neuro:mosquitobrains:volume:Aedes-Reference-Brain.zip:female_reference_brain.zip:female_reference_brain/female_reference_brain.mhd",
                x=1,
                y=1,
                z=0,
            )
            self.assertEqual(mhd_value["value"], 13)


if __name__ == "__main__":
    unittest.main()
