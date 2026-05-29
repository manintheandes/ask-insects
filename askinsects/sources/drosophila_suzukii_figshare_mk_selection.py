from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import re
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID = "drosophila_suzukii_figshare_mk_selection"
SPECIES = "Drosophila suzukii"
FIGSHARE_DOWNLOAD_URL = "https://ndownloader.figshare.com/files/26251579"
FIGSHARE_ARTICLE_URL = "https://figshare.com/articles/dataset/Suzukii_Subpulchrella_Sig_MK_two_methods_csv/13366079/3"
FIGSHARE_DOI = "10.6084/m9.figshare.13366079.v3"
FIGSHARE_ARTICLE_ID = "13366079"
FIGSHARE_VERSION = "3"
FIGSHARE_FILE_ID = "26251579"
FIGSHARE_FILE_NAME = "Suzukii.Subpulchrella.Sig.MK_two_methods.csv"
FIGSHARE_FILE_SIZE = 4_650_598
FIGSHARE_FILE_MD5 = "63790466069467f1437e357dcfcb1b96"
EXPECTED_DATA_ROWS = 3_311
LICENSE = "CC BY 4.0"
USER_AGENT = "AskInsects/0.1 source-plane"


@dataclass(frozen=True)
class DrosophilaSuzukiiFigshareMkSelectionResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    parsed_row_count: int


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lstrip("\ufeff")


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", _clean(value)).strip("_") or "unknown"


