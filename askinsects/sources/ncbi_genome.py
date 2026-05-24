from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.parse import unquote

from askinsects.records import EvidenceRecord, Provenance


NCBI_GENOME_SOURCE_ID = "ncbi_datasets_genome"
DEFAULT_ASSEMBLY_ACCESSION = "GCF_002204515.2"
NCBI_GENOME_WEB_BASE = "https://www.ncbi.nlm.nih.gov/datasets/genome"


@dataclass(frozen=True)
class NCBIGenomeBuildResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    package_dir: str
    assembly_accession: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_url(assembly_accession: str) -> str:
    return f"{NCBI_GENOME_WEB_BASE}/{assembly_accession}/"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _assembly_species(report: dict[str, object]) -> str:
    organism = report.get("organism")
    if isinstance(organism, dict) and organism.get("organismName"):
        return str(organism["organismName"])
    return "Aedes aegypti"


def _assembly_name(report: dict[str, object], assembly_accession: str) -> str:
    info = report.get("assemblyInfo")
    if isinstance(info, dict) and info.get("assemblyName"):
        return str(info["assemblyName"])
    return assembly_accession


def _assembly_text(report: dict[str, object], assembly_accession: str) -> str:
    info = report.get("assemblyInfo") if isinstance(report.get("assemblyInfo"), dict) else {}
    organism = report.get("organism") if isinstance(report.get("organism"), dict) else {}
    assembly_name = _assembly_name(report, assembly_accession)
    species = _assembly_species(report)
    level = info.get("assemblyLevel") or "unknown assembly level"
    bioproject = info.get("bioprojectAccession") or "unknown BioProject"
    common = organism.get("commonName") or "no common name supplied"
    return (
        f"NCBI Datasets genome assembly {assembly_name} ({assembly_accession}) for {species} "
        f"({common}), assembly level {level}, BioProject {bioproject}."
    )


def _assembly_record(
    report: dict[str, object],
    *,
    assembly_accession: str,
    report_path: Path,
    line_number: int,
    retrieved_at: str,
) -> EvidenceRecord:
    assembly_name = _assembly_name(report, assembly_accession)
    species = _assembly_species(report)
    return EvidenceRecord(
        record_id=f"ncbi:assembly:{assembly_accession}",
        lane="genome_assemblies",
        source=NCBI_GENOME_SOURCE_ID,
        title=f"{species} genome assembly {assembly_name}",
        text=_assembly_text(report, assembly_accession),
        species=species,
        url=_source_url(assembly_accession),
        media_url=None,
        provenance=Provenance(
            source_id=NCBI_GENOME_SOURCE_ID,
            locator=f"{report_path.as_posix()}#line/{line_number}",
            retrieved_at=retrieved_at,
            license="NCBI public data metadata",
            source_url=_source_url(assembly_accession),
        ),
        payload={"assembly_report": report},
    )


