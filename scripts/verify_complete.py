#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import sqlite3
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VERIFY_ARTIFACT_DIR = Path(tempfile.mkdtemp(prefix="ask-insects-verify-")) / "mosquito-v1"
VERIFY_ENV = {**os.environ, "ASK_INSECTS_ARTIFACT_DIR": VERIFY_ARTIFACT_DIR.as_posix()}

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "config/source-map.yaml",
    "config/mosquito-intelligence-coverage.json",
    "data/fixtures/mosquito_records.json",
    "docs/querying-ask-insects.md",
    "docs/source-lanes.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-gbif-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-inaturalist-v1-design.md",
    "docs/superpowers/specs/2026-05-23-inaturalist-deep-aedes-ingest-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-literature-source-lane-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-hosted-vm-infra-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-genomics-lane-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-neurobiology-deep-source-completion-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-aegypti-world-intelligence-source-plane-design.md",
    "docs/superpowers/specs/2026-05-23-neurobiology-gap-closure-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-vector-competence-assay-candidates-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-ncbi-biosample-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-resistance-marker-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-occurrence-ecology-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-vectorbase-genomics-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-mendeley-behavior-media-lane-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-mendeley-behavior-table-deep-parse-design.md",
    "docs/superpowers/specs/2026-05-24-aedes-osf-flighttrackai-video-lane-design.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-mosquito-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-gbif-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-inaturalist-v1.md",
    "docs/superpowers/plans/2026-05-23-inaturalist-deep-aedes-ingest.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-literature-source-lane.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-hosted-vm-infra.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-genomics-lane.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-neurobiology-deep-source-completion.md",
    "docs/superpowers/plans/2026-05-23-neurobiology-gap-closure.md",
    "docs/superpowers/plans/2026-05-24-aedes-vector-competence-assay-candidates.md",
    "docs/superpowers/plans/2026-05-24-aedes-ncbi-biosample-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-resistance-marker-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-occurrence-ecology-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-vectorbase-genomics-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-mendeley-behavior-media-lane.md",
    "docs/superpowers/plans/2026-05-24-aedes-mendeley-behavior-table-deep-parse.md",
    "docs/superpowers/plans/2026-05-24-aedes-osf-flighttrackai-video-lane.md",
    "askinsects/__init__.py",
    "askinsects/__main__.py",
    "askinsects/answer.py",
    "askinsects/builder.py",
    "askinsects/cli.py",
    "askinsects/hosted.py",
    "askinsects/index.py",
    "askinsects/planner.py",
    "askinsects/records.py",
    "askinsects/server.py",
    "askinsects/voxels.py",
    "askinsects/sources/__init__.py",
    "askinsects/sources/fixtures.py",
    "askinsects/sources/bold_barcodes.py",
    "askinsects/sources/gbif.py",
    "askinsects/sources/inaturalist.py",
    "askinsects/sources/literature.py",
    "askinsects/sources/ncbi_genome.py",
    "askinsects/sources/neurobiology.py",
    "askinsects/sources/pmc_videos.py",
    "askinsects/sources/irmapper.py",
    "askinsects/sources/mosquito_alert.py",
    "askinsects/sources/dryad_behavior_videos.py",
    "askinsects/sources/mendeley_behavior_media.py",
    "askinsects/sources/osf_flighttrackai_videos.py",
    "askinsects/sources/public_health.py",
    "askinsects/sources/paho_surveillance.py",
    "askinsects/sources/pathogen_taxonomy.py",
    "askinsects/sources/ncbi_biosample.py",
    "askinsects/sources/vectorbase_genomics.py",
    "askinsects/sources/vector_competence_assays.py",
    "askinsects/sources/resistance_markers.py",
    "askinsects/sources/occurrence_ecology.py",
    "scripts/build_source_index.py",
    "scripts/enrich_literature_index.py",
    "scripts/ingest_neurobiology_sources.py",
    "scripts/deploy_gce_app.sh",
    "scripts/deploy_gce_vm.sh",
    "scripts/verify_complete.py",
    "scripts/verify_mosquito_intelligence_coverage.py",
    "scripts/build_literature_facets.py",
    "scripts/ingest_bold_barcodes.py",
    "scripts/ingest_inaturalist_observations.py",
    "scripts/ingest_pmc_videos.py",
    "scripts/ingest_irmapper.py",
    "scripts/ingest_mosquito_alert_observations.py",
    "scripts/ingest_dryad_behavior_videos.py",
    "scripts/ingest_mendeley_behavior_media.py",
    "scripts/ingest_osf_flighttrackai_videos.py",
    "scripts/ingest_public_health_guidance.py",
    "scripts/ingest_paho_dengue_surveillance.py",
    "scripts/ingest_pathogen_taxonomy.py",
    "scripts/ingest_ncbi_biosamples.py",
    "scripts/ingest_vectorbase_genomics.py",
    "scripts/ingest_vector_competence_assays.py",
    "scripts/ingest_resistance_markers.py",
    "scripts/ingest_occurrence_ecology.py",
    "deploy/systemd/ask-insects.service",
    "tests/test_answer.py",
    "tests/test_builder.py",
    "tests/test_bold_barcode_source.py",
    "tests/test_cli.py",
    "tests/test_cli_hosted.py",
    "tests/test_deploy_files.py",
    "tests/test_fixture_source.py",
    "tests/test_gbif_source.py",
    "tests/test_hosted_client.py",
    "tests/test_inaturalist_source.py",
    "tests/test_literature_source.py",
    "tests/test_literature_enrichment.py",
    "tests/test_index.py",
    "tests/test_ncbi_genome_source.py",
    "tests/test_neurobiology_source.py",
    "tests/test_records.py",
    "tests/test_server.py",
    "tests/test_verify_complete.py",
    "tests/test_mosquito_intelligence_coverage.py",
    "tests/test_literature_facets.py",
    "tests/test_ingest_bold_barcodes.py",
    "tests/test_ingest_inaturalist_observations.py",
    "tests/test_ingest_pmc_videos.py",
    "tests/test_pmc_video_source.py",
    "tests/test_ingest_irmapper.py",
    "tests/test_irmapper_source.py",
    "tests/test_mosquito_alert_source.py",
    "tests/test_ingest_mosquito_alert_observations.py",
    "tests/test_dryad_behavior_videos_source.py",
    "tests/test_ingest_dryad_behavior_videos.py",
    "tests/test_mendeley_behavior_media_source.py",
    "tests/test_ingest_mendeley_behavior_media.py",
    "tests/test_osf_flighttrackai_videos_source.py",
    "tests/test_ingest_osf_flighttrackai_videos.py",
    "tests/test_public_health_source.py",
    "tests/test_ingest_public_health_guidance.py",
    "tests/test_paho_surveillance_source.py",
    "tests/test_ingest_paho_dengue_surveillance.py",
    "tests/test_pathogen_taxonomy_source.py",
    "tests/test_ingest_pathogen_taxonomy.py",
    "tests/test_ncbi_biosample_source.py",
    "tests/test_ingest_ncbi_biosamples.py",
    "tests/test_vectorbase_genomics_source.py",
    "tests/test_ingest_vectorbase_genomics.py",
    "tests/test_vector_competence_assays_source.py",
    "tests/test_ingest_vector_competence_assays.py",
    "tests/test_resistance_markers_source.py",
    "tests/test_ingest_resistance_markers.py",
    "tests/test_occurrence_ecology_source.py",
    "tests/test_ingest_occurrence_ecology.py",
)

