from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID = "drosophila_suzukii_dryad_population_variants"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
DRYAD_SITE_BASE = "https://datadryad.org"
DATASET_DOI = "10.25338/B89P86"
DATASET_API_URL = "https://datadryad.org/api/v2/datasets/doi%3A10.25338%2FB89P86"
VERSION_API_URL = "https://datadryad.org/api/v2/versions/110476"
FILES_API_URL = "https://datadryad.org/api/v2/versions/110476/files"
ARTICLE_DOI = "10.1093/g3journal/jkab343"
BIOPROJECT_ACCESSION = "PRJNA705744"
VCF_FILE_NAME = "SNPs-q30-original-SWD.vcf.gz"
VCF_FILE_ID = "620083"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class DrosophilaSuzukiiDryadPopulationVariantsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    file_count: int


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def _write_json(raw_dir: Path, filename: str, payload: object) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", _clean(value)).strip("_") or "unknown"


def _link(payload: dict[str, object], rel: str) -> str | None:
    links = payload.get("_links") if isinstance(payload.get("_links"), dict) else {}
    item = links.get(rel) if isinstance(links, dict) else None
    if not isinstance(item, dict):
        return None
    href = str(item.get("href") or "")
    return urljoin(DRYAD_SITE_BASE, href) if href else None


def _record(
    *,
    record_id: str,
    title: str,
    text: str,
    url: str | None,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    source_url: str | None,
    payload: dict[str, object],
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=record_id,
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#{locator_suffix}",
            retrieved_at=retrieved_at,
            license="CC0-1.0",
            source_url=source_url or url,
        ),
        payload=payload,
    )


