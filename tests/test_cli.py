import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_source_index
from scripts.build_source_index import create_parser
from tests.test_neurobiology_source import write_fake_neurobiology_artifacts
from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.literature import FullTextUnit


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "askinsects", *args],
            capture_output=True,
            text=True,
        )

    def test_health_summary_sources_and_ask(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            subprocess.run(
                [sys.executable, "scripts/build_source_index.py", "--fixtures", "--artifact-dir", artifact_dir],
                check=True,
            )

            health = subprocess.check_output([sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir, "health"], text=True)
            self.assertTrue(json.loads(health)["ok"])

            summary = subprocess.check_output([sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir, "summary"], text=True)
            self.assertGreater(json.loads(summary)["record_count"], 0)

            sources = subprocess.check_output([sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir, "sources"], text=True)
            self.assertIn("mosquito_v1_fixtures", sources)

            answer = subprocess.check_output(
                [
                    sys.executable,
                    "-m",
                    "askinsects",
                    "--artifact-dir",
                    artifact_dir,
                    "ask",
                    "what do we know about Aedes aegypti?",
                    "--json",
                ],
                text=True,
            )
            payload = json.loads(answer)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["evidence"])

    def test_missing_index_commands_return_structured_errors(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            cases = [
                ("summary",),
                ("search", "taxonomy", "Aedes"),
                ("sql", "select * from records"),
                ("ask", "what do we know about Aedes aegypti?", "--json"),
            ]
            for args in cases:
                with self.subTest(args=args):
                    result = self.run_cli("--artifact-dir", artifact_dir, *args)

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr, "")
                    payload = json.loads(result.stdout)
                    self.assertFalse(payload["ok"])
                    self.assertIn("error", payload)
                    self.assertIn("mosquito_v1", payload["source_gap"]["reason"])

    def test_invalid_write_sql_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            subprocess.run(
                [sys.executable, "scripts/build_source_index.py", "--fixtures", "--artifact-dir", artifact_dir],
                check=True,
            )

            result = self.run_cli("--artifact-dir", artifact_dir, "sql", "delete from records")

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)
            self.assertEqual(payload["source_gap"]["lane"], "sql")

    def test_search_papers_alias_returns_literature_rows(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            subprocess.run(
                [sys.executable, "scripts/build_source_index.py", "--fixtures", "--artifact-dir", artifact_dir],
                check=True,
            )

            result = self.run_cli("--artifact-dir", artifact_dir, "search", "papers", "host seeking")

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["rows"])
            self.assertTrue(any(row["lane"] == "literature" for row in payload["rows"]))

    def test_search_fulltext_alias_returns_literature_fulltext_rows(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            index = SourceIndex(Path(artifact_dir) / "source_index.sqlite")
            index.initialize()
            provenance = Provenance(
                source_id="aedes_literature_openalex",
                locator="raw/literature/page.json#WCLI",
                retrieved_at="2026-05-23T00:00:00Z",
            )
            index.upsert_records_and_fulltext_units(
                [
                    EvidenceRecord(
                        record_id="openalex:WCLI",
                        lane="literature",
                        source="aedes_literature_openalex",
                        title="Aedes aegypti paper",
                        text="Aedes aegypti metadata.",
                        species="Aedes aegypti",
                        url="https://example.org/paper",
                        media_url=None,
                        provenance=provenance,
                    )
                ],
                [
                    FullTextUnit(
                        unit_id="openalex:WCLI:fulltext:0",
                        record_id="openalex:WCLI",
                        source="aedes_literature_openalex",
                        unit_index=0,
                        text="Aedes aegypti legal full text mentions microbiota.",
                        url="https://example.org/fulltext",
                        license="CC BY",
                        provenance=provenance,
                    )
                ],
            )

            result = self.run_cli("--artifact-dir", artifact_dir, "search", "fulltext", "microbiota")

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["rows"][0]["lane"], "literature_fulltext")

    def test_sources_reads_indexed_sources_from_status_file(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            status_path = Path(artifact_dir) / "source_status.json"
            status_path.write_text(
                json.dumps({"sources": ["mosquito_v1_fixtures", "gbif_api"]}) + "\n",
                encoding="utf-8",
            )

            result = self.run_cli("--artifact-dir", artifact_dir, "sources")

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["sources"], ["mosquito_v1_fixtures", "gbif_api"])

    def test_ask_with_malformed_index_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as artifact_dir:
            conn = sqlite3.connect(f"{artifact_dir}/source_index.sqlite")
            conn.execute(
                """
                CREATE TABLE records (
                  record_id TEXT PRIMARY KEY,
                  lane TEXT NOT NULL,
                  source TEXT NOT NULL,
                  title TEXT NOT NULL,
                  text TEXT NOT NULL,
                  species TEXT,
                  url TEXT,
                  media_url TEXT,
                  provenance_json TEXT NOT NULL
                )
                """
            )
            conn.close()

            result = self.run_cli(
                "--artifact-dir",
                artifact_dir,
                "ask",
                "what do we know about Aedes aegypti?",
                "--json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)
            self.assertIn("source_gap", payload)

    def test_build_script_accepts_literature_flags(self):
        parser = create_parser()

        args = parser.parse_args(
            [
                "--openalex-literature",
                "--literature-species",
                "Aedes aegypti",
                "--literature-from-date",
                "2020-01-01",
                "--literature-to-date",
                "2026-05-23",
                "--literature-work-type",
                "article",
                "--literature-page-size",
                "25",
                "--literature-delay-seconds",
                "0",
                "--literature-max-works",
                "1",
                "--unpaywall-email",
                "test@example.com",
                "--skip-fulltext",
                "--skip-pubmed",
            ]
        )

        self.assertTrue(args.openalex_literature)
        self.assertEqual(args.literature_species, "Aedes aegypti")
        self.assertEqual(args.literature_from_date, "2020-01-01")
        self.assertEqual(args.literature_to_date, "2026-05-23")
        self.assertEqual(args.literature_work_type, "article")
        self.assertEqual(args.literature_page_size, 25)
        self.assertEqual(args.literature_delay_seconds, 0)
        self.assertEqual(args.literature_max_works, 1)
        self.assertEqual(args.unpaywall_email, "test@example.com")
        self.assertTrue(args.skip_fulltext)
        self.assertTrue(args.skip_pubmed)

    def test_build_script_accepts_plan_aliases_for_literature_flags(self):
        parser = create_parser()

        args = parser.parse_args(
            [
                "--openalex-literature",
                "--from-date",
                "2020-01-01",
                "--to-date",
                "2026-05-23",
                "--work-type",
                "article",
                "--max-works",
                "1",
                "--delay-seconds",
                "0",
            ]
        )

        self.assertTrue(args.openalex_literature)
        self.assertEqual(args.literature_from_date, "2020-01-01")
        self.assertEqual(args.literature_to_date, "2026-05-23")
        self.assertEqual(args.literature_work_type, "article")
        self.assertEqual(args.literature_max_works, 1)
        self.assertEqual(args.delay_seconds, 0)

    def test_build_script_leaves_literature_to_date_unset_by_default(self):
        parser = create_parser()

        args = parser.parse_args(["--openalex-literature"])

        self.assertIsNone(args.literature_to_date)

    def test_build_script_accepts_ncbi_genome_flags(self):
        parser = create_parser()

        args = parser.parse_args(
            [
                "--fixtures",
                "--ncbi-genome",
                "--genome-package-dir",
                "/tmp/aedes-ncbi-package",
                "--genome-assembly-accession",
                "GCF_002204515.2",
            ]
        )

        self.assertTrue(args.fixtures)
        self.assertTrue(args.ncbi_genome)
        self.assertEqual(args.genome_package_dir, "/tmp/aedes-ncbi-package")
        self.assertEqual(args.genome_assembly_accession, "GCF_002204515.2")

    def test_build_script_accepts_neurobiology_flag(self):
        parser = create_parser()

        args = parser.parse_args(["--fixtures", "--neurobiology", "--neurobiology-artifact-dir", "/tmp/aedes-neurobiology"])

        self.assertTrue(args.fixtures)
        self.assertTrue(args.neurobiology)
        self.assertEqual(args.neurobiology_artifact_dir, "/tmp/aedes-neurobiology")

    def test_voxel_command_reads_coordinate_from_neurobiology_volume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_dir = write_fake_neurobiology_artifacts(tmp_path)
            artifact_dir = tmp_path / "mosquito-v1"
            build_source_index(
                include_fixtures=True,
                include_gbif=False,
                include_inaturalist=False,
                include_neurobiology=True,
                artifact_dir=artifact_dir,
                neurobiology_artifact_dir=source_dir,
                retrieved_at="2026-05-23T00:00:00Z",
            )

            result = self.run_cli(
                "--artifact-dir",
                str(artifact_dir),
                "voxel",
                "neuro:mosquitobrains:volume:Segmentation-Files.zip:individual_brain_regions/Individual_Brain_regions.mha",
                "--x",
                "1",
                "--y",
                "0",
                "--z",
                "1",
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["value"], 6)
            self.assertEqual(payload["coordinate"], {"x": 1, "y": 0, "z": 1})


if __name__ == "__main__":
    unittest.main()
