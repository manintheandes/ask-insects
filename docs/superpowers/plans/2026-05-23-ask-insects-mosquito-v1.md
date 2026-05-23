# Ask Insects Mosquito V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new CLI-first Ask Insects repo that indexes a local mosquito source plane and answers identity, evidence, and action questions with provenance or honest gaps.

**Architecture:** Use a small Python package with focused modules for records, SQLite indexing, source loading, planning, answering, and CLI commands. Build the first local index from fixture-backed mosquito source records so the completion gate is deterministic, while keeping source-lane boundaries compatible with later GBIF, iNaturalist, OpenAlex, and BHL fetchers.

**Tech Stack:** Python 3.11+, standard library only for V1 (`argparse`, `sqlite3`, `json`, `dataclasses`, `urllib` later), `unittest`, local SQLite, Markdown docs, YAML-like source map stored as plain text.

---

## File Structure

- Create `AGENTS.md`: repo-local operating rules and read order.
- Create `README.md`: project overview, CLI examples, source contract, and quick start.
- Create `pyproject.toml`: package metadata and `ask-insects` console script.
- Create `askinsects/__init__.py`: package version.
- Create `askinsects/__main__.py`: supports `python3 -m askinsects`.
- Create `askinsects/records.py`: normalized source record dataclasses and provenance helpers.
- Create `askinsects/index.py`: SQLite schema, read/write helpers, health/summary queries, read-only SQL guard.
- Create `askinsects/sources/__init__.py`: source package marker.
- Create `askinsects/sources/fixtures.py`: deterministic mosquito fixture source loader.
- Create `askinsects/builder.py`: builds `artifacts/mosquito-v1/source_index.sqlite`, receipts, status, and gaps.
- Create `askinsects/planner.py`: maps plain-English questions to answer shapes and source lanes.
- Create `askinsects/answer.py`: assembles identity, evidence, action, and gap answers.
- Create `askinsects/cli.py`: command-line interface.
- Create `config/source-map.yaml`: mosquito V1 source contract.
- Create `data/fixtures/mosquito_records.json`: seed records for four mosquito taxa.
- Create `docs/querying-ask-insects.md`: CLI use and answer citation rules.
- Create `docs/source-lanes.md`: taxonomy, observations/media, literature, and action lanes.
- Create `scripts/build_source_index.py`: thin wrapper around `askinsects.builder`.
- Create `scripts/verify_complete.py`: deterministic completion gate.
- Create tests under `tests/`: unit and end-to-end coverage.

## Task 1: Repo Skeleton And Docs

**Files:**
- Create: `AGENTS.md`
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `askinsects/__init__.py`
- Create: `askinsects/__main__.py`
- Create: `config/source-map.yaml`
- Create: `docs/querying-ask-insects.md`
- Create: `docs/source-lanes.md`

- [ ] **Step 1: Write package and CLI skeleton files**

Create `pyproject.toml`:

```toml
[project]
name = "askinsects"
version = "0.1.0"
description = "CLI-first local source plane for mosquito evidence."
requires-python = ">=3.11"

[project.scripts]
ask-insects = "askinsects.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `askinsects/__init__.py`:

```python
"""Ask Insects: local source-backed mosquito evidence CLI."""

__version__ = "0.1.0"
```

Create `askinsects/__main__.py`:

```python
from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write repo-local operating docs**

Create `AGENTS.md`:

```markdown
# AGENTS.md

Keep this repo focused on Ask Insects: a CLI-first local source plane for mosquito evidence.

## Read Order

1. `README.md`
2. `docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md`
3. `docs/source-lanes.md`
4. `docs/querying-ask-insects.md`
5. `config/source-map.yaml`

## Source Rule

Do not answer mosquito questions from model memory when the local source index can be queried. Use `ask-insects` commands or the SQLite index, cite provenance, and report source gaps honestly.

## Completion Gate

Run:

```bash
python3 scripts/verify_complete.py
```

Do not call the repo complete until the gate passes.
```

Create `README.md`:

```markdown
# Ask Insects

Ask Insects is a CLI-first local source plane for mosquito evidence.

V1 starts with mosquitoes, then expands to other insect groups. It follows the Ask Monarch pattern:

```text
source artifacts -> mapped lanes -> local parsed indexes -> receipts -> CLI -> answer with provenance or gap
```

## Quick Start

```bash
python3 scripts/build_source_index.py --fixtures
python3 -m askinsects health
python3 -m askinsects summary
python3 -m askinsects sources
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects ask "show mosquito observations with images in Brazil"
python3 -m askinsects ask "what should a scientist inspect next for Culex pipiens?"
python3 scripts/verify_complete.py
```

## Contract

Ask Insects answers from local indexed records. Every answer includes provenance or a clear source gap. V1 does not claim to mirror all mosquito knowledge. It proves a bounded mosquito seed source plane end to end.
```

