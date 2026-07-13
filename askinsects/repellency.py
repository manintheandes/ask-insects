from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any

from .index import SourceIndex
from .records import EvidenceRecord


REPELLENCY_COMPARISON_CONTRACT_VERSION = "repellency-comparison.v1"
SOURCE_GAP_DETAIL_LIMIT = 25

MOSQUITO_REPELLENCY_METADATA_SOURCES = (
    "mosquito_repellent_literature",
    "mosquito_repellent_external_discovery",
)

MOSQUITO_REPELLENCY_DEPTH_SOURCES = (
    "mosquito_repellent_literature_extracted_facts",
    "mosquito_repellent_external_discovery_extracted_facts",
)

SWD_REPELLENCY_METADATA_SOURCES = (
    "drosophila_suzukii_core",
    "drosophila_suzukii_pubmed_literature",
    "drosophila_suzukii_elicit_discovery",
    "drosophila_suzukii_olfaction_literature",
)

SWD_REPELLENCY_DEPTH_SOURCES = (
    "drosophila_suzukii_extracted_facts",
    "drosophila_suzukii_pubmed_literature_extracted_facts",
    "drosophila_suzukii_elicit_extracted_facts",
)

COMPARISON_DIMENSIONS = (
    "species",
    "strain",
    "sex",
    "life_stage",
    "compound",
    "formulation",
    "dose",
    "exposure_mode",
    "assay",
    "endpoint",
    "outcome",
    "duration",
    "control",
    "sample_size",
    "statistical_result",
)

SUPERLATIVE_TARGET_REQUIREMENTS = (
    ("species", "species"),
    ("exposure_mode", "exposure_modes"),
    ("assay", "assays"),
    ("endpoint", "endpoints"),
    ("dose", "dose"),
    ("duration", "duration"),
    ("outcome", "outcome"),
)

_REPELLENCY_TERMS = (
    "repellent",
    "repellents",
    "repellency",
    "spatial repell",
    "topical repell",
    "deet",
    "picaridin",
    "icaridin",
    "ir3535",
    "pmd",
    "citronella",
    "avoidance",
    "deterrence",
)

_COMPARISON_TERMS = (
    "compare",
    "comparison",
    "better",
    "stronger",
    "outperform",
    "beat",
    "best",
    "strongest",
    "most effective",
    "rank",
    "ranking",
    "leading",
    "superior",
    "winner",
    "versus",
    "comparable",
    "summarize",
    "nothing in the literature",
)

_COMPOUND_PATTERNS = {
    "deet": (r"\bdeet\b", r"\bn,n-diethyl-m-toluamide\b"),
    "picaridin": (r"\bpicaridin\b", r"\bicaridin\b"),
    "ir3535": (r"\bir3535\b", r"\bethyl butylacetylaminopropionate\b"),
    "pmd": (r"\bpmd\b", r"\bpara-menthane-3,8-diol\b"),
    "citronella": (r"\bcitronella\b",),
    "metofluthrin": (r"\bmetofluthrin\b",),
    "transfluthrin": (r"\btransfluthrin\b",),
    "prallethrin": (r"\bprallethrin\b",),
}

_EXPOSURE_PATTERNS = {
    "non-contact": (r"\bnon[- ]?contact\b", r"\bno[- ]contact\b"),
    "contact": (r"(?<!non[- ])(?<!no[- ])\bcontact\b",),
    "spatial": (r"\bspatial repell", r"\bvapou?r[- ]phase\b", r"\bairborne\b"),
    "topical": (r"\btopical\b", r"\bskin application\b"),
}

_ASSAY_PATTERNS = {
    "arm-in-cage": (r"\barm[- ]in[- ]cage\b",),
    "hand-in-cage": (r"\bhand[- ]in[- ]cage\b",),
    "olfactometer": (r"\bolfactometer\b",),
    "choice assay": (r"\bchoice assay\b", r"\btwo[- ]choice\b"),
    "landing assay": (r"\blanding assay\b",),
    "field trial": (r"\bfield trial\b", r"\bfield study\b"),
    "chamber": (r"\bchamber\b",),
    "cage": (r"\bcage\b",),
}

_ENDPOINT_PATTERNS = {
    "landing inhibition": (r"\blanding inhibition\b",),
    "landing": (r"\blanding(?:s)?\b",),
    "biting inhibition": (r"\bbiting inhibition\b",),
    "biting": (r"\bbit(?:e|es|ing)\b",),
    "complete protection time": (r"\bcomplete protection time\b", r"\bcpt\b"),
    "protection": (r"\bprotection\b",),
    "repellency": (
        r"\brepellency\b",
        r"\bpercent repellen",
    ),
    "avoidance": (r"\bavoidance\b",),
    "oviposition deterrence": (r"\boviposition deterr",),
}

