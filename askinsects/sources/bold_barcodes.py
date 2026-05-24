from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import urllib.parse
import urllib.request

from ..records import EvidenceRecord, Provenance


BOLD_SOURCE_ID = "bold_api"
BOLD_API_URL = "https://v3.boldsystems.org/index.php/API_Public/combined"
DEFAULT_BOLD_SPECIES = "Aedes aegypti"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class BoldBarcodeResult:
    source_id: str
    species: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_limit: int
    fetched_row_count: int


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bold_url(species: str) -> str:
    query = urllib.parse.urlencode({"taxon": species, "format": "tsv"})
    return f"{BOLD_API_URL}?{query}"


def _default_fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def _parse_rows(tsv_text: str) -> list[dict[str, str]]:
    rows = []
    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    for row in reader:
        process_id = _clean(row.get("processid"))
        if not process_id or process_id == "image_ids":
            continue
        species_name = _clean(row.get("species_name"))
        if not species_name:
            continue
        rows.append({str(key): _clean(value) for key, value in row.items() if key is not None})
    return rows


def _barcode_record(row: dict[str, str], *, raw_path: Path, row_number: int, retrieved_at: str) -> EvidenceRecord:
    process_id = row["processid"]
    species = row.get("species_name") or DEFAULT_BOLD_SPECIES
    marker = row.get("markercode") or "unknown marker"
    country = row.get("country") or "unknown country"
    province = row.get("province") or ""
    collection_date = row.get("collectiondate") or "unknown date"
    nucleotides = row.get("nucleotides") or ""
    sequence_length = len(nucleotides.replace("-", "").replace(" ", ""))
    bin_uri = row.get("bin_uri") or ""
    genbank = row.get("genbank_accession") or ""
    location = ", ".join(part for part in (country, province) if part)
    title = f"BOLD DNA barcode {process_id} for {species}"
    text = (
        f"BOLD barcode specimen {process_id} identifies {species}. "
        f"Marker: {marker}. Country/province: {location}. Collection date: {collection_date}. "
        f"Sequence length: {sequence_length if sequence_length else 'not provided'} bp."
    )
    if bin_uri:
        text += f" BIN: {bin_uri}."
    if genbank:
        text += f" GenBank accession: {genbank}."
    return EvidenceRecord(
        record_id=f"bold:barcode:{process_id}",
        lane="dna_barcodes",
        source=BOLD_SOURCE_ID,
        title=title,
        text=text,
        species=species,
        url=f"https://portal.boldsystems.org/record/{urllib.parse.quote(process_id)}",
        media_url=None,
        provenance=Provenance(
            source_id=BOLD_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{row_number}",
            retrieved_at=retrieved_at,
            license="BOLD public data",
            source_url=_bold_url(species),
        ),
        payload={
            "bold_row": row,
            "process_id": process_id,
            "marker_code": marker,
            "sequence_length": sequence_length,
            "country": country,
            "province": province,
            "bin_uri": bin_uri,
            "genbank_accession": genbank,
        },
    )


def fetch_bold_barcode_records(
    *,
    species: str = DEFAULT_BOLD_SPECIES,
    raw_dir: Path,
    limit: int = 500,
    fetch_text=None,
    retrieved_at: str,
) -> BoldBarcodeResult:
    if limit < 1:
        raise ValueError("limit must be positive")
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = _bold_url(species)
    fetch = fetch_text or _default_fetch_text
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    try:
        tsv_text = fetch(url)
    except Exception as exc:
        return BoldBarcodeResult(
            source_id=BOLD_SOURCE_ID,
            species=species,
            records=[],
            gaps=[
                {
                    "source": BOLD_SOURCE_ID,
                    "lane": "dna_barcodes",
                    "species": species,
                    "reason": "bold_fetch_failed",
                    "url": url,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            ],
            raw_artifacts=[],
            requested_limit=limit,
            fetched_row_count=0,
        )
    safe_species = species.replace(" ", "_").replace("/", "_")
    raw_path = raw_dir / f"{safe_species}_bold_combined.tsv"
    raw_path.write_text(tsv_text, encoding="utf-8")
    raw_artifacts.append(raw_path.as_posix())
    parsed_rows = _parse_rows(tsv_text)
    records = [
        _barcode_record(row, raw_path=raw_path, row_number=index + 1, retrieved_at=retrieved_at)
        for index, row in enumerate(parsed_rows[:limit])
    ]
    if not records:
        gaps.append(
            {
                "source": BOLD_SOURCE_ID,
                "lane": "dna_barcodes",
                "species": species,
                "reason": "bold_no_barcode_rows",
                "url": url,
                "retrieved_at": retrieved_at,
            }
        )
    if len(parsed_rows) > limit:
        gaps.append(
            {
                "source": BOLD_SOURCE_ID,
                "lane": "dna_barcodes",
                "species": species,
                "reason": "bold_limit_applied",
                "url": url,
                "limit": limit,
                "available_rows": len(parsed_rows),
                "retrieved_at": retrieved_at,
            }
        )
    return BoldBarcodeResult(
        source_id=BOLD_SOURCE_ID,
        species=species,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_limit=limit,
        fetched_row_count=len(parsed_rows),
    )

