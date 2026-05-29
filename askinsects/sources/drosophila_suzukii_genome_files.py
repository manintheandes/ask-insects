from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import json
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance
from askinsects.sources.ncbi_genome import _gff_records, _protein_records


DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID = "drosophila_suzukii_genome_files"
DEFAULT_ASSEMBLY_ACCESSION = "GCF_043229965.1"
SPECIES = "Drosophila suzukii"


@dataclass(frozen=True)
class DrosophilaSuzukiiGenomeFilesResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    assembly_accession: str
    lane_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_json(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _assembly_payload(index: SourceIndex, assembly_accession: str) -> tuple[dict[str, object] | None, EvidenceRecord | None]:
    with index.connect() as conn:
        row = conn.execute(
            """
            select r.*, p.payload_json
            from records r
            left join record_payloads p on p.record_id=r.record_id
            where r.source='drosophila_suzukii_deep_sources'
              and r.record_id=?
            """,
            (f"swd:assembly:{assembly_accession}",),
        ).fetchone()
    if row is None:
        return None, None
    return _safe_json(row["payload_json"]), EvidenceRecord.from_row(dict(row))


def _https_ftp_url(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return "https://ftp.ncbi.nlm.nih.gov/" + text[len("ftp://ftp.ncbi.nlm.nih.gov/") :]
    if text.startswith("https://"):
        return text
    return None


def _default_fetch_bytes(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "AskInsects/0.1 source-plane"})
    with urlopen(request, timeout=180) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"download_too_large:{content_length}")
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"download_too_large:{len(payload)}")
    return payload


def _write_download(
    *,
    url: str,
    destination: Path,
    max_bytes: int,
    fetch_bytes_fn: Callable[[str, int], bytes],
) -> Path:
    payload = fetch_bytes_fn(url, max_bytes)
    if url.endswith(".gz"):
        payload = gzip.decompress(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def _record_for_assembly(
    *,
    assembly_accession: str,
    assembly_record: EvidenceRecord,
    payload: dict[str, object],
    raw_dir: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    raw_summary = payload.get("raw_summary") if isinstance(payload.get("raw_summary"), dict) else {}
    assembly_name = str(payload.get("assembly_name") or raw_summary.get("assemblyname") or assembly_accession)
    status = str(raw_summary.get("assemblystatus") or "unknown")
    bioproject = str(payload.get("bioproject") or raw_summary.get("bioproject") or "not supplied")
    biosample = str(payload.get("biosample") or raw_summary.get("biosampleaccn") or "not supplied")
    report_path = raw_dir / "assembly_metadata.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return EvidenceRecord(
        record_id=f"swd:genome_files:assembly:{assembly_accession}",
        lane="genome_assemblies",
        source=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        title=f"Drosophila suzukii genome file assembly {assembly_accession}: {assembly_name}",
        text=(
            f"Parsed NCBI genome files for Drosophila suzukii assembly {assembly_accession}. "
            f"Assembly name: {assembly_name}. Status: {status}. BioProject: {bioproject}. BioSample: {biosample}."
        ),
        species=SPECIES,
        url=assembly_record.url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
            locator=f"{report_path.as_posix()}#assembly",
            retrieved_at=retrieved_at,
            license="NCBI public data metadata",
            source_url=assembly_record.url,
        ),
        payload={"assembly_accession": assembly_accession, "assembly_metadata": payload},
    )


def _remap_record(record: EvidenceRecord) -> EvidenceRecord:
    record_id = record.record_id
    if record_id.startswith("ncbi:"):
        record_id = "swd:genome_files:" + record_id[len("ncbi:") :]
    provenance = Provenance(
        source_id=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        locator=record.provenance.locator,
        retrieved_at=record.provenance.retrieved_at,
        license=record.provenance.license,
        source_url=record.provenance.source_url,
    )
    payload = dict(record.payload or {})
    payload["input_parser"] = "ncbi_genome_file_parser"
    return EvidenceRecord(
        record_id=record_id,
        lane=record.lane,
        source=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        title=record.title,
        text=record.text,
        species=SPECIES,
        url=record.url,
        media_url=record.media_url,
        provenance=provenance,
        payload=payload,
    )


