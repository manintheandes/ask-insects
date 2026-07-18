from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from askinsects.index import SourceIndex
from askinsects.sources.plutella_xylostella_literature import (
    PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
    PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS,
    fetch_plutella_xylostella_literature_records,
)
from scripts.ingest_plutella_xylostella_literature import (
    ingest_plutella_xylostella_literature,
)


RETRIEVED_AT = "2026-07-17T00:00:00Z"


def inverted(text: str) -> dict[str, list[int]]:
    return {token: [index] for index, token in enumerate(text.split())}


def openalex_work(work_id: str) -> dict[str, object]:
    return {
        "id": f"https://openalex.org/{work_id}",
        "display_name": f"Direct Plutella xylostella study {work_id}",
        "doi": f"https://doi.org/10.1000/{work_id.casefold()}",
        "abstract_inverted_index": inverted(
            "Direct Plutella xylostella behavior, host finding, oviposition, and crop evidence."
        ),
        "primary_location": {
            "source": {"display_name": "Primary Insect Science Journal"}
        },
    }


class PlutellaXylostellaLiteratureSourceTests(unittest.TestCase):
    def test_curated_work_set_includes_direct_cues_and_repellent_assays(self):
        self.assertTrue(
            {
                "W1996826081",
                "W2164349268",
                "W3093961030",
                "W2141627881",
                "W4383535925",
                "W4393189143",
            }.issubset(set(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS))
        )

    def test_exact_openalex_works_become_dedicated_dbm_records(self):
        requested: list[str] = []

        def fake_fetch(url: str) -> dict[str, object]:
            requested.append(url)
            return openalex_work(url.rsplit("/", 1)[-1])

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_plutella_xylostella_literature_records(
                raw_dir=Path(tmpdir) / "raw" / "plutella_xylostella_literature",
                fetch_json=fake_fetch,
                retrieved_at=RETRIEVED_AT,
            )

        self.assertEqual(len(result.records), len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS))
        self.assertEqual(len(requested), len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS))
        self.assertFalse(result.gaps)
        for record in result.records:
            with self.subTest(record_id=record.record_id):
                self.assertTrue(record.record_id.startswith("dbm:openalex:"))
                self.assertEqual(
                    record.source,
                    PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                )
                self.assertEqual(record.species, "Plutella xylostella")
                self.assertIn("Plutella xylostella", record.title)
                self.assertTrue(str(record.url).startswith("10."))
                self.assertEqual(
                    record.provenance.source_id,
                    PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,
                )
                self.assertIn(
                    "raw/plutella_xylostella_literature/",
                    record.provenance.locator,
                )
                self.assertNotIn("drosophila_suzukii", record.provenance.locator)
                self.assertNotIn("aedes", record.provenance.locator.casefold())

    def test_non_dbm_openalex_result_is_rejected_as_a_source_gap(self):
        bad_id = PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS[0]

        def fake_fetch(url: str) -> dict[str, object]:
            work_id = url.rsplit("/", 1)[-1]
            if work_id == bad_id:
                payload = openalex_work(work_id)
                payload["display_name"] = "Unrelated mosquito paper"
                payload["abstract_inverted_index"] = inverted(
                    "This source does not name the focal moth species."
                )
                return payload
            return openalex_work(work_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_plutella_xylostella_literature_records(
                raw_dir=Path(tmpdir) / "raw" / "plutella_xylostella_literature",
                fetch_json=fake_fetch,
                retrieved_at=RETRIEVED_AT,
            )

        self.assertEqual(
            len(result.records),
            len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS) - 1,
        )
        self.assertEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0]["reason"], "exact_species_not_confirmed")
        self.assertEqual(result.gaps[0]["openalex_work_id"], bad_id)

    def test_ingest_installs_all_exact_records_and_preserves_them_on_partial_refresh(self):
        def complete_fetch(url: str) -> dict[str, object]:
            return openalex_work(url.rsplit("/", 1)[-1])

        failed_id = PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS[0]

        def partial_fetch(url: str) -> dict[str, object]:
            if url.endswith(f"/{failed_id}"):
                raise OSError("temporary OpenAlex failure")
            return complete_fetch(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            with (
                patch.object(
                    SourceIndex,
                    "summary",
                    side_effect=AssertionError("full index summary is not allowed"),
                ),
                patch.object(
                    SourceIndex,
                    "sql",
                    side_effect=AssertionError("broad index SQL is not allowed"),
                ),
            ):
                installed = ingest_plutella_xylostella_literature(
                    artifact_dir=artifact_dir,
                    fetch_json=complete_fetch,
                    retrieved_at=RETRIEVED_AT,
                )
                failed_refresh = ingest_plutella_xylostella_literature(
                    artifact_dir=artifact_dir,
                    fetch_json=partial_fetch,
                    retrieved_at="2026-07-18T00:00:00Z",
                )
                recovered = ingest_plutella_xylostella_literature(
                    artifact_dir=artifact_dir,
                    fetch_json=complete_fetch,
                    retrieved_at="2026-07-19T00:00:00Z",
                )
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            retained = index.sql(
                "select record_id from records where record_id like 'dbm:openalex:%'",
                limit=20,
            )
            with index.connect() as connection:
                searchable_count = int(
                    connection.execute(
                        "select count(*) as n from records_fts f "
                        "join records r on r.record_id=f.record_id where r.source=?",
                        (PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID,),
                    ).fetchone()["n"]
                )
            status = json.loads(
                (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            )

        self.assertTrue(installed["ok"])
        self.assertTrue(installed["complete"])
        self.assertFalse(failed_refresh["ok"])
        self.assertFalse(failed_refresh["complete"])
        self.assertTrue(failed_refresh["preserved_existing"])
        self.assertTrue(recovered["ok"])
        self.assertTrue(recovered["complete"])
        self.assertEqual(len(retained), len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS))
        self.assertEqual(
            searchable_count,
            len(PLUTELLA_XYLOSTELLA_OPENALEX_WORK_IDS),
        )
        self.assertEqual(
            status["source_counts"][PLUTELLA_XYLOSTELLA_LITERATURE_SOURCE_ID],
            recovered["record_count"],
        )
        self.assertEqual(
            status["record_count"],
            recovered["record_count"],
        )
        self.assertEqual(
            status["lanes"]["literature"],
            recovered["record_count"],
        )


if __name__ == "__main__":
    unittest.main()
