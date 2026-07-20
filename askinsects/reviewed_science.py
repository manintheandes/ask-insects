from __future__ import annotations

from importlib.resources import files as resource_files
import json
from pathlib import Path
import re

from .index import SourceIndex
from .provenance import public_provenance_locator
from .records import EvidenceRecord


CATALOG_SCHEMA_VERSION = "ask-insects-reviewed-science.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_CATALOG = REPO_ROOT / "config" / "reviewed-scientific-evidence.json"
EVALUATION_ONLY_FIELDS = frozenset(
    {
        "case_id",
        "expected_behavior",
        "forbidden_claims",
        "holdout",
        "question",
        "truth_packet",
        "why_realistic",
    }
)
_MATCH_TOKEN_EQUIVALENTS = {
    "assayed": "assay",
    "assaying": "assay",
    "allocation": "allocate",
    "allocations": "allocate",
    "allocated": "allocate",
    "boundary": "border",
    "boundaries": "border",
    "census": "sampling",
    "censuses": "sampling",
    "central": "center",
    "checks": "monitor",
    "colored": "color",
    "coloring": "color",
    "colors": "color",
    "collecting": "collect",
    "collects": "collect",
    "coloured": "color",
    "colour": "color",
    "colouring": "color",
    "colours": "color",
    "composited": "composite",
    "crowns": "crown",
    "distort": "misrepresent",
    "distorted": "misrepresent",
    "distribute": "stratify",
    "distributed": "stratified",
    "drawn": "sample",
    "draw": "sample",
    "enumerate": "measure",
    "enumerated": "measure",
    "enumerating": "measure",
    "examination": "inspect",
    "examinations": "inspect",
    "generalise": "represent",
    "generalize": "represent",
    "inspected": "inspect",
    "inspecting": "inspect",
    "inspections": "inspect",
    "measured": "measure",
    "monitoring": "monitor",
    "observations": "measurement",
    "partition": "stratify",
    "partitioned": "stratified",
    "perimeter": "border",
    "picks": "pick",
    "quantified": "measure",
    "quantify": "measure",
    "quantifying": "measure",
    "replicated": "replicate",
    "ripe": "ripening",
    "ripeness": "ripening",
    "subsampled": "sample",
    "subsampling": "sampling",
    "surveys": "survey",
    "tallies": "measurement",
    "tally": "measurement",
    "stiff": "hardness",
    "stiffer": "harder",
    "stiffest": "harder",
    "stiffness": "hardness",
    "treetop": "top",
    "treetops": "top",
}
_QUESTION_INTENTS = frozenset({"sampling_design"})
FORBIDDEN_SCIENTIFIC_SOURCE_PREFIXES = (
    "insect_intelligence_programs:",
)
EXACT_PUBLIC_SOURCE_ID_PREFIXES = ("doi:", "pubmed:", "pmc:", "epa:", "who:")
INDEX_LOCATOR_MARKERS = (
    "/home/",
    "artifacts/",
    "config/",
    "jsonpath=",
    ".json#",
    "#records/",
    "#works/",
)


class ReviewedScienceError(ValueError):
    pass


def default_reviewed_science_catalog() -> Path:
    if _REPOSITORY_CATALOG.is_file():
        return _REPOSITORY_CATALOG
    return Path(
        str(
            resource_files("askinsects.resources").joinpath(
                "reviewed-scientific-evidence.json"
            )
        )
    )


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ReviewedScienceError(f"{label} must be a list of objects")
    return value


