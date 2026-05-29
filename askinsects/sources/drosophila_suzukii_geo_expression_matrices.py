from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import gzip
import math
import re
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID = "drosophila_suzukii_geo_expression_matrices"
SPECIES = "Drosophila suzukii"
LICENSE = "NCBI GEO public supplementary file; NCBI terms apply"
USER_AGENT = "AskInsects/0.1 source-plane"

GEO_DIFF_FILES: tuple[dict[str, str], ...] = (
    {
        "accession": "GSE126708",
        "study": "Gene differential expression after cold acclimation in D. suzukii",
        "comparison": "Control_vs_Acclimated",
        "url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE126nnn/GSE126708/suppl/GSE126708_Cuffdiff_gene_differential_expression_testing.tabular.txt.gz",
    },
    *(
        {
            "accession": "GSE73595",
            "study": "Transcriptome response to insecticide treatment in D. suzukii",
            "comparison": comparison,
            "url": f"https://ftp.ncbi.nlm.nih.gov/geo/series/GSE73nnn/GSE73595/suppl/{filename}",
        }
        for comparison, filename in (
            ("Control_vs_Malathion_Field", "GSE73595_Control_Malathion_Field_gene_exp.diff.txt.gz"),
            ("Control_vs_Malathion_Lab", "GSE73595_Control_Malathion_Lab_gene_exp.diff.txt.gz"),
            ("Control_vs_Spinosad_Field", "GSE73595_Control_Spinosad_Field_gene_exp.diff.txt.gz"),
            ("Control_vs_Spinosad_Lab", "GSE73595_Control_Spinosad_Lab_gene_exp.diff.txt.gz"),
            ("Control_vs_Zeta_cypermethrin_Field", "GSE73595_Control_Zeta-cypermethrin_Field_gene_exp.diff.txt.gz"),
            ("Control_vs_Zeta_cypermethrin_Lab", "GSE73595_Control_Zeta-cypermethrin_Lab_gene_exp.diff.txt.gz"),
        )
    ),
)


@dataclass(frozen=True)
class DrosophilaSuzukiiGeoExpressionMatricesResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    file_count: int
    parsed_row_count: int
    significant_row_count: int
    accessions: list[str]


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown"


def _default_fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _float_or_none(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _record_from_row(
    row: dict[str, str],
    *,
    accession: str,
    study: str,
    comparison: str,
    filename: str,
    raw_path: Path,
    row_number: int,
    retrieved_at: str,
    source_url: str,
) -> EvidenceRecord:
    gene = _clean(row.get("gene")) or _clean(row.get("gene_id")) or _clean(row.get("test_id")) or "unknown_gene"
    sample_1 = _clean(row.get("sample_1"))
    sample_2 = _clean(row.get("sample_2"))
    log2_fold_change = _clean(row.get("log2(fold_change)"))
    q_value = _clean(row.get("q_value"))
    significant = _clean(row.get("significant")).lower()
    title = f"{SPECIES} GEO differential expression: {accession} {gene} {comparison}"
    text = " ".join(
        part
        for part in (
            f"GEO differential-expression row for {SPECIES} gene {gene}.",
            f"Study: {study}.",
            f"Accession: {accession}.",
            f"Comparison: {comparison} ({sample_1} versus {sample_2})." if sample_1 or sample_2 else f"Comparison: {comparison}.",
            f"log2 fold change: {log2_fold_change}." if log2_fold_change else "",
            f"q value: {q_value}." if q_value else "",
            f"Significant: {significant}." if significant else "",
        )
        if part
    )
    payload = {
        "atom_type": "geo_differential_expression_row",
        "accession": accession,
        "study": study,
        "comparison": comparison,
        "filename": filename,
        "row_number": row_number,
        "test_id": _clean(row.get("test_id")) or None,
        "gene_id": _clean(row.get("gene_id")) or None,
        "gene": gene,
        "locus": _clean(row.get("locus")) or None,
        "sample_1": sample_1 or None,
        "sample_2": sample_2 or None,
        "status": _clean(row.get("status")) or None,
        "value_1": _float_or_none(_clean(row.get("value_1"))),
        "value_2": _float_or_none(_clean(row.get("value_2"))),
        "log2_fold_change": _float_or_none(log2_fold_change),
        "test_stat": _float_or_none(_clean(row.get("test_stat"))),
        "p_value": _float_or_none(_clean(row.get("p_value"))),
        "q_value": _float_or_none(q_value),
        "significant": significant == "yes" if significant else None,
        "table_row": dict(row),
    }
    return EvidenceRecord(
        record_id=f"swd_geo_expression:{accession}:{_safe_id(filename)}:r{row_number}",
        lane="expression",
        source=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=source_url,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#row/{row_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=source_url,
        ),
        payload=payload,
    )


def fetch_drosophila_suzukii_geo_expression_matrices_records(
    *,
    artifact_dir: Path,
    fetch_bytes=None,
    retrieved_at: str,
    max_download_bytes: int = 10_000_000,
    max_rows_per_file: int | None = None,
) -> DrosophilaSuzukiiGeoExpressionMatricesResult:
    fetch = fetch_bytes or _default_fetch_bytes
    raw_dir = artifact_dir / "raw" / DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    significant_count = 0
    requested_urls: list[str] = []
    for spec in GEO_DIFF_FILES:
        url = spec["url"]
        requested_urls.append(url)
        filename = url.rsplit("/", 1)[-1]
        raw_path = raw_dir / filename
        try:
            data = fetch(url)
            if len(data) > max_download_bytes:
                gaps.append(
                    {
                        "source": DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
                        "lane": "expression",
                        "reason": "geo_expression_file_too_large",
                        "url": url,
                        "filename": filename,
                        "byte_size": len(data),
                        "retrieved_at": retrieved_at,
                    }
                )
                continue
            raw_path.write_bytes(data)
            raw_artifacts.append(raw_path.as_posix())
            text = gzip.decompress(data).decode("utf-8", "replace")
            reader = csv.DictReader(text.splitlines(), delimiter="\t")
            for row_number, row in enumerate(reader, start=1):
                if max_rows_per_file is not None and row_number > max_rows_per_file:
                    gaps.append(
                        {
                            "source": DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
                            "lane": "expression",
                            "reason": "geo_expression_row_limit_applied",
                            "url": url,
                            "filename": filename,
                            "max_rows_per_file": max_rows_per_file,
                            "retrieved_at": retrieved_at,
                        }
                    )
                    break
                record = _record_from_row(
                    row,
                    accession=str(spec["accession"]),
                    study=str(spec["study"]),
                    comparison=str(spec["comparison"]),
                    filename=filename,
                    raw_path=raw_path,
                    row_number=row_number,
                    retrieved_at=retrieved_at,
                    source_url=url,
                )
                if (record.payload or {}).get("significant") is True:
                    significant_count += 1
                records.append(record)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
                    "lane": "expression",
                    "reason": "geo_expression_file_fetch_or_parse_failed",
                    "url": url,
                    "filename": filename,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                }
            )
    return DrosophilaSuzukiiGeoExpressionMatricesResult(
        source_id=DROSOPHILA_SUZUKII_GEO_EXPRESSION_MATRICES_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
        file_count=len(raw_artifacts),
        parsed_row_count=len(records),
        significant_row_count=significant_count,
        accessions=sorted({str(spec["accession"]) for spec in GEO_DIFF_FILES}),
    )