UNIT_TEST_MODULES = (
    "tests.test_answer",
    "tests.test_builder",
    "tests.test_bold_barcode_source",
    "tests.test_cli",
    "tests.test_cli_hosted",
    "tests.test_deploy_files",
    "tests.test_fixture_source",
    "tests.test_gbif_source",
    "tests.test_hosted_client",
    "tests.test_inaturalist_source",
    "tests.test_literature_source",
    "tests.test_literature_enrichment",
    "tests.test_index",
    "tests.test_ncbi_genome_source",
    "tests.test_neurobiology_source",
    "tests.test_records",
    "tests.test_server",
    "tests.test_mosquito_intelligence_coverage",
    "tests.test_literature_facets",
    "tests.test_ingest_bold_barcodes",
    "tests.test_ingest_inaturalist_observations",
    "tests.test_ingest_pmc_videos",
    "tests.test_pmc_video_source",
    "tests.test_ingest_irmapper",
    "tests.test_irmapper_source",
    "tests.test_mosquito_alert_source",
    "tests.test_ingest_mosquito_alert_observations",
    "tests.test_dryad_behavior_videos_source",
    "tests.test_ingest_dryad_behavior_videos",
    "tests.test_mendeley_behavior_media_source",
    "tests.test_ingest_mendeley_behavior_media",
    "tests.test_osf_flighttrackai_videos_source",
    "tests.test_ingest_osf_flighttrackai_videos",
    "tests.test_public_health_source",
    "tests.test_ingest_public_health_guidance",
    "tests.test_paho_surveillance_source",
    "tests.test_ingest_paho_dengue_surveillance",
    "tests.test_pathogen_taxonomy_source",
    "tests.test_ingest_pathogen_taxonomy",
    "tests.test_ncbi_biosample_source",
    "tests.test_ingest_ncbi_biosamples",
    "tests.test_vectorbase_genomics_source",
    "tests.test_ingest_vectorbase_genomics",
    "tests.test_vector_competence_assays_source",
    "tests.test_ingest_vector_competence_assays",
    "tests.test_resistance_markers_source",
    "tests.test_ingest_resistance_markers",
    "tests.test_occurrence_ecology_source",
    "tests.test_ingest_occurrence_ecology",
)


