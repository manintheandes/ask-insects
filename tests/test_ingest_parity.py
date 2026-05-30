import json
import unittest
from pathlib import Path

from tests.parity.fixtures import LANE_CASES, _serialize

GOLDEN = Path(__file__).parent / "parity" / "golden"


class IngestParityTests(unittest.TestCase):
    def test_each_migrated_lane_matches_golden(self):
        for case in LANE_CASES:
            with self.subTest(source=case.source_id):
                golden_path = GOLDEN / f"{case.source_id}.json"
                self.assertTrue(golden_path.exists(), f"missing golden for {case.source_id}")
                expected = json.loads(golden_path.read_text())
                result = case.run()
                actual = _serialize(*result)
                self.assertEqual(actual, expected, f"parity drift in {case.source_id}")


if __name__ == "__main__":
    unittest.main()
