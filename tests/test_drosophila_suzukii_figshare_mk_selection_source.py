import tempfile
import unittest
from pathlib import Path

from askinsects.sources.drosophila_suzukii_figshare_mk_selection import (
    DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
    fetch_drosophila_suzukii_figshare_mk_selection_records,
)


class DrosophilaSuzukiiFigshareMkSelectionSourceTests(unittest.TestCase):
    def test_fetch_parses_duplicate_header_mk_rows(self):
        table = (
            "d.sub_gene,D.suzukii_gene,NSpoly,NSfix,Spoly,Sfix,MKcodons,FETpval,alpha,rank,pn/ps,dn/ds,"
            "D.suzukii_gene,Pn_,Dn,Ps,Ds,Alpha,P-value,rank,pn/ps,dn/ds,D.suzukii_gene,D.mel_gene,description\n"
            "dsub1,DS20_00004020,131,2251,107,1292,1908,0.01017457,0.297292584,3477,1.224299065,1.742260062,"
            "DS20_00004020,79,2267,65,1304,0.301,4.24E-02,3879,1.215384615,1.738496933,DS20_00004020,FBgn0037025,kinetochore assembly\n"
            "dsub2,DS20_00004021,1,2,3,4,5,0.9,-0.1,6,0.1,0.2,"
            "DS20_00004021,7,8,9,10,-0.2,0.8,11,0.3,0.4,DS20_00004021,FBgn0000001,control row\n"
        )

        def fake_fetch(url):
            return table.encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_drosophila_suzukii_figshare_mk_selection_records(
                artifact_dir=Path(tmpdir),
                fetch_bytes=fake_fetch,
                retrieved_at="2026-05-29T00:00:00Z",
                max_rows=1,
            )

        self.assertEqual(result.source_id, DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID)
        self.assertEqual(result.parsed_row_count, 1)
        self.assertEqual(result.records[0].source, DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID)
        self.assertEqual(result.records[0].lane, "genome_features")
        self.assertEqual(result.records[0].payload["d_suzukii_gene"], "DS20_00004020")
        self.assertEqual(result.records[0].payload["d_melanogaster_gene"], "FBgn0037025")
        self.assertEqual(result.records[0].payload["method_1"]["NSpoly"], 131)
        self.assertEqual(result.records[0].payload["method_1"]["FETpval"], 0.01017457)
        self.assertEqual(result.records[0].payload["method_2"]["P-value"], 0.0424)
        self.assertIn("figshare_mk_selection_row_limit_applied", {gap["reason"] for gap in result.gaps})


if __name__ == "__main__":
    unittest.main()