def fail(message: str) -> int:
    print(f"verify_complete failed: {message}", file=sys.stderr)
    return 1


def run_command(args: list[str], *, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=REPO_ROOT, env=VERIFY_ENV, capture_output=True, text=True)
    if result.returncode != expected_returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} exited {result.returncode}: {detail}")
    return result


def run_json(args: list[str], *, expected_returncode: int = 0) -> dict[str, object]:
    result = run_command(args, expected_returncode=expected_returncode)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(args)} did not return JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{' '.join(args)} returned non-object JSON")
    return payload


def check_required_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (REPO_ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"missing required file(s): {', '.join(missing)}")


def check_unit_tests() -> None:
    run_command([sys.executable, "-m", "unittest", *UNIT_TEST_MODULES, "-v"])


def check_source_index_build() -> None:
    payload = run_json(
        [
            sys.executable,
            "scripts/build_source_index.py",
            "--fixtures",
            "--artifact-dir",
            VERIFY_ARTIFACT_DIR.as_posix(),
        ]
    )
    if not payload.get("ok"):
        raise RuntimeError("fixture index build did not report ok true")
    if int(payload.get("record_count", 0)) < 7:
        raise RuntimeError("fixture index build produced fewer than 7 records")


def check_literature_source_map() -> None:
    text = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    required_terms = (
        "aedes_literature_openalex",
        "pmc_open_access_videos",
        "irmapper_aedes",
        "dryad_aedes_behavior_videos",
        "mendeley_aedes_behavior_media",
        "osf_flighttrackai_aedes_videos",
        "aedes_pathogen_taxonomy",
        "ncbi_biosamples",
        "aedes_vector_competence_assays",
        "aedes_resistance_markers",
        "aedes_occurrence_ecology",
        "OpenAlex articles where Aedes aegypti is material in title, abstract, or accepted topic metadata",
        "sqlite_payload_table: record_payloads",
        "sqlite_fulltext_table: literature_fulltext_units",
        "search fulltext",
        "live_fetch: opt_in",
        "pubmed_eutilities",
        "unpaywall_api",
    )
    missing = [term for term in required_terms if term not in text]
    if missing:
        raise RuntimeError(f"source map missing literature term(s): {', '.join(missing)}")


