from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import json
import re
import time
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID = "drosophila_suzukii_ensembl_metazoa_orthology"
SPECIES = "Drosophila suzukii"
ENSEMBL_RELEASE = "Ensembl Metazoa release 62"
BASE_URL = "https://ftp.ensemblgenomes.ebi.ac.uk/pub/release-62/metazoa"
MART_URL = f"{BASE_URL}/mysql/metazoa_mart_62"
CORE_URL = f"{BASE_URL}/mysql/drosophila_suzukii_gca037355615v1rs_core_62_115_1"
GENE_MAIN_FILE = "dsgca037355615v1rs_eg_gene__gene__main.txt.gz"
DMEL_HOMOLOG_FILE = "dsgca037355615v1rs_eg_gene__homolog_dmelanogaster_eg__dm.txt.gz"
GENEID_XREF_FILE = "dsgca037355615v1rs_eg_gene__ox_geneid__dm.txt.gz"
GENE_ARCHIVE_FILE = "gene_archive.txt.gz"
STABLE_ID_EVENT_FILE = "stable_id_event.txt.gz"
MAPPING_SESSION_FILE = "mapping_session.txt.gz"
LICENSE = "Ensembl Genomes FTP public data; EMBL-EBI terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"


@dataclass(frozen=True)
class DrosophilaSuzukiiEnsemblMetazoaOrthologyResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    current_gene_count: int
    dmel_homolog_count: int
    geneid_xref_count: int
    stable_id_event_count: int
    gene_archive_count: int
    homolog_relationship_counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "")).strip("_") or "unknown"


def _fetch_bytes(url: str, *, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=180) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError(f"download_too_large:{content_length}")
                payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError(f"download_too_large:{len(payload)}")
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _iter_gzip_tsv(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            yield line_number, line.split("\t")


def _clean(value: object) -> str:
    text = str(value or "")
    return "" if text == r"\N" else text


def _raw_url(filename: str) -> str:
    if filename in {GENE_MAIN_FILE, DMEL_HOMOLOG_FILE, GENEID_XREF_FILE}:
        return f"{MART_URL}/{filename}"
    return f"{CORE_URL}/{filename}"


def _download_file(raw_dir: Path, filename: str, fetcher: Callable[[str, int], bytes], max_download_bytes: int) -> Path:
    path = raw_dir / filename
    path.write_bytes(fetcher(_raw_url(filename), max_download_bytes))
    return path


def _current_gene_record(row: list[str], *, raw_path: Path, line_number: int, retrieved_at: str) -> tuple[str, EvidenceRecord] | None:
    if len(row) < 13:
        return None
    gene_key = _clean(row[0])
    stable_id = _clean(row[5])
    symbol = _clean(row[6])
    description = _clean(row[9])
    seq_region = _clean(row[10])
    strand = _clean(row[11])
    start = _clean(row[12])
    end = _clean(row[8])
    biotype = _clean(row[1])
    source = _clean(row[7])
    title_label = symbol or stable_id or f"gene {gene_key}"
    text = (
        f"Ensembl Metazoa current gene row for Drosophila suzukii {title_label}. "
        f"Stable ID {stable_id or 'not supplied'}, biotype {biotype or 'not supplied'}, "
        f"source {source or 'not supplied'}, location {seq_region}:{start}-{end} strand {strand}."
    )
    if description:
        text += f" Description: {description}."
    payload = {
        "atom_type": "ensembl_metazoa_current_gene",
        "ensembl_release": ENSEMBL_RELEASE,
        "gene_key": gene_key,
        "stable_id": stable_id or None,
        "display_label": symbol or None,
        "description": description or None,
        "biotype": biotype or None,
        "source": source or None,
        "seq_region": seq_region or None,
        "start": int(start) if start.isdigit() else None,
        "end": int(end) if end.isdigit() else None,
        "strand": int(strand) if re.fullmatch(r"-?\d+", strand) else None,
        "source_file": raw_path.name,
        "line_number": line_number,
    }
    record = EvidenceRecord(
        record_id=f"swd_ensembl_current_gene:{_safe_id(gene_key)}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
        title=f"Drosophila suzukii Ensembl Metazoa current gene: {title_label}",
        text=text,
        species=SPECIES,
        url=f"https://metazoa.ensembl.org/Drosophila_suzukii_gca037355615v1rs/Gene/Summary?g={stable_id}" if stable_id else None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#line/{line_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=_raw_url(raw_path.name),
        ),
        payload=payload,
    )
    return gene_key, record