def _float_or_none(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_none(value: object) -> int | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _unique_headers(headers: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    unique: list[str] = []
    for header in headers:
        base = _clean(header) or "column"
        counts[base] = counts.get(base, 0) + 1
        unique.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return unique


def _row_dict(headers: list[str], values: list[str]) -> dict[str, str]:
    return {header: _clean(values[index]) if index < len(values) else "" for index, header in enumerate(headers)}


def _record_from_row(
    row: dict[str, str],
    *,
    raw_path: Path,
    row_number: int,
    retrieved_at: str,
) -> EvidenceRecord:
    dsuz_gene = row.get("D.suzukii_gene") or row.get("D.suzukii_gene_2") or row.get("D.suzukii_gene_3") or "unknown_gene"
    dmel_gene = row.get("D.mel_gene") or None
    dsub_gene = row.get("d.sub_gene") or None
    description = row.get("description") or None
    alpha_method_1 = _float_or_none(row.get("alpha"))
    alpha_method_2 = _float_or_none(row.get("Alpha"))
    p_value_method_1 = _float_or_none(row.get("FETpval"))
    p_value_method_2 = _float_or_none(row.get("P-value"))
    payload = {
        "atom_type": "figshare_mk_selection_row",
        "article_id": FIGSHARE_ARTICLE_ID,
        "dataset_doi": FIGSHARE_DOI,
        "version": FIGSHARE_VERSION,
        "figshare_url": FIGSHARE_ARTICLE_URL,
        "file_id": FIGSHARE_FILE_ID,
        "file_name": FIGSHARE_FILE_NAME,
        "file_size": FIGSHARE_FILE_SIZE,
        "md5": FIGSHARE_FILE_MD5,
        "license": LICENSE,
        "download_url": FIGSHARE_DOWNLOAD_URL,
        "row_number": row_number,
        "d_sub_gene": dsub_gene,
        "d_suzukii_gene": dsuz_gene,
        "d_melanogaster_gene": dmel_gene,
        "description": description,
        "method_1": {
            "NSpoly": _int_or_none(row.get("NSpoly")),
            "NSfix": _int_or_none(row.get("NSfix")),
            "Spoly": _int_or_none(row.get("Spoly")),
            "Sfix": _int_or_none(row.get("Sfix")),
            "MKcodons": _int_or_none(row.get("MKcodons")),
            "FETpval": p_value_method_1,
            "alpha": alpha_method_1,
            "rank": _int_or_none(row.get("rank")),
            "pn_ps": _float_or_none(row.get("pn/ps")),
            "dn_ds": _float_or_none(row.get("dn/ds")),
        },
        "method_2": {
            "Pn": _int_or_none(row.get("Pn_")),
            "Dn": _int_or_none(row.get("Dn")),
            "Ps": _int_or_none(row.get("Ps")),
            "Ds": _int_or_none(row.get("Ds")),
            "Alpha": alpha_method_2,
            "P-value": p_value_method_2,
            "rank": _int_or_none(row.get("rank_2")),
            "pn_ps": _float_or_none(row.get("pn/ps_2")),
            "dn_ds": _float_or_none(row.get("dn/ds_2")),
        },
        "table_row": row,
    }
    parts = [
        f"Figshare McDonald-Kreitman selection row for {SPECIES} gene {dsuz_gene}.",
        f"D. melanogaster homolog: {dmel_gene}." if dmel_gene else "",
        f"Method 1 alpha: {alpha_method_1}." if alpha_method_1 is not None else "",
        f"Method 1 Fisher exact p value: {p_value_method_1}." if p_value_method_1 is not None else "",
        f"Method 2 alpha: {alpha_method_2}." if alpha_method_2 is not None else "",
        f"Method 2 p value: {p_value_method_2}." if p_value_method_2 is not None else "",
        description[:500] if description else "",
    ]
    return EvidenceRecord(
        record_id=f"swd_figshare_mk_selection:{_safe_id(dsuz_gene)}:r{row_number}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
        title=f"{SPECIES} Figshare MK selection row: {dsuz_gene}",
        text=" ".join(part for part in parts if part),
        species=SPECIES,
        url=FIGSHARE_ARTICLE_URL,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{row_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=FIGSHARE_DOWNLOAD_URL,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_figshare_mk_selection_records(
    *,
    artifact_dir: Path,
    fetch_bytes=None,
    retrieved_at: str,
    max_download_bytes: int = 10_000_000,
    max_rows: int | None = None,
) -> DrosophilaSuzukiiFigshareMkSelectionResult:
    fetch = fetch_bytes or _default_fetch_bytes
    raw_dir = artifact_dir / "raw" / DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / FIGSHARE_FILE_NAME
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    try:
        data = fetch(FIGSHARE_DOWNLOAD_URL)
        digest = hashlib.md5(data).hexdigest()
        if digest != FIGSHARE_FILE_MD5:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "figshare_mk_selection_checksum_mismatch",
                    "url": FIGSHARE_DOWNLOAD_URL,
                    "expected_md5": FIGSHARE_FILE_MD5,
                    "actual_md5": digest,
                    "retrieved_at": retrieved_at,
                }
            )
        if len(data) > max_download_bytes:
            return DrosophilaSuzukiiFigshareMkSelectionResult(
                source_id=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                records=[],
                gaps=[
                    {
                        "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "figshare_mk_selection_file_too_large",
                        "url": FIGSHARE_DOWNLOAD_URL,
                        "byte_size": len(data),
                        "retrieved_at": retrieved_at,
                    }
                ],
                raw_artifacts=[],
                requested_urls=[FIGSHARE_DOWNLOAD_URL],
                parsed_row_count=0,
            )
        if len(data) != FIGSHARE_FILE_SIZE:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "figshare_mk_selection_byte_size_changed",
                    "url": FIGSHARE_DOWNLOAD_URL,
                    "expected_byte_size": FIGSHARE_FILE_SIZE,
                    "actual_byte_size": len(data),
                    "retrieved_at": retrieved_at,
                }
            )
        raw_path.write_bytes(data)
        raw_artifacts.append(raw_path.as_posix())
        text = data.decode("utf-8-sig", "replace")
        reader = csv.reader(text.splitlines())
        headers = _unique_headers(next(reader, []))
        for row_number, values in enumerate(reader, start=1):
            if max_rows is not None and row_number > max_rows:
                gaps.append(
                    {
                        "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "figshare_mk_selection_row_limit_applied",
                        "url": FIGSHARE_DOWNLOAD_URL,
                        "max_rows": max_rows,
                        "retrieved_at": retrieved_at,
                    }
                )
                break
            row = _row_dict(headers, values)
            if not any(row.values()):
                continue
            records.append(_record_from_row(row, raw_path=raw_path, row_number=row_number, retrieved_at=retrieved_at))
        if max_rows is None and len(records) != EXPECTED_DATA_ROWS:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "figshare_mk_selection_row_count_changed",
                    "url": FIGSHARE_DOWNLOAD_URL,
                    "expected_row_count": EXPECTED_DATA_ROWS,
                    "actual_row_count": len(records),
                    "retrieved_at": retrieved_at,
                }
            )
    except Exception as exc:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
                "lane": "genome_features",
                "reason": "figshare_mk_selection_fetch_or_parse_failed",
                "url": FIGSHARE_DOWNLOAD_URL,
                "error": str(exc),
                "retrieved_at": retrieved_at,
            }
        )
    return DrosophilaSuzukiiFigshareMkSelectionResult(
        source_id=DROSOPHILA_SUZUKII_FIGSHARE_MK_SELECTION_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=[FIGSHARE_DOWNLOAD_URL],
        parsed_row_count=len(records),
    )