def _strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewedScienceError(f"{label} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise ReviewedScienceError(f"{label} must not be empty")
    return [item.strip() for item in value]


def _reject_evaluation_coupling(value: object, *, path: str = "catalog") -> None:
    if isinstance(value, dict):
        forbidden = EVALUATION_ONLY_FIELDS.intersection(value)
        if forbidden:
            raise ReviewedScienceError(
                f"evaluation coupling is forbidden at {path}: {sorted(forbidden)}"
            )
        for key, child in value.items():
            _reject_evaluation_coupling(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_evaluation_coupling(child, path=f"{path}[{index}]")
    elif isinstance(value, str) and re.search(
        r"\b(?:swd|aedes|dbm)-[a-z0-9-]+-\d{2}\b", value, flags=re.IGNORECASE
    ):
        raise ReviewedScienceError(
            f"evaluation coupling is forbidden at {path}: case-like identifier"
        )


def _source_provenance_by_record(
    value: object,
    label: str,
) -> dict[str, dict[str, object]]:
    sources = _objects(value, label)
    by_record: dict[str, dict[str, object]] = {}
    for source_index, source in enumerate(sources):
        item_label = f"{label}[{source_index}]"
        record_id = str(source.get("record_id") or "").strip()
        title = str(source.get("title") or "").strip()
        public_url = str(source.get("public_url") or "").strip()
        source_id = str(source.get("source_id") or "").strip()
        locator = str(source.get("locator") or "").strip()
        if not all((record_id, title, source_id, locator)):
            raise ReviewedScienceError(
                f"{item_label} requires record_id, title, source_id, and locator"
            )
        if not public_url.startswith(("https://", "http://")):
            raise ReviewedScienceError(
                f"{item_label}.public_url must be a public HTTP(S) URL"
            )
        if record_id in by_record:
            raise ReviewedScienceError(f"{label} record_ids must be unique")
        by_record[record_id] = source
    return by_record


def validate_reviewed_science_catalog(payload: dict[str, object]) -> None:
    _reject_evaluation_coupling(payload)
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ReviewedScienceError(
            f"schema_version must be {CATALOG_SCHEMA_VERSION}"
        )
    if not isinstance(payload.get("last_reviewed"), str) or not str(
        payload["last_reviewed"]
    ).strip():
        raise ReviewedScienceError("last_reviewed must be a non-empty string")
    require_exact_source_provenance = payload.get(
        "require_exact_source_provenance", False
    )
    if not isinstance(require_exact_source_provenance, bool):
        raise ReviewedScienceError(
            "require_exact_source_provenance must be a boolean"
        )
    catalog_source_provenance = _source_provenance_by_record(
        payload.get("source_provenance", []),
        "source_provenance",
    )

    species = _objects(payload.get("species"), "species")
    topics = _objects(payload.get("topics"), "topics")
    species_ids: set[str] = set()
    for item in species:
        species_id = str(item.get("id") or "").strip()
        if not species_id or species_id in species_ids:
            raise ReviewedScienceError("species ids must be non-empty and unique")
        species_ids.add(species_id)
        if not isinstance(item.get("scientific_name"), str) or not str(
            item["scientific_name"]
        ).strip():
            raise ReviewedScienceError(
                f"species {species_id} scientific_name must be non-empty"
            )
        _strings(item.get("aliases"), f"species {species_id}.aliases")

    topic_ids: set[str] = set()
    referenced_record_ids: set[str] = set()
    for topic in topics:
        topic_id = str(topic.get("id") or "").strip()
        if not topic_id or topic_id in topic_ids:
            raise ReviewedScienceError("topic ids must be non-empty and unique")
        topic_ids.add(topic_id)
        requested_species = set(
            _strings(topic.get("species_ids"), f"topic {topic_id}.species_ids")
        )
        if not requested_species.issubset(species_ids):
            raise ReviewedScienceError(
                f"topic {topic_id} references unknown species ids"
            )
        match = topic.get("match")
        if not isinstance(match, dict):
            raise ReviewedScienceError(f"topic {topic_id}.match must be an object")
        if "species_may_be_implicit" in match and not isinstance(
            match["species_may_be_implicit"], bool
        ):
            raise ReviewedScienceError(
                f"topic {topic_id}.match.species_may_be_implicit must be a boolean"
            )
        implicit_required = match.get("implicit_species_required_any")
        if implicit_required is not None:
            if match.get("species_may_be_implicit") is not True:
                raise ReviewedScienceError(
                    f"topic {topic_id}.match.implicit_species_required_any requires "
                    "species_may_be_implicit=true"
                )
            if not _objects_as_string_groups(
                implicit_required,
                f"topic {topic_id}.match.implicit_species_required_any",
            ):
                raise ReviewedScienceError(
                    f"topic {topic_id}.match.implicit_species_required_any must not be empty"
                )
        question_intent = match.get("question_intent")
        if question_intent is not None and (
            not isinstance(question_intent, str)
            or question_intent not in _QUESTION_INTENTS
        ):
            raise ReviewedScienceError(
                f"topic {topic_id}.match.question_intent must be one of "
                f"{sorted(_QUESTION_INTENTS)}"
            )
        priority = match.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ReviewedScienceError(
                f"topic {topic_id}.match.priority must be an integer"
            )
        _strings(
            match.get("phrases"),
            f"topic {topic_id}.match.phrases",
            allow_empty=True,
        )
        required = _objects_as_string_groups(
            match.get("required_any"), f"topic {topic_id}.match.required_any"
        )
        if not required:
            raise ReviewedScienceError(
                f"topic {topic_id}.match.required_any must not be empty"
            )
        _strings(
            match.get("optional"),
            f"topic {topic_id}.match.optional",
            allow_empty=True,
        )
        _strings(
            match.get("excluded_any", []),
            f"topic {topic_id}.match.excluded_any",
            allow_empty=True,
        )
        if not isinstance(topic.get("answer"), str) or not str(
            topic["answer"]
        ).strip():
            raise ReviewedScienceError(f"topic {topic_id}.answer must be non-empty")
        source_record_ids = _strings(
            topic.get("source_record_ids"),
            f"topic {topic_id}.source_record_ids",
        )
        referenced_record_ids.update(source_record_ids)
        if any(
            record_id.startswith(FORBIDDEN_SCIENTIFIC_SOURCE_PREFIXES)
            for record_id in source_record_ids
        ):
            raise ReviewedScienceError(
                f"topic {topic_id} must cite an original scientific or official source; "
                "the internal insect-intelligence program ledger cannot substitute for evidence"
            )
        source_provenance = _source_provenance_by_record(
            topic.get("source_provenance", []),
            f"topic {topic_id}.source_provenance",
        )
        unknown_provenance_ids = set(source_provenance).difference(source_record_ids)
        if unknown_provenance_ids:
            raise ReviewedScienceError(
                f"topic {topic_id}.source_provenance references unknown source records"
            )
        if require_exact_source_provenance:
            missing_provenance = set(source_record_ids).difference(
                catalog_source_provenance,
                source_provenance,
            )
            if missing_provenance:
                raise ReviewedScienceError(
                    f"topic {topic_id} is missing exact source provenance for: "
                    + ", ".join(sorted(missing_provenance))
                )
            effective_provenance = dict(catalog_source_provenance)
            effective_provenance.update(source_provenance)
            for record_id in source_record_ids:
                source = effective_provenance[record_id]
                source_id = str(source["source_id"]).strip().casefold()
                locator = str(source["locator"]).strip().casefold()
                if not source_id.startswith(EXACT_PUBLIC_SOURCE_ID_PREFIXES):
                    raise ReviewedScienceError(
                        f"topic {topic_id} record {record_id} requires an exact public source_id"
                    )
                if any(marker in locator for marker in INDEX_LOCATOR_MARKERS):
                    raise ReviewedScienceError(
                        f"topic {topic_id} record {record_id} requires a claim-level locator, not an index locator"
                    )

    unknown_catalog_provenance_ids = set(catalog_source_provenance).difference(
        referenced_record_ids
    )
    if unknown_catalog_provenance_ids:
        raise ReviewedScienceError(
            "source_provenance references unknown source records: "
            + ", ".join(sorted(unknown_catalog_provenance_ids))
        )


def _objects_as_string_groups(value: object, label: str) -> list[list[str]]:
    if not isinstance(value, list):
        raise ReviewedScienceError(f"{label} must be a list of string lists")
    return [
        _strings(group, f"{label}[{index}]")
        for index, group in enumerate(value)
    ]


def load_reviewed_science_catalog(path: Path | None = None) -> dict[str, object]:
    catalog_path = Path(path) if path is not None else default_reviewed_science_catalog()
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewedScienceError(
            f"could not load reviewed science catalog: {catalog_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReviewedScienceError("reviewed science catalog must be an object")
    validate_reviewed_science_catalog(payload)
    return payload


def _normalize(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    return " ".join(_MATCH_TOKEN_EQUIVALENTS.get(token, token) for token in tokens)


def _contains(normalized_question: str, value: str) -> bool:
    needle = _normalize(value)
    if not needle:
        return False
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])",
            normalized_question,
        )
    )


