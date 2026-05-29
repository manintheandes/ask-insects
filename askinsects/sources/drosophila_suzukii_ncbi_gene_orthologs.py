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

from askinsects.index import SourceIndex
from askinsects.records import EvidenceRecord, Provenance


DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID = "drosophila_suzukii_ncbi_gene_orthologs"
SPECIES = "Drosophila suzukii"
COMMON_NAME = "spotted wing drosophila"
TAX_ID = "28584"
NCBI_GENE_ORTHOLOGS_URL = "https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene_orthologs.gz"
NCBI_GENE_ORTHOLOGS_LICENSE = "NCBI Gene ortholog FTP public data; source terms apply"
USER_AGENT = "ask-insects/0.1 (+https://openinsects.org)"


@dataclass(frozen=True)
class DrosophilaSuzukiiNcbiGeneOrthologsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    fetched_pair_count: int
    swd_gene_count: int
    partner_taxon_count: int
    relationship_counts: dict[str, int]
    matched_gene_record_count: int


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


def _safe_payload(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _gene_metadata(index: SourceIndex) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    with index.connect() as conn:
        rows = conn.execute(
            """
            select r.record_id, r.title, r.text, r.url, p.payload_json
            from records r
            left join record_payloads p on p.record_id=r.record_id
            where r.source='drosophila_suzukii_genome_files'
              and r.lane='genes'
            """
        ).fetchall()
    for row in rows:
        payload = _safe_payload(row["payload_json"])
        attrs = payload.get("gff_attributes") if isinstance(payload.get("gff_attributes"), dict) else {}
        dbxref = str(attrs.get("Dbxref") or "")
        match = re.search(r"(?:^|,)GeneID:(\d+)(?:,|$)", dbxref)
        if not match:
            continue
        gene_id = match.group(1)
        metadata[gene_id] = {
            "record_id": row["record_id"],
            "title": row["title"],
            "text": row["text"],
            "url": row["url"],
            "symbol": attrs.get("gene") or attrs.get("Name"),
            "description": attrs.get("description") or attrs.get("product") or attrs.get("Note"),
            "gff_attributes": attrs,
        }
    return metadata


def _partner_label(tax_id: str, gene_id: str) -> str:
    if tax_id == "7227":
        return f"Drosophila melanogaster GeneID {gene_id}"
    return f"taxon {tax_id} GeneID {gene_id}"


def _record_for_pair(
    *,
    swd_gene_id: str,
    partner_tax_id: str,
    partner_gene_id: str,
    relationship: str,
    raw_path: Path,
    line_number: int,
    retrieved_at: str,
    gene_metadata: dict[str, object] | None,
) -> EvidenceRecord:
    symbol = str((gene_metadata or {}).get("symbol") or f"GeneID {swd_gene_id}")
    description = str((gene_metadata or {}).get("description") or "no local GFF description")
    local_record_id = str((gene_metadata or {}).get("record_id") or "")
    partner = _partner_label(partner_tax_id, partner_gene_id)
    relationship_label = relationship.lower()
    title = f"Drosophila suzukii NCBI Gene {relationship_label}: {symbol} to {partner}"
    text = (
        f"NCBI Gene ortholog row for Drosophila suzukii GeneID {swd_gene_id}"
        f" ({symbol}, {description}) links by {relationship} to {partner}."
    )
    if local_record_id:
        text += f" Local GFF gene record: {local_record_id}."
    payload = {
        "atom_type": "ncbi_gene_ortholog_pair",
        "relationship": relationship,
        "swd_tax_id": TAX_ID,
        "swd_gene_id": swd_gene_id,
        "swd_gene_symbol": symbol,
        "swd_gene_description": description,
        "swd_gene_record_id": local_record_id or None,
        "partner_tax_id": partner_tax_id,
        "partner_gene_id": partner_gene_id,
        "partner_label": partner,
        "source_file": raw_path.name,
        "line_number": line_number,
        "current_id_mapping": bool(local_record_id),
    }
    return EvidenceRecord(
        record_id=f"swd_ncbi_gene_ortholog:{_safe_id(swd_gene_id)}:{_safe_id(partner_tax_id)}:{_safe_id(partner_gene_id)}:{line_number}",
        lane="genome_features",
        source=DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
        title=title,
        text=text,
        species=SPECIES,
        url=f"https://www.ncbi.nlm.nih.gov/gene/{swd_gene_id}",
        media_url=None,
        provenance=Provenance(
            source_id=DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
            locator=f"{raw_path.as_posix()}#line/{line_number}",
            retrieved_at=retrieved_at,
            license=NCBI_GENE_ORTHOLOGS_LICENSE,
            source_url=NCBI_GENE_ORTHOLOGS_URL,
        ),
        payload=payload,
    )


def _iter_gene_ortholog_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) != 5:
                yield line_number, None
                continue
            yield line_number, columns


