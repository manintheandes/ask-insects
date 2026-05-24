from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from askinsects.records import EvidenceRecord, Provenance


VECTORBASE_GENOMICS_SOURCE_ID = "vectorbase_aedes_genomics"
VECTORBASE_RELEASE = "Current_Release"
VECTORBASE_ORGANISM = "AaegyptiLVP_AGWG"
VECTORBASE_BASE_URL = f"https://vectorbase.org/common/downloads/{VECTORBASE_RELEASE}/{VECTORBASE_ORGANISM}"
DEFAULT_VECTORBASE_FILE_URLS = {
    "gff": f"{VECTORBASE_BASE_URL}/gff/data/VectorBase-68_AaegyptiLVP_AGWG.gff",
    "proteins": f"{VECTORBASE_BASE_URL}/fasta/data/VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta",
    "go": f"{VECTORBASE_BASE_URL}/gaf/VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz",
}
DEFAULT_VECTORBASE_SPECIES = "Aedes aegypti"


@dataclass(frozen=True)
class VectorBaseGenomicsResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]
    release: str
    organism: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_gff_attributes(raw: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in raw.split(";"):
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        attributes[unquote(key)] = unquote(value)
    return attributes


def _download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    if parsed.scheme == "file":
        shutil.copy2(Path(unquote(parsed.path)), destination)
        return destination
    request = Request(url, headers={"User-Agent": "ask-insects-vectorbase-source/0.1"})
    with urlopen(request, timeout=120) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return destination


def _safe_download_name(kind: str, url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or f"{kind}.dat"


def _feature_lane(feature_type: str) -> str | None:
    normalized = feature_type.lower()
    if normalized == "gene" or normalized.endswith("_gene") or normalized == "pseudogene":
        return "genes"
    if normalized in {
        "mrna",
        "transcript",
        "ncrna",
        "lnc_rna",
        "rrna",
        "trna",
        "snrna",
        "snorna",
        "pre_mirna",
        "rnase_p_rna",
        "rnase_mrp_rna",
        "srp_rna",
        "pseudogenic_transcript",
    }:
        return "transcripts"
    return None


def _feature_name(attributes: dict[str, str], feature_type: str) -> str:
    for key in ("Name", "gene", "ID", "description", "product"):
        value = attributes.get(key)
        if value:
            return value
    return feature_type


def _feature_text(
    *,
    feature_type: str,
    name: str,
    seqid: str,
    start: str,
    end: str,
    strand: str,
    attributes: dict[str, str],
) -> str:
    description = attributes.get("description") or attributes.get("product")
    coordinate_text = f"{seqid}:{start}-{end} ({strand})"
    if description and description != name:
        return f"VectorBase {feature_type} {name} for Aedes aegypti at {coordinate_text}, annotated as {description}."
    return f"VectorBase {feature_type} {name} for Aedes aegypti at {coordinate_text}."


def _parse_gff(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) != 9:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_gff_row",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            seqid, row_source, feature_type, start, end, score, strand, phase, raw_attributes = columns
            lane = _feature_lane(feature_type)
            if lane is None:
                continue
            attributes = parse_gff_attributes(raw_attributes)
            identifier = attributes.get("ID") or attributes.get("Name") or f"{feature_type}:{line_number}"
            name = _feature_name(attributes, feature_type)
            prefix = "gene" if lane == "genes" else "transcript"
            records.append(
                EvidenceRecord(
                    record_id=f"vectorbase:{prefix}:{identifier}",
                    lane=lane,
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase {feature_type} {name}",
                    text=_feature_text(
                        feature_type=feature_type,
                        name=name,
                        seqid=seqid,
                        start=start,
                        end=end,
                        strand=strand,
                        attributes=attributes,
                    ),
                    species=DEFAULT_VECTORBASE_SPECIES,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                        locator=f"{path.as_posix()}#line/{line_number}",
                        retrieved_at=retrieved_at,
                        license="VectorBase/VEuPathDB public download; source terms apply",
                        source_url=source_url,
                    ),
                    payload={
                        "release": VECTORBASE_RELEASE,
                        "organism": VECTORBASE_ORGANISM,
                        "gff_columns": {
                            "seqid": seqid,
                            "source": row_source,
                            "type": feature_type,
                            "start": int(start),
                            "end": int(end),
                            "score": score,
                            "strand": strand,
                            "phase": phase,
                        },
                        "gff_attributes": attributes,
                    },
                )
            )
    return records, gaps


def _parse_fasta_header(header: str) -> tuple[str, dict[str, str]]:
    parts = [part.strip() for part in header.split("|")]
    identifier = parts[0].strip().lstrip(">")
    attributes: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        attributes[key.strip()] = value.strip()
    return identifier, attributes


def _parse_proteins(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line.startswith(">"):
                continue
            protein_id, attributes = _parse_fasta_header(line)
            if not protein_id:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "proteins",
                        "reason": "malformed_protein_header",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            product = attributes.get("gene_product") or "annotated protein"
            gene = attributes.get("gene")
            transcript = attributes.get("transcript")
            pieces = [f"VectorBase protein {protein_id} for Aedes aegypti, annotated as {product}."]
            if gene:
                pieces.append(f"Gene: {gene}.")
            if transcript:
                pieces.append(f"Transcript: {transcript}.")
            if attributes.get("length"):
                pieces.append(f"Length: {attributes['length']} amino acids.")
            records.append(
                EvidenceRecord(
                    record_id=f"vectorbase:protein:{protein_id}",
                    lane="proteins",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase protein {protein_id}",
                    text=" ".join(pieces),
                    species=DEFAULT_VECTORBASE_SPECIES,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                        locator=f"{path.as_posix()}#line/{line_number}",
                        retrieved_at=retrieved_at,
                        license="VectorBase/VEuPathDB public download; source terms apply",
                        source_url=source_url,
                    ),
                    payload={
                        "release": VECTORBASE_RELEASE,
                        "organism": VECTORBASE_ORGANISM,
                        "protein_id": protein_id,
                        "fasta_header": line,
                        "attributes": attributes,
                    },
                )
            )
    return records, gaps


GAF_COLUMNS = (
    "db",
    "db_object_id",
    "db_object_symbol",
    "qualifier",
    "go_id",
    "db_reference",
    "evidence_code",
    "with_or_from",
    "aspect",
    "db_object_name",
    "db_object_synonym",
    "db_object_type",
    "taxon",
    "date",
    "assigned_by",
    "annotation_extension",
    "gene_product_form_id",
)


def _open_gaf(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def _parse_go(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with _open_gaf(path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line or line.startswith("!"):
                continue
            columns = line.split("\t")
            if len(columns) < len(GAF_COLUMNS):
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_gaf_row",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            payload = dict(zip(GAF_COLUMNS, columns[: len(GAF_COLUMNS)], strict=False))
            gene_id = payload["db_object_id"]
            go_id = payload["go_id"]
            name = payload["db_object_name"] or payload["db_object_symbol"] or gene_id
            evidence = payload["evidence_code"]
            aspect = payload["aspect"]
            records.append(
                EvidenceRecord(
                    record_id=f"vectorbase:go:{gene_id}:{go_id}:{line_number}",
                    lane="genome_features",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase GO annotation {gene_id} {go_id}",
                    text=(
                        f"VectorBase GO annotation for Aedes aegypti gene {gene_id}: {go_id} "
                        f"({name}), aspect {aspect}, evidence {evidence}."
                    ),
                    species=DEFAULT_VECTORBASE_SPECIES,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                        locator=f"{path.as_posix()}#line/{line_number}",
                        retrieved_at=retrieved_at,
                        license="VectorBase/VEuPathDB public download; source terms apply",
                        source_url=source_url,
                    ),
                    payload={
                        "release": VECTORBASE_RELEASE,
                        "organism": VECTORBASE_ORGANISM,
                        "go_id": go_id,
                        "gene_id": gene_id,
                        "gaf": payload,
                    },
                )
            )
    return records, gaps


def fetch_vectorbase_genomics_records(
    *,
    raw_dir: Path,
    file_urls: dict[str, str] | None = None,
    retrieved_at: str | None = None,
) -> VectorBaseGenomicsResult:
    retrieved = retrieved_at or utc_now()
    urls = dict(DEFAULT_VECTORBASE_FILE_URLS)
    if file_urls:
        urls.update({key: value for key, value in file_urls.items() if value})
    raw_dir.mkdir(parents=True, exist_ok=True)

    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []

    downloaded: dict[str, Path] = {}
    for kind, url in urls.items():
        destination = raw_dir / _safe_download_name(kind, url)
        try:
            downloaded[kind] = _download_file(url, destination)
            raw_artifacts.append(destination.as_posix())
        except Exception as exc:
            gaps.append(
                {
                    "source": VECTORBASE_GENOMICS_SOURCE_ID,
                    "lane": "genomics",
                    "reason": "download_failed",
                    "kind": kind,
                    "url": url,
                    "error": str(exc),
                }
            )

    if "gff" in downloaded:
        parsed, parse_gaps = _parse_gff(downloaded["gff"], source_url=urls["gff"], retrieved_at=retrieved)
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "proteins" in downloaded:
        parsed, parse_gaps = _parse_proteins(downloaded["proteins"], source_url=urls["proteins"], retrieved_at=retrieved)
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "go" in downloaded:
        parsed, parse_gaps = _parse_go(downloaded["go"], source_url=urls["go"], retrieved_at=retrieved)
        records.extend(parsed)
        gaps.extend(parse_gaps)

    return VectorBaseGenomicsResult(
        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=list(urls.values()),
        release=VECTORBASE_RELEASE,
        organism=VECTORBASE_ORGANISM,
    )