def _has_intervention_decision_context(normalized_question: str) -> bool:
    contextless_question = re.sub(
        r"\b(?:repellent|spray|insecticide|pesticide|treatment|net|netting|mesh|"
        r"barrier)\s+(?:efficacy\s+)?"
        r"(?:trial|experiment|assay|study|arm|arms)\b",
        "",
        normalized_question,
    )
    contextless_question = re.sub(
        r"\b(?:adult\s+)?trap\s+counts?\b",
        "",
        contextless_question,
    )
    contextless_question = re.sub(
        r"\b(?:we are\s+)?testing\s+(?:an?\s+)?(?:[a-z0-9]+\s+)?treatment\b|"
        r"\b(?:treatment|treated) and (?:control|untreated) blocks\b",
        "",
        contextless_question,
    )
    sampling = (
        r"(?:sample|samples|sampled|sampling|collect|collected|collection|collections|"
        r"take|taking|taken|gather|gathered|gathering|pick|picked|picking|pull|pulls|"
        r"measure|measuring|measurement|measurements|monitor|estimate|estimated|"
        r"estimator|readout|stratify|stratified|represent|representative|"
        r"representativeness|assay|assaying|inspect|inspection|allocate|allocated|"
        r"balance|balanced|divide|divided|subsample|subsamples|replicate|replication|"
        r"select|selected|score|scoring|survey|apportion|apportioned|map|mapping|"
        r"surveillance)"
    )
    intervention = (
        r"(?:insecticide|pesticide|spray|sprayed|spraying|treated|treatment|repellent|repellents|"
        r"dispenser|dispensers|emitter|emitters|hardware|release|screen|screening|"
        r"fabric|barrier|net|netting|netted|sticky card|sticky cards|mesh|trap|traps|"
        r"trapping|station|stations|device|devices|application|applications|protection)"
    )
    sampling_match = re.search(rf"\b{sampling}\b", contextless_question)
    intervention_matches = list(
        re.finditer(rf"\b{intervention}\b", contextless_question)
    )
    if not intervention_matches:
        return False
    if re.search(
        rf"\b{intervention}\b.*\b(?:effective|effectiveness|efficacy|reliable|"
        r"reliability|works|work|prove|demonstrate|demonstrates)\b|"
        rf"\b(?:effective|effectiveness|efficacy|reliable|reliability|works|work|"
        rf"prove|demonstrate|demonstrates)\b.*\b{intervention}\b",
        contextless_question,
    ):
        return True
    if re.search(
        r"\b(?:screen|barrier|mesh|net|netting)\b.*\b"
        r"(?:effective|effectiveness|efficacy|reliable|reliability|works|work|prove)\b|"
        r"\b(?:effective|effectiveness|efficacy|reliable|reliability|works|work|prove)"
        r"\b.*\b(?:screen|barrier|mesh|net|netting)\b",
        contextless_question,
    ):
        return True
    if sampling_match is None:
        return True
    first_intervention = intervention_matches[0]
    if first_intervention.start() < sampling_match.start():
        prefix = contextless_question[: first_intervention.start()]
        return bool(
            re.search(
                r"^(?:should|where|which|can|could|does|do|is|are|would|will)\b",
                prefix.strip(),
            )
        )
    purpose = contextless_question[sampling_match.end() : first_intervention.start()]
    return bool(
        re.search(
            r"\b(?:to|for|so|before|where|which|guide|guides|determine|decide|choose|"
            r"choosing|select|selecting|locate|identify|establish|tell|target|targeting|"
            r"focus|focusing|put|hang|gets|needs|placement|prove)\b",
            purpose,
        )
    )


