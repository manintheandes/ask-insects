from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..records import EvidenceRecord, Provenance
from ..species import resolve_species


UNIPROT_PROTEIN_SOURCE_ID = "aedes_uniprot_proteins"
USER_AGENT = "AskInsects/0.1 source-plane"
UNIPROTKB_BASE = "https://rest.uniprot.org/uniprotkb/search"
PROTEOME_BASE = "https://rest.uniprot.org/proteomes/search"


@dataclass(frozen=True)
class UniProtProteinResult:
    source_id: str
    records: list[EvidenceRecord]
    gaps: list[dict[str, object]]
    raw_artifacts: list[str]
    requested_urls: list[str]


def _default_fetch_json(url: str) -> dict[str, object]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _write_raw(raw_dir: Path, filename: str, payload: dict[str, object]) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _recommended_name(entry: dict[str, object]) -> str:
    description = entry.get("proteinDescription")
    if not isinstance(description, dict):
        return ""
    recommended = description.get("recommendedName")
    if isinstance(recommended, dict):
        full_name = recommended.get("fullName")
        if isinstance(full_name, dict):
            return _clean(full_name.get("value"))
    submission_names = description.get("submissionNames")
    if isinstance(submission_names, list) and submission_names:
        first = submission_names[0]
        if isinstance(first, dict) and isinstance(first.get("fullName"), dict):
            return _clean(first["fullName"].get("value"))
    return ""


def _gene_names(entry: dict[str, object]) -> list[str]:
    names: list[str] = []
    genes = entry.get("genes")
    if not isinstance(genes, list):
        return names
    for gene in genes:
        if not isinstance(gene, dict):
            continue
        for key in ("geneName", "orderedLocusNames", "orfNames", "synonyms"):
            value = gene.get(key)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, dict) and item.get("value"):
                    names.append(_clean(item["value"]))
    return list(dict.fromkeys(name for name in names if name))


def _function_text(entry: dict[str, object]) -> str:
    comments = entry.get("comments")
    if not isinstance(comments, list):
        return ""
    texts: list[str] = []
    for comment in comments:
        if not isinstance(comment, dict) or comment.get("commentType") != "FUNCTION":
            continue
        for text in comment.get("texts") or []:
            if isinstance(text, dict) and text.get("value"):
                texts.append(_clean(text["value"]))
    return " ".join(texts)


def _cross_refs(entry: dict[str, object]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    refs = entry.get("uniProtKBCrossReferences")
    if not isinstance(refs, list):
        return grouped
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        database = _clean(ref.get("database"))
        value = _clean(ref.get("id"))
        if database and value:
            grouped.setdefault(database, []).append(value)
    return {key: list(dict.fromkeys(values)) for key, values in grouped.items()}


def _keywords(entry: dict[str, object]) -> list[str]:
    values = []
    keywords = entry.get("keywords")
    if isinstance(keywords, list):
        for keyword in keywords:
            if isinstance(keyword, dict) and keyword.get("name"):
                values.append(_clean(keyword["name"]))
    return values


def _protein_record(
    entry: dict[str, object],
    *,
    raw_path: Path,
    index: int,
    retrieved_at: str,
    source_id: str = UNIPROT_PROTEIN_SOURCE_ID,
    species_scope: str = "Aedes aegypti",
    record_prefix: str = "uniprot",
    taxonomy_id: int = 7159,
) -> EvidenceRecord | None:
    accession = _clean(entry.get("primaryAccession"))
    if not accession:
        return None
    protein_name = _recommended_name(entry) or _clean(entry.get("uniProtkbId")) or accession
    organism = entry.get("organism")
    species = resolve_species(
        _clean(organism.get("scientificName")) if isinstance(organism, dict) else None,
        scope=species_scope,
    )
    genes = _gene_names(entry)
    function = _function_text(entry)
    refs = _cross_refs(entry)
    keywords = _keywords(entry)
    reviewed = "reviewed" if "reviewed" in _clean(entry.get("entryType")).lower() else "unreviewed"
    url = f"https://www.uniprot.org/uniprotkb/{accession}/entry"
    vectorbase_refs = refs.get("VectorBase", [])
    go_refs = refs.get("GO", [])
    text = " ".join(
        part
        for part in (
            f"UniProt {reviewed} {species_scope} protein record {accession}.",
            f"Protein: {protein_name}.",
            f"Gene names: {', '.join(genes)}." if genes else "",
            f"Function: {function}" if function else "",
            f"VectorBase cross-references: {', '.join(vectorbase_refs)}." if vectorbase_refs else "",
            f"GO terms: {', '.join(go_refs[:10])}." if go_refs else "",
            f"Keywords: {', '.join(keywords)}." if keywords else "",
        )
        if part
    )
    payload = {
        "record_type": "uniprotkb_protein",
        "accession": accession,
        "uniprot_id": _clean(entry.get("uniProtkbId")),
        "entry_type": _clean(entry.get("entryType")),
        "protein_name": protein_name,
        "gene_names": genes,
        "function": function,
        "cross_references": refs,
        "keywords": keywords,
        "raw_json_path": raw_path.as_posix(),
    }
    if source_id != UNIPROT_PROTEIN_SOURCE_ID or species_scope != "Aedes aegypti" or taxonomy_id != 7159:
        payload.update({"query_species": species_scope, "query_taxonomy_id": taxonomy_id})
    return EvidenceRecord(
        record_id=f"{record_prefix}:protein:{accession}",
        lane="proteins",
        source=source_id,
        title=f"UniProt protein {accession}: {protein_name}",
        text=text,
        species=species,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=source_id,
            locator=f"{raw_path.as_posix()}#results/{index}",
            retrieved_at=retrieved_at,
            license="UniProt public data; CC BY 4.0",
            source_url=url,
        ),
        payload=payload,
    )