def _gap_record(
    *,
    reason: str,
    title: str,
    text: str,
    raw_path: Path,
    locator_suffix: str,
    retrieved_at: str,
    source_url: str | None,
    file_payload: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> EvidenceRecord:
    file_id = str((file_payload or {}).get("id") or (file_payload or {}).get("file_id") or VCF_FILE_ID)
    return _record(
        record_id=f"swd_dryad_population_variants:gap:{_safe_id(reason)}:{_safe_id(file_id)}",
        title=title,
        text=text,
        url=f"https://doi.org/{DATASET_DOI}",
        raw_path=raw_path,
        locator_suffix=locator_suffix,
        retrieved_at=retrieved_at,
        source_url=source_url,
        payload={
            "atom_type": "source_gap",
            "reason": reason,
            "dataset_doi": DATASET_DOI,
            "article_doi": ARTICLE_DOI,
            "bioproject": BIOPROJECT_ACCESSION,
            "file": file_payload or {},
            **(extra or {}),
        },
    )


def _dataset_record(dataset: dict[str, object], *, raw_path: Path, retrieved_at: str) -> EvidenceRecord:
    title = _clean(dataset.get("title"))
    abstract = _clean(dataset.get("abstract"))
    methods = _clean(dataset.get("methods"))
    storage_size = dataset.get("storageSize")
    text = (
        f"Dryad population-variant dataset for {SPECIES} ({COMMON_NAME}). "
        f"DOI: {DATASET_DOI}. Related article DOI: {ARTICLE_DOI}. BioProject: {BIOPROJECT_ACCESSION}. "
        f"Storage size: {storage_size or 'not supplied'} bytes. Title: {title}. "
        f"Evidence scope: whole genomes of 237 individual flies and genetic markers for population structure, migration, diversity, and differentiation. "
        f"Abstract excerpt: {abstract[:700]}. Methods excerpt: {methods[:500]}."
    )
    return _record(
        record_id=f"swd_dryad_population_variants:dataset:{_safe_id(DATASET_DOI)}",
        title=f"Drosophila suzukii Dryad population variant dataset {DATASET_DOI}",
        text=text,
        url=f"https://doi.org/{DATASET_DOI}",
        raw_path=raw_path,
        locator_suffix="dataset",
        retrieved_at=retrieved_at,
        source_url=DATASET_API_URL,
        payload={
            "atom_type": "dryad_variant_dataset",
            "dataset_doi": DATASET_DOI,
            "article_doi": ARTICLE_DOI,
            "bioproject": BIOPROJECT_ACCESSION,
            "title": title,
            "storage_size": storage_size,
            "license": dataset.get("license") or "https://spdx.org/licenses/CC0-1.0.html",
            "version_url": _link(dataset, "stash:version") or VERSION_API_URL,
            "download_url": _link(dataset, "stash:download"),
            "raw_dataset": dataset,
        },
    )


def _file_records(
    files_payload: dict[str, object],
    *,
    raw_path: Path,
    retrieved_at: str,
    max_mirror_bytes: int,
) -> list[EvidenceRecord]:
    embedded = files_payload.get("_embedded") if isinstance(files_payload.get("_embedded"), dict) else {}
    files = embedded.get("stash:files") if isinstance(embedded, dict) else []
    records: list[EvidenceRecord] = []
    for index, file_payload in enumerate(files if isinstance(files, list) else [], start=1):
        if not isinstance(file_payload, dict):
            continue
        path = _clean(file_payload.get("path")) or f"file-{index}"
        file_id_value = file_payload.get("id")
        if not file_id_value and path == VCF_FILE_NAME:
            file_id_value = VCF_FILE_ID
        file_id = str(file_id_value or index)
        size = int(file_payload.get("size") or 0)
        digest = _clean(file_payload.get("digest"))
        digest_type = _clean(file_payload.get("digestType"))
        download_url = _link(file_payload, "stash:download")
        is_vcf = path.lower().endswith(".vcf.gz") or path == VCF_FILE_NAME
        records.append(
            _record(
                record_id=f"swd_dryad_population_variants:file:{_safe_id(file_id)}",
                title=f"Drosophila suzukii Dryad population variant file {path}",
                text=(
                    f"Dryad file manifest for {SPECIES} population variants. File: {path}. "
                    f"File id: {file_id}. Size: {size} bytes. Digest: {digest_type} {digest}. "
                    f"Download locator: {download_url or 'not supplied'}."
                ),
                url=f"https://doi.org/{DATASET_DOI}",
                raw_path=raw_path,
                locator_suffix=f"files/{index}",
                retrieved_at=retrieved_at,
                source_url=download_url,
                payload={
                    "atom_type": "dryad_variant_file_manifest",
                    "dataset_doi": DATASET_DOI,
                    "article_doi": ARTICLE_DOI,
                    "bioproject": BIOPROJECT_ACCESSION,
                    "file_id": file_id,
                    "path": path,
                    "mime_type": file_payload.get("mimeType"),
                    "byte_size": size,
                    "digest": digest,
                    "digest_type": digest_type,
                    "download_url": download_url,
                    "is_vcf": is_vcf,
                    "raw_file": file_payload,
                },
            )
        )
        if is_vcf:
            if size > max_mirror_bytes:
                records.append(
                    _gap_record(
                        reason="dryad_variant_file_too_large",
                        title=f"Drosophila suzukii Dryad VCF source gap: file too large",
                        text=(
                            f"The {path} whole-genome VCF is {size} bytes, above the current mirror limit of {max_mirror_bytes} bytes. "
                            "Ask Insects keeps the manifest and checksum but does not mirror the file in this pass."
                        ),
                        raw_path=raw_path,
                        locator_suffix=f"files/{index}#gap/dryad_variant_file_too_large",
                        retrieved_at=retrieved_at,
                        source_url=download_url,
                        file_payload={"id": file_id, **file_payload},
                        extra={"byte_size": size, "max_mirror_bytes": max_mirror_bytes},
                    )
                )
            records.append(
                _gap_record(
                    reason="dryad_variant_rows_not_mirrored",
                    title="Drosophila suzukii Dryad VCF source gap: variant rows not mirrored",
                    text=(
                        f"The {path} whole-genome VCF exists in Dryad with checksum {digest_type} {digest}, "
                        "but individual variant rows are not mirrored or queryable yet."
                    ),
                    raw_path=raw_path,
                    locator_suffix=f"files/{index}#gap/dryad_variant_rows_not_mirrored",
                    retrieved_at=retrieved_at,
                    source_url=download_url,
                    file_payload={"id": file_id, **file_payload},
                )
            )
            records.append(
                _gap_record(
                    reason="dryad_variant_header_not_indexed",
                    title="Drosophila suzukii Dryad VCF source gap: header not indexed",
                    text=(
                        f"The {path} VCF header, contig metadata, and sample list are not indexed yet because the file was not mirrored."
                    ),
                    raw_path=raw_path,
                    locator_suffix=f"files/{index}#gap/dryad_variant_header_not_indexed",
                    retrieved_at=retrieved_at,
                    source_url=download_url,
                    file_payload={"id": file_id, **file_payload},
                )
            )
            records.append(
                _gap_record(
                    reason="dryad_variant_checksum_unverified",
                    title="Drosophila suzukii Dryad VCF source gap: checksum unverified locally",
                    text=(
                        f"Dryad reports {digest_type} checksum {digest} for {path}, but Ask Insects has not downloaded the 18.7 GB file to verify the checksum locally."
                    ),
                    raw_path=raw_path,
                    locator_suffix=f"files/{index}#gap/dryad_variant_checksum_unverified",
                    retrieved_at=retrieved_at,
                    source_url=download_url,
                    file_payload={"id": file_id, **file_payload},
                )
            )
    return records


def fetch_drosophila_suzukii_dryad_population_variants_records(
    *,
    raw_dir: Path,
    retrieved_at: str,
    fetch_json=None,
    max_mirror_bytes: int = 1_000_000_000,
) -> DrosophilaSuzukiiDryadPopulationVariantsResult:
    fetch = fetch_json or _default_fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    requested_urls = [DATASET_API_URL, VERSION_API_URL, FILES_API_URL]
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    try:
        dataset = fetch(DATASET_API_URL)
        version = fetch(VERSION_API_URL)
        files = fetch(FILES_API_URL)
    except Exception as exc:
        boundary = _write_json(raw_dir, "dryad_population_variants_fetch_failed.json", {"error": str(exc), "requested_urls": requested_urls})
        return DrosophilaSuzukiiDryadPopulationVariantsResult(
            source_id=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
            records=[
                _gap_record(
                    reason="dryad_variant_metadata_fetch_failed",
                    title="Drosophila suzukii Dryad population variants source gap: metadata fetch failed",
                    text=f"Ask Insects could not fetch Dryad population-variant metadata for {SPECIES}: {exc}",
                    raw_path=boundary,
                    locator_suffix="gap/dryad_variant_metadata_fetch_failed",
                    retrieved_at=retrieved_at,
                    source_url=DATASET_API_URL,
                    extra={"error": str(exc)},
                )
            ],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "dryad_variant_metadata_fetch_failed",
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            ],
            raw_artifacts=[boundary.as_posix()],
            requested_urls=requested_urls,
            file_count=0,
        )
    dataset_path = _write_json(raw_dir, "dryad_dataset_10.25338_B89P86.json", dataset)
    version_path = _write_json(raw_dir, "dryad_version_110476.json", version)
    files_path = _write_json(raw_dir, "dryad_files_110476.json", files)
    raw_artifacts.extend([dataset_path.as_posix(), version_path.as_posix(), files_path.as_posix()])
    records.append(_dataset_record(dataset, raw_path=dataset_path, retrieved_at=retrieved_at))
    records.extend(_file_records(files, raw_path=files_path, retrieved_at=retrieved_at, max_mirror_bytes=max_mirror_bytes))
    embedded = files.get("_embedded") if isinstance(files.get("_embedded"), dict) else {}
    file_list = embedded.get("stash:files") if isinstance(embedded, dict) else []
    return DrosophilaSuzukiiDryadPopulationVariantsResult(
        source_id=DROSOPHILA_SUZUKII_DRYAD_POPULATION_VARIANTS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        file_count=len(file_list) if isinstance(file_list, list) else 0,
    )