def _has_swd_fruit_sampling_subject(normalized_question: str) -> bool:
    sampling_term = (
        r"(?:sample|samples|sampled|sampling|collect|collected|collection|collections|"
        r"take|taking|taken|gather|gathered|gathering|pick|picked|picking|pull|pulls|"
        r"measure|measuring|measurement|measurements|monitor|estimate|estimated|"
        r"estimator|readout|stratify|stratified|position|positions|location|locations|"
        r"represent|representative|representativeness|stand|describe|pool|pools|"
        r"pooled|pooling|composite|compositing|rotate|rotated|assay|assaying|inspect|"
        r"inspection|allocate|allocated|balance|balanced|divide|divided|subsample|"
        r"subsamples|replicate|replication|revisit|revisited|selected|score|scoring|"
        r"survey|select|apportion|apportioned|map|mapping|surveillance)"
    )
    non_target = (
        r"(?:parasitoid|parasitoids|pollinator|pollinators|yeast|yeasts|predator|"
        r"predators|pathogen|pathogens|microbiome|fungus|fungi|bacterium|bacteria|"
        r"soil|leaf|leaves|mite|mites|spider|spiders)"
    )
    if re.search(rf"\b{non_target}\b", normalized_question):
        return False
    if re.search(
        r"\b(?:raspberry|raspberries|blueberry|blueberries|strawberry|strawberries|"
        r"blackberry|blackberries|grape|grapes|peach|peaches|plum|plums|"
        r"apricot|apricots|pear|pears)\b",
        normalized_question,
    ):
        return False
    if re.search(
        r"\b(?:adult\s+(?:swd\s+)?trap\s+counts?|trapping\s+stations?|trap\s+stations?)\b",
        normalized_question,
    ) and not re.search(
        r"\b(?:fruit|infestation)\b", normalized_question
    ):
        return False
    if re.search(
        r"\b(?:sunrise|sunset|dawn|dusk|clock time|clock times|time of day|diurnal|"
        r"morning|afternoon|photoperiod)\b",
        normalized_question,
    ):
        return False
    if re.search(r"\b(?:sugar|firmness|brix)\b", normalized_question) and not re.search(
        r"\binfestation\b", normalized_question
    ):
        return False
    return bool(re.search(rf"\b{sampling_term}\b", normalized_question))