_FORMULATION_PATTERNS = {
    "emanator": (r"\bemanator\b",),
    "treated fabric": (r"\btreated (?:fabric|net|material)\b",),
    "lotion": (r"\blotion\b",),
    "aerosol": (r"\baerosol\b",),
    "oil": (r"\boil\b",),
    "solution": (r"\bsolution\b",),
}

_DISCOVERY_METADATA_MARKERS = (
    "\nInclusion paths:",
    "\nOpenAlex search term:",
    "\nOpenAlex search mode:",
    "\nOpenAlex topic group:",
    "\nOpenAlex candidate status:",
)


def is_repellency_comparison_question(question: str) -> bool:
    normalized = question.lower()
    return any(term in normalized for term in _REPELLENCY_TERMS) and any(
        term in normalized for term in _COMPARISON_TERMS
    )


def _comparison_scope(question: str) -> dict[str, object]:
    normalized = question.lower()
    if (
        "drosophila suzukii" in normalized
        or "spotted wing drosophila" in normalized
        or re.search(r"\bswd\b", normalized)
    ):
        return {
            "species": "Drosophila suzukii",
            "metadata_sources": SWD_REPELLENCY_METADATA_SOURCES,
            "depth_sources": SWD_REPELLENCY_DEPTH_SOURCES,
            "metadata_is_repellency_bounded": False,
        }
    return {
        "species": "Culicidae",
        "metadata_sources": MOSQUITO_REPELLENCY_METADATA_SOURCES,
        "depth_sources": MOSQUITO_REPELLENCY_DEPTH_SOURCES,
        "metadata_is_repellency_bounded": True,
    }


def _record_with_payload(row: dict[str, object]) -> EvidenceRecord:
    record = EvidenceRecord.from_row(row)
    raw_payload = row.get("payload_json")
    payload: dict[str, Any] | None = None
    if isinstance(raw_payload, str) and raw_payload:
        parsed = json.loads(raw_payload)
        if isinstance(parsed, dict):
            payload = parsed
    return EvidenceRecord(
        record_id=record.record_id,
        lane=record.lane,
        source=record.source,
        title=record.title,
        text=record.text,
        species=record.species,
        url=record.url,
        media_url=record.media_url,
        provenance=record.provenance,
        payload=payload,
    )


