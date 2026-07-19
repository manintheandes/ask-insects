from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from askinsects.index import SourceIndex
from askinsects.sources.human_repellent_testing_guidance import (
    HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
    build_human_repellent_testing_guidance_records,
)
from scripts.ingest_human_repellent_testing_guidance import (
    ingest_human_repellent_testing_guidance,
)


class HumanRepellentTestingGuidanceSourceTests(unittest.TestCase):
    def test_records_point_to_exact_original_guidance_sources(self):
        records = build_human_repellent_testing_guidance_records(
            retrieved_at="2026-07-17T00:00:00Z"
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(
            {record.record_id for record in records},
            {
                "human_repellent_guidance:who:2009.4",
                "human_repellent_guidance:epa:810.3700",
            },
        )
        for record in records:
            with self.subTest(record_id=record.record_id):
                self.assertEqual(
                    record.source,
                    HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
                )
                self.assertEqual(
                    record.provenance.source_id,
                    HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
                )
                self.assertTrue(record.title)
                self.assertTrue(str(record.url).startswith("https://"))
                self.assertTrue(record.provenance.locator.startswith("https://"))
                self.assertNotIn("config/", record.provenance.locator)
                self.assertEqual(record.provenance.source_url, record.url)

        epa = next(
            record
            for record in records
            if record.record_id == "human_repellent_guidance:epa:810.3700"
        )
        who = next(
            record
            for record in records
            if record.record_id == "human_repellent_guidance:who:2009.4"
        )
        self.assertEqual(
            who.provenance.locator,
            "https://iris.who.int/server/api/core/bitstreams/"
            "bf0c03d6-ccf4-428d-a299-23c6a74b2b04/content#page=15",
        )
        self.assertEqual(
            who.title,
            "Guidelines for efficacy testing of mosquito repellents for human skin",
        )
        self.assertEqual(
            epa.title,
            "Product Performance Test Guidelines OPPTS 810.3700: Insect "
            "Repellents to be Applied to Human Skin",
        )
        self.assertEqual(
            epa.url,
            "https://www.epa.gov/system/files/documents/2023-12/"
            "1d.-oppts-810.3700-guidelines-july-7-2010.pdf",
        )
        self.assertEqual(epa.provenance.locator, f"{epa.url}#page=11")

    def test_ingest_installs_the_two_exact_guidance_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "mosquito-v1"
            index = SourceIndex(artifact_dir / "source_index.sqlite")
            index.initialize()
            initial_records = build_human_repellent_testing_guidance_records(
                retrieved_at="2026-07-16T00:00:00Z"
            )
            who = next(
                record
                for record in initial_records
                if record.record_id == "human_repellent_guidance:who:2009.4"
            )
            index.upsert_records(
                [
                    replace(
                        who,
                        title="Obsolete WHO title",
                        text="oldwhoftsmarker",
                    ),
                    replace(
                        who,
                        record_id="human_repellent_guidance:pubmed:26811157",
                        title="Obsolete review record",
                        text="washinreviewmarker",
                    ),
                ]
            )
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
                result = ingest_human_repellent_testing_guidance(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-17T00:00:00Z",
                )
                repeated = ingest_human_repellent_testing_guidance(
                    artifact_dir=artifact_dir,
                    retrieved_at="2026-07-18T00:00:00Z",
                )
            with index.connect() as connection:
                rows = connection.execute(
                    "select title, url from records where source=? order by record_id",
                    (HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,),
                ).fetchall()
                searchable_count = int(
                    connection.execute(
                        "select count(*) as n from records_fts f "
                        "join records r on r.record_id=f.record_id where r.source=?",
                        (HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,),
                    ).fetchone()["n"]
                )
                fts_rows = connection.execute(
                    "select record_id, title, text from records_fts "
                    "where record_id like 'human_repellent_guidance:%' "
                    "order by record_id"
                ).fetchall()
            status = json.loads(
                (artifact_dir / "source_status.json").read_text(encoding="utf-8")
            )

        self.assertTrue(result["ok"])
        self.assertTrue(repeated["ok"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(searchable_count, 2)
        self.assertEqual(
            [row["record_id"] for row in fts_rows],
            [
                "human_repellent_guidance:epa:810.3700",
                "human_repellent_guidance:who:2009.4",
            ],
        )
        self.assertNotIn(
            "Obsolete WHO title",
            {row["title"] for row in fts_rows},
        )
        self.assertNotIn(
            "oldwhoftsmarker",
            {row["text"] for row in fts_rows},
        )
        self.assertNotIn(
            "washinreviewmarker",
            {row["text"] for row in fts_rows},
        )
        self.assertTrue(all(row["title"] for row in rows))
        self.assertTrue(all(str(row["url"]).startswith("https://") for row in rows))
        self.assertEqual(
            status["source_counts"][HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID],
            2,
        )
        self.assertEqual(status["record_count"], 2)
        self.assertEqual(status["lanes"]["guidance"], 2)


if __name__ == "__main__":
    unittest.main()