def fetch_drosophila_suzukii_genome_file_records(
    artifact_dir: Path,
    *,
    assembly_accession: str = DEFAULT_ASSEMBLY_ACCESSION,
    retrieved_at: str | None = None,
    max_download_bytes: int = 100_000_000,
    fetch_bytes_fn: Callable[[str, int], bytes] | None = None,
) -> DrosophilaSuzukiiGenomeFilesResult:
    artifact_dir = Path(artifact_dir)
    retrieved_at = retrieved_at or utc_now()
    fetcher = fetch_bytes_fn or _default_fetch_bytes
    index = SourceIndex(artifact_dir / "source_index.sqlite")
    payload, assembly_record = _assembly_payload(index, assembly_accession)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []
    raw_dir = artifact_dir / "raw" / "drosophila_suzukii_genome_files" / assembly_accession
    raw_dir.mkdir(parents=True, exist_ok=True)
    if payload is None or assembly_record is None:
        gap = {
            "source": DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
            "lane": "genome_assemblies",
            "reason": "assembly_metadata_not_installed",
            "assembly_accession": assembly_accession,
        }
        gaps.append(gap)
        return DrosophilaSuzukiiGenomeFilesResult(
            source_id=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=[],
            requested_urls=[],
            assembly_accession=assembly_accession,
            lane_counts={},
        )
    raw_summary = payload.get("raw_summary") if isinstance(payload.get("raw_summary"), dict) else {}
    base_url = _https_ftp_url(raw_summary.get("ftppath_refseq") or raw_summary.get("ftppath_genbank"))
    if not base_url:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
                "lane": "genome_features",
                "reason": "assembly_ftp_path_missing",
                "assembly_accession": assembly_accession,
            }
        )
        return DrosophilaSuzukiiGenomeFilesResult(
            source_id=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=[],
            requested_urls=[],
            assembly_accession=assembly_accession,
            lane_counts={},
        )
    stem = base_url.rstrip("/").split("/")[-1]
    file_specs = {
        "gff": (f"{base_url}/{stem}_genomic.gff.gz", raw_dir / "genomic.gff"),
        "protein": (f"{base_url}/{stem}_protein.faa.gz", raw_dir / "protein.faa"),
    }
    records.append(
        _record_for_assembly(
            assembly_accession=assembly_accession,
            assembly_record=assembly_record,
            payload=payload,
            raw_dir=raw_dir,
            retrieved_at=retrieved_at,
        )
    )
    raw_artifacts.append((raw_dir / "assembly_metadata.json").as_posix())
    for file_kind, (url, path) in file_specs.items():
        requested_urls.append(url)
        try:
            _write_download(url=url, destination=path, max_bytes=max_download_bytes, fetch_bytes_fn=fetcher)
            raw_artifacts.append(path.as_posix())
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
                    "lane": "proteins" if file_kind == "protein" else "genome_features",
                    "reason": f"{file_kind}_download_failed",
                    "assembly_accession": assembly_accession,
                    "url": url,
                    "error": str(exc),
                }
            )
    gff_path = file_specs["gff"][1]
    if gff_path.exists():
        gff_records, gff_gaps = _gff_records(gff_path, assembly_accession=assembly_accession, species=SPECIES, retrieved_at=retrieved_at)
        records.extend(_remap_record(record) for record in gff_records)
        for gap in gff_gaps:
            remapped = dict(gap)
            remapped["source"] = DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID
            gaps.append(remapped)
    protein_path = file_specs["protein"][1]
    if protein_path.exists():
        records.extend(
            _remap_record(record)
            for record in _protein_records(protein_path, assembly_accession=assembly_accession, species=SPECIES, retrieved_at=retrieved_at)
        )
    lane_counts: dict[str, int] = {}
    for record in records:
        lane_counts[record.lane] = lane_counts.get(record.lane, 0) + 1
    return DrosophilaSuzukiiGenomeFilesResult(
        source_id=DROSOPHILA_SUZUKII_GENOME_FILES_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        assembly_accession=assembly_accession,
        lane_counts=lane_counts,
    )