- [ ] **Step 3: Write source map and docs**

Create `config/source-map.yaml`:

```yaml
sources:
  - id: mosquito_v1_fixtures
    name: Ask Insects mosquito V1 fixture source
    source_type: local_fixture
    boundary: mosquitoes first
    query_plane: sqlite_atomic_index
    artifact_dir: artifacts/mosquito-v1
    artifacts:
      sqlite_index: artifacts/mosquito-v1/source_index.sqlite
      source_status: artifacts/mosquito-v1/source_status.json
      source_receipt: artifacts/mosquito-v1/source_receipt.json
      gaps: artifacts/mosquito-v1/gaps.json
    lanes:
      - taxonomy
      - observations
      - media
      - literature
      - action_notes
    provenance_required: true
```

Create `docs/querying-ask-insects.md`:

```markdown
# Querying Ask Insects

Build the local source index first:

```bash
python3 scripts/build_source_index.py --fixtures
```

Then query through the CLI:

```bash
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects search observations "Brazil"
python3 -m askinsects search papers "host seeking"
python3 -m askinsects sql "select species, count(*) as records from records group by species"
```

Answers must include source, record id, and provenance locator. If evidence is missing, Ask Insects should say which source lane is missing or thin.
```

Create `docs/source-lanes.md`:

```markdown
# Source Lanes

V1 covers mosquitoes first.

## Taxonomy

Scientific names, common labels, synonyms, rank, family, genus, and species.

## Observations And Images

Observation records with date, region, source URL, media URL, and license when available.

## Videos And Media

Public moving-image or inspectable media records. V1 reports missing video coverage honestly.

## Papers And Literature

Paper metadata, abstracts when available, open access URLs, and source identifiers.

## Action Notes

Source-backed next steps for scientists, grounded in indexed observations and literature.
```

- [ ] **Step 4: Run a syntax-free documentation check**

Run:

```bash
test -f AGENTS.md && test -f README.md && test -f config/source-map.yaml && test -f docs/querying-ask-insects.md && test -f docs/source-lanes.md
```

Expected: command exits `0`.

- [ ] **Step 5: Commit skeleton**

```bash
git add AGENTS.md README.md pyproject.toml askinsects/__init__.py askinsects/__main__.py config/source-map.yaml docs/querying-ask-insects.md docs/source-lanes.md
git commit -m "chore: add ask insects repo skeleton"
```

## Task 2: Normalized Records

**Files:**
- Create: `askinsects/records.py`
- Create: `tests/test_records.py`

- [ ] **Step 1: Write failing record tests**

Create `tests/test_records.py`:

```python
import json
import unittest

from askinsects.records import EvidenceRecord, Provenance


class RecordTests(unittest.TestCase):
    def test_record_round_trip_preserves_provenance(self):
        record = EvidenceRecord(
            record_id="taxon:aedes_aegypti",
            lane="taxonomy",
            source="mosquito_v1_fixtures",
            title="Aedes aegypti",
            text="Aedes aegypti is a mosquito species.",
            species="Aedes aegypti",
            url="https://example.org/aedes",
            media_url=None,
            provenance=Provenance(
                source_id="mosquito_v1_fixtures",
                locator="data/fixtures/mosquito_records.json#taxon:aedes_aegypti",
                retrieved_at="2026-05-23T00:00:00Z",
                license="CC0",
            ),
        )

        payload = record.to_row()
        self.assertEqual(payload["record_id"], "taxon:aedes_aegypti")
        self.assertEqual(payload["provenance_json"], json.dumps(record.provenance.to_dict(), sort_keys=True))

        restored = EvidenceRecord.from_row(payload)
        self.assertEqual(restored.species, "Aedes aegypti")
        self.assertEqual(restored.provenance.locator, "data/fixtures/mosquito_records.json#taxon:aedes_aegypti")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_records -v
```

Expected: FAIL with an import error for `askinsects.records`.

- [ ] **Step 3: Implement records**

Create `askinsects/records.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class Provenance:
    source_id: str
    locator: str
    retrieved_at: str
    license: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at,
            "license": self.license,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str | None]) -> "Provenance":
        return cls(
            source_id=str(payload["source_id"]),
            locator=str(payload["locator"]),
            retrieved_at=str(payload["retrieved_at"]),
            license=payload.get("license"),
            source_url=payload.get("source_url"),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    lane: str
    source: str
    title: str
    text: str
    species: str | None
    url: str | None
    media_url: str | None
    provenance: Provenance

    def to_row(self) -> dict[str, str | None]:
        return {
            "record_id": self.record_id,
            "lane": self.lane,
            "source": self.source,
            "title": self.title,
            "text": self.text,
            "species": self.species,
            "url": self.url,
            "media_url": self.media_url,
            "provenance_json": json.dumps(self.provenance.to_dict(), sort_keys=True),
        }

    @classmethod
    def from_row(cls, row: dict[str, str | None]) -> "EvidenceRecord":
        provenance = Provenance.from_dict(json.loads(str(row["provenance_json"])))
        return cls(
            record_id=str(row["record_id"]),
            lane=str(row["lane"]),
            source=str(row["source"]),
            title=str(row["title"]),
            text=str(row["text"]),
            species=row.get("species"),
            url=row.get("url"),
            media_url=row.get("media_url"),
            provenance=provenance,
        )
```

