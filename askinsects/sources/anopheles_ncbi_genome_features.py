from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import hashlib
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import unquote
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID = "anopheles_ncbi_genome_features"
USER_AGENT = "AskInsects/0.1 source-plane"
DEFAULT_ANNOTATION_RELEASE = "auto"


@dataclass(frozen=True)
class AnophelesNCBIGenomeFeaturesResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    assembly_accession: str
    species: str
    source_urls: list[str]
    sha256: dict[str, str]
    lane_counts: dict[str, int]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _https_ftp(url: str) -> str:
    if url.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return "https://ftp.ncbi.nlm.nih.gov/" + url.removeprefix("ftp://ftp.ncbi.nlm.nih.gov/")
    return url


def _download(url: str, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    digest = hashlib.sha256()
    request = Request(_https_ftp(url), headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=300) as response, temp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            handle.write(chunk)
    temp.replace(path)
    return digest.hexdigest()


def _discover_annotation_files(base_url: str) -> dict[str, str]:
    request = Request(base_url.rstrip("/") + "/", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        listing = response.read().decode("utf-8", errors="replace")
    filenames = [unquote(value) for value in re.findall(r'href="([^"?#]+)"', listing, flags=re.I)]

    def matching(suffix: str, *, exclude_prefix: str = "") -> str:
        matches = [
            name for name in filenames
            if name.endswith(suffix) and (not exclude_prefix or not name.endswith(exclude_prefix + suffix))
        ]
        return sorted(matches)[-1] if matches else ""

    return {
        "go": matching("_gene_ontology.gaf.gz"),
        "raw_expression": matching(
            "_gene_expression_counts.txt.gz",
            exclude_prefix="_normalized",
        ),
        "normalized_expression": matching("_normalized_gene_expression_counts.txt.gz"),
    }


def parse_gff_attributes(raw: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in raw.split(";"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        attributes[unquote(key)] = unquote(value)
    return attributes


def _feature_identifier(feature_type: str, attributes: dict[str, str], line_number: int) -> str:
    return (
        attributes.get("ID")
        or attributes.get("gene")
        or attributes.get("Name")
        or attributes.get("protein_id")
        or f"{feature_type}:{line_number}"
    )


def _feature_name(feature_type: str, attributes: dict[str, str]) -> str:
    return attributes.get("gene") or attributes.get("Name") or attributes.get("product") or attributes.get("ID") or feature_type


def _functional(attributes: dict[str, str]) -> bool:
    text = " ".join(str(value) for value in attributes.values()).lower()
    return any(term in text for term in (
        "odorant", "olfact", "gustatory", "ionotropic receptor", "orco", "chemosensory",
        "cytochrome p450", "glutathione s-transferase", "esterase", "sodium channel",
        "insecticide", "resistance", "detoxification", "heat shock", "aquaporin",
    ))


def _feature_lane(feature_type: str, attributes: dict[str, str]) -> str | None:
    normalized = feature_type.lower()
    if normalized == "gene":
        return "genes"
    if normalized in {"mrna", "transcript", "ncrna", "lnc_rna", "rrna", "trna", "snrna", "snorna"}:
        return "transcripts"
    if normalized in {"cds", "region", "sequence_feature"} and _functional(attributes):
        return "genome_features"
    return None


def _gff_records(
    path: Path, *, assembly_accession: str, species: str, source_url: str, retrieved_at: str
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.startswith("#"):
                continue
            columns = line.rstrip("\n").split("\t")
            if len(columns) != 9:
                gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genome_features", "reason": "malformed_gff_row", "line": line_number})
                continue
            seqid, origin, feature_type, start, end, score, strand, phase, raw_attributes = columns
            attributes = parse_gff_attributes(raw_attributes)
            lane = _feature_lane(feature_type, attributes)
            if lane is None:
                continue
            identifier = _feature_identifier(feature_type, attributes, line_number)
            name = _feature_name(feature_type, attributes)
            product = attributes.get("product") or attributes.get("description") or attributes.get("Note") or ""
            coordinates = f"{seqid}:{start}-{end} ({strand})"
            text = f"NCBI {feature_type} {name} for {species}, assembly {assembly_accession}, at {coordinates}."
            if product and product != name:
                text += f" Annotation: {product}."
            record_identifier = identifier
            if lane == "genome_features":
                record_identifier = f"{identifier}:{seqid}:{start}-{end}"
            records.append(EvidenceRecord(
                record_id=f"anopheles_ncbi_genome:{assembly_accession}:{lane}:{record_identifier}",
                lane=lane,
                source=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                title=f"{species} {feature_type} {name}",
                text=text,
                species=species,
                url=f"https://www.ncbi.nlm.nih.gov/datasets/genome/{assembly_accession}/",
                media_url=None,
                provenance=Provenance(
                    source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                    locator=f"{path.as_posix()}#line/{line_number}", retrieved_at=retrieved_at,
                    license="NCBI public genome annotation; NCBI terms apply", source_url=source_url,
                ),
                payload={
                    "record_type": "ncbi_gff_feature", "assembly_accession": assembly_accession,
                    "feature_type": feature_type, "identifier": identifier, "name": name,
                    "seqid": seqid, "origin": origin, "start": int(start), "end": int(end),
                    "score": score, "strand": strand, "phase": phase, "attributes": attributes,
                },
            ))
    return records, gaps


def _iter_fasta(path: Path) -> Iterable[tuple[int, str, str]]:
    header: str | None = None
    sequence_parts: list[str] = []
    record_number = 0
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(">"):
                if header is not None:
                    yield record_number, header, "".join(sequence_parts)
                record_number += 1
                header = line[1:].strip()
                sequence_parts = []
            else:
                sequence_parts.append(line.strip())
    if header is not None:
        yield record_number, header, "".join(sequence_parts)


def _protein_records(
    path: Path, *, assembly_accession: str, species: str, source_url: str, retrieved_at: str
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for record_number, header, sequence in _iter_fasta(path):
        accession = header.split(None, 1)[0]
        description = header.split(None, 1)[1] if " " in header else accession
        records.append(EvidenceRecord(
            record_id=f"anopheles_ncbi_genome:{assembly_accession}:protein:{accession}",
            lane="proteins", source=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
            title=f"{species} NCBI protein {accession}",
            text=f"NCBI protein {accession} for {species}, assembly {assembly_accession}: {description}. Sequence length {len(sequence)} amino acids.",
            species=species, url=f"https://www.ncbi.nlm.nih.gov/protein/{accession}", media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                locator=f"{path.as_posix()}#record/{record_number}", retrieved_at=retrieved_at,
                license="NCBI public protein sequence metadata; NCBI terms apply", source_url=source_url,
            ),
            payload={"record_type": "ncbi_protein", "assembly_accession": assembly_accession, "protein_accession": accession, "fasta_header": header, "sequence_length": len(sequence)},
        ))
    return records


def _go_records(
    path: Path, *, assembly_accession: str, species: str, source_url: str, retrieved_at: str
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.startswith("!"):
                continue
            columns = line.rstrip("\n").split("\t")
            if len(columns) < 15:
                continue
            database, object_id, symbol, qualifier, go_id, reference, evidence_code, with_from, aspect, object_name, synonym, object_type, taxon, date, assigned_by = columns[:15]
            title_name = symbol or object_id
            text = (
                f"NCBI Gene Ontology annotation for {species} {title_name}: {go_id}; aspect {aspect}; "
                f"qualifier {qualifier or 'none'}; evidence code {evidence_code}; reference {reference}; "
                f"assigned by {assigned_by}; assembly {assembly_accession}."
            )
            records.append(EvidenceRecord(
                record_id=f"anopheles_ncbi_genome:{assembly_accession}:go:{object_id}:{go_id}:{line_number}",
                lane="genome_features", source=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                title=f"{species} GO annotation {title_name} {go_id}", text=text, species=species,
                url=f"https://amigo.geneontology.org/amigo/term/{go_id}", media_url=None,
                provenance=Provenance(
                    source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                    locator=f"{path.as_posix()}#line/{line_number}", retrieved_at=retrieved_at,
                    license="NCBI public Gene Ontology annotation; NCBI terms apply", source_url=source_url,
                ),
                payload={
                    "record_type": "ncbi_go_annotation", "assembly_accession": assembly_accession,
                    "database": database, "object_id": object_id, "symbol": symbol, "qualifier": qualifier,
                    "go_id": go_id, "reference": reference, "evidence_code": evidence_code,
                    "with_from": with_from, "aspect": aspect, "object_name": object_name,
                    "synonym": synonym, "object_type": object_type, "taxon": taxon, "date": date,
                    "assigned_by": assigned_by,
                },
            ))
    return records


def _expression_table(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str], dict[str, str]]]]:
    samples: list[str] = []
    rows: list[tuple[int, dict[str, str], dict[str, str]]] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        header: list[str] = []
        for line_number, line in enumerate(handle, start=1):
            columns = line.rstrip("\n").split("\t")
            if not header:
                header = [value.removeprefix("#") for value in columns]
                samples = header[8:]
                continue
            if len(columns) != len(header):
                continue
            metadata = dict(zip(header[:8], columns[:8]))
            values = dict(zip(samples, columns[8:]))
            rows.append((line_number, metadata, values))
    return samples, rows


def _expression_records(
    raw_path: Path, normalized_path: Path, *, assembly_accession: str, species: str,
    raw_url: str, normalized_url: str, retrieved_at: str,
) -> list[EvidenceRecord]:
    raw_samples, raw_rows = _expression_table(raw_path)
    normalized_samples, normalized_rows = _expression_table(normalized_path)
    normalized_by_gene = {
        str(metadata.get("GFF3ID") or metadata.get("GeneID") or metadata.get("GTFID")): (line_number, values)
        for line_number, metadata, values in normalized_rows
    }
    records: list[EvidenceRecord] = []
    for line_number, metadata, raw_values in raw_rows:
        gene_key = str(metadata.get("GFF3ID") or metadata.get("GeneID") or metadata.get("GTFID"))
        normalized_line, normalized_values = normalized_by_gene.get(gene_key, (0, {}))
        numeric = [float(value) for value in normalized_values.values() if value not in {"", "NA"}]
        nonzero = sum(1 for value in numeric if value > 0)
        maximum = max(numeric) if numeric else 0.0
        gene_symbol = metadata.get("GeneSym") or metadata.get("GTFID") or gene_key
        text = (
            f"NCBI normalized gene-expression profile for {species} {gene_symbol}, assembly {assembly_accession}, "
            f"across {len(normalized_samples or raw_samples)} public SRA runs; nonzero runs {nonzero}; maximum normalized value {maximum:g}."
        )
        records.append(EvidenceRecord(
            record_id=f"anopheles_ncbi_genome:{assembly_accession}:expression:{gene_key}",
            lane="expression", source=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
            title=f"{species} NCBI expression profile {gene_symbol}", text=text, species=species,
            url=f"https://www.ncbi.nlm.nih.gov/datasets/genome/{assembly_accession}/", media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID,
                locator=f"{normalized_path.as_posix()}#line/{normalized_line or line_number}", retrieved_at=retrieved_at,
                license="NCBI public gene expression counts; NCBI terms apply", source_url=normalized_url,
            ),
            payload={
                "record_type": "ncbi_gene_expression_profile", "assembly_accession": assembly_accession,
                "gene_metadata": metadata, "sample_ids": normalized_samples or raw_samples,
                "raw_counts": raw_values, "normalized_counts": normalized_values,
                "raw_counts_locator": f"{raw_path.as_posix()}#line/{line_number}",
                "normalized_counts_locator": f"{normalized_path.as_posix()}#line/{normalized_line}" if normalized_line else "",
                "raw_source_url": raw_url, "normalized_source_url": normalized_url,
            },
        ))
    return records


def fetch_anopheles_ncbi_genome_features(
    *, raw_dir: Path, assembly_accession: str, species: str, assembly_ftp: str,
    annotation_release: str | None = DEFAULT_ANNOTATION_RELEASE,
    retrieved_at: str | None = None,
) -> AnophelesNCBIGenomeFeaturesResult:
    retrieved = retrieved_at or _utc_now()
    base_url = _https_ftp(assembly_ftp).rstrip("/")
    stem = base_url.rsplit("/", 1)[-1]
    gff_url = f"{base_url}/{stem}_genomic.gff.gz"
    protein_url = f"{base_url}/{stem}_protein.faa.gz"
    annotation_files: dict[str, str] = {}
    annotation_discovery_error = ""
    if annotation_release == "auto":
        try:
            annotation_files = _discover_annotation_files(base_url)
        except Exception as exc:
            annotation_discovery_error = str(exc)
    elif annotation_release:
        annotation_files = {
            "go": f"{annotation_release}_gene_ontology.gaf.gz",
            "raw_expression": f"{annotation_release}_gene_expression_counts.txt.gz",
            "normalized_expression": f"{annotation_release}_normalized_gene_expression_counts.txt.gz",
        }
    go_filename = annotation_files.get("go", "")
    raw_expression_filename = annotation_files.get("raw_expression", "")
    normalized_expression_filename = annotation_files.get("normalized_expression", "")
    go_url = f"{base_url}/{go_filename}" if go_filename else ""
    raw_expression_url = f"{base_url}/{raw_expression_filename}" if raw_expression_filename else ""
    normalized_expression_url = f"{base_url}/{normalized_expression_filename}" if normalized_expression_filename else ""
    raw_dir.mkdir(parents=True, exist_ok=True)
    gff_path = raw_dir / f"{stem}_genomic.gff.gz"
    protein_path = raw_dir / f"{stem}_protein.faa.gz"
    go_path = raw_dir / (go_filename or "gene_ontology.gaf.gz")
    raw_expression_path = raw_dir / (raw_expression_filename or "gene_expression_counts.txt.gz")
    normalized_expression_path = raw_dir / (normalized_expression_filename or "normalized_gene_expression_counts.txt.gz")
    gaps: list[dict[str, object]] = []
    records: list[EvidenceRecord] = []
    raw_artifacts: list[str] = []
    hashes: dict[str, str] = {}

    try:
        hashes[gff_path.name] = _download(gff_url, gff_path)
        raw_artifacts.append(gff_path.as_posix())
        gff_records, gff_gaps = _gff_records(gff_path, assembly_accession=assembly_accession, species=species, source_url=gff_url, retrieved_at=retrieved)
        records.extend(gff_records)
        gaps.extend(gff_gaps)
    except Exception as exc:
        gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genes", "reason": "gff_download_or_parse_failed", "assembly_accession": assembly_accession, "error": str(exc), "source_url": gff_url, "locator": gff_url, "retrieved_at": retrieved})
    try:
        hashes[protein_path.name] = _download(protein_url, protein_path)
        raw_artifacts.append(protein_path.as_posix())
        records.extend(_protein_records(protein_path, assembly_accession=assembly_accession, species=species, source_url=protein_url, retrieved_at=retrieved))
    except Exception as exc:
        gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "proteins", "reason": "protein_download_or_parse_failed", "assembly_accession": assembly_accession, "error": str(exc), "source_url": protein_url, "locator": protein_url, "retrieved_at": retrieved})
    if annotation_release:
        if annotation_discovery_error:
            gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genome_features", "reason": "ncbi_annotation_file_listing_failed", "assembly_accession": assembly_accession, "error": annotation_discovery_error, "source_url": base_url + "/", "locator": base_url + "/", "retrieved_at": retrieved})
        if not go_url:
            gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genome_features", "reason": "ncbi_gene_ontology_not_available", "assembly_accession": assembly_accession, "source_url": base_url + "/", "locator": base_url + "/", "retrieved_at": retrieved})
        try:
            if go_url:
                hashes[go_path.name] = _download(go_url, go_path)
                raw_artifacts.append(go_path.as_posix())
                records.extend(_go_records(go_path, assembly_accession=assembly_accession, species=species, source_url=go_url, retrieved_at=retrieved))
        except Exception as exc:
            gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genome_features", "reason": "ncbi_gene_ontology_download_or_parse_failed", "assembly_accession": assembly_accession, "error": str(exc), "source_url": go_url, "locator": go_url, "retrieved_at": retrieved})
        if not raw_expression_url or not normalized_expression_url:
            gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "expression", "reason": "ncbi_expression_counts_not_available", "assembly_accession": assembly_accession, "source_url": base_url + "/", "locator": base_url + "/", "retrieved_at": retrieved})
        try:
            if raw_expression_url and normalized_expression_url:
                hashes[raw_expression_path.name] = _download(raw_expression_url, raw_expression_path)
                hashes[normalized_expression_path.name] = _download(normalized_expression_url, normalized_expression_path)
                raw_artifacts.extend([raw_expression_path.as_posix(), normalized_expression_path.as_posix()])
                records.extend(_expression_records(
                    raw_expression_path, normalized_expression_path, assembly_accession=assembly_accession,
                    species=species, raw_url=raw_expression_url, normalized_url=normalized_expression_url,
                    retrieved_at=retrieved,
                ))
        except Exception as exc:
            gaps.append({"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "expression", "reason": "ncbi_expression_counts_download_or_parse_failed", "assembly_accession": assembly_accession, "error": str(exc), "source_url": normalized_expression_url or raw_expression_url, "locator": normalized_expression_url or raw_expression_url, "retrieved_at": retrieved})
    else:
        gaps.extend([
            {"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "expression", "reason": "ncbi_expression_annotation_release_not_configured", "assembly_accession": assembly_accession, "retrieved_at": retrieved},
            {"source": ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, "lane": "genome_features", "reason": "ncbi_gene_ontology_annotation_release_not_configured", "assembly_accession": assembly_accession, "retrieved_at": retrieved},
        ])
    for gap in gaps:
        gap.setdefault("assembly_accession", assembly_accession)
        gap.setdefault("species", species)
    lane_counts: dict[str, int] = {}
    for record in records:
        lane_counts[record.lane] = lane_counts.get(record.lane, 0) + 1
    return AnophelesNCBIGenomeFeaturesResult(
        source_id=ANOPHELES_NCBI_GENOME_FEATURES_SOURCE_ID, records=records, gaps=gaps,
        raw_artifacts=raw_artifacts, assembly_accession=assembly_accession, species=species,
        source_urls=[url for url in (gff_url, protein_url, go_url, raw_expression_url, normalized_expression_url) if url], sha256=hashes, lane_counts=lane_counts,
    )