def parse_gff_attributes(raw: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in raw.split(";"):
        if not item:
            continue
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        attributes[unquote(key)] = unquote(value)
    return attributes


def _feature_name(attributes: dict[str, str], feature_type: str) -> str:
    for key in ("gene", "Name", "product", "ID"):
        value = attributes.get(key)
        if value:
            return value
    return feature_type


def _feature_lane(feature_type: str) -> str | None:
    normalized = feature_type.lower()
    if normalized == "gene":
        return "genes"
    if normalized in {"mrna", "transcript", "ncrna", "lnc_rna", "rrna", "trna"}:
        return "transcripts"
    if normalized in {"cds", "exon", "region", "sequence_feature"}:
        return "genome_features"
    return None


def _feature_record_id(feature_type: str, attributes: dict[str, str]) -> str:
    identifier = attributes.get("ID") or attributes.get("protein_id") or attributes.get("Name") or feature_type
    lane = _feature_lane(feature_type)
    if lane == "genes":
        prefix = "gene"
    elif lane == "transcripts":
        prefix = "transcript"
    else:
        prefix = "feature"
    return f"ncbi:{prefix}:{identifier}"


def _feature_text(
    *,
    species: str,
    feature_type: str,
    seqid: str,
    start: str,
    end: str,
    strand: str,
    attributes: dict[str, str],
) -> str:
    name = _feature_name(attributes, feature_type)
    product = attributes.get("product") or attributes.get("description")
    coordinate_text = f"{seqid}:{start}-{end} ({strand})"
    if product and product != name:
        return f"NCBI genome {feature_type} {name} for {species} at {coordinate_text}, annotated as {product}."
    return f"NCBI genome {feature_type} {name} for {species} at {coordinate_text}."


def _gff_records(
    gff_path: Path,
    *,
    assembly_accession: str,
    species: str,
    retrieved_at: str,
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    for line_number, line in enumerate(gff_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) != 9:
            gaps.append(
                {
                    "source": NCBI_GENOME_SOURCE_ID,
                    "lane": "genome_features",
                    "assembly_accession": assembly_accession,
                    "reason": f"Malformed GFF row at line {line_number}.",
                }
            )
            continue
        seqid, source, feature_type, start, end, score, strand, phase, raw_attributes = columns
        lane = _feature_lane(feature_type)
        if lane is None:
            continue
        attributes = parse_gff_attributes(raw_attributes)
        record_id = _feature_record_id(feature_type, attributes)
        name = _feature_name(attributes, feature_type)
        payload = {
            "assembly_accession": assembly_accession,
            "gff_columns": {
                "seqid": seqid,
                "source": source,
                "type": feature_type,
                "start": int(start),
                "end": int(end),
                "score": score,
                "strand": strand,
                "phase": phase,
            },
            "gff_attributes": attributes,
        }
        records.append(
            EvidenceRecord(
                record_id=record_id,
                lane=lane,
                source=NCBI_GENOME_SOURCE_ID,
                title=f"{species} {feature_type} {name}",
                text=_feature_text(
                    species=species,
                    feature_type=feature_type,
                    seqid=seqid,
                    start=start,
                    end=end,
                    strand=strand,
                    attributes=attributes,
                ),
                species=species,
                url=_source_url(assembly_accession),
                media_url=None,
                provenance=Provenance(
                    source_id=NCBI_GENOME_SOURCE_ID,
                    locator=f"{gff_path.as_posix()}#line/{line_number}",
                    retrieved_at=retrieved_at,
                    license="NCBI public data metadata",
                    source_url=_source_url(assembly_accession),
                ),
                payload=payload,
            )
        )
    return records, gaps


def _iter_fasta(path: Path) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    header: str | None = None
    sequence_parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            if header is not None:
                records.append((header, "".join(sequence_parts)))
            header = line[1:].strip()
            sequence_parts = []
        else:
            sequence_parts.append(line.strip())
    if header is not None:
        records.append((header, "".join(sequence_parts)))
    return records


def _protein_records(
    protein_path: Path,
    *,
    assembly_accession: str,
    species: str,
    retrieved_at: str,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for header, sequence in _iter_fasta(protein_path):
        accession = header.split(None, 1)[0]
        description = header.split(None, 1)[1] if " " in header else accession
        records.append(
            EvidenceRecord(
                record_id=f"ncbi:protein:{accession}",
                lane="proteins",
                source=NCBI_GENOME_SOURCE_ID,
                title=f"{species} protein {accession}",
                text=f"NCBI protein {accession} for {species}: {description}. Sequence length {len(sequence)} amino acids.",
                species=species,
                url=_source_url(assembly_accession),
                media_url=None,
                provenance=Provenance(
                    source_id=NCBI_GENOME_SOURCE_ID,
                    locator=f"{protein_path.as_posix()}#protein/{accession}",
                    retrieved_at=retrieved_at,
                    license="NCBI public data metadata",
                    source_url=_source_url(assembly_accession),
                ),
                payload={
                    "assembly_accession": assembly_accession,
                    "fasta_header": header,
                    "protein_accession": accession,
                    "sequence_length": len(sequence),
                },
            )
        )
    return records


def fetch_ncbi_genome_records(
    *,
    package_dir: Path,
    assembly_accession: str = DEFAULT_ASSEMBLY_ACCESSION,
    retrieved_at: str | None = None,
) -> NCBIGenomeBuildResult:
    package_dir = Path(package_dir)
    if not package_dir.exists():
        raise FileNotFoundError(f"NCBI genome package does not exist: {package_dir}")

    retrieved = retrieved_at or utc_now()
    data_dir = package_dir / "ncbi_dataset" / "data"
    assembly_dir = data_dir / assembly_accession
    report_path = data_dir / "assembly_data_report.jsonl"
    gff_path = assembly_dir / "genomic.gff"
    protein_path = assembly_dir / "protein.faa"
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    species = "Aedes aegypti"

    if report_path.exists():
        raw_artifacts.append(report_path.as_posix())
        reports = _read_jsonl(report_path)
        report = next((item for item in reports if item.get("accession") == assembly_accession), reports[0] if reports else None)
        if report is None:
            gaps.append(
                {
                    "source": NCBI_GENOME_SOURCE_ID,
                    "lane": "genome_assemblies",
                    "assembly_accession": assembly_accession,
                    "reason": "Assembly metadata file contained no JSON records.",
                }
            )
        else:
            species = _assembly_species(report)
            line_number = next(
                (index for index, item in enumerate(reports, start=1) if item.get("accession") == report.get("accession")),
                1,
            )
            records.append(
                _assembly_record(
                    report,
                    assembly_accession=assembly_accession,
                    report_path=report_path,
                    line_number=line_number,
                    retrieved_at=retrieved,
                )
            )
    else:
        gaps.append(
            {
                "source": NCBI_GENOME_SOURCE_ID,
                "lane": "genome_assemblies",
                "assembly_accession": assembly_accession,
                "reason": "Missing assembly_data_report.jsonl.",
            }
        )

    if gff_path.exists():
        raw_artifacts.append(gff_path.as_posix())
        gff_records, gff_gaps = _gff_records(
            gff_path,
            assembly_accession=assembly_accession,
            species=species,
            retrieved_at=retrieved,
        )
        records.extend(gff_records)
        gaps.extend(gff_gaps)
    else:
        gaps.append(
            {
                "source": NCBI_GENOME_SOURCE_ID,
                "lane": "genome_features",
                "assembly_accession": assembly_accession,
                "reason": "Missing genomic.gff.",
            }
        )

    if protein_path.exists():
        raw_artifacts.append(protein_path.as_posix())
        records.extend(
            _protein_records(
                protein_path,
                assembly_accession=assembly_accession,
                species=species,
                retrieved_at=retrieved,
            )
        )
    else:
        gaps.append(
            {
                "source": NCBI_GENOME_SOURCE_ID,
                "lane": "proteins",
                "assembly_accession": assembly_accession,
                "reason": "Missing optional protein.faa.",
            }
        )

    return NCBIGenomeBuildResult(
        source_id=NCBI_GENOME_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        package_dir=package_dir.as_posix(),
        assembly_accession=assembly_accession,
    )