def _has_sampling_design_intent(normalized_question: str) -> bool:
    if _has_intervention_decision_context(normalized_question):
        return False
    if not _has_swd_fruit_sampling_subject(normalized_question):
        return False
    design_term = (
        r"(?:sample|samples|sampled|sampling|collect|collected|collection|collections|"
        r"take|taking|taken|gather|gathered|gathering|pick|picked|picking|pull|pulls|"
        r"measure|measuring|measurement|measurements|monitor|estimate|estimated|"
        r"estimator|readout|stratify|stratified|represent|representative|"
        r"representativeness|misrepresent|defensible|hide|cover|rotate|repeated|"
        r"separate|span|capture|track|describe|scheme|routine|layout|location|locations|"
        r"stand|pool|pools|pooled|pooling|composite|compositing|conceal|understate|"
        r"obscure|rotated|assay|assaying|inspect|inspection|allocate|allocated|balance|"
        r"balanced|divide|divided|subsample|subsamples|replicate|replication|revisit|"
        r"revisited|select|selected|score|scoring|survey|apportion|apportioned|map|mapping|"
        r"surveillance)"
    )
    spatial_term = (
        r"(?:spatial|spatially|space|stratified|orchard|canopy|row|rows|aspect|aspects|side|sides|edge|edges|"
        r"border|interior|margin|tree|trees|center|centre|core|zone|zones|stratum|"
        r"strata|tier|tiers|quarter|height|heights|vertical|top|bottom|ground|lower|"
        r"upper|north|south|east|west|crown|layer|layers|neighborhood|neighborhoods|"
        r"sector|sectors|quadrant|quadrants|third|thirds|block|blocks|transect|"
        r"transects|depth|depths|terminus|termini|proximal|shell|shells|azimuth|"
        r"face|faces|limb|limbs|"
        r"branch|branches|position|positions|exposure|exposures|windward|leeward|"
        r"inner|outer|compass)"
    )
    temporal_term = (
        r"(?:season|seasonal|seasonwide|summer|week|weekly|fortnightly|successive|successively|"
        r"preharvest|midseason|first|final|initial|maximum|early|late|later|mature|"
        r"matures|maturity|phenology|phenological|development|multistage|ripen|"
        r"ripening|blush|color|cultivar|"
        r"cultivars|variety|varieties|harvest|pick|picking|population|density|"
        r"densities|changing|numbers|rise|temporally|abundance|pressure|sparse|"
        r"clustered|aggregation|peak|serial|succession|progression|over time)"
    )
    return bool(
        re.search(rf"\b{design_term}\b", normalized_question)
        and re.search(rf"\b{spatial_term}\b", normalized_question)
        and re.search(rf"\b{temporal_term}\b", normalized_question)
    )