- [ ] **Step 4: Run record tests**

Run:

```bash
python3 -m unittest tests.test_records -v
```

Expected: PASS.

- [ ] **Step 5: Commit records**

```bash
git add askinsects/records.py tests/test_records.py
git commit -m "feat: add normalized evidence records"
```

## Task 3: SQLite Index

**Files:**
- Create: `askinsects/index.py`
- Create: `tests/test_index.py`

- [ ] **Step 1: Write failing index tests**

Create `tests/test_index.py`:

```python
import tempfile
import unittest
from pathlib import Path

from askinsects.index import SourceIndex, ensure_read_only_sql
from askinsects.records import EvidenceRecord, Provenance


def sample_record(record_id="obs:1", lane="observations", text="Aedes aegypti observed in Brazil"):
    return EvidenceRecord(
        record_id=record_id,
        lane=lane,
        source="mosquito_v1_fixtures",
        title="Brazil observation",
        text=text,
        species="Aedes aegypti",
        url="https://example.org/obs/1",
        media_url="https://example.org/image.jpg",
        provenance=Provenance(
            source_id="mosquito_v1_fixtures",
            locator=f"data/fixtures/mosquito_records.json#{record_id}",
            retrieved_at="2026-05-23T00:00:00Z",
            license="CC-BY",
        ),
    )


class IndexTests(unittest.TestCase):
    def test_write_search_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index = SourceIndex(Path(tmpdir) / "source_index.sqlite")
            index.initialize()
            index.upsert_records([sample_record()])

            rows = index.search("Brazil", lane="observations", limit=5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].record_id, "obs:1")

            summary = index.summary()
            self.assertEqual(summary["record_count"], 1)
            self.assertEqual(summary["lanes"]["observations"], 1)

    def test_read_only_sql_guard(self):
        self.assertEqual(ensure_read_only_sql("select * from records"), "select * from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("delete from records")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("select * from records; drop table records")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_index -v
```

Expected: FAIL with an import error for `askinsects.index`.

- [ ] **Step 3: Implement index**

Create `askinsects/index.py`:

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sqlite3

from .records import EvidenceRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  record_id TEXT PRIMARY KEY,
  lane TEXT NOT NULL,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  species TEXT,
  url TEXT,
  media_url TEXT,
  provenance_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_lane ON records(lane);
