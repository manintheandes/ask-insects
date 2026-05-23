from __future__ import annotations

import json
from pathlib import Path

from .index import SourceIndex
from .sources.fixtures import FIXTURE_RETRIEVED_AT, FIXTURE_SOURCE_ID, load_fixture_records


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts/mosquito-v1"
DEFAULT_FIXTURE_PATH = REPO_ROOT / "data/fixtures/mosquito_records.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_fixture_index(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    db_path = artifact_dir / "source_index.sqlite"
    if db_path.exists():
        db_path.unlink()

    records = load_fixture_records(fixture_path)
    index = SourceIndex(db_path)
    index.initialize()
    index.upsert_records(records)
    summary = index.summary()

    gaps: list[dict[str, object]] = []
    status = {
        "ok": True,
        "source_id": FIXTURE_SOURCE_ID,
        "boundary": "mosquitoes first",
        "generated_at": FIXTURE_RETRIEVED_AT,
        "fully_parsed": True,
        "record_count": summary["record_count"],
        "species_count": summary["species_count"],
        "lanes": summary["lanes"],
        "gap_count": len(gaps),
    }
    receipt = {
        "source_id": FIXTURE_SOURCE_ID,
        "fixture_path": fixture_path.as_posix(),
        "artifact_dir": artifact_dir.as_posix(),
        "sqlite_index": db_path.as_posix(),
        "generated_at": FIXTURE_RETRIEVED_AT,
        "record_count": summary["record_count"],
        "lanes": summary["lanes"],
    }

    write_json(artifact_dir / "gaps.json", gaps)
    write_json(artifact_dir / "source_status.json", status)
    write_json(artifact_dir / "source_receipt.json", receipt)
    return {"ok": True, "artifact_dir": artifact_dir.as_posix(), **status}
