from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from askinsects.records import EvidenceRecord, Provenance


VECTORBASE_GENOMICS_SOURCE_ID = "vectorbase_aedes_genomics"
VECTORBASE_RELEASE = "Current_Release"
VECTORBASE_ORGANISM = "AaegyptiLVP_AGWG"
VECTORBASE_BASE_URL = f"https://vectorbase.org/common/downloads/{VECTORBASE_RELEASE}/{VECTORBASE_ORGANISM}"
ORTHOMCL_RELEASE = "release-6.21"
ORTHOMCL_CORE_PAIRS_URL = f"https://orthomcl.org/common/downloads/{ORTHOMCL_RELEASE}/corePairs_OrthoMCL-CURRENT"
ORTHOMCL_AEDES_PREFIX = "aaeg-old|"
DEFAULT_VECTORBASE_FILE_URLS = {
    "gff": f"{VECTORBASE_BASE_URL}/gff/data/VectorBase-68_AaegyptiLVP_AGWG.gff",
    "proteins": f"{VECTORBASE_BASE_URL}/fasta/data/VectorBase-68_AaegyptiLVP_AGWG_AnnotatedProteins.fasta",
    "cds": f"{VECTORBASE_BASE_URL}/fasta/data/VectorBase-68_AaegyptiLVP_AGWG_AnnotatedCDSs.fasta",
    "transcript_sequences": f"{VECTORBASE_BASE_URL}/fasta/data/VectorBase-68_AaegyptiLVP_AGWG_AnnotatedTranscripts.fasta",
    "go": f"{VECTORBASE_BASE_URL}/gaf/VectorBase-CURRENT_AaegyptiLVP_AGWG_GO.gaf.gz",
    "codon_usage": f"{VECTORBASE_BASE_URL}/txt/VectorBase-68_AaegyptiLVP_AGWG_CodonUsage.txt",
    "id_events": f"{VECTORBASE_BASE_URL}/txt/VectorBase-68_AaegyptiLVP_AGWG_ids_events.tab",
    "ncbi_linkout": f"{VECTORBASE_BASE_URL}/xml/VectorBase-68_AaegyptiLVP_AGWG_NCBILinkout_Nucleotide.xml",
    "orthologs": f"{ORTHOMCL_CORE_PAIRS_URL}/orthologs.txt.gz",
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


def _record_id_piece(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip()) or "unknown"


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


def _parse_sequence_fasta(
    path: Path,
    *,
    source_url: str,
    retrieved_at: str,
    kind: str,
    lane: str,
    record_prefix: str,
    label: str,
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    current_id: str | None = None
    current_header = ""
    current_attributes: dict[str, str] = {}
    current_line_number = 0
    sequence_length = 0

    def emit_record() -> None:
        if current_id is None:
            return
        product = (
            current_attributes.get("transcript_product")
            or current_attributes.get("gene_product")
            or current_attributes.get("product")
            or label
        )
        gene = current_attributes.get("gene")
        location = current_attributes.get("location")
        declared_length = current_attributes.get("length")
        pieces = [
            f"VectorBase {label} {current_id} for Aedes aegypti, annotated as {product}.",
        ]
        if gene:
            pieces.append(f"Gene: {gene}.")
        if location:
            pieces.append(f"Location: {location}.")
        if declared_length:
            pieces.append(f"Declared length: {declared_length} nucleotides.")
        pieces.append(f"Observed FASTA sequence length: {sequence_length} nucleotides.")
        records.append(
            EvidenceRecord(
                record_id=f"vectorbase:{record_prefix}:{current_id}",
                lane=lane,
                source=VECTORBASE_GENOMICS_SOURCE_ID,
                title=f"Aedes aegypti VectorBase {label} {current_id}",
                text=" ".join(pieces),
                species=DEFAULT_VECTORBASE_SPECIES,
                url=source_url,
                media_url=None,
                provenance=Provenance(
                    source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                    locator=f"{path.as_posix()}#line/{current_line_number}",
                    retrieved_at=retrieved_at,
                    license="VectorBase/VEuPathDB public download; source terms apply",
                    source_url=source_url,
                ),
                payload={
                    "release": VECTORBASE_RELEASE,
                    "organism": VECTORBASE_ORGANISM,
                    "sequence_kind": kind,
                    "sequence_id": current_id,
                    "fasta_header": current_header,
                    "attributes": current_attributes,
                    "declared_length": int(declared_length) if declared_length and declared_length.isdigit() else None,
                    "observed_sequence_length": sequence_length,
                },
            )
        )

    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if line.startswith(">"):
                emit_record()
                current_id, current_attributes = _parse_fasta_header(line)
                current_header = line
                current_line_number = line_number
                sequence_length = 0
                if not current_id:
                    gaps.append(
                        {
                            "source": VECTORBASE_GENOMICS_SOURCE_ID,
                            "lane": lane,
                            "reason": f"malformed_{kind}_header",
                            "file": path.as_posix(),
                            "line_number": line_number,
                        }
                    )
                continue
            if current_id and line:
                sequence_length += len(line.strip())
    emit_record()
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


def _open_text_or_gzip(path: Path):
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


def _parse_codon_usage(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        header = handle.readline().strip().split("\t")
        if header != ["CODON", "AA", "FREQ", "ABUNDANCE"]:
            gaps.append(
                {
                    "source": VECTORBASE_GENOMICS_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "malformed_codon_usage_header",
                    "file": path.as_posix(),
                    "header": header,
                }
            )
            return records, gaps
        for line_number, raw_line in enumerate(handle, start=2):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            columns = [column.strip() for column in line.split("\t")]
            if len(columns) != 4:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_codon_usage_row",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            codon, amino_acid, frequency, abundance = columns
            records.append(
                EvidenceRecord(
                    record_id=f"vectorbase:codon_usage:{_record_id_piece(codon)}",
                    lane="genome_features",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase codon usage {codon}",
                    text=(
                        f"VectorBase codon usage for Aedes aegypti codon {codon}: "
                        f"amino acid {amino_acid}, frequency {frequency}, relative abundance {abundance}."
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
                        "codon": codon,
                        "amino_acid": amino_acid,
                        "frequency": frequency,
                        "relative_abundance": abundance,
                    },
                )
            )
    return records, gaps


def _parse_id_events(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            columns = [column.strip() for column in line.split("\t")]
            if len(columns) != 5:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_id_event_row",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            old_id, new_id, event, release, event_date = columns
            successor = new_id or "no successor"
            records.append(
                EvidenceRecord(
                    record_id=(
                        f"vectorbase:id_event:{_record_id_piece(old_id)}:"
                        f"{_record_id_piece(new_id or 'none')}:{line_number}"
                    ),
                    lane="genome_features",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase ID event {old_id} {event}",
                    text=(
                        f"VectorBase identifier event for Aedes aegypti {old_id}: {event} "
                        f"to {successor}, release {release}, date {event_date}."
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
                        "old_id": old_id,
                        "new_id": new_id or None,
                        "event": event,
                        "event_release": release,
                        "event_date": event_date,
                    },
                )
            )
    return records, gaps


def _child_text(element: ET.Element, name: str) -> str:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return ""


def _parse_ncbi_linkout(path: Path, *, source_url: str, retrieved_at: str) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return records, [
            {
                "source": VECTORBASE_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "malformed_ncbi_linkout_xml",
                "file": path.as_posix(),
                "error": str(exc),
            }
        ]

    for link in root.iter():
        if link.tag.rsplit("}", 1)[-1] != "Link":
            continue
        link_id = _child_text(link, "LinkId")
        database = _child_text(link, "Database")
        base_url = _child_text(link, "Base")
        rule = _child_text(link, "Rule")
        queries = [
            child.text.strip()
            for child in link.iter()
            if child.tag.rsplit("}", 1)[-1] == "Query" and child.text and child.text.strip()
        ]
        if not queries:
            gaps.append(
                {
                    "source": VECTORBASE_GENOMICS_SOURCE_ID,
                    "lane": "genome_features",
                    "reason": "ncbi_linkout_missing_query",
                    "file": path.as_posix(),
                    "link_id": link_id,
                }
            )
            continue
        for query in queries:
            records.append(
                EvidenceRecord(
                    record_id=(
                        f"vectorbase:ncbi_linkout:{_record_id_piece(database)}:"
                        f"{_record_id_piece(query)}:{_record_id_piece(link_id)}"
                    ),
                    lane="genome_features",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti VectorBase NCBI {database} linkout {query}",
                    text=(
                        f"VectorBase NCBI LinkOut maps Aedes aegypti {database} query {query} "
                        f"to VectorBase base URL {base_url}."
                    ),
                    species=DEFAULT_VECTORBASE_SPECIES,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                        locator=f"{path.as_posix()}#link/{link_id or query}",
                        retrieved_at=retrieved_at,
                        license="VectorBase/VEuPathDB public download; source terms apply",
                        source_url=source_url,
                    ),
                    payload={
                        "release": VECTORBASE_RELEASE,
                        "organism": VECTORBASE_ORGANISM,
                        "link_id": link_id,
                        "database": database,
                        "query": query,
                        "base_url": base_url,
                        "rule": rule,
                    },
                )
            )
    return records, gaps


def _split_orthomcl_id(identifier: str) -> tuple[str, str]:
    if "|" not in identifier:
        return "", identifier
    species_code, local_id = identifier.split("|", 1)
    return species_code, local_id


def _parse_orthomcl_pairs(
    path: Path,
    *,
    source_url: str,
    retrieved_at: str,
    relationship_type: str = "ortholog",
) -> tuple[list[EvidenceRecord], list[dict[str, object]]]:
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    with _open_text_or_gzip(path) as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            columns = line.split("\t")
            if len(columns) != 3:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_orthomcl_pair_row",
                        "file": path.as_posix(),
                        "line_number": line_number,
                    }
                )
                continue
            left_id, right_id, raw_score = [column.strip() for column in columns]
            if not (left_id.startswith(ORTHOMCL_AEDES_PREFIX) or right_id.startswith(ORTHOMCL_AEDES_PREFIX)):
                continue
            try:
                score = float(raw_score)
            except ValueError:
                gaps.append(
                    {
                        "source": VECTORBASE_GENOMICS_SOURCE_ID,
                        "lane": "genome_features",
                        "reason": "malformed_orthomcl_score",
                        "file": path.as_posix(),
                        "line_number": line_number,
                        "score": raw_score,
                    }
                )
                continue
            aedes_id = left_id if left_id.startswith(ORTHOMCL_AEDES_PREFIX) else right_id
            partner_id = right_id if aedes_id == left_id else left_id
            partner_species_code, partner_local_id = _split_orthomcl_id(partner_id)
            _, aedes_gene_id = _split_orthomcl_id(aedes_id)
            records.append(
                EvidenceRecord(
                    record_id=(
                        f"vectorbase:{relationship_type}:"
                        f"{_record_id_piece(aedes_id)}:{_record_id_piece(partner_id)}:{line_number}"
                    ),
                    lane="genome_features",
                    source=VECTORBASE_GENOMICS_SOURCE_ID,
                    title=f"Aedes aegypti OrthoMCL {relationship_type} {aedes_gene_id} to {partner_id}",
                    text=(
                        f"OrthoMCL CURRENT {relationship_type} pair for Aedes aegypti gene {aedes_gene_id} "
                        f"({aedes_id}) with partner {partner_id}, score {raw_score}."
                    ),
                    species=DEFAULT_VECTORBASE_SPECIES,
                    url=source_url,
                    media_url=None,
                    provenance=Provenance(
                        source_id=VECTORBASE_GENOMICS_SOURCE_ID,
                        locator=f"{path.as_posix()}#line/{line_number}",
                        retrieved_at=retrieved_at,
                        license="OrthoMCL public download; source terms apply",
                        source_url=source_url,
                    ),
                    payload={
                        "release": VECTORBASE_RELEASE,
                        "organism": VECTORBASE_ORGANISM,
                        "orthomcl_release": ORTHOMCL_RELEASE,
                        "relationship_type": relationship_type,
                        "aedes_orthomcl_id": aedes_id,
                        "aedes_gene_id": aedes_gene_id,
                        "partner_orthomcl_id": partner_id,
                        "partner_species_code": partner_species_code or None,
                        "partner_id": partner_local_id,
                        "score": score,
                        "line_number": line_number,
                        "source_file": path.name,
                    },
                )
            )
    if not records:
        gaps.append(
            {
                "source": VECTORBASE_GENOMICS_SOURCE_ID,
                "lane": "genome_features",
                "reason": "orthomcl_no_aedes_ortholog_rows",
                "file": path.as_posix(),
                "url": source_url,
            }
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
    if "cds" in downloaded:
        parsed, parse_gaps = _parse_sequence_fasta(
            downloaded["cds"],
            source_url=urls["cds"],
            retrieved_at=retrieved,
            kind="cds",
            lane="genome_features",
            record_prefix="cds",
            label="CDS sequence",
        )
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "transcript_sequences" in downloaded:
        parsed, parse_gaps = _parse_sequence_fasta(
            downloaded["transcript_sequences"],
            source_url=urls["transcript_sequences"],
            retrieved_at=retrieved,
            kind="transcript_sequence",
            lane="transcripts",
            record_prefix="transcript_sequence",
            label="transcript sequence",
        )
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "go" in downloaded:
        parsed, parse_gaps = _parse_go(downloaded["go"], source_url=urls["go"], retrieved_at=retrieved)
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "codon_usage" in downloaded:
        parsed, parse_gaps = _parse_codon_usage(
            downloaded["codon_usage"], source_url=urls["codon_usage"], retrieved_at=retrieved
        )
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "id_events" in downloaded:
        parsed, parse_gaps = _parse_id_events(downloaded["id_events"], source_url=urls["id_events"], retrieved_at=retrieved)
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "ncbi_linkout" in downloaded:
        parsed, parse_gaps = _parse_ncbi_linkout(
            downloaded["ncbi_linkout"], source_url=urls["ncbi_linkout"], retrieved_at=retrieved
        )
        records.extend(parsed)
        gaps.extend(parse_gaps)
    if "orthologs" in downloaded:
        parsed, parse_gaps = _parse_orthomcl_pairs(
            downloaded["orthologs"], source_url=urls["orthologs"], retrieved_at=retrieved
        )
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