CREATE INDEX IF NOT EXISTS idx_records_species ON records(species);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts
USING fts5(record_id UNINDEXED, lane UNINDEXED, species UNINDEXED, title, text);
"""


def ensure_read_only_sql(sql: str) -> str:
    statement = sql.strip()
    if not re.match(r"(?is)^(select|with|pragma)\b", statement):
        raise ValueError("sql is read-only; use SELECT, WITH, or PRAGMA")
    if ";" in statement.rstrip(";"):
        raise ValueError("sql accepts one read-only statement at a time")
    return statement


class SourceIndex:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_records(self, records: list[EvidenceRecord]) -> None:
        with self.connect() as conn:
            for record in records:
                row = record.to_row()
                conn.execute(
                    """
                    INSERT INTO records (
                      record_id, lane, source, title, text, species, url, media_url, provenance_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                      lane=excluded.lane,
                      source=excluded.source,
                      title=excluded.title,
                      text=excluded.text,
                      species=excluded.species,
                      url=excluded.url,
                      media_url=excluded.media_url,
                      provenance_json=excluded.provenance_json
                    """,
                    (
                        row["record_id"],
                        row["lane"],
                        row["source"],
                        row["title"],
                        row["text"],
                        row["species"],
                        row["url"],
                        row["media_url"],
                        row["provenance_json"],
                    ),
                )
                conn.execute("DELETE FROM records_fts WHERE record_id=?", (record.record_id,))
                conn.execute(
                    "INSERT INTO records_fts(record_id, lane, species, title, text) VALUES (?, ?, ?, ?, ?)",
                    (record.record_id, record.lane, record.species, record.title, record.text),
                )

    def search(self, query: str, lane: str | None = None, limit: int = 10) -> list[EvidenceRecord]:
        terms = [term for term in re.findall(r"[A-Za-z0-9]+", query) if term]
        if not terms:
            return []
        match = " AND ".join(f"{term}*" for term in terms)
        params: list[object] = [match]
        lane_filter = ""
        if lane:
            lane_filter = "AND r.lane = ?"
            params.append(lane)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.*
                FROM records_fts f
                JOIN records r ON r.record_id = f.record_id
                WHERE records_fts MATCH ?
                {lane_filter}
                ORDER BY bm25(records_fts)
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [EvidenceRecord.from_row(dict(row)) for row in rows]

    def sql(self, sql: str, limit: int = 100) -> list[dict[str, object]]:
        statement = ensure_read_only_sql(sql)
        with self.connect() as conn:
            cursor = conn.execute(statement)
            rows = []
            for row in cursor:
                rows.append(dict(row))
                if len(rows) >= limit:
                    break
        return rows

    def summary(self) -> dict[str, object]:
        with self.connect() as conn:
            rows = conn.execute("SELECT lane, COUNT(*) AS count FROM records GROUP BY lane").fetchall()
            record_count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            species_count = conn.execute("SELECT COUNT(DISTINCT species) FROM records WHERE species IS NOT NULL").fetchone()[0]
        return {
            "record_count": int(record_count),
            "species_count": int(species_count),
            "lanes": dict(Counter({row["lane"]: row["count"] for row in rows})),
        }
```

- [ ] **Step 4: Run index tests**

Run:

```bash
python3 -m unittest tests.test_index -v
```

Expected: PASS.

- [ ] **Step 5: Commit index**

```bash
git add askinsects/index.py tests/test_index.py
git commit -m "feat: add local SQLite source index"
```

## Task 4: Fixture Source Loader

**Files:**
- Create: `askinsects/sources/__init__.py`
- Create: `askinsects/sources/fixtures.py`
- Create: `data/fixtures/mosquito_records.json`
- Create: `tests/test_fixture_source.py`

- [ ] **Step 1: Write fixture data**

Create `data/fixtures/mosquito_records.json`:

```json
[
  {
    "record_id": "taxon:aedes_aegypti",
    "lane": "taxonomy",
    "title": "Aedes aegypti",
    "text": "Aedes aegypti is a mosquito species strongly associated with human habitats and widely studied in public health, behavior, and vector-control literature.",
    "species": "Aedes aegypti",
    "url": "https://www.gbif.org/species/1651891",
    "media_url": null,
    "license": "CC0"
  },
  {
    "record_id": "obs:aedes_aegypti_brazil_image",
    "lane": "observations",
    "title": "Aedes aegypti observation with image in Brazil",
    "text": "A public mosquito observation record reports Aedes aegypti in Brazil with an inspectable image and location context.",
    "species": "Aedes aegypti",
    "url": "https://www.inaturalist.org/observations/example-aedes-brazil",
    "media_url": "https://static.inaturalist.org/photos/example-aedes-brazil.jpg",
    "license": "CC-BY"
  },
  {
    "record_id": "paper:aedes_host_seeking",
    "lane": "literature",
    "title": "Mosquito host seeking and human-associated cues",
    "text": "Literature about Aedes aegypti host seeking discusses odor, heat, carbon dioxide, and visual cues as evidence-backed signals to inspect.",
    "species": "Aedes aegypti",
    "url": "https://openalex.org/works/example-aedes-host-seeking",
    "media_url": null,
    "license": "metadata"
  },
  {
    "record_id": "taxon:aedes_albopictus",
    "lane": "taxonomy",
    "title": "Aedes albopictus",
    "text": "Aedes albopictus is a mosquito species known as the Asian tiger mosquito and is globally important in invasion ecology and vector surveillance.",
    "species": "Aedes albopictus",
    "url": "https://www.gbif.org/species/1651431",
    "media_url": null,
    "license": "CC0"
  },
  {
    "record_id": "taxon:anopheles_gambiae",
    "lane": "taxonomy",
    "title": "Anopheles gambiae",
    "text": "Anopheles gambiae is a mosquito species complex central to malaria-vector research and field surveillance.",
    "species": "Anopheles gambiae",
    "url": "https://www.gbif.org/species/1651041",
    "media_url": null,
    "license": "CC0"
  },
  {
    "record_id": "taxon:culex_pipiens",
    "lane": "taxonomy",
    "title": "Culex pipiens",
    "text": "Culex pipiens is a mosquito species complex often discussed in urban ecology, bird-associated feeding, and disease-vector monitoring.",
    "species": "Culex pipiens",
    "url": "https://www.gbif.org/species/1652358",
    "media_url": null,
    "license": "CC0"
  },
  {
    "record_id": "action:culex_pipiens_next_steps",
    "lane": "action_notes",
    "title": "Culex pipiens inspection next steps",
    "text": "For Culex pipiens, inspect local observation seasonality, nearby standing-water habitat, and literature about bird-associated host choice before making intervention claims.",
    "species": "Culex pipiens",
    "url": "docs/source-lanes.md#action-notes",
    "media_url": null,
    "license": "repo-authored"
  }
]
```

- [ ] **Step 2: Write failing fixture loader test**

Create `tests/test_fixture_source.py`:

```python
import unittest
from pathlib import Path

from askinsects.sources.fixtures import load_fixture_records


class FixtureSourceTests(unittest.TestCase):
    def test_fixture_loader_returns_records_with_provenance(self):
        records = load_fixture_records(Path("data/fixtures/mosquito_records.json"))

        self.assertGreaterEqual(len(records), 7)
        first = records[0]
        self.assertEqual(first.source, "mosquito_v1_fixtures")
        self.assertTrue(first.provenance.locator.startswith("data/fixtures/mosquito_records.json#"))
        self.assertEqual(first.provenance.retrieved_at, "2026-05-23T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_fixture_source -v
```

Expected: FAIL with an import error for `askinsects.sources.fixtures`.

- [ ] **Step 4: Implement fixture loader**

Create `askinsects/sources/__init__.py`:

```python
"""Source loaders for Ask Insects."""
```

Create `askinsects/sources/fixtures.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from askinsects.records import EvidenceRecord, Provenance


FIXTURE_RETRIEVED_AT = "2026-05-23T00:00:00Z"
FIXTURE_SOURCE_ID = "mosquito_v1_fixtures"


def load_fixture_records(path: Path) -> list[EvidenceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: list[EvidenceRecord] = []
    for item in payload:
        record_id = str(item["record_id"])
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane=str(item["lane"]),
                source=FIXTURE_SOURCE_ID,
                title=str(item["title"]),
                text=str(item["text"]),
                species=item.get("species"),
                url=item.get("url"),
                media_url=item.get("media_url"),
                provenance=Provenance(
                    source_id=FIXTURE_SOURCE_ID,
                    locator=f"{path.as_posix()}#{record_id}",
                    retrieved_at=FIXTURE_RETRIEVED_AT,
                    license=item.get("license"),
                    source_url=item.get("url"),
                ),
            )
        )
    return records
```

- [ ] **Step 5: Run fixture tests**

Run:

```bash
python3 -m unittest tests.test_fixture_source -v
```

Expected: PASS.

- [ ] **Step 6: Commit fixtures**

```bash
git add askinsects/sources/__init__.py askinsects/sources/fixtures.py data/fixtures/mosquito_records.json tests/test_fixture_source.py
git commit -m "feat: add mosquito fixture source lane"
```

## Task 5: Build Artifacts And Receipts

**Files:**
- Create: `askinsects/builder.py`
- Create: `scripts/build_source_index.py`
- Create: `tests/test_builder.py`

- [ ] **Step 1: Write failing builder test**

Create `tests/test_builder.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from askinsects.builder import build_fixture_index


class BuilderTests(unittest.TestCase):
    def test_build_fixture_index_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            result = build_fixture_index(
                fixture_path=Path("data/fixtures/mosquito_records.json"),
                artifact_dir=artifact_dir,
            )

            self.assertTrue(result["ok"])
            self.assertTrue((artifact_dir / "source_index.sqlite").exists())
            self.assertTrue((artifact_dir / "source_status.json").exists())
            self.assertTrue((artifact_dir / "source_receipt.json").exists())
            self.assertTrue((artifact_dir / "gaps.json").exists())

            status = json.loads((artifact_dir / "source_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["source_id"], "mosquito_v1_fixtures")
            self.assertTrue(status["fully_parsed"])
            self.assertEqual(status["gap_count"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_builder -v
```

Expected: FAIL with an import error for `askinsects.builder`.

- [ ] **Step 3: Implement builder**

Create `askinsects/builder.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from .index import SourceIndex
from .sources.fixtures import FIXTURE_RETRIEVED_AT, FIXTURE_SOURCE_ID, load_fixture_records


DEFAULT_ARTIFACT_DIR = Path("artifacts/mosquito-v1")
DEFAULT_FIXTURE_PATH = Path("data/fixtures/mosquito_records.json")


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
```

Create `scripts/build_source_index.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from askinsects.builder import DEFAULT_ARTIFACT_DIR, DEFAULT_FIXTURE_PATH, build_fixture_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Ask Insects local mosquito source index.")
    parser.add_argument("--fixtures", action="store_true", help="Build from deterministic fixture records.")
    parser.add_argument("--fixture-path", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    args = parser.parse_args()

    if not args.fixtures:
        parser.error("V1 supports --fixtures. Live source fetchers will be added after the local plane is proven.")

    result = build_fixture_index(Path(args.fixture_path), Path(args.artifact_dir))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run builder tests and script**

Run:

```bash
python3 -m unittest tests.test_builder -v
python3 scripts/build_source_index.py --fixtures
```

Expected: tests PASS and script prints JSON containing `"ok": true`.

- [ ] **Step 5: Commit builder**

```bash
git add askinsects/builder.py scripts/build_source_index.py tests/test_builder.py
git commit -m "feat: build local mosquito source artifacts"
```

## Task 6: Planner And Answer Layer

**Files:**
- Create: `askinsects/planner.py`
- Create: `askinsects/answer.py`
- Create: `tests/test_answer.py`

- [ ] **Step 1: Write failing answer tests**

Create `tests/test_answer.py`:

```python
import tempfile
import unittest
from pathlib import Path

from askinsects.answer import answer_question
from askinsects.builder import build_fixture_index
from askinsects.planner import plan_question


class AnswerTests(unittest.TestCase):
    def test_planner_routes_identity_evidence_action_and_gap(self):
        self.assertEqual(plan_question("what do we know about Aedes aegypti?").answer_shape, "identity")
        self.assertEqual(plan_question("show mosquito observations with images in Brazil").answer_shape, "evidence")
        self.assertEqual(plan_question("what should a scientist inspect next for Culex pipiens?").answer_shape, "action")
        self.assertEqual(plan_question("show mosquito videos from Brazil").answer_shape, "media")

    def test_answers_include_provenance_or_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            build_fixture_index(artifact_dir=artifact_dir)

            identity = answer_question("what do we know about Aedes aegypti?", artifact_dir=artifact_dir)
            self.assertTrue(identity["ok"])
            self.assertEqual(identity["answer_shape"], "identity")
            self.assertTrue(identity["evidence"])
            self.assertIn("provenance", identity["evidence"][0])

            action = answer_question("what should a scientist inspect next for Culex pipiens?", artifact_dir=artifact_dir)
            self.assertTrue(action["ok"])
            self.assertEqual(action["answer_shape"], "action")
            self.assertTrue(action["evidence"])

            media_gap = answer_question("show mosquito videos from Brazil", artifact_dir=artifact_dir)
            self.assertFalse(media_gap["ok"])
            self.assertEqual(media_gap["source_gap"]["lane"], "media")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_answer -v
```

Expected: FAIL with import errors for `askinsects.answer` or `askinsects.planner`.

- [ ] **Step 3: Implement planner**

Create `askinsects/planner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    question: str
    answer_shape: str
    lanes: tuple[str, ...]
    search_query: str


def plan_question(question: str) -> QueryPlan:
    q = question.lower()
    if "video" in q or "moving" in q:
        return QueryPlan(question, "media", ("media",), question)
    if "what should" in q or "inspect next" in q or "take action" in q or "next step" in q:
        return QueryPlan(question, "action", ("action_notes", "literature", "observations"), question)
    if "observation" in q or "image" in q or "photo" in q or "show" in q:
        return QueryPlan(question, "evidence", ("observations", "media", "literature"), question)
    return QueryPlan(question, "identity", ("taxonomy", "literature", "observations"), question)
```

- [ ] **Step 4: Implement answer layer**

Create `askinsects/answer.py`:

```python
from __future__ import annotations

from pathlib import Path

from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex
from .planner import QueryPlan, plan_question
from .records import EvidenceRecord


def record_to_evidence(record: EvidenceRecord) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "lane": record.lane,
        "source": record.source,
        "title": record.title,
        "text": record.text,
        "species": record.species,
        "url": record.url,
        "media_url": record.media_url,
        "provenance": record.provenance.to_dict(),
    }


def source_gap(plan: QueryPlan, reason: str) -> dict[str, object]:
    lane = plan.lanes[0] if plan.lanes else "unknown"
    return {
        "ok": False,
        "answer_shape": plan.answer_shape,
        "answer": f"I do not see enough indexed mosquito evidence for this question yet. {reason}",
        "evidence": [],
        "source_gap": {
            "lane": lane,
            "reason": reason,
            "checked_lanes": list(plan.lanes),
        },
    }


def _answer_text(plan: QueryPlan, records: list[EvidenceRecord]) -> str:
    if plan.answer_shape == "identity":
        return f"From the local mosquito index, {records[0].title}: {records[0].text}"
    if plan.answer_shape == "evidence":
        return f"I found {len(records)} indexed mosquito evidence record(s) matching the question."
    if plan.answer_shape == "action":
        return f"The local mosquito index supports this next step: {records[0].text}"
    if plan.answer_shape == "media":
        return f"I found {len(records)} indexed mosquito media record(s)."
    return f"I found {len(records)} indexed mosquito record(s)."


def answer_question(question: str, artifact_dir: Path = DEFAULT_ARTIFACT_DIR, limit: int = 5) -> dict[str, object]:
    plan = plan_question(question)
    index = SourceIndex(Path(artifact_dir) / "source_index.sqlite")
    all_records: list[EvidenceRecord] = []
    for lane in plan.lanes:
        all_records.extend(index.search(plan.search_query, lane=lane, limit=limit))
        if len(all_records) >= limit:
            break

    if plan.answer_shape == "media":
        media_records = [record for record in all_records if record.media_url and record.lane == "media"]
        if not media_records:
            return source_gap(plan, "The mosquito V1 index has no matching moving-image media records.")
        all_records = media_records

    if not all_records:
        return source_gap(plan, "No matching local records were found in the checked lanes.")

    evidence = [record_to_evidence(record) for record in all_records[:limit]]
    return {
        "ok": True,
        "answer_shape": plan.answer_shape,
        "answer": _answer_text(plan, all_records),
        "evidence": evidence,
        "source_gap": None,
    }
```

- [ ] **Step 5: Run answer tests**

Run:

```bash
python3 -m unittest tests.test_answer -v
```

Expected: PASS.

- [ ] **Step 6: Commit planner and answers**

```bash
git add askinsects/planner.py askinsects/answer.py tests/test_answer.py
git commit -m "feat: answer mosquito questions from local evidence"
```

## Task 7: CLI Commands

**Files:**
- Create: `askinsects/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import json
import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
    def test_health_summary_sources_and_ask(self):
        subprocess.run([sys.executable, "scripts/build_source_index.py", "--fixtures"], check=True)

        health = subprocess.check_output([sys.executable, "-m", "askinsects", "health"], text=True)
        self.assertTrue(json.loads(health)["ok"])

        summary = subprocess.check_output([sys.executable, "-m", "askinsects", "summary"], text=True)
        self.assertGreater(json.loads(summary)["record_count"], 0)

        sources = subprocess.check_output([sys.executable, "-m", "askinsects", "sources"], text=True)
        self.assertIn("mosquito_v1_fixtures", sources)

        answer = subprocess.check_output(
            [sys.executable, "-m", "askinsects", "ask", "what do we know about Aedes aegypti?", "--json"],
            text=True,
        )
        payload = json.loads(answer)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["evidence"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_cli -v
```

Expected: FAIL because `askinsects.cli` does not exist.

- [ ] **Step 3: Implement CLI**

Create `askinsects/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .answer import answer_question
from .builder import DEFAULT_ARTIFACT_DIR
from .index import SourceIndex


def emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def render_answer(payload: dict[str, object]) -> str:
    lines = [str(payload["answer"]), ""]
    evidence = payload.get("evidence") or []
    if evidence:
        lines.append("Evidence:")
        for item in evidence:
            provenance = item["provenance"]
            lines.append(f"- {item['title']} [{item['source']} {item['record_id']}]")
            lines.append(f"  locator: {provenance['locator']}")
    gap = payload.get("source_gap")
    if gap:
        lines.append("Source gap:")
        lines.append(f"- lane: {gap['lane']}")
        lines.append(f"- reason: {gap['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ask-insects")
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("summary")
    sub.add_parser("sources")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument("--json", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("lane")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    sql = sub.add_parser("sql")
    sql.add_argument("sql")
    sql.add_argument("--limit", type=int, default=100)

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)
    index = SourceIndex(artifact_dir / "source_index.sqlite")

    if args.command == "health":
        db_exists = (artifact_dir / "source_index.sqlite").exists()
        status_exists = (artifact_dir / "source_status.json").exists()
        emit({"ok": db_exists and status_exists, "db_exists": db_exists, "status_exists": status_exists})
        return 0
    if args.command == "summary":
        emit(index.summary())
        return 0
    if args.command == "sources":
        emit({"sources": ["mosquito_v1_fixtures"], "artifact_dir": artifact_dir.as_posix()})
        return 0
    if args.command == "ask":
        payload = answer_question(args.question, artifact_dir=artifact_dir, limit=args.limit)
        if args.json:
            emit(payload)
        else:
            print(render_answer(payload))
        return 0 if payload.get("ok") else 2
    if args.command == "search":
        rows = [record.to_row() for record in index.search(args.query, lane=args.lane, limit=args.limit)]
        emit({"ok": True, "rows": rows})
        return 0
    if args.command == "sql":
        emit({"ok": True, "rows": index.sql(args.sql, limit=args.limit)})
        return 0
    parser.error("unknown command")
    return 1
```

- [ ] **Step 4: Run CLI tests and smoke commands**

Run:

```bash
python3 -m unittest tests.test_cli -v
python3 -m askinsects ask "what do we know about Aedes aegypti?"
python3 -m askinsects ask "show mosquito videos from Brazil" --json; test "$?" = "2"
```

Expected: tests PASS; first ask prints Evidence; media ask returns exit code `2` with source gap JSON.

- [ ] **Step 5: Commit CLI**

```bash
git add askinsects/cli.py tests/test_cli.py
git commit -m "feat: add ask-insects CLI"
```

## Task 8: Completion Gate

**Files:**
- Create: `scripts/verify_complete.py`
- Create: `tests/test_verify_complete.py`

- [ ] **Step 1: Write failing completion-gate test**

Create `tests/test_verify_complete.py`:

```python
import subprocess
import sys
import unittest


class VerifyCompleteTests(unittest.TestCase):
    def test_verify_complete_passes(self):
        proc = subprocess.run(
            [sys.executable, "scripts/verify_complete.py"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("verify_complete ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_verify_complete -v
```

Expected: FAIL because `scripts/verify_complete.py` does not exist.

- [ ] **Step 3: Implement completion gate**

Create `scripts/verify_complete.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "config/source-map.yaml",
    "docs/querying-ask-insects.md",
    "docs/source-lanes.md",
    "docs/superpowers/specs/2026-05-23-ask-insects-mosquito-v1-design.md",
    "askinsects/__init__.py",
    "askinsects/__main__.py",
    "askinsects/cli.py",
    "askinsects/records.py",
    "askinsects/index.py",
    "askinsects/planner.py",
    "askinsects/answer.py",
    "askinsects/builder.py",
    "data/fixtures/mosquito_records.json",
]


def run(command: list[str], allow_exit: int = 0) -> str:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != allow_exit:
        raise AssertionError(f"{' '.join(command)} exited {proc.returncode}, expected {allow_exit}\n{proc.stdout}")
    return proc.stdout


def main() -> int:
    missing = [path for path in REQUIRED_FILES if not Path(path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "scripts/build_source_index.py", "--fixtures"])

    health = json.loads(run([sys.executable, "-m", "askinsects", "health"]))
    if not health.get("ok"):
        raise SystemExit(f"health failed: {health}")

    summary = json.loads(run([sys.executable, "-m", "askinsects", "summary"]))
    if summary.get("record_count", 0) < 7:
        raise SystemExit(f"summary record_count too low: {summary}")

    sources = json.loads(run([sys.executable, "-m", "askinsects", "sources"]))
    if "mosquito_v1_fixtures" not in sources.get("sources", []):
        raise SystemExit(f"source missing: {sources}")

    identity = json.loads(run([sys.executable, "-m", "askinsects", "ask", "what do we know about Aedes aegypti?", "--json"]))
    if not identity.get("ok") or not identity.get("evidence"):
        raise SystemExit(f"identity answer failed: {identity}")

    evidence = json.loads(run([sys.executable, "-m", "askinsects", "ask", "show mosquito observations with images in Brazil", "--json"]))
    if not evidence.get("ok") or not evidence.get("evidence"):
        raise SystemExit(f"evidence answer failed: {evidence}")

    action = json.loads(run([sys.executable, "-m", "askinsects", "ask", "what should a scientist inspect next for Culex pipiens?", "--json"]))
    if not action.get("ok") or not action.get("evidence"):
        raise SystemExit(f"action answer failed: {action}")

    media_gap = json.loads(run([sys.executable, "-m", "askinsects", "ask", "show mosquito videos from Brazil", "--json"], allow_exit=2))
    if media_gap.get("ok") or not media_gap.get("source_gap"):
        raise SystemExit(f"media gap failed: {media_gap}")

    print("verify_complete ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run completion-gate test**

Run:

```bash
python3 -m unittest tests.test_verify_complete -v
python3 scripts/verify_complete.py
```

Expected: PASS and `verify_complete ok`.

- [ ] **Step 5: Commit completion gate**

```bash
git add scripts/verify_complete.py tests/test_verify_complete.py
git commit -m "test: add ask insects completion gate"
```

## Task 9: Final Verification And Repo Hygiene

**Files:**
- Modify: `.gitignore`
- No other file should change in this task unless a verification command exposes a concrete defect in a file created by an earlier task.

- [ ] **Step 1: Ignore generated artifacts**

Modify `.gitignore`:

```gitignore
.superpowers/
__pycache__/
*.pyc
artifacts/
```

- [ ] **Step 2: Run full verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/verify_complete.py
git status --short
```

Expected: tests PASS, completion gate prints `verify_complete ok`, and `git status --short` only shows intentional tracked changes before final commit.

- [ ] **Step 3: Commit hygiene changes**

```bash
git add .gitignore
git commit -m "chore: ignore generated ask insects artifacts"
```

- [ ] **Step 4: Final proof command**

Run:

```bash
python3 scripts/verify_complete.py
```

Expected: `verify_complete ok`.

## Self-Review Notes

- Spec coverage: this plan covers the CLI-first interface, mosquito V1 boundary, local indexes, source lanes, provenance, honest source gaps, completion gate, and expansion path.
- Scope check: live public API fetchers are intentionally excluded from the first implementation because V1 must first prove the local source plane end to end. The source-lane structure keeps live GBIF, iNaturalist, OpenAlex, and BHL fetchers compatible with later work.
- Type consistency: `EvidenceRecord`, `Provenance`, `SourceIndex`, `QueryPlan`, and `answer_question` are introduced before later tasks use them.
- Placeholder scan: no implementation step should require unstated code or undefined functions.