def _geneid_xref_record(
    row: list[str],
    *,
    current_genes: dict[str, EvidenceRecord],
    raw_path: Path,
    line_number: int,
    retrieved_at: str,
) -> EvidenceRecord | None:
    if len(row) < 4:
        return None
    gene_key = _clean(row[0])
    geneid = _clean(row[3]) or _clean(row[2])
    if not gene_key or not geneid:
        return None
    gene = current_genes.get(gene_key)
    gene_payload = gene.payload if gene else {}
    stable_id = str(gene_payload.get("stable_id") or "")
    symbol = str(gene_payload.get("display_label") or stable_id or f"gene {gene_key}")
    payload = {
        "atom_type": "ensembl_metazoa_geneid_xref",
        "ensembl_release": ENSEMBL_RELEASE,
        "gene_key": gene_key,
        "stable_id": stable_id or None,
        "display_label": symbol or None,
        "geneid": geneid,
        "source_file": raw_path.name,
        "line_number": line_number,
    }
    return EvidenceRecord(
        record_id=f"swd_ensembl_geneid_xref:{_safe_id(gene_key)}:{_safe_id(geneid)}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
        title=f"Drosophila suzukii Ensembl Metazoa GeneID xref: {symbol} to GeneID {geneid}",
        text=f"Ensembl Metazoa maps Drosophila suzukii {symbol} (stable ID {stable_id or 'not supplied'}) to NCBI GeneID {geneid}.",
        species=SPECIES,
        url=f"https://www.ncbi.nlm.nih.gov/gene/{geneid}",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#line/{line_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=_raw_url(raw_path.name),
        ),
        payload=payload,
    )


def _dmel_homolog_record(
    row: list[str],
    *,
    current_genes: dict[str, EvidenceRecord],
    raw_path: Path,
    line_number: int,
    retrieved_at: str,
) -> EvidenceRecord | None:
    if len(row) < 14:
        return None
    gene_key = _clean(row[1])
    relationship = _clean(row[4])
    dmel_gene = _clean(row[8])
    dmel_protein = _clean(row[9])
    swd_protein = _clean(row[10])
    dmel_symbol = _clean(row[11])
    identity = _clean(row[12])
    high_confidence = _clean(row[13])
    if not gene_key or not relationship:
        return None
    gene = current_genes.get(gene_key)
    gene_payload = gene.payload if gene else {}
    swd_stable_id = str(gene_payload.get("stable_id") or "")
    swd_symbol = str(gene_payload.get("display_label") or swd_stable_id or f"gene {gene_key}")
    text = (
        f"Ensembl Metazoa homolog row links Drosophila suzukii {swd_symbol}"
        f" (stable ID {swd_stable_id or 'not supplied'}) to Drosophila melanogaster"
        f" gene {dmel_gene or 'not supplied'}"
    )
    if dmel_symbol:
        text += f" ({dmel_symbol})"
    text += f" with relationship {relationship}."
    if identity:
        text += f" Percent identity is {identity}."
    payload = {
        "atom_type": "ensembl_metazoa_dmel_homolog",
        "ensembl_release": ENSEMBL_RELEASE,
        "gene_key": gene_key,
        "swd_stable_id": swd_stable_id or None,
        "swd_display_label": swd_symbol or None,
        "swd_protein_stable_id": swd_protein or None,
        "dmel_gene_stable_id": dmel_gene or None,
        "dmel_protein_stable_id": dmel_protein or None,
        "dmel_display_label": dmel_symbol or None,
        "relationship": relationship,
        "percent_identity": float(identity) if re.fullmatch(r"\d+(?:\.\d+)?", identity) else None,
        "is_high_confidence": high_confidence == "1",
        "source_file": raw_path.name,
        "line_number": line_number,
    }
    return EvidenceRecord(
        record_id=f"swd_ensembl_dmel_homolog:{_safe_id(gene_key)}:{_safe_id(dmel_gene)}:{line_number}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
        title=f"Drosophila suzukii Ensembl Metazoa homolog: {swd_symbol} to Dmel {dmel_gene or dmel_symbol}",
        text=text,
        species=SPECIES,
        url=f"https://metazoa.ensembl.org/Drosophila_melanogaster/Gene/Summary?g={dmel_gene}" if dmel_gene else None,
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#line/{line_number}",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=_raw_url(raw_path.name),
        ),
        payload=payload,
    )