def fetch_drosophila_suzukii_ncbi_gene_ortholog_records(
    *,
    artifact_dir: Path,
    retrieved_at: str | None = None,
    fetch_bytes: Callable[[str, int], bytes] | None = None,
    max_download_bytes: int = 200_000_000,
    max_rows: int | None = None,
) -> DrosophilaSuzukiiNcbiGeneOrthologsResult:
    retrieved = retrieved_at or utc_now()
    artifact_dir = Path(artifact_dir)
    raw_dir = artifact_dir / "raw" / "drosophila_suzukii_ncbi_gene_orthologs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "gene_orthologs.gz"
    requested_urls = [NCBI_GENE_ORTHOLOGS_URL]
    gaps: list[dict[str, object]] = []
    fetcher = fetch_bytes or (lambda url, max_bytes: _fetch_bytes(url, max_bytes=max_bytes))
    try:
        raw_path.write_bytes(fetcher(NCBI_GENE_ORTHOLOGS_URL, max_download_bytes))
    except Exception as exc:
        return DrosophilaSuzukiiNcbiGeneOrthologsResult(
            source_id=DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
            records=[],
            gaps=[
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
                    "lane": "genome_features",
                    "species": SPECIES,
                    "reason": "swd_ncbi_gene_orthologs_download_failed",
                    "url": NCBI_GENE_ORTHOLOGS_URL,
                    "error": str(exc),
                    "retrieved_at": retrieved,
                }
            ],
            raw_artifacts=[],
            requested_urls=requested_urls,
            fetched_pair_count=0,
            swd_gene_count=0,
            partner_taxon_count=0,
            relationship_counts={},
            matched_gene_record_count=0,
        )
    gene_by_id = _gene_metadata(SourceIndex(artifact_dir / "source_index.sqlite"))
    records: list[EvidenceRecord] = []
    relationship_counts: dict[str, int] = {}
    swd_gene_ids: set[str] = set()
    partner_taxa: set[str] = set()
    matched_swd_gene_ids: set[str] = set()
    malformed_rows = 0
    limit = max_rows if max_rows and max_rows > 0 else None
    for line_number, columns in _iter_gene_ortholog_rows(raw_path):
        if columns is None:
            malformed_rows += 1
            continue
        tax_id, gene_id, relationship, other_tax_id, other_gene_id = columns
        if tax_id == TAX_ID:
            swd_gene_id = gene_id
            partner_tax_id = other_tax_id
            partner_gene_id = other_gene_id
        elif other_tax_id == TAX_ID:
            swd_gene_id = other_gene_id
            partner_tax_id = tax_id
            partner_gene_id = gene_id
        else:
            continue
        gene_meta = gene_by_id.get(swd_gene_id)
        records.append(
            _record_for_pair(
                swd_gene_id=swd_gene_id,
                partner_tax_id=partner_tax_id,
                partner_gene_id=partner_gene_id,
                relationship=relationship,
                raw_path=raw_path,
                line_number=line_number,
                retrieved_at=retrieved,
                gene_metadata=gene_meta,
            )
        )
        swd_gene_ids.add(swd_gene_id)
        partner_taxa.add(partner_tax_id)
        if gene_meta:
            matched_swd_gene_ids.add(swd_gene_id)
        relationship_counts[relationship] = relationship_counts.get(relationship, 0) + 1
        if limit and len(records) >= limit:
            gaps.append(
                {
                    "source": DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
                    "lane": "genome_features",
                    "species": SPECIES,
                    "reason": "swd_ncbi_gene_orthologs_limit_applied",
                    "max_rows": limit,
                    "retrieved_at": retrieved,
                }
            )
            break
    if malformed_rows:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
                "lane": "genome_features",
                "species": SPECIES,
                "reason": "swd_ncbi_gene_orthologs_malformed_rows",
                "malformed_row_count": malformed_rows,
                "retrieved_at": retrieved,
            }
        )
    if not records:
        gaps.append(
            {
                "source": DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
                "lane": "genome_features",
                "species": SPECIES,
                "reason": "swd_ncbi_gene_orthologs_no_swd_rows",
                "tax_id": TAX_ID,
                "retrieved_at": retrieved,
            }
        )
    return DrosophilaSuzukiiNcbiGeneOrthologsResult(
        source_id=DROSOPHILA_SUZUKII_NCBI_GENE_ORTHOLOGS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=[raw_path.as_posix()],
        requested_urls=requested_urls,
        fetched_pair_count=len(records),
        swd_gene_count=len(swd_gene_ids),
        partner_taxon_count=len(partner_taxa),
        relationship_counts=relationship_counts,
        matched_gene_record_count=len(matched_swd_gene_ids),
    )