def _question_intent_matches(intent: str, normalized_question: str) -> bool:
    if intent == "sampling_design":
        return _has_sampling_design_intent(normalized_question)
    return False


def _species_matches(
    normalized_question: str,
    species: list[dict[str, object]],
) -> set[str]:
    matches: set[str] = set()
    for item in species:
        aliases = [str(item["scientific_name"]), *_strings(item["aliases"], "aliases")]
        if any(_contains(normalized_question, alias) for alias in aliases):
            matches.add(str(item["id"]))
    return matches


def _topic_score(
    topic: dict[str, object],
    *,
    normalized_question: str,
    matched_species: set[str],
) -> int | None:
    topic_species = set(_strings(topic["species_ids"], "topic species_ids"))
    match = topic["match"]
    assert isinstance(match, dict)
    if matched_species and not topic_species.intersection(matched_species):
        return None
    if not matched_species:
        if match.get("species_may_be_implicit") is not True:
            return None
        implicit_required = _objects_as_string_groups(
            match.get("implicit_species_required_any", []),
            "topic match.implicit_species_required_any",
        )
        if implicit_required and not all(
            any(_contains(normalized_question, term) for term in group)
            for group in implicit_required
        ):
            return None
    question_intent = match.get("question_intent")
    if isinstance(question_intent, str) and not _question_intent_matches(
        question_intent, normalized_question
    ):
        return None
    excluded = _strings(
        match.get("excluded_any", []), "topic match.excluded_any", allow_empty=True
    )
    if any(_contains(normalized_question, term) for term in excluded):
        return None
    required_groups = _objects_as_string_groups(
        match["required_any"], "topic match.required_any"
    )
    if question_intent is None and not all(
        any(_contains(normalized_question, term) for term in group)
        for group in required_groups
    ):
        return None
    phrases = _strings(match["phrases"], "topic match.phrases", allow_empty=True)
    optional = _strings(match["optional"], "topic match.optional", allow_empty=True)
    score = int(match.get("priority", 0)) + 10 * len(required_groups)
    if question_intent is not None:
        score += 1000
    score += sum(
        8 + 2 * len(_normalize(phrase).split())
        for phrase in phrases
        if _contains(normalized_question, phrase)
    )
    score += sum(2 for term in optional if _contains(normalized_question, term))
    return score


