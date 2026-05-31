from pathlib import Path

from tests.parity.fixtures import ParityCase
from askinsects.sources.drosophila_suzukii_dryad_population_variants import (
    fetch_drosophila_suzukii_dryad_population_variants_records,
)

_RAW_DIR = "/tmp/ask-insects-parity/drosophila_suzukii_dryad_population_variants"
_RETRIEVED_AT = "2026-05-29T00:00:00Z"


def _fake_fetch_json(url: str):
    if "/datasets/" in url:
        return {
            "identifier": "doi:10.25338/B89P86",
            "id": 64736,
            "storageSize": 18752579970,
            "title": "Population structure of Drosophila suzukii and signals of multiple invasions",
            "abstract": "We sequenced whole genomes of 237 individual flies.",
            "methods": "Illumina sequencing libraries were prepared.",
            "license": "https://spdx.org/licenses/CC0-1.0.html",
            "_links": {"stash:version": {"href": "/api/v2/versions/110476"}},
        }
    if "/versions/110476/files" in url:
        return {
            "count": 2,
            "total": 2,
            "_embedded": {
                "stash:files": [
                    {
                        "id": 620084,
                        "path": "README",
                        "size": 95,
                        "digest": "readme-sha",
                        "digestType": "sha-256",
                        "_links": {"stash:download": {"href": "/api/v2/files/620084/download"}},
                    },
                    {
                        "id": 620083,
                        "path": "SNPs-q30-original-SWD.vcf.gz",
                        "size": 18752495016,
                        "mimeType": "text/vcard",
                        "digest": "2b8328db94a71e66b89e67e62a9d9b88407e0d4f705e87ff26be05c6379675a2",
                        "digestType": "sha-256",
                        "_links": {"stash:download": {"href": "/api/v2/files/620083/download"}},
                    },
                ]
            },
        }
    if "/versions/110476" in url:
        return {"id": 110476, "versionNumber": 1}
    raise AssertionError(url)


def _run():
    raw_dir = Path(_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    r = fetch_drosophila_suzukii_dryad_population_variants_records(
        raw_dir=raw_dir,
        retrieved_at=_RETRIEVED_AT,
        fetch_json=_fake_fetch_json,
        max_mirror_bytes=1_000_000_000,
    )
    return list(r.records), list(r.gaps)


CASE = ParityCase(
    source_id="drosophila_suzukii_dryad_population_variants",
    run=_run,
    raw_dir=_RAW_DIR,
)
