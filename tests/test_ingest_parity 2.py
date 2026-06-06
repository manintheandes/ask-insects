import json
import unittest
from pathlib import Path

from tests.parity.fixtures import IMPORT_ERRORS, LANE_CASES, _serialize

GOLDEN = Path(__file__).parent / "parity" / "golden"


class IngestParityTests(unittest.TestCase):
    def test_no_case_import_errors(self):
        self.assertEqual(IMPORT_ERRORS, [], f"parity case modules failed to import: {IMPORT_ERRORS}")

    def test_each_migrated_lane_matches_golden(self):
        self.assertGreater(len(LANE_CASES), 0, "LANE_CASES is empty — register at least one lane case")
        for case in LANE_CASES:
            with self.subTest(source=case.source_id):
                golden_path = GOLDEN / f"{case.source_id}.json"
                self.assertTrue(golden_path.exists(), f"missing golden for {case.source_id}")
                expected = json.loads(golden_path.read_text())
                actual = _serialize(*case.run(), raw_dir=case.raw_dir)
                self.assertEqual(actual, expected, f"parity drift in {case.source_id}")


if __name__ == "__main__":
    unittest.main()