def _proteome_record(
    entry: dict[str, object],
    *,
    raw_path: Path,
    index: int,
    retrieved_at: str,
    source_id: str = UNIPROT_PROTEIN_SOURCE_ID,
    species_scope: str = "Aedes aegypti",
    record_prefix: str = "uniprot",
    taxonomy_id: int = 7159,
) -> EvidenceRecord | None:
    proteome_id = _clean(entry.get("id"))
    if not proteome_id:
        return None
    taxonomy = entry.get("taxonomy")
    species = species_scope
    if isinstance(taxonomy, dict):
        species = _clean(taxonomy.get("scientificName") or taxonomy.get("organismName")) or species
    description = _clean(entry.get("description"))
    protein_count = _clean(entry.get("proteinCount"))
    url = f"https://www.uniprot.org/proteomes/{proteome_id}"
    text = " ".join(
        part
        for part in (
            f"UniProt proteome record {proteome_id} for {species_scope}.",
            f"Description: {description}." if description else "",
            f"Protein count: {protein_count}." if protein_count else "",
        )
        if part
    )
    payload = {
        "record_type": "uniprot_proteome",
        "proteome_id": proteome_id,
        "description": description,
        "protein_count": protein_count,
        "raw_json_path": raw_path.as_posix(),
    }
    if source_id != UNIPROT_PROTEIN_SOURCE_ID or species_scope != "Aedes aegypti" or taxonomy_id != 7159:
        payload.update({"query_species": species_scope, "query_taxonomy_id": taxonomy_id})
    return EvidenceRecord(
        record_id=f"{record_prefix}:proteome:{proteome_id}",
        lane="proteins",
        source=source_id,
        title=f"UniProt proteome {proteome_id}: {species_scope}",
        text=text,
        species=species,
        url=url,
        media_url=None,
        provenance=Provenance(
            source_id=source_id,
            locator=f"{raw_path.as_posix()}#results/{index}",
            retrieved_at=retrieved_at,
            license="UniProt public data; CC BY 4.0",
            source_url=url,
        ),
        payload=payload,
    )


def fetch_uniprot_protein_records(
    *,
    raw_dir: Path,
    fetch_json=None,
    retrieved_at: str,
    protein_limit: int = 250,
    proteome_limit: int = 10,
    taxonomy_id: int = 7159,
    species_name: str = "Aedes aegypti",
    source_id: str = UNIPROT_PROTEIN_SOURCE_ID,
    record_prefix: str = "uniprot",
    raw_prefix: str = "aedes_aegypti",
) -> UniProtProteinResult:
    fetch = fetch_json or _default_fetch_json
    raw_dir.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    gaps: list[dict[str, object]] = []
    raw_artifacts: list[str] = []
    requested_urls: list[str] = []

    uniprot_url = f"{UNIPROTKB_BASE}?{urlencode({'query': f'organism_id:{taxonomy_id}', 'fields': 'accession,id,reviewed,protein_name,gene_names,organism_name,go_id,cc_function,xref_vectorbase,keyword', 'format': 'json', 'size': max(1, int(protein_limit))})}"
    requested_urls.append(uniprot_url)
    try:
        uniprot_payload = fetch(uniprot_url)
    except Exception as exc:
        gaps.append({"source": source_id, "lane": "proteins", "reason": "uniprot_proteins_fetch_failed", "error": str(exc), "retrieved_at": retrieved_at, "species": species_name, "taxonomy_id": taxonomy_id})
    else:
        raw_path = _write_raw(raw_dir, f"uniprotkb_{raw_prefix}.json", uniprot_payload)
        raw_artifacts.append(raw_path.as_posix())
        for index, entry in enumerate(uniprot_payload.get("results") if isinstance(uniprot_payload.get("results"), list) else [], start=1):
            if isinstance(entry, dict):
                record = _protein_record(
                    entry,
                    raw_path=raw_path,
                    index=index,
                    retrieved_at=retrieved_at,
                    source_id=source_id,
                    species_scope=species_name,
                    record_prefix=record_prefix,
                    taxonomy_id=taxonomy_id,
                )
                if record is not None:
                    records.append(record)

    proteome_url = f"{PROTEOME_BASE}?{urlencode({'query': f'organism_id:{taxonomy_id}', 'format': 'json', 'size': max(1, int(proteome_limit))})}"
    requested_urls.append(proteome_url)
    try:
        proteome_payload = fetch(proteome_url)
    except Exception as exc:
        gaps.append({"source": source_id, "lane": "proteins", "reason": "uniprot_proteome_fetch_failed", "error": str(exc), "retrieved_at": retrieved_at, "species": species_name, "taxonomy_id": taxonomy_id})
    else:
        raw_path = _write_raw(raw_dir, f"uniprot_proteomes_{raw_prefix}.json", proteome_payload)
        raw_artifacts.append(raw_path.as_posix())
        for index, entry in enumerate(proteome_payload.get("results") if isinstance(proteome_payload.get("results"), list) else [], start=1):
            if isinstance(entry, dict):
                record = _proteome_record(
                    entry,
                    raw_path=raw_path,
                    index=index,
                    retrieved_at=retrieved_at,
                    source_id=source_id,
                    species_scope=species_name,
                    record_prefix=record_prefix,
                    taxonomy_id=taxonomy_id,
                )
                if record is not None:
                    records.append(record)

    return UniProtProteinResult(
        source_id=source_id,
        records=records,
        gaps=gaps,
        raw_artifacts=raw_artifacts,
        requested_urls=requested_urls,
    )
