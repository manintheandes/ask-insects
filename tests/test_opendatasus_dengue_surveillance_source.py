from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from askinsects.sources.opendatasus_dengue_surveillance import (
    OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID,
    OpenDataSusDengueFileSpec,
    default_opendatasus_dengue_file_specs,
    fetch_opendatasus_dengue_surveillance_records,
)


CSV_TEXT = """TP_NOT,ID_AGRAVO,DT_NOTIFIC,SEM_NOT,NU_ANO,SG_UF_NOT,DT_SIN_PRI,SEM_PRI,SG_UF,CLASSI_FIN,CRITERIO,EVOLUCAO,HOSPITALIZ,CS_SEXO
2,A90,2025-01-05,202501,2025,35,2025-01-04,202501,35,10,1,1,2,F
2,A90,2025-01-06,202501,2025,35,2025-01-05,202501,35,12,1,2,1,M
2,A90,2025-01-07,202501,2025,33,2025-01-06,202501,33,11,2,3,1,F
"""


def zip_bytes(text: str = CSV_TEXT, name: str = "DENGBR25.csv") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


class OpenDataSusDengueSurveillanceSourceTests(unittest.TestCase):
    def test_default_specs_cover_public_historical_backfiles(self):
        specs = default_opendatasus_dengue_file_specs()

        self.assertEqual(specs[0].year, 2007)
        self.assertEqual(specs[-1].year, 2026)
        self.assertEqual(len(specs), 20)
        self.assertEqual(specs[0].url, "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR07.csv.zip")
        self.assertEqual(specs[-1].url, "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR26.csv.zip")

    def test_fetch_opendatasus_records_parses_current_zip_aggregates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_opendatasus_dengue_surveillance_records(
                [OpenDataSusDengueFileSpec(year=2025, url="https://opendatasus.example/DENGBR25.csv.zip")],
                raw_dir=Path(tmpdir) / "raw",
                fetch_bytes=lambda url: zip_bytes(),
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertEqual(result.source_id, OPENDATASUS_DENGUE_SURVEILLANCE_SOURCE_ID)
            self.assertEqual(result.gaps, [])
            self.assertEqual(result.file_count, 1)
            self.assertEqual(result.row_count, 3)
            self.assertEqual(result.country_year_record_count, 1)
            self.assertEqual(result.state_year_record_count, 4)
            self.assertEqual(result.country_week_record_count, 1)
            self.assertEqual(result.state_week_record_count, 2)
            self.assertEqual(len(result.records), 9)

            summary = next(record for record in result.records if record.record_id.endswith(":country:brazil:2025"))
            self.assertEqual(summary.lane, "public_health")
            self.assertEqual(summary.species, "Aedes aegypti")
            self.assertEqual(summary.payload["notifications"], 3)
            self.assertEqual(summary.payload["deaths_by_disease"], 1)
            self.assertEqual(summary.payload["deaths_other_causes"], 1)
            self.assertEqual(summary.payload["severe_dengue"], 1)
            self.assertIn("Notifications: 3", summary.text)
            self.assertTrue(Path(result.raw_artifacts[0]).exists())

            state = next(record for record in result.records if ":residence_state:35:2025" in record.record_id)
            self.assertEqual(state.payload["residence_state"], "Sao Paulo")
            self.assertEqual(state.payload["notifications"], 2)

    def test_fetch_opendatasus_records_records_fetch_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_opendatasus_dengue_surveillance_records(
                [OpenDataSusDengueFileSpec(year=2025, url="https://opendatasus.example/missing.zip")],
                raw_dir=Path(tmpdir) / "raw",
                fetch_bytes=lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
                retrieved_at="2026-05-26T00:00:00Z",
            )

            self.assertFalse(result.records)
            self.assertEqual(result.gaps[0]["reason"], "opendatasus_dengue_file_fetch_failed")


if __name__ == "__main__":
    unittest.main()
