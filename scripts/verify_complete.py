#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "config/source-map.yaml",
    "data/fixtures/mosquito_records.json",
    "docs/querying-ask-insects.md",
    "docs/source-lanes.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-gbif-v1-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-inaturalist-v1-design.md",
    "docs/superpowers/specs/2026-05-23-inaturalist-deep-aedes-ingest-design.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-hosted-vm-infra-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-genomics-lane-design.md",
    "docs/superpowers/specs/2026-05-23-aedes-aegypti-neurobiology-lane-design.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-mosquito-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-gbif-v1.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-inaturalist-v1.md",
    "docs/superpowers/plans/2026-05-23-inaturalist-deep-aedes-ingest.md",
    "docs/superpowers/plans/2026-05-23-ask-insects-hosted-vm-infra.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-genomics-lane.md",
    "docs/superpowers/plans/2026-05-23-aedes-aegypti-neurobiology-lane.md",
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
    "askinsects/sources/__init__.py",
    "askinsects/sources/fixtures.py",
    "askinsects/sources/gbif.py",
    "askinsects/sources/inaturalist.py",
    "askinsects/sources/ncbi_genome.py",
    "askinsects/sources/neurobiology.py",
    "scripts/build_source_index.py",
    "scripts/deploy_gce_app.sh",
    "scripts/deploy_gce_vm.sh",
    "scripts/verify_complete.py",
    "deploy/systemd/ask-insects.service",
    "tests/test_answer.py",
    "tests/test_builder.py",
    "tests/test_cli.py",
    "tests/test_cli_hosted.py",
    "tests/test_deploy_files.py",
    "tests/test_fixture_source.py",
    "tests/test_gbif_source.py",
    "tests/test_hosted_client.py",
    "tests/test_inaturalist_source.py",
    "tests/test_index.py",
    "tests/test_ncbi_genome_source.py",
    "tests/test_neurobiology_source.py",
    "tests/test_records.py",
    "tests/test_server.py",
    "tests/test_verify_complete.py",
)

UNIT_TEST_MODULES = (
    "tests.test_answer",
    "tests.test_builder",
    "tests.test_cli",
    "tests.test_cli_hosted",
    "tests.test_deploy_files",
    "tests.test_fixture_source",
    "tests.test_gbif_source",
    "tests.test_hosted_client",
    "tests.test_inaturalist_source",
    "tests.test_index",
    "tests.test_ncbi_genome_source",
    "tests.test_neurobiology_source",
    "tests.test_records",
    "tests.test_server",
)


def fail(message: str) -> int:
    print(f"verify_complete failed: {message}", file=sys.stderr)
    return 1


def run_command(args: list[str], *, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)
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
    payload = run_json([sys.executable, "scripts/build_source_index.py", "--fixtures"])
    if not payload.get("ok"):
        raise RuntimeError("fixture index build did not report ok true")
    if int(payload.get("record_count", 0)) < 7:
        raise RuntimeError("fixture index build produced fewer than 7 records")


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


def main() -> int:
    try:
        check_required_files()
        check_unit_tests()
        check_source_index_build()
        check_cli()
    except Exception as exc:
        return fail(str(exc))
    print("verify_complete ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