def _history_gap_record(
    *,
    reason: str,
    filename: str,
    title: str,
    text: str,
    raw_path: Path,
    retrieved_at: str,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=f"swd_ensembl_history_gap:{_safe_id(reason)}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=_raw_url(filename),
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#empty",
            retrieved_at=retrieved_at,
            license=LICENSE,
            source_url=_raw_url(filename),
        ),
        payload={
            "atom_type": "ensembl_metazoa_stable_id_history_gap",
            "reason": reason,
            "ensembl_release": ENSEMBL_RELEASE,
            "source_file": filename,
            "row_count": 0,
        },
    )


def fetch_drosophila_suzukii_ensembl_metazoa_orthology_records(
    *,
    artifact_dir: Path,
    retrieved_at: str | None = None,
    fetch_bytes: Callable[[str, int], bytes] | None = None,
    max_download_bytes: int = 50_000_000,
    max_rows_per_file: int | None = None,
) -> DrosophilaSuzukiiEnsemblMetazoaOrthologyResult:
    retrieved = retrieved_at or utc_now()
    artifact_dir = Path(artifact_dir)
    raw_dir = artifact_dir / "raw" / "drosophila_suzukii_ensembl_metazoa_orthology"
    raw_dir.mkdir(parents=True, exist_ok=True)
    filenames = [GENE_MAIN_FILE, DMEL_HOMOLOG_FILE, GENEID_XREF_FILE, GENE_ARCHIVE_FILE, STABLE_ID_EVENT_FILE, MAPPING_SESSION_FILE]
    requested_urls = [_raw_url(filename) for filename in filenames]
    fetcher = fetch_bytes or (lambda url, max_bytes: _fetch_bytes(url, max_bytes=max_bytes))
    paths: dict[str, Path] = {}
    gaps: list[dict[str, object]] = []
    for filename in filenames:
        try:
            paths[filename] = _download_file(raw_dir, filename, fetcher, max_download_bytes)
        except Exception as exc:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
                    "lane": "genome_features",
                    "species": SPECIES,
                    "reason": "swd_ensembl_metazoa_download_failed",
                    "url": _raw_url(filename),
                    "filename": filename,
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            )
    if any(gap.get("reason") == "swd_ensembl_metazoa_download_failed" for gap in gaps):
        return DrosophilaSuzukiiEnsemblMetazoaOrthologyResult(
            source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
            records=[],
            gaps=gaps,
            raw_artifacts=[path.as_posix() for path in paths.values()],
            requested_urls=requested_urls,
            current_gene_count=0,
            dmel_homolog_count=0,
            geneid_xref_count=0,
            stable_id_event_count=0,
            gene_archive_count=0,
            homolog_relationship_counts={},
        )

    records: list[EvidenceRecord] = []
    current_genes: dict[str, EvidenceRecord] = {}
    limit = max_rows_per_file if max_rows_per_file and max_rows_per_file > 0 else None
    for index, (line_number, row) in enumerate(_iter_gzip_tsv(paths[GENE_MAIN_FILE]), start=1):
        if limit and index > limit:
            break
        parsed = _current_gene_record(row, raw_path=paths[GENE_MAIN_FILE], line_number=line_number, retrieved_at=retrieved)
        if parsed:
            gene_key, record = parsed
            current_genes[gene_key] = record
            records.append(record)

    geneid_xref_count = 0
    for index, (line_number, row) in enumerate(_iter_gzip_tsv(paths[GENEID_XREF_FILE]), start=1):
        if limit and index > limit:
            break
        record = _geneid_xref_record(row, current_genes=current_genes, raw_path=paths[GENEID_XREF_FILE], line_number=line_number, retrieved_at=retrieved)
        if record:
            records.append(record)
            geneid_xref_count += 1

    relationship_counts: dict[str, int] = {}
    dmel_homolog_count = 0
    for index, (line_number, row) in enumerate(_iter_gzip_tsv(paths[DMEL_HOMOLOG_FILE]), start=1):
        if limit and index > limit:
            break
        record = _dmel_homolog_record(row, current_genes=current_genes, raw_path=paths[DMEL_HOMOLOG_FILE], line_number=line_number, retrieved_at=retrieved)
        if record:
            records.append(record)
            dmel_homolog_count += 1
            relationship = str(record.payload.get("relationship") or "unknown")
            relationship_counts[relationship] = relationship_counts.get(relationship, 0) + 1

    stable_id_event_count = sum(1 for _ in _iter_gzip_tsv(paths[STABLE_ID_EVENT_FILE]))
    gene_archive_count = sum(1 for _ in _iter_gzip_tsv(paths[GENE_ARCHIVE_FILE]))
    if stable_id_event_count == 0:
        records.append(
            _history_gap_record(
                reason="swd_ensembl_metazoa_stable_id_event_empty",
                filename=STABLE_ID_EVENT_FILE,
                title="Drosophila suzukii Ensembl Metazoa stable-ID event table is empty",
                text=(
                    "Ensembl Metazoa release 62 provides stable_id_event.txt.gz for Drosophila suzukii, "
                    "but the table has zero rows. Ask Insects can show current IDs and homologs, but not historical "
                    "stable-ID change events from this release."
                ),
                raw_path=paths[STABLE_ID_EVENT_FILE],
                retrieved_at=retrieved,
            )
        )
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
                "lane": "genome_features",
                "species": SPECIES,
                "reason": "swd_ensembl_metazoa_stable_id_event_empty",
                "url": _raw_url(STABLE_ID_EVENT_FILE),
                "filename": STABLE_ID_EVENT_FILE,
                "retrieved_at": retrieved,
            }
        )
    if gene_archive_count == 0:
        records.append(
            _history_gap_record(
                reason="swd_ensembl_metazoa_gene_archive_empty",
                filename=GENE_ARCHIVE_FILE,
                title="Drosophila suzukii Ensembl Metazoa gene archive table is empty",
                text=(
                    "Ensembl Metazoa release 62 provides gene_archive.txt.gz for Drosophila suzukii, "
                    "but the table has zero rows. Ask Insects therefore keeps historical gene archive mappings "
                    "as an explicit source gap."
                ),
                raw_path=paths[GENE_ARCHIVE_FILE],
                retrieved_at=retrieved,
            )
        )
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
                "lane": "genome_features",
                "species": SPECIES,
                "reason": "swd_ensembl_metazoa_gene_archive_empty",
                "url": _raw_url(GENE_ARCHIVE_FILE),
                "filename": GENE_ARCHIVE_FILE,
                "retrieved_at": retrieved,
            }
        )

    return DrosophilaSuzukiiEnsemblMetazoaOrthologyResult(
        source_id=DROSOPHILA_SUZUKII_ENSEMBL_METAZOA_ORTHOLOGY_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=[path.as_posix() for path in paths.values()],
        requested_urls=requested_urls,
        current_gene_count=len(current_genes),
        dmel_homolog_count=dmel_homolog_count,
        geneid_xref_count=geneid_xref_count,
        stable_id_event_count=stable_id_event_count,
        gene_archive_count=gene_archive_count,
        homolog_relationship_counts=relationship_counts,
    )