def _source_records(
    index: SourceIndex,
    source_ids: tuple[str, ...],
    *,
    lanes: tuple[str, ...] | None = None,
    fact_types: tuple[str, ...] | None = None,
) -> list[EvidenceRecord]:
    source_placeholders = ",".join("?" for _ in source_ids)
    conditions = [f"r.source IN ({source_placeholders})"]
    params: list[object] = list(source_ids)
    if lanes:
        lane_placeholders = ",".join("?" for _ in lanes)
        conditions.append(f"r.lane IN ({lane_placeholders})")
        params.extend(lanes)
    if fact_types:
        fact_placeholders = ",".join("?" for _ in fact_types)
        conditions.append(
            "("
            f"json_extract(p.payload_json, '$.fact_type') IN ({fact_placeholders}) "
            "OR json_extract(p.payload_json, '$.atom_type') = 'source_gap' "
            "OR r.record_id LIKE r.source || ':gap:%'"
            ")"
        )
        params.extend(fact_types)
    with index.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, p.payload_json
            FROM records r
            LEFT JOIN record_payloads p ON p.record_id = r.record_id
            WHERE {" AND ".join(conditions)}
            ORDER BY r.source, r.record_id
            """,
            params,
        ).fetchall()
    return [_record_with_payload(dict(row)) for row in rows]


def _is_source_gap(record: EvidenceRecord) -> bool:
    payload = record.payload or {}
    return (
        payload.get("artifact_type") == "source_gap"
        or payload.get("atom_type") == "source_gap"
        or record.record_id.startswith(f"{record.source}:gap:")
    )


_NON_MATERIAL_GAP_REASONS = {
    "missing_doi",
    "no_supplement_metadata_found",
    "pubmed_skipped",
    "supplement_discovery_not_run",
}


def _reference_aliases(record: EvidenceRecord) -> set[str]:
    payload = record.payload or {}
    values: list[object] = [
        record.record_id,
        payload.get("record_id"),
        payload.get("source_record_id"),
        payload.get("id"),
        payload.get("openalex_id"),
    ]
    raw_openalex = payload.get("raw_openalex_work")
    if isinstance(raw_openalex, dict):
        values.append(raw_openalex.get("id"))

    aliases: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        aliases.add(text.lower())
        openalex_match = re.search(r"(?:openalex(?:\.org/|:))?(W\d+)", text, re.I)
        if openalex_match:
            aliases.add(f"openalex:{openalex_match.group(1).upper()}".lower())
    return aliases


def _is_material_source_gap(
    record: EvidenceRecord,
    *,
    metadata_is_repellency_bounded: bool,
    candidate_aliases: set[str],
) -> bool:
    payload = record.payload or {}
    reason = str(payload.get("reason") or payload.get("gap_reason") or "").strip()
    normalized_reason = reason.lower()
    if normalized_reason in _NON_MATERIAL_GAP_REASONS:
        return False
    if metadata_is_repellency_bounded:
        return True

    referenced_aliases = {
        alias
        for alias in _reference_aliases(record)
        if alias != record.record_id.lower()
    }
    if referenced_aliases:
        return bool(referenced_aliases.intersection(candidate_aliases))
    if record.source != "drosophila_suzukii_core":
        return True
    return any(
        term in normalized_reason
        for term in ("literature", "openalex", "pubmed", "fulltext", "supplement")
    )


def _normalize_doi(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.rstrip(".") or None


def _normalized_title(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _paper_key(record: EvidenceRecord) -> str:
    payload = record.payload or {}
    doi = _normalize_doi(payload.get("doi"))
    if doi:
        return f"doi:{doi}"
    pmid = str(payload.get("pmid") or "").strip()
    if pmid:
        return f"pmid:{pmid}"
    title = _normalized_title(payload.get("title") or record.title)
    return f"title:{title}" if title else f"record:{record.record_id}"


def _paper_identities(record: EvidenceRecord) -> tuple[str | None, str | None, str]:
    payload = record.payload or {}
    return (
        _normalize_doi(payload.get("doi")),
        str(payload.get("pmid") or "").strip() or None,
        _normalized_title(payload.get("title") or record.title),
    )


def _document_evidence_text(record: EvidenceRecord) -> str:
    text = record.text
    cutoffs = [
        position
        for marker in _DISCOVERY_METADATA_MARKERS
        if (position := text.find(marker)) >= 0
    ]
    if cutoffs:
        text = text[: min(cutoffs)]
    text = re.sub(
        r"\s+Common name:\s*spotted[- ]wing drosophila\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"<[^>]+>", " ", f"{record.title}\n{text}")


def _is_swd_subject_candidate(record: EvidenceRecord) -> bool:
    document_text = _document_evidence_text(record)
    return bool(
        re.search(
            r"\bsuzukii\b|\bspotted[- ]wing drosophil(?:a|id)\b",
            document_text,
            flags=re.IGNORECASE,
        )
    )


def _is_repellency_candidate(record: EvidenceRecord) -> bool:
    haystack = _document_evidence_text(record).lower()
    return any(
        term in haystack
        for term in (
            "repellent",
            "repellency",
            "deterren",
            "avoidance",
            "deet",
            "picaridin",
            "icaridin",
            "ir3535",
            "citronella",
            "metofluthrin",
            "transfluthrin",
            "prallethrin",
        )
    )


def _deduplicated_papers(
    records: list[EvidenceRecord],
) -> dict[str, list[EvidenceRecord]]:
    if not records:
        return {}

    identities = [_paper_identities(record) for record in records]
    parents = list(range(len(records)))
    group_dois = [{doi} if doi else set() for doi, _, _ in identities]
    group_pmids = [{pmid} if pmid else set() for _, pmid, _ in identities]

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int, *, identity_type: str) -> bool:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return True
        if (
            identity_type != "doi"
            and group_dois[left_root]
            and group_dois[right_root]
            and group_dois[left_root].isdisjoint(group_dois[right_root])
        ):
            return False
        if (
            identity_type == "title"
            and group_pmids[left_root]
            and group_pmids[right_root]
            and group_pmids[left_root].isdisjoint(group_pmids[right_root])
        ):
            return False
        parents[right_root] = left_root
        group_dois[left_root].update(group_dois[right_root])
        group_pmids[left_root].update(group_pmids[right_root])
        return True

    for identity_type, position in (("doi", 0), ("pmid", 1), ("title", 2)):
        buckets: dict[str, list[int]] = {}
        for index, identity in enumerate(identities):
            value = identity[position]
            if value:
                buckets.setdefault(value, []).append(index)
        for members in buckets.values():
            for offset, member in enumerate(members[1:], start=1):
                for candidate in members[:offset]:
                    if union(candidate, member, identity_type=identity_type):
                        break

    grouped: dict[int, list[EvidenceRecord]] = {}
    for index, record in enumerate(records):
        grouped.setdefault(find(index), []).append(record)

    papers: dict[str, list[EvidenceRecord]] = {}
    for root, paper_records in grouped.items():
        dois = sorted(group_dois[find(root)])
        pmids = sorted(group_pmids[find(root)])
        titles = sorted(
            title
            for index, (_, _, title) in enumerate(identities)
            if find(index) == find(root) and title
        )
        if dois:
            key = f"doi:{dois[0]}"
        elif pmids:
            key = f"pmid:{pmids[0]}"
        elif titles:
            key = f"title:{titles[0]}"
        else:
            key = f"record:{paper_records[0].record_id}"
        papers[key] = paper_records
    return papers


def _field_values(payload: dict[str, Any], key: str) -> list[str]:
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return []
    value = fields.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _matches(text: str, patterns: dict[str, tuple[str, ...]]) -> list[str]:
    matches: list[str] = []
    for label, alternatives in patterns.items():
        if any(
            re.search(pattern, text, flags=re.IGNORECASE) for pattern in alternatives
        ):
            matches.append(label)
    return matches


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_exposure_values(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        lowered = value.strip().lower()
        if re.search(r"\b(?:non|no)[- ]?contact\b", lowered):
            normalized.append("non-contact")
        elif (
            "spatial" in lowered
            or "vapor" in lowered
            or "vapour" in lowered
            or "airborne" in lowered
        ):
            normalized.append("spatial")
        elif "topical" in lowered or "skin application" in lowered:
            normalized.append("topical")
        elif lowered == "contact":
            normalized.append("contact")
    return _unique(normalized)


def _first_match(
    text: str, patterns: tuple[str, ...], *, flags: int = re.IGNORECASE
) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=flags)
        if match:
            return match.group(1).strip()
    return None


def _extract_outcome(text: str) -> str | None:
    metric = r"landing inhibition|biting inhibition|repellency|protection|avoidance|oviposition deterrence"
    direct = re.search(
        rf"\b({metric})\s+(?:was|of|=|:)\s*(\d+(?:\.\d+)?\s*%)",
        text,
        flags=re.IGNORECASE,
    )
    if direct:
        return f"{direct.group(2).replace(' ', '')} {direct.group(1).lower()}"
    reverse = re.search(
        rf"\b(\d+(?:\.\d+)?\s*%)\s+({metric})\b", text, flags=re.IGNORECASE
    )
    if reverse:
        return f"{reverse.group(1).replace(' ', '')} {reverse.group(2).lower()}"
    return None


def _extract_species(text: str, fallback: str | None) -> str | None:
    species_patterns = (
        (r"\baedes aegypti\b", "Aedes aegypti"),
        (r"\baedes albopictus\b", "Aedes albopictus"),
        (r"\banopheles gambiae\b", "Anopheles gambiae"),
        (r"\bculex quinquefasciatus\b", "Culex quinquefasciatus"),
        (r"\bdrosophila suzukii\b", "Drosophila suzukii"),
    )
    for pattern, species in species_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return species
    return fallback


def _comparison_row(
    record: EvidenceRecord, parent_record: EvidenceRecord | None = None
) -> dict[str, object]:
    payload = record.payload or {}
    evidence_text = str(payload.get("evidence_text") or record.text)
    combined = f"{record.title}\n{evidence_text}"

    compounds = _unique(
        _field_values(payload, "compound") + _matches(combined, _COMPOUND_PATTERNS)
    )
    exposures = _normalize_exposure_values(
        _field_values(payload, "exposure_mode") + _matches(combined, _EXPOSURE_PATTERNS)
    )
    assays = _unique(
        _field_values(payload, "assay") + _matches(combined, _ASSAY_PATTERNS)
    )
    declared_endpoints = _field_values(payload, "endpoint")
    endpoints = _unique(declared_endpoints or _matches(combined, _ENDPOINT_PATTERNS))
    formulations = _unique(
        _field_values(payload, "formulation")
        + _matches(combined, _FORMULATION_PATTERNS)
    )
    life_stages = _unique(
        _field_values(payload, "life_stage")
        + _matches(
            combined, {"adult": (r"\badults?\b",), "larva": (r"\blarv(?:a|ae|al)\b",)}
        )
    )
    sexes = _unique(
        _field_values(payload, "sex")
        + _matches(combined, {"female": (r"\bfemales?\b",), "male": (r"\bmales?\b",)})
    )

    dose = _first_match(
        evidence_text,
        (
            r"\b(\d+(?:\.\d+)?\s*%)",
            r"\b(\d+(?:\.\d+)?\s*(?:mg|ug|g)/(?:cm2|m2|ml|l))\b",
            r"\b(\d+(?:\.\d+)?\s*ppm)\b",
        ),
    )
    duration = _first_match(
        evidence_text, (r"\b(\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?))\b",)
    )
    sample_size_text = _first_match(evidence_text, (r"\bn\s*=\s*(\d+)\b",))
    statistical_result = _first_match(evidence_text, (r"\b(p\s*[<=>]\s*0?\.\d+)\b",))
    uncertainty = _first_match(
        evidence_text, (r"\b(\d+(?:\.\d+)?%?\s*(?:ci|confidence interval)[^.;,]*)",)
    )
    control = _first_match(
        evidence_text,
        (
            r"\b((?:untreated|solvent|vehicle|negative|positive) control)\b",
            r"\b(control (?:group|arm|condition))\b",
        ),
    )
    confidence = str(payload.get("confidence") or "candidate").strip().lower()
    human_verified = bool(payload.get("human_verified")) or confidence in {
        "human_verified",
        "verified",
    }

    return {
        "record_id": record.record_id,
        "source_record_id": payload.get("source_record_id"),
        "source": record.source,
        "title": record.title,
        "paper_title": parent_record.title if parent_record else record.title,
        "paper_record_id": parent_record.record_id
        if parent_record
        else payload.get("source_record_id"),
        "paper_key": _paper_key(parent_record) if parent_record else None,
        "doi": _normalize_doi((parent_record.payload or {}).get("doi"))
        if parent_record
        else None,
        "pmid": (parent_record.payload or {}).get("pmid") if parent_record else None,
        "species": _extract_species(combined, record.species),
        "strain": _field_values(payload, "strain"),
        "sexes": sexes,
        "life_stages": life_stages,
        "compounds": compounds,
        "formulations": formulations,
        "dose": dose.replace(" ", "") if dose and dose.endswith("%") else dose,
        "exposure_modes": exposures,
        "assays": assays,
        "endpoints": endpoints,
        "outcome": _extract_outcome(evidence_text),
        "duration": duration,
        "control": control.lower() if control else None,
        "sample_size": int(sample_size_text) if sample_size_text else None,
        "statistical_result": statistical_result.replace(" ", "")
        if statistical_result
        else None,
        "uncertainty": uncertainty,
        "confidence": confidence,
        "human_verified": human_verified,
        "evidence_text": evidence_text,
        "url": record.url,
        "provenance": record.provenance.to_dict(),
    }


def _target_profile(question: str) -> dict[str, object]:
    normalized = question.lower()
    dose = _first_match(
        question, (r"\b(\d+(?:\.\d+)?\s*%)", r"\b(\d+(?:\.\d+)?\s*ppm)\b")
    )
    return {
        "species": _extract_species(question, None),
        "compounds": _matches(normalized, _COMPOUND_PATTERNS),
        "exposure_modes": _matches(normalized, _EXPOSURE_PATTERNS),
        "assays": _matches(normalized, _ASSAY_PATTERNS),
        "endpoints": _matches(normalized, _ENDPOINT_PATTERNS),
        "dose": dose.replace(" ", "") if dose else None,
        "duration": _first_match(
            question, (r"\b(\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?))\b",)
        ),
        "outcome": _extract_outcome(question),
    }


def _claim_type(question: str) -> str:
    normalized = question.lower()
    named_compounds = _matches(normalized, _COMPOUND_PATTERNS)
    literature_wide = any(
        term in normalized
        for term in (
            "in the literature",
            "than the literature",
            "best",
            "strongest",
            "most effective",
            "leading",
            "nothing beats",
            "nothing in the literature",
        )
    )
    if literature_wide:
        return "literature_superlative"
    if len(named_compounds) >= 2 and any(
        term in normalized for term in ("compare", "beat", "better", "outperform")
    ):
        return "pairwise_comparison"
    return "comparative_summary"


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _directly_comparable(row: dict[str, object], target: dict[str, object]) -> bool:
    if any(
        not target.get(target_key) for _, target_key in SUPERLATIVE_TARGET_REQUIREMENTS
    ):
        return False
    if row.get("species") != target.get("species"):
        return False
    for row_field, target_field in (
        ("exposure_modes", "exposure_modes"),
        ("assays", "assays"),
        ("endpoints", "endpoints"),
    ):
        if not set(row.get(row_field) or []).intersection(
            target.get(target_field) or []
        ):
            return False
    return all(
        row.get(field) == target.get(field) for field in ("dose", "duration", "outcome")
    )


def _row_matches_target_context(
    row: dict[str, object], target: dict[str, object]
) -> bool:
    target_species = target.get("species")
    if target_species and row.get("species") != target_species:
        return False
    for row_field, target_field in (
        ("exposure_modes", "exposure_modes"),
        ("assays", "assays"),
        ("endpoints", "endpoints"),
    ):
        requested = set(target.get(target_field) or [])
        if requested and not set(row.get(row_field) or []).intersection(requested):
            return False
    for field in ("dose", "duration"):
        requested_value = target.get(field)
        if requested_value and row.get(field) != requested_value:
            return False
    return True


def _pairwise_comparable_rows(
    rows: list[dict[str, object]],
    requested_compounds: set[str],
    target: dict[str, object],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    if len(requested_compounds) != 2:
        return []
    first_compound, second_compound = sorted(requested_compounds)
    first_rows = [row for row in rows if first_compound in row.get("compounds", [])]
    second_rows = [row for row in rows if second_compound in row.get("compounds", [])]
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for first in first_rows:
        for second in second_rows:
            if not _row_matches_target_context(
                first, target
            ) or not _row_matches_target_context(second, target):
                continue
            if first.get("species") != second.get("species"):
                continue
            if any(
                not set(first.get(field) or []).intersection(second.get(field) or [])
                for field in ("exposure_modes", "assays", "endpoints")
            ):
                continue
            if any(
                not first.get(field) or first.get(field) != second.get(field)
                for field in ("dose", "duration")
            ):
                continue
            if not all(
                row.get("outcome")
                and (row.get("statistical_result") or row.get("uncertainty"))
                for row in (first, second)
            ):
                continue
            pairs.append((first, second))
    return pairs


def _evidence_item(record: EvidenceRecord) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "lane": record.lane,
        "source": record.source,
        "title": record.title,
        "text": record.text,
        "species": record.species,
        "url": record.url,
        "media_url": record.media_url,
        "provenance": record.provenance.to_dict(),
    }


def _fulltext_paper_count(
    index: SourceIndex,
    paper_key_by_record_id: dict[str, str],
) -> int:
    with index.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT record_id FROM literature_fulltext_units",
        ).fetchall()
    return len(
        {
            paper_key_by_record_id[str(row[0])]
            for row in rows
            if str(row[0]) in paper_key_by_record_id
        }
    )


def build_repellency_comparison_answer(
    index: SourceIndex,
    question: str,
    *,
    limit: int = 10,
) -> dict[str, object]:
    scope = _comparison_scope(question)
    metadata_sources = tuple(str(source) for source in scope["metadata_sources"])
    depth_sources = tuple(str(source) for source in scope["depth_sources"])
    metadata_records = _source_records(
        index,
        metadata_sources,
        lanes=("literature", "datasets", "patents", "source_coverage"),
    )
    depth_records = _source_records(
        index,
        depth_sources,
        fact_types=("supplement_audit", "repellency_assay"),
    )

    all_source_gaps = [
        record for record in metadata_records + depth_records if _is_source_gap(record)
    ]
    discovered_records = [
        record
        for record in metadata_records
        if not _is_source_gap(record)
        and record.lane in {"literature", "datasets", "patents"}
        and (
            bool(scope["metadata_is_repellency_bounded"])
            or (
                _is_swd_subject_candidate(record)
                and _is_repellency_candidate(record)
            )
        )
    ]
    papers = _deduplicated_papers(discovered_records)
    candidate_aliases = {
        alias for record in discovered_records for alias in _reference_aliases(record)
    }
    source_gaps = [
        record
        for record in all_source_gaps
        if _is_material_source_gap(
            record,
            metadata_is_repellency_bounded=bool(
                scope["metadata_is_repellency_bounded"]
            ),
            candidate_aliases=candidate_aliases,
        )
    ]
    metadata_by_record_id = {record.record_id: record for record in discovered_records}
    paper_key_by_record_id = {
        record.record_id: paper_key
        for paper_key, paper_records in papers.items()
        for record in paper_records
    }

    audit_records = [
        record
        for record in depth_records
        if (record.payload or {}).get("fact_type") == "supplement_audit"
    ]
    depth_parent_ids = {
        str((record.payload or {}).get("source_record_id"))
        for record in audit_records
        if (record.payload or {}).get("source_record_id")
    }
    depth_paper_keys = {
        paper_key_by_record_id[parent_id]
        for parent_id in depth_parent_ids
        if parent_id in paper_key_by_record_id
    }
    all_assay_records = [
        record
        for record in depth_records
        if (record.payload or {}).get("fact_type") == "repellency_assay"
    ]
    assay_records = [
        record
        for record in all_assay_records
        if str((record.payload or {}).get("source_record_id") or "")
        in metadata_by_record_id
    ]
    orphan_assay_records = [
        record for record in all_assay_records if record not in assay_records
    ]
    comparison_rows = [
        _comparison_row(
            record,
            metadata_by_record_id.get(
                str((record.payload or {}).get("source_record_id") or "")
            ),
        )
        for record in assay_records
    ]
    target = _target_profile(question)
    direct_rows = [row for row in comparison_rows if _directly_comparable(row, target)]
    verified_rows = [row for row in comparison_rows if row["human_verified"]]

    installed_sources = sorted(
        {record.source for record in metadata_records + depth_records}
    )
    source_gap_reason_counts = Counter(
        str(
            (record.payload or {}).get("reason")
            or (record.payload or {}).get("gap_reason")
            or "unspecified"
        )
        for record in source_gaps
    )
    coverage = {
        "discovered_records": len(discovered_records),
        "deduplicated_papers": len(papers),
        "papers_with_fulltext": _fulltext_paper_count(
            index, paper_key_by_record_id
        ),
        "papers_with_depth_outcome": len(depth_paper_keys),
        "structured_assay_facts": len(comparison_rows),
        "orphan_structured_assay_facts": len(orphan_assay_records),
        "human_verified_assay_facts": len(verified_rows),
        "directly_comparable_assay_facts": len(direct_rows),
        "unresolved_source_gaps": len(source_gaps),
        "bookkeeping_gap_records_excluded": len(all_source_gaps)
        - len(source_gaps),
        "depth_coverage_fraction": (
            round(len(depth_paper_keys) / len(papers), 4) if papers else 0.0
        ),
        "searched_sources": list(metadata_sources + depth_sources),
        "installed_sources": installed_sources,
        "source_gap_reason_counts": dict(sorted(source_gap_reason_counts.items())),
        "source_gap_records_omitted": max(
            0, len(source_gaps) - SOURCE_GAP_DETAIL_LIMIT
        ),
        "source_gaps": [
            {
                "record_id": record.record_id,
                "source_family": (record.payload or {}).get("source_family"),
                "reason": (record.payload or {}).get("reason"),
                "detail": (record.payload or {}).get("detail"),
                "provenance": record.provenance.to_dict(),
            }
            for record in source_gaps[:SOURCE_GAP_DETAIL_LIMIT]
        ],
    }

    claim_type = _claim_type(question)
    reasons: list[dict[str, str]] = []
    comparable_pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    missing_target_fields = [
        label
        for label, target_key in SUPERLATIVE_TARGET_REQUIREMENTS
        if not target.get(target_key)
    ]

    if claim_type == "literature_superlative":
        if missing_target_fields:
            reasons.append(
                _reason(
                    "missing_target_profile",
                    "The target result is missing required assay dimensions: "
                    + ", ".join(missing_target_fields)
                    + ".",
                )
            )
        if len(depth_paper_keys) < len(papers):
            reasons.append(
                _reason(
                    "incomplete_depth_coverage",
                    f"Only {len(depth_paper_keys)} of {len(papers)} deduplicated candidate papers have a recorded depth outcome.",
                )
            )
        if not direct_rows:
            reasons.append(
                _reason(
                    "no_directly_comparable_assays",
                    "No structured assay fact matches every required target dimension.",
                )
            )
        if source_gaps:
            reasons.append(
                _reason(
                    "unresolved_source_gaps",
                    f"{len(source_gaps)} literature-discovery source gap(s) remain unresolved.",
                )
            )
        if orphan_assay_records:
            reasons.append(
                _reason(
                    "orphan_assay_facts",
                    f"{len(orphan_assay_records)} structured assay fact(s) are not linked to a discovered parent paper.",
                )
            )
        decisive_verified = [row for row in direct_rows if row["human_verified"]]
        if not decisive_verified:
            reasons.append(
                _reason(
                    "no_human_verified_decisive_evidence",
                    "No directly comparable decisive assay fact is marked as human verified.",
                )
            )
        if direct_rows and not any(
            row.get("outcome")
            and (row.get("uncertainty") or row.get("statistical_result"))
            for row in direct_rows
        ):
            reasons.append(
                _reason(
                    "missing_numeric_or_statistical_evidence",
                    "Directly comparable rows lack a numeric outcome with uncertainty or a statistical result.",
                )
            )
        status = "insufficient_evidence" if reasons else "eligible_for_expert_review"
    elif claim_type == "pairwise_comparison":
        requested_compounds = set(target["compounds"])
        evidenced_compounds = {
            compound for row in comparison_rows for compound in row["compounds"]
        }
        missing_compounds = sorted(requested_compounds - evidenced_compounds)
        comparable_pairs = _pairwise_comparable_rows(
            comparison_rows, requested_compounds, target
        )
        if missing_compounds:
            reasons.append(
                _reason(
                    "missing_pairwise_evidence",
                    "No structured assay fact was found for: "
                    + ", ".join(missing_compounds)
                    + ".",
                )
            )
        elif not comparable_pairs:
            reasons.append(
                _reason(
                    "no_comparable_pair",
                    "Both compounds have indexed assay facts, but no pair matches on species, exposure mode, assay, endpoint, dose, duration, and statistical evidence.",
                )
            )
        status = (
            "comparison_ready"
            if comparable_pairs and not missing_compounds
            else "insufficient_evidence"
        )
    else:
        if not comparison_rows:
            reasons.append(
                _reason(
                    "no_structured_assay_facts",
                    "The indexed repellent papers have no structured repellency assay facts yet.",
                )
            )
        status = "comparison_ready" if comparison_rows else "insufficient_evidence"

    if not discovered_records and not assay_records:
        answer = "I do not see indexed Ask Insects repellency evidence for this comparison yet."
        source_gap: dict[str, object] | None = {
            "lane": "literature",
            "reason": "The repellent metadata and paper-depth lanes contain no usable records.",
            "checked_sources": list(metadata_sources + depth_sources),
        }
        ok = False
    elif claim_type == "literature_superlative":
        if status == "eligible_for_expert_review":
            answer = (
                "The indexed evidence meets the mechanical prerequisites for expert review of a literature-wide "
                "repellency claim. Ask Insects does not automatically approve that claim."
            )
        else:
            answer = (
                "Ask Insects cannot support a literature-wide superiority claim from the indexed evidence. "
                f"It found {len(papers)} deduplicated candidate paper(s), {len(depth_paper_keys)} paper-depth "
                f"outcome(s), and {len(comparison_rows)} structured assay fact(s). "
                "The claim is blocked because "
                + "; ".join(reason["message"] for reason in reasons)
            )
        source_gap = None
        ok = True
    else:
        answer = (
            f"Ask Insects found {len(comparison_rows)} structured repellency assay fact(s) across "
            f"{len(papers)} deduplicated candidate paper(s). "
            + (
                "The indexed rows are ready for a bounded comparison on the reported dimensions."
                if status == "comparison_ready"
                else "A defensible comparison is not ready because "
                + "; ".join(reason["message"] for reason in reasons)
            )
        )
        source_gap = None
        ok = True

    ordered_evidence = [
        *assay_records,
        *audit_records,
        *discovered_records,
        *orphan_assay_records,
        *source_gaps,
    ]
    return {
        "ok": ok,
        "contract_version": REPELLENCY_COMPARISON_CONTRACT_VERSION,
        "answer_shape": "repellency_comparison",
        "answer": answer,
        "claim": {
            "type": claim_type,
            "status": status,
            "reasons": reasons,
            "missing_target_fields": missing_target_fields
            if claim_type == "literature_superlative"
            else [],
            "requires_human_review": claim_type == "literature_superlative",
        },
        "comparison": {
            "dimensions": list(COMPARISON_DIMENSIONS),
            "scope": {"species": scope["species"]},
            "target": target,
            "rows": comparison_rows[:limit],
            "directly_comparable_record_ids": [
                str(row["record_id"]) for row in direct_rows[:limit]
            ],
            "comparable_pair_record_ids": [
                [str(first["record_id"]), str(second["record_id"])]
                for first, second in comparable_pairs[:limit]
            ],
        },
        "coverage": coverage,
        "evidence": [_evidence_item(record) for record in ordered_evidence[:limit]],
        "source_gap": source_gap,
    }