def check_mosquito_intelligence_coverage() -> None:
    from scripts.verify_mosquito_intelligence_coverage import load_coverage, verify_coverage

    verify_coverage(load_coverage())
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    lanes_doc = (REPO_ROOT / "docs/source-lanes.md").read_text(encoding="utf-8")
    source_map = (REPO_ROOT / "config/source-map.yaml").read_text(encoding="utf-8")
    required_terms = (
        "config/mosquito-intelligence-coverage.json",
        "Aedes",
        "aedes_literature_facets",
        "aedes_public_health_guidance",
        "aedes_paho_dengue_surveillance",
        "mosquito_alert_gbif",
        "dryad_aedes_behavior_videos",
        "aedes_pathogen_taxonomy",
        "ncbi_biosamples",
        "aedes_vector_competence_assays",
        "aedes_occurrence_ecology",
        "vectorbase_aedes_genomics",
        "osf_flighttrackai_aedes_videos",
    )
    for term in required_terms:
        if term not in readme:
            raise RuntimeError(f"README.md missing coverage term: {term}")
        if term not in lanes_doc:
            raise RuntimeError(f"docs/source-lanes.md missing coverage term: {term}")
    if "mosquito-intelligence-coverage.json" not in source_map:
        raise RuntimeError("config/source-map.yaml missing coverage ledger link")
    if "aedes_literature_facets" not in source_map:
        raise RuntimeError("config/source-map.yaml missing aedes_literature_facets")
    for term in ("aedes_public_health_guidance", "scripts/ingest_public_health_guidance.py", "public_health"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing public-health guidance term: {term}")
    for term in ("aedes_paho_dengue_surveillance", "scripts/ingest_paho_dengue_surveillance.py", "official_paho_dengue_report_html_to_sqlite_public_health_records", "PAHO/PLISA country-week dashboard data remains a source gap"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing PAHO dengue surveillance term: {term}")
    for term in ("mosquito_alert_gbif", "scripts/ingest_mosquito_alert_observations.py", "observations", "media"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Mosquito Alert term: {term}")
    for term in ("dryad_aedes_behavior_videos", "scripts/ingest_dryad_behavior_videos.py", "behavior", "media"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Dryad behavior/video term: {term}")
    for term in (
        "mendeley_aedes_behavior_media",
        "scripts/ingest_mendeley_behavior_media.py",
        "mendeley_public_snapshot_folder_file_manifest_and_table_rows_to_sqlite",
        "6gvs94p6r2:1",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing Mendeley behavior/media term: {term}")
    for term in (
        "osf_flighttrackai_aedes_videos",
        "scripts/ingest_osf_flighttrackai_videos.py",
        "osf_project_file_manifest_to_sqlite",
        "cx762",
        "manifest_and_download_locators_only_by_default",
    ):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing OSF FlightTrackAI term: {term}")
    for term in ("aedes_pathogen_taxonomy", "scripts/ingest_pathogen_taxonomy.py", "vector_competence"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing pathogen taxonomy term: {term}")
    for term in ("ncbi_biosamples", "scripts/ingest_ncbi_biosamples.py", "biosamples", "ncbi_eutils_biosample_esearch_esummary_to_sqlite"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing NCBI BioSample term: {term}")
    for term in ("vectorbase_aedes_genomics", "scripts/ingest_vectorbase_genomics.py", "vectorbase_current_release_downloads_to_sqlite", "VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing VectorBase genomics term: {term}")
    for term in ("aedes_vector_competence_assays", "scripts/ingest_vector_competence_assays.py", "literature_fulltext_units", "legal_fulltext_only"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing vector competence assay term: {term}")
    for term in ("aedes_resistance_markers", "scripts/ingest_resistance_markers.py", "literature_records_and_fulltext_units_to_sqlite_resistance_marker_records", "legal_fulltext_only"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing resistance marker term: {term}")
    for term in ("aedes_occurrence_ecology", "scripts/ingest_occurrence_ecology.py", "indexed_observation_payloads_to_sqlite_ecology_records", "GBIF and iNaturalist observation joins"):
        if term not in source_map:
            raise RuntimeError(f"config/source-map.yaml missing occurrence ecology term: {term}")


def check_cli() -> None:
    health = run_json([sys.executable, "-m", "askinsects", "health"])
    if health.get("ok") is not True:
        raise RuntimeError("health did not report ok true")

    summary = run_json([sys.executable, "-m", "askinsects", "summary"])
    if int(summary.get("record_count", 0)) < 7:
        raise RuntimeError("summary reported fewer than 7 records")

    sources = run_json([sys.executable, "-m", "askinsects", "sources"])
    if "mosquito_v1_fixtures" not in sources.get("sources", []):
        raise RuntimeError("sources did not include mosquito_v1_fixtures")

    answer_cases = (
        "what do we know about Aedes aegypti?",
        "show mosquito observations with images in Brazil",
        "what should a scientist inspect next for Culex pipiens?",
    )
    for question in answer_cases:
        payload = run_json([sys.executable, "-m", "askinsects", "ask", question, "--json"])
        if payload.get("ok") is not True:
            raise RuntimeError(f"answer did not report ok true for: {question}")
        if not payload.get("evidence"):
            raise RuntimeError(f"answer did not include evidence for: {question}")

    gap = run_json(
        [
            sys.executable,
            "-m",
            "askinsects",
            "ask",
            "show mosquito videos from Brazil",
            "--json",
        ],
        expected_returncode=2,
    )
    if gap.get("ok") is not False:
        raise RuntimeError("media source gap did not report ok false")
    if not gap.get("source_gap"):
        raise RuntimeError("media source gap did not include source_gap")


def _direct_fulltext_from_payload(payload: dict[str, object]) -> bool:
    unpaywall = payload.get("unpaywall")
    if isinstance(unpaywall, dict) and unpaywall.get("is_oa"):
        location = unpaywall.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("url_for_pdf") or location.get("url_for_xml")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return True
    work = payload.get("raw_openalex_work")
    if isinstance(work, dict):
        location = work.get("best_oa_location")
        if isinstance(location, dict):
            url = location.get("pdf_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return True
    return False


def check_literature_artifact() -> None:
    artifact_dir = REPO_ROOT / "artifacts/aedes-literature-2020"
    db_path = artifact_dir / "source_index.sqlite"
    status_path = artifact_dir / "source_status.json"
    receipt_path = artifact_dir / "source_receipt.json"
    enrichment_receipt_path = artifact_dir / "literature_enrichment_receipt.json"
    gaps_path = artifact_dir / "gaps.json"
    for path in (db_path, status_path, receipt_path, enrichment_receipt_path, gaps_path):
        if not path.exists():
            raise RuntimeError(f"missing Aedes literature artifact file: {path.relative_to(REPO_ROOT)}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        literature_records = int(
            conn.execute("select count(*) from records where source='aedes_literature_openalex'").fetchone()[0]
        )
        payload_rows = conn.execute(
            "select record_id, payload_json from record_payloads where source='aedes_literature_openalex'"
        ).fetchall()
        pubmed_enriched = int(
            conn.execute(
                "select count(*) from record_payloads where source='aedes_literature_openalex' and json_type(payload_json, '$.pubmed')='object'"
            ).fetchone()[0]
        )
        unpaywall_enriched = int(
            conn.execute(
                "select count(*) from record_payloads where source='aedes_literature_openalex' and json_type(payload_json, '$.unpaywall')='object'"
            ).fetchone()[0]
        )
        fulltext_records = int(conn.execute("select count(distinct record_id) from literature_fulltext_units").fetchone()[0])
        fulltext_units = int(conn.execute("select count(*) from literature_fulltext_units").fetchone()[0])
        fulltext_fts = int(conn.execute("select count(*) from literature_fulltext_fts").fetchone()[0])
        fulltext_record_ids = {row[0] for row in conn.execute("select distinct record_id from literature_fulltext_units")}
        facet_counts = {
            str(row["lane"]): int(row["n"])
            for row in conn.execute(
                """
                select lane, count(*) as n
                from records
                where source='aedes_literature_facets'
                group by lane
                """
            )
        }

    if literature_records != 10683:
        raise RuntimeError(f"Aedes literature record count is {literature_records}, expected 10683")
    if len(payload_rows) != literature_records:
        raise RuntimeError("Aedes literature payload count does not match record count")
    if pubmed_enriched < 3800:
        raise RuntimeError(f"PubMed enrichment count is too low: {pubmed_enriched}")
    if unpaywall_enriched < 9500:
        raise RuntimeError(f"Unpaywall enrichment count is too low: {unpaywall_enriched}")
    if fulltext_records == 0 or fulltext_units == 0:
        raise RuntimeError("Aedes literature full text has not been extracted")
    if fulltext_fts != fulltext_units:
        raise RuntimeError("literature_fulltext_fts count does not match literature_fulltext_units")
    required_facet_counts = {
        "behavior": 2816,
        "vector_competence": 4534,
        "resistance": 2843,
        "ecology": 5253,
        "public_health": 8261,
    }
    for lane, expected in required_facet_counts.items():
        actual = facet_counts.get(lane, 0)
        if actual != expected:
            raise RuntimeError(f"Aedes literature facet count for {lane} is {actual}, expected {expected}")

    payloads = {row["record_id"]: json.loads(row["payload_json"]) for row in payload_rows}
    direct_candidates = {record_id for record_id, payload in payloads.items() if _direct_fulltext_from_payload(payload)}
    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    if not isinstance(gaps, list):
        raise RuntimeError("gaps.json is not a list")
    gap_keys = {
        (
            str(gap.get("source")),
            str(gap.get("lane")),
            str(gap.get("reason")),
            str(gap.get("record_id")),
            str(gap.get("locator")),
        )
        for gap in gaps
        if isinstance(gap, dict)
    }
    if len(gap_keys) != len(gaps):
        raise RuntimeError("gaps.json contains duplicate source/lane/reason/record/locator rows")
    failed_fulltext_ids = {
        str(gap.get("record_id"))
        for gap in gaps
        if isinstance(gap, dict)
        and gap.get("source") == "aedes_literature_openalex"
        and gap.get("reason") in {"fulltext_fetch_failed", "fulltext_parse_failed"}
    }
    unresolved_direct = direct_candidates - fulltext_record_ids - failed_fulltext_ids
    if unresolved_direct:
        sample = ", ".join(sorted(unresolved_direct)[:5])
        raise RuntimeError(f"{len(unresolved_direct)} direct full-text candidates lack extracted text or explicit gap, sample: {sample}")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    status_lit = status.get("literature") if isinstance(status, dict) else None
    receipt_lit = receipt.get("literature") if isinstance(receipt, dict) else None
    if not isinstance(status_lit, dict) or not isinstance(receipt_lit, dict):
        raise RuntimeError("literature counts missing from source_status.json or source_receipt.json")
    if status.get("source_id") != "aedes_literature_openalex":
        raise RuntimeError("source_status.json source_id does not identify the Aedes literature source")
    if receipt.get("source_id") != "aedes_literature_openalex":
        raise RuntimeError("source_receipt.json source_id does not identify the Aedes literature source")
    if "aedes_literature_openalex" not in status.get("sources", []):
        raise RuntimeError("source_status.json sources does not include the Aedes literature source")
    if "aedes_literature_openalex" not in receipt.get("sources", []):
        raise RuntimeError("source_receipt.json sources does not include the Aedes literature source")
    expected_pairs = {
        "record_count": literature_records,
        "payload_count": len(payload_rows),
        "pubmed_enriched_count": pubmed_enriched,
        "unpaywall_enriched_count": unpaywall_enriched,
        "direct_fulltext_candidate_count": len(direct_candidates),
        "fulltext_record_count": fulltext_records,
        "fulltext_unit_count": fulltext_units,
        "fulltext_fts_count": fulltext_fts,
    }
    for key, value in expected_pairs.items():
        if int(status_lit.get(key, -1)) != value:
            raise RuntimeError(f"source_status.json literature.{key} does not match SQLite")
        if int(receipt_lit.get(key, -1)) != value:
            raise RuntimeError(f"source_receipt.json literature.{key} does not match SQLite")

    sources = run_json([sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir.as_posix(), "sources"])
    if "aedes_literature_openalex" not in sources.get("sources", []):
        raise RuntimeError("Aedes artifact sources command does not include aedes_literature_openalex")
    if "aedes_literature_facets" not in sources.get("sources", []):
        raise RuntimeError("Aedes artifact sources command does not include aedes_literature_facets")
    search = run_json(
        [sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir.as_posix(), "search", "literature", "Wolbachia", "--limit", "3"]
    )
    if not search.get("rows"):
        raise RuntimeError("Aedes artifact literature search returned no rows for Wolbachia")
    answer = run_json(
        [sys.executable, "-m", "askinsects", "--artifact-dir", artifact_dir.as_posix(), "ask", "Aedes aegypti research", "--json"]
    )
    if answer.get("ok") is not True or not answer.get("evidence"):
        raise RuntimeError("Aedes artifact ask query did not return provenance-bearing evidence")


def main() -> int:
    try:
        check_required_files()
        check_unit_tests()
        check_source_index_build()
        check_literature_source_map()
        check_mosquito_intelligence_coverage()
        check_cli()
        check_literature_artifact()
    except Exception as exc:
        return fail(str(exc))
    print("verify_complete ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