def _records_by_ids(index: SourceIndex, record_ids: list[str]) -> list[EvidenceRecord]:
    placeholders = ",".join("?" for _ in record_ids)
    with index.connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM records WHERE record_id IN ({placeholders})",
            record_ids,
        ).fetchall()
    by_id = {
        str(row["record_id"]): EvidenceRecord.from_row(dict(row))
        for row in rows
    }
    return [by_id[record_id] for record_id in record_ids if record_id in by_id]


def _record_to_evidence(
    record: EvidenceRecord,
    source_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    provenance = record.provenance.to_dict()
    title = record.title
    url = record.url
    if source_provenance:
        title = str(source_provenance["title"]).strip()
        url = str(source_provenance["public_url"]).strip()
        provenance["source_id"] = str(source_provenance["source_id"]).strip()
        provenance["locator"] = str(source_provenance["locator"]).strip()
        provenance["source_url"] = url
    else:
        provenance["locator"] = public_provenance_locator(
            str(provenance.get("locator") or ""),
            record.provenance.source_id,
        )
    return {
        "record_id": record.record_id,
        "lane": record.lane,
        "source": record.source,
        "title": title,
        "text": record.text,
        "species": record.species,
        "url": url,
        "media_url": record.media_url,
        "provenance": provenance,
    }


def _has_original_public_url(record: EvidenceRecord) -> bool:
    candidates = (record.url, record.provenance.source_url)
    return any(
        isinstance(value, str)
        and bool(
            value.startswith(("https://", "http://"))
            or re.fullmatch(r"10\.\S+/\S+", value, flags=re.IGNORECASE)
        )
        for value in candidates
    )


def build_reviewed_science_answer(
    index: SourceIndex,
    question: str,
    *,
    catalog_path: Path | None = None,
) -> dict[str, object] | None:
    catalog = load_reviewed_science_catalog(catalog_path)
    species = _objects(catalog["species"], "species")
    normalized_question = _normalize(question)
    matched_species = _species_matches(normalized_question, species)

    scored: list[tuple[int, str, dict[str, object]]] = []
    for topic in _objects(catalog["topics"], "topics"):
        score = _topic_score(
            topic,
            normalized_question=normalized_question,
            matched_species=matched_species,
        )
        if score is not None:
            scored.append((score, str(topic["id"]), topic))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    topic = scored[0][2]
    record_ids = _strings(topic["source_record_ids"], "topic source_record_ids")
    records = _records_by_ids(index, record_ids)
    found_record_ids = {record.record_id for record in records}
    missing = [
        record_id for record_id in record_ids if record_id not in found_record_ids
    ]
    if missing:
        return {
            "ok": False,
            "answer_shape": "reviewed_science",
            "answer": "I do not see enough indexed Ask Insects evidence for this reviewed scientific topic yet.",
            "evidence": [],
            "source_gap": {
                "lane": "reviewed_science",
                "reason": (
                    "The reviewed source record set is incomplete: "
                    + ", ".join(missing)
                ),
            },
        }
    invalid_original_sources = [
        record.record_id
        for record in records
        if record.provenance.source_id == "insect_intelligence_programs"
        or not _has_original_public_url(record)
    ]
    if invalid_original_sources:
        return {
            "ok": False,
            "answer_shape": "reviewed_science",
            "answer": "I do not see enough exact original-source evidence for this reviewed scientific topic yet.",
            "evidence": [],
            "source_gap": {
                "lane": "reviewed_science",
                "reason": (
                    "Every reviewed scientific claim requires an original public source URL; "
                    "invalid records: " + ", ".join(invalid_original_sources)
                ),
            },
        }
    source_provenance = {
        str(item["record_id"]): item
        for item in _objects(
            catalog.get("source_provenance", []),
            "source_provenance",
        )
    }
    source_provenance.update({
        str(item["record_id"]): item
        for item in _objects(
            topic.get("source_provenance", []),
            "topic source_provenance",
        )
    })
    return {
        "ok": True,
        "answer_shape": "reviewed_science",
        "answer": str(topic["answer"]).strip(),
        "evidence": [
            _record_to_evidence(record, source_provenance.get(record.record_id))
            for record in records
        ],
        "source_gap": None,
    }
