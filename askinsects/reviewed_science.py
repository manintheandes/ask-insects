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
    "touched": "touch",
    "touches": "touch",
    "touching": "touch",
    "treetop": "top",
    "treetops": "top",
}
_QUESTION_INTENTS = frozenset(
    {
        "deet_repeat_exposure",
        "er_contact_only_result_pattern",
        "movement_inference",
        "olfactory_experience",
        "sampling_design",
    }
)
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
        _strings(
            item.get("generic_aliases", []),
            f"species {species_id}.generic_aliases",
            allow_empty=True,
        )

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
        required_normalized_pattern_groups = _objects_as_string_groups(
            match.get("required_normalized_pattern_groups", []),
            f"topic {topic_id}.match.required_normalized_pattern_groups",
        )
        for group in required_normalized_pattern_groups:
            for pattern in group:
                try:
                    re.compile(pattern, flags=re.IGNORECASE)
                except re.error as exc:
                    raise ReviewedScienceError(
                        f"topic {topic_id}.match.required_normalized_pattern_groups contains invalid regex"
                    ) from exc
        implicit_species_excluded_patterns = _strings(
            match.get("implicit_species_excluded_normalized_patterns", []),
            f"topic {topic_id}.match.implicit_species_excluded_normalized_patterns",
            allow_empty=True,
        )
        for pattern in implicit_species_excluded_patterns:
            try:
                re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                raise ReviewedScienceError(
                    f"topic {topic_id}.match.implicit_species_excluded_normalized_patterns contains invalid regex"
                ) from exc
        excluded_normalized_patterns = _strings(
            match.get("excluded_normalized_patterns", []),
            f"topic {topic_id}.match.excluded_normalized_patterns",
            allow_empty=True,
        )
        for pattern in excluded_normalized_patterns:
            try:
                re.compile(pattern, flags=re.IGNORECASE)
            except re.error as exc:
                raise ReviewedScienceError(
                    f"topic {topic_id}.match.excluded_normalized_patterns contains invalid regex"
                ) from exc
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
    if _has_movement_inference_intent(normalized_question):
        return False
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


def _has_movement_inference_intent(normalized_question: str) -> bool:
    spatial_pattern = re.search(
        r"\b(?:orchard|block|canopy|row|rows|edge|border|center|centre|north|south|"
        r"spatial|distribution|infestation|emergence)\b",
        normalized_question,
    )
    movement_claim = re.search(
        r"\b(?:movement|move|moved|moving|entry|entered|entering|immigration|"
        r"dispersal|trajectory|transition|transitions|flight path|flight paths|"
        r"origin|origins|direction|directional|trace|traced|tracing)\b",
        normalized_question,
    )
    inference_decision = re.search(
        r"\b(?:infer|inference|prove|establish|show|demonstrate|fit|fitting|model|"
        r"estimate|reconstruct|conclude|claim|evidence|study|track|tracked)\b",
        normalized_question,
    )
    return bool(spatial_pattern and movement_claim and inference_decision)


def _has_olfactory_experience_intent(normalized_question: str) -> bool:
    target = r"(?:odor|odour|host|repellent|repellency|deet)"
    experience = (
        r"(?:experience|experienced|exposure|exposed|contact|training|learning|"
        r"learned|habituation|adaptation|pre exposure)"
    )
    prior_target_experience = re.search(
        rf"\b(?:prior|previous|past|repeat|repeated|retested)\s+{target}"
        rf"(?:\s+\w+){{0,2}}\s+{experience}\b",
        normalized_question,
    )
    prior_experience_target = re.search(
        rf"\b(?:prior|previous|past|repeat|repeated|retested)\s+{experience}"
        rf"(?:\s+(?:to|with|from))?\s+{target}\b",
        normalized_question,
    )
    previously_exposed_target = re.search(
        rf"\bpreviously\s+exposed(?:\s+(?:to|with))?\s+{target}\b",
        normalized_question,
    )
    retested_after_target_experience = re.search(
        rf"\bretested(?:\s+\w+){{0,4}}\s+(?:after|following)\s+(?:"
        rf"{target}(?:\s+\w+){{0,2}}\s+{experience}|"
        rf"{experience}(?:\s+(?:to|with|from))?\s+{target})\b",
        normalized_question,
    )
    named_learning = re.search(
        r"\b(?:olfactory learning|odor learning|odour learning|host experience|"
        r"repellent experience|deet experience)\b",
        normalized_question,
    )
    bound_experience = re.search(
        rf"\b(?:{target}(?:\s+\w+){{0,2}}\s+{experience}|"
        rf"{experience}(?:\s+(?:to|with|from))?\s+{target})\b",
        normalized_question,
    )
    mechanism_question = re.search(
        r"\b(?:learning|learned|training|habituation|adaptation)\b",
        normalized_question,
    )
    return bool(
        named_learning
        or prior_target_experience
        or prior_experience_target
        or previously_exposed_target
        or retested_after_target_experience
        or (bound_experience and mechanism_question)
    )


def _has_deet_repeat_exposure_intent(normalized_question: str) -> bool:
    if not re.search(r"\bdeet\b", normalized_question):
        return False
    decision = re.search(
        r"\b(?:independent|replicate|efficacy|screen|control|rank|measurement|"
        r"assay|design|protocol|cohort|compare|comparison|crossover|carryover)\b",
        normalized_question,
    )
    repeat_before_deet = re.search(
        r"\b(?:repeat(?:ed|ing)?|retest(?:ed|ing)?|re exposure|prior exposure|"
        r"previous exposure|earlier exposure|pre exposure|second exposure|"
        r"previously exposed)\b"
        r"(?:\s+\w+){0,2}\s+\bdeet\b",
        normalized_question,
    )
    deet_exposure_before_effect = re.search(
        r"\bdeet\s+(?:exposure|challenge|test|measurement)\b"
        r"(?:\s+\w+){0,5}\s+\b(?:less|lower|reduced|decreased|weaker|changes?|changed)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:repel|repelled|repellency|response|responds?|responded)\b",
        normalized_question,
    )
    effect_after_deet_exposure = re.search(
        r"\b(?:(?:less|lower|reduced|decreased|weaker|changes?|changed)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:repel|repelled|repellency|response|responds?|responded)|"
        r"responded\s+(?:less|weakly|weaklier))\b"
        r"(?:\s+\w+){0,8}\s+\b(?:after|following)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:prior|previous|earlier|past)?\s*deet\s+"
        r"(?:exposure|challenge|test|measurement)\b",
        normalized_question,
    )
    exposed_to_deet_before = re.search(
        r"\bexposed(?:\s+\w+){0,2}\s+\bdeet\s+before\b",
        normalized_question,
    )
    qualified_deet_event = re.search(
        r"\b(?:prior|previous|repeat|repeated|second)\s+deet\s+"
        r"(?:exposure|challenge|test|measurement)\b",
        normalized_question,
    )
    deet_before_repeat = re.search(
        r"\bdeet\b(?:\s+\w+){0,4}\s+\b(?:again|carryover|repeat(?:ed|ing)?|"
        r"retest(?:ed|ing)?|re exposure|pre exposure|second challenge|exposure history)\b",
        normalized_question,
    )
    cage_rechallenge = re.search(
        r"\b(?:challenge|challenged|rechallenge|rechallenged|reuse|reuses|reusing)\s+"
        r"(?:the\s+)?same\s+(?:aedes\s+)?cage(?:\s+\w+){0,4}\s+deet\b|"
        r"\bsame\s+(?:aedes\s+)?cage(?:\s+\w+){0,4}\s+"
        r"(?:challenged|rechallenged|reused)(?:\s+\w+){0,2}\s+deet\b|"
        r"\bdeet(?:\s+\w+){0,4}\s+(?:challenge|challenged|rechallenge|"
        r"rechallenged|reuse|reuses|reusing)\s+(?:the\s+)?same\s+(?:aedes\s+)?cage\b|"
        r"\bsame\s+(?:aedes\s+)?cage(?:\s+\w+){0,5}\s+after\s+(?:a\s+)?deet\s+challenge\b",
        normalized_question,
    )
    return bool(
        decision
        and (
            repeat_before_deet
            or deet_exposure_before_effect
            or effect_after_deet_exposure
            or exposed_to_deet_before
            or qualified_deet_event
            or deet_before_repeat
            or cage_rechallenge
        )
    )


def _has_er_contact_only_result_pattern_intent(
    normalized_question: str,
    raw_question: str | None = None,
) -> bool:
    raw_text = raw_question or normalized_question
    before_question_mark = raw_text.rsplit("?", 1)[0]
    sentence_parts = re.split(
        r"(?<=[.!])\s+(?=[A-Za-z])",
        before_question_mark,
    )
    if "?" in raw_text and len(sentence_parts) > 1:
        raw_statement_text = " ".join(sentence_parts[:-1])
    else:
        raw_statement_text = before_question_mark
    statement_text = _normalize(raw_statement_text)
    clause_split_pattern = (
        r"(?<=[.!])\s+(?=[A-Za-z])|"
        r"\b(?:while|whereas|but|although|yet|then|and there was)\b|"
        r"\band (?=(?:became|greater|higher|increased|more|rose|"
        r"exceed(?:s|ed|ing)?)\b)|"
        r"\band (?=present with contact\b)|"
        r"\band (?=with (?:(?:direct|surface|paper|residue) )?contact\b)|"
        r"\band (?=(?:treatment|treated)\b"
        r"(?:\s+\w+){0,4}\s+"
        r"\b(?:escap(?:e|es|ed|ing)|exit(?:s|ed|ing)?|egress|"
        r"depart(?:ure|ed|ing)?|leav(?:e|es|ing)|left)\b"
        r"(?:\s+\w+){0,8}\s+\bwith "
        r"(?:(?:direct|surface|paper|residue) )?contact\b)"
    )

    def split_result_clauses(text: str) -> list[str]:
        clauses: list[str] = []
        for connector_part in re.split(
            clause_split_pattern,
            text,
            flags=re.IGNORECASE,
        ):
            depth = 0
            start = 0
            for index, character in enumerate(connector_part):
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth = max(0, depth - 1)
                elif character == ";" and depth == 0:
                    clauses.append(connector_part[start:index])
                    start = index + 1
            clauses.append(connector_part[start:])
        return clauses

    raw_result_clauses = split_result_clauses(raw_statement_text)
    result_clauses = [_normalize(clause) for clause in raw_result_clauses]
    noncontact_state_pattern = re.compile(
        r"\b(?:no contact|non contact|no touch|non touch|"
        r"without (?:contact|direct contact|surface contact|"
        r"paper contact|residue contact)|contact barred|contact free|"
        r"contact barrier (?:was )?in place|"
        r"contact restricted|(?:paper|surface|residue) (?:was )?inaccessible|"
        r"contact (?:was )?not (?:allowed|available|possible)|"
        r"contact (?:was )?"
        r"(?:blocked|denied|prevented|prohibited|restricted|unavailable|"
        r"excluded|impossible)|"
        r"(?:mesh|barrier) (?:blocked|prevented)|"
        r"(?:mesh|screen) separated (?:aedes|females|mosquitoes) from "
        r"(?:the )?(?:paper|surface|residue)|"
        r"behind (?:the )?(?:contact )?(?:mesh|barrier))\b"
    )
    contact_result_state_pattern = re.compile(
        r"(?<!no )(?<!non )\bcontact "
        r"(?:arm|chamber|condition|contrast|escape|estimate|group|increase|"
        r"result|treatment)\b|"
        r"(?<!without )(?<!blocked )(?<!denied )(?<!prevented )"
        r"\b(?:direct|surface|paper|residue) contact\b"
        r"(?! (?:was )?(?:blocked|excluded|prevented|prohibited|unavailable))|"
        r"(?<!no )(?<!non )\bcontact (?:was )?"
        r"(?:allowed|available|enabled|permitted|possible)\b|"
        r"\bcontact access (?:was )?(?:allowed|enabled|granted|permitted)\b|"
        r"\b(?:paper|surface|residue) became reachable(?: for contact)?\b|"
        r"\bwith contact\b"
        r"(?! (?:was )?(?:blocked|excluded|prevented|prohibited|unavailable))"
    )

    def qualifier_is_noncontact_only(clause: str) -> bool:
        return bool(noncontact_state_pattern.search(clause)) and not bool(
            contact_result_state_pattern.search(clause)
        )

    interval_failure_pattern = re.compile(
        r"\b(?:confidence|credible) interval\b"
        r"(?:\s+\w+){0,12}\s+"
        r"\b(?:covered|covering|crossed|included|contained|spanned|spanning|"
        r"straddled|straddling|overlapped|encompassed|encompassing) zero\b|"
        r"\b(?:confidence|credible) interval\b"
        r"(?:\s+\w+){0,12}\s+\b(?:extended|extends) below zero\b|"
        r"\b(?:confidence|credible) interval\b"
        r"(?:\s+\w+){0,6}\s+"
        r"\bran from\s+-|"
        r"\binterval\b(?:\s+\w+){0,4}\s+"
        r"\b(?:crossed|included|contained|spanned|overlapped) zero\b"
    )
    result_qualifier_pattern = re.compile(
        r"\b[pfq]\s*(?:>=|<=|=|>|<)\s*0?\.\d+\b|"
        r"\b(?:the )?same (?:one|two|three|four|five|six|seven|eight|"
        r"nine|ten|\d+) timepoints?\b|"
        r"\bin each (?:arm|condition|comparison|group)\b|"
        r"\b(?:\d+\s+)?(?:(?:confidence|credible)\s+)?interval"
        r"(?:\s+[a-z]+){1,12}(?:\s+\d+){1,3}\s+to"
        r"(?:\s+\d+){1,3}\b|"
        r"\b(?:\d+\s+)?(?:(?:confidence|credible)\s+)?interval"
        r"(?:\s+(?:from|of))?"
        r"(?:\s+\d+){1,3}\s+to(?:\s+\d+){1,3}\b|"
        r"\b(?:(?:confidence|credible)\s+)?interval\b"
        r"(?:\s+\w+){0,8}\s+\bpositive lower bound\b|"
        r"\b(?:entirely|wholly) positive "
        r"(?:(?:confidence|credible)\s+)?interval\b|"
        r"\b(?:(?:confidence|credible)\s+)?interval\b"
        r"(?:\s+\w+){0,12}\s+"
        r"\b(?:covered|covering|crossed|included|contained|spanned|spanning|"
        r"straddled|straddling|overlapped|overlapping|encompassed|"
        r"encompassing) zero\b|"
        r"\b(?:(?:confidence|credible)\s+)?interval\b"
        r"(?:\s+\w+){0,12}\s+"
        r"\b(?:(?:entirely|fully|wholly) (?:above zero|positive)|"
        r"(?:lay|remained|stayed) (?:above zero|positive))\b"
    )

    def raw_interval_spans_zero(raw_clause: str) -> bool:
        bounds = re.findall(
            r"\binterval(?:\s+[a-z-]+){0,12}\s+"
            r"(-?\d+(?:\.\d+)?)\s+to\s+"
            r"(-?\d+(?:\.\d+)?)\b",
            raw_clause.casefold(),
        )
        return any(float(low) <= 0 <= float(high) for low, high in bounds)

    no_contact_numeric_interval_null = any(
        raw_interval_spans_zero(raw_clause)
        and qualifier_is_noncontact_only(clause)
        for raw_clause, clause in zip(
            raw_result_clauses,
            result_clauses,
            strict=True,
        )
    )
    design_or_genetics_intent = re.search(
        r"\b(?:design|set up|plan)\s+(?:an?\s+)?(?:experiment|assay|study)\b|"
        r"\bhow should\b(?:\s+\w+){0,5}\s+\bset up\b|"
        r"\bshould (?:we|i)\b(?:\s+\w+){0,5}\s+\buse\b"
        r"(?:\s+\w+){0,5}\s+\bmodel\b|"
        r"\btest whether\b|"
        r"\b(?:which|what) (?:statistical model|regression model|"
        r"hypothesis test|"
        r"statistical test|statistical method|sample size|receptors?)\b|"
        r"\b(?:which|what) model\b|"
        r"\bwhich(?:\s+\w+){1,5}\s+model\b|"
        r"\bwhat analysis\b|"
        r"\bwhat statistical approach\b|"
        r"\bwhat statistical method\b|"
        r"\bwhat (?:statistical )?power\b|"
        r"\bwhat number of\b(?:\s+\w+){0,5}\s+\b(?:is|are) required\b|"
        r"\bwhat(?:\s+\w+){0,5}\s+\bdimensions\b|"
        r"\b(?:which|what) test\b|"
        r"\bwhich (?:analytical|analysis|statistical) test\b|"
        r"\bwhat(?:\s+\w+){0,3}\s+statistical test\b|"
        r"\bwhich link function\b|"
        r"\binteraction term\b|"
        r"\b(?:how should|what|which) (?:the )?"
        r"(?:confidence|credible) intervals?\b|"
        r"\bmultiplicity correction\b|"
        r"\bcontrast coding\b|"
        r"\bpost hoc test\b|"
        r"\b(?:paired )?t test\b|"
        r"\bbinomial model\b|"
        r"\bmesh pore size\b|"
        r"\bwhat chamber length\b|"
        r"\bshould\b(?:\s+\w+){0,5}\s+\b(?:separator|screen|mesh|barrier)\b"
        r"(?:\s+\w+){0,5}\s+\bmounted\b|"
        r"\bwhich(?:\s+\w+){1,5}\s+analysis\b|"
        r"\bwhich(?:\s+\w+){0,2}\s+receptors?\b|"
        r"\bwhich sensory neurons?\b|"
        r"\bhow many\b(?:\s+\w+){0,5}\s+\b(?:replicate|replicates)\b|"
        r"\bhow many\b(?:\s+\w+){0,5}\s+\b(?:batch|batches|cohort|cohorts|"
        r"group|groups|trial|trials)\b|"
        r"\bhow many mosquitoes\b(?:\s+\w+){0,5}\s+\b(?:group|contain)\b|"
        r"\bhow many mosquitoes (?:are )?needed\b|"
        r"\bhow many mosquitoes per chamber (?:are )?needed\b|"
        r"\bhow many mosquitoes per condition\b|"
        r"\bhow many chambers\b(?:\s+\w+){0,5}\s+\b(?:needed|required)\b|"
        r"\bhow many females\b(?:\s+\w+){0,5}\s+\b(?:test|tested)\b|"
        r"\bhow many females\b(?:\s+\w+){0,5}\s+\b(?:(?:is|are) )?needed\b|"
        r"\bhow many females per arm (?:are )?needed\b|"
        r"\bhow many insects\b(?:\s+\w+){0,6}\s+\beach arm\b|"
        r"\brandomiz(?:e|ed|es|ing|ation)\b|"
        r"\bbuild (?:an? )?apparatus\b|"
        r"\bwhich genes?\b|"
        r"\bknock ?out\b|"
        r"\breceptor perturbation\b",
        normalized_question,
    )
    procedural_question = re.search(
        r"^(?:which|what|how|where|should)\b",
        normalized_question,
    ) and re.search(
        r"\b(?:analyz(?:e|ed|es|ing)|analysis|apparatus|calculat(?:e|ed|ing)|"
        r"chamber dimensions?|covariance|fit|fitted|interaction|model|"
        r"outlet|position(?:ed|ing)?|"
        r"random slope|statistical|structure|test|transform(?:ed|ing)?)\b",
        normalized_question,
    )
    mechanism_term = re.search(
        r"\b(?:orco|pathway|chemosensation|olfaction|receptor|gene|mutant|"
        r"mutation|knockdown|trpa1|ir25a|absorption|tarsi|tarsal|"
        r"olfactory|gustatory neurons?|adaptation|"
        r"motor activation|motor stimulation|toxic effect|"
        r"toxic action|toxic response|toxicity|paralysis|sedation|"
        r"toxic stimulation|"
        r"sensory neurons?)\b",
        normalized_question,
    )
    causal_question = re.search(
        r"\b(?:could|can|might|may|would|does|did|are|were|is|was)\b",
        normalized_question,
    ) and re.search(
        r"\b(?:responsible|causes?|caused|causing|causal|creates?|created|"
        r"creating|explain|explained|"
        r"account|"
        r"drive|drives|mediate|mediates|mediated|reason)\b",
        normalized_question,
    )
    causal_mechanism_question = re.search(
        r"^(?:does|do|did|could|can|is|are|was|were)\b"
        r"(?:\s+\w+){0,12}\s+"
        r"\b(?:cause|causes|explain|mediate|drive|responsible)\b",
        normalized_question,
    )
    passive_knockdown_cause = re.search(
        r"\b(?:caused|explained|accounted for)\s+by\s+knockdown\b",
        normalized_question,
    )
    unsupported_contact_increase = re.search(
        r"\b(?:contact increase|increase in contact escape|contact escape increase)\b"
        r"(?:\s+\w+){0,8}\s+\b(?:failed (?:the )?significance test|"
        r"was not statistically significant|did not reach significance|"
        r"disappeared after adjustment|was lost after adjustment)\b",
        normalized_question,
    )
    explicitly_nonsignificant_contact_increase = re.search(
        r"\bno significant\b(?:\s+\w+){0,3}\s+\bcontact increase\b",
        normalized_question,
    )
    unsupported_statistical_qualification = re.search(
        r"\b(?:contact (?:escape|contrast|increase)|increase)\b"
        r"(?:\s+\w+){0,12}\s+\b(?:no longer significant|"
        r"nonsignificant after)\b|"
        r"\bno longer significant after\b(?:\s+\w+){0,5}\s+"
        r"\b(?:correction|adjustment)\b|"
        r"\b(?:difference|effect|contrast)\b(?:\s+\w+){0,3}\s+"
        r"\bdisappeared after adjust(?:ing|ment)\b|"
        r"\bbefore adjustment\b(?:\s+\w+){0,10}\s+"
        r"\bmatched (?:the )?control after accounting\b",
        normalized_question,
    )
    unsupported_interval = any(
        (
            interval_failure_pattern.search(clause)
            or raw_interval_spans_zero(raw_clause)
        )
        and not qualifier_is_noncontact_only(clause)
        for raw_clause, clause in zip(
            raw_result_clauses,
            result_clauses,
            strict=True,
        )
    )
    confounded_arm_comparison = re.search(
        r"\b(?:contact|non ?contact|treatment|control) (?:arm|condition|group)\b"
        r"(?:\s+\w+){0,8}\s+\b(?:degrees? warmer|degrees? cooler|"
        r"different temperature|temperature imbalance)\b|"
        r"\b(?:humidity|temperature)\b(?:\s+\w+){0,5}\s+"
        r"\b(?:higher|lower|warmer|cooler|different)\b|"
        r"\b(?:two|three|four|five|six|seven|eight|nine|ten)fold dose\b|"
        r"\bdifferent dose\b|"
        r"\b(?:morning|dawn|daytime)\b(?:\s+\w+){0,12}\s+"
        r"\b(?:dusk|evening|night)\b|"
        r"\b(?:dusk|evening|night)\b(?:\s+\w+){0,12}\s+"
        r"\b(?:morning|dawn|daytime)\b|"
        r"\blight phase\b(?:\s+\w+){0,12}\s+\bdarkness\b|"
        r"\bdarkness\b(?:\s+\w+){0,12}\s+\blight phase\b",
        normalized_question,
    )
    contradictory_result_direction = re.search(
        r"\b(?:fell|dropped|declined|decreased)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:below|under|lower than)\s+(?:the )?control\b|"
        r"\b(?:fell|dropped)\s+below\s+(?:the )?control\b|"
        r"\b(?:was|were|is|remained)\s+lower than\s+(?:the )?control\b|"
        r"\b(?:was|were|is|remained)\s+below\s+(?:the )?control\b|"
        r"\b(?:produced|showed|had|with)\s+less\s+escape\s+than\s+control\b",
        statement_text,
    )
    explicit_arm_confound = re.search(
        r"\b(?:antibiotic(?: treated)?|microbiome|wolbachia|"
        r"(?:dengue|pathogen|virus)[ -]infected|uninfected|"
        r"carbon dioxide anesthesia|anestheti[sz]ed|"
        r"fluorescent(?:ly)? dusted|undusted|chill(?:ed|ing)|sorting|"
        r"crowded larval|low density|larval density|larval diet|"
        r"wing length|small females?|large females?|"
        r"light cycle|photoperiod|ceiling|floor|"
        r"filter paper|cotton fabric|water rinsed|detergent cleaned)\b",
        normalized_question,
    )
    explicit_contact_null = re.search(
        r"(?<!no )(?<!non )\bcontact (?:treatment|arm|condition|group)\b"
        r"(?:\s+\w+){0,5}\s+"
        r"\b(?:matched|equaled|was equal to|did not exceed|did not increase over)\b"
        r"(?:\s+(?:the )?)?\b(?:control|vehicle)\b|"
        r"\b(?:remained|stayed|was|were)\s+equal to\s+(?:the )?"
        r"(?:control|vehicle)\s+(?:with|under|during)\s+contact\b"
        r"(?! (?:was )?(?:blocked|denied|excluded|prevented|prohibited|"
        r"restricted|unavailable))",
        statement_text,
    )
    reported_temperatures = re.findall(
        r"\b(\d+(?:\.\d+)?)\s*(?:degrees?\s*)?(?:c|celsius)\b",
        (raw_question or normalized_question).casefold(),
    )
    mismatched_temperatures = len(set(reported_temperatures)) > 1
    reported_durations = re.findall(
        r"\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|"
        r"ten|fifteen|twenty|thirty|forty|fifty|sixty)\s+"
        r"(seconds?|minutes?|hours?)\b",
        normalized_question,
    )
    normalized_durations = [
        (value, unit.removesuffix("s"))
        for value, unit in reported_durations
    ]
    duration_matches = list(
        re.finditer(
            r"\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|"
            r"nine|ten|fifteen|twenty|thirty|forty|fifty|sixty)\s+"
            r"(?:seconds?|minutes?|hours?)\b",
            normalized_question,
        )
    )
    duration_counts = {
        duration: normalized_durations.count(duration)
        for duration in set(normalized_durations)
    }
    repeated_timepoints_across_arms = bool(duration_counts) and all(
        count >= 2 for count in duration_counts.values()
    )
    shared_timepoint_statement = bool(
        re.search(
            r"\bat both\b(?:\s+\w+){0,6}\s+\band\b"
            r"(?:\s+\w+){0,4}\s+\b(?:seconds?|minutes?|hours?)\b|"
            r"\b(?:the )?same (?:one|two|three|four|five|six|seven|eight|"
            r"nine|ten|\d+) timepoints?\b",
            normalized_question,
        )
    )
    first_noncontact_state = noncontact_state_pattern.search(normalized_question)
    shared_timepoint_preamble = bool(
        len(duration_matches) > 1
        and first_noncontact_state
        and duration_matches[-1].end() < first_noncontact_state.start()
    )
    mismatched_durations = (
        len(duration_counts) > 1
        and not repeated_timepoints_across_arms
        and not shared_timepoint_statement
        and not shared_timepoint_preamble
        and not re.search(
            r"\b(?:both|each)\s+(?:arm|condition|comparison|group)s?\b",
            normalized_question,
        )
    )
    reported_clock_times = re.findall(
        r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
        raw_statement_text,
    )
    clock_time_counts = {
        clock_time: reported_clock_times.count(clock_time)
        for clock_time in set(reported_clock_times)
    }
    mismatched_clock_times = (
        len(clock_time_counts) > 1
        and not all(count >= 2 for count in clock_time_counts.values())
    )
    mixed_sex_arms = bool(
        re.search(r"\bmales?\b", normalized_question)
        and re.search(r"\bfemales?\b", normalized_question)
        and re.search(r"\b(?:arm|condition|exposure|group)\b", normalized_question)
    )
    mixed_feeding_states = bool(
        re.search(r"\bfed\b", normalized_question)
        and re.search(r"\bstarved\b", normalized_question)
        and re.search(r"\b(?:arm|condition|exposure|group)\b", normalized_question)
    )
    mixed_reproductive_states = bool(
        re.search(r"\bnulliparous\b", normalized_question)
        and re.search(r"\bgravid\b", normalized_question)
    )
    changed_cage_orientation = bool(
        re.search(r"\bhorizontal\b", normalized_question)
        and re.search(r"\bvertical\b", normalized_question)
        and re.search(r"\bcages?\b", normalized_question)
    )
    residual_odor_confound = bool(
        re.search(r"\bfreshly cleaned\b", normalized_question)
        and re.search(r"\bresidual odor\b", normalized_question)
    )
    incomplete_no_contact_evidence = re.search(
        r"\b(?:no contact|noncontact) results?\b"
        r"(?:\s+\w+){0,3}\s+\b(?:absent|missing|unavailable|"
        r"not collected|not measured)\b",
        normalized_question,
    )
    changed_host_odor = bool(
        re.search(r"\bno host odor\b", normalized_question)
        and re.search(r"\bhost odor (?:was )?added\b", normalized_question)
    )
    changed_carbon_dioxide = bool(
        re.search(r"\bno carbon dioxide\b", normalized_question)
        and re.search(
            r"\bcarbon dioxide (?:source )?(?:was )?added\b",
            normalized_question,
        )
    )
    changed_room = bool(
        re.search(r"\bone room\b", normalized_question)
        and re.search(r"\banother room\b", normalized_question)
    )
    changed_cage_size = bool(
        re.search(r"\bsmall cages?\b", normalized_question)
        and re.search(
            r"\b(?:large cages?|cages? twice as large)\b",
            normalized_question,
        )
    )
    changed_escape_opening = bool(
        re.search(r"\bescape opening\b", normalized_question)
        and re.search(r"\b(?:larger|smaller|different)\b", normalized_question)
        and re.search(r"\bcages?\b", normalized_question)
    )
    age_values = re.findall(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"fifteen|twenty|thirty)\s+days?\s+old\b",
        normalized_question,
    )
    mismatched_ages = len(set(age_values)) > 1
    airflow_values = re.findall(
        r"\b(\d+(?:\.\d+)?)\s*m\s*/\s*s\b",
        (raw_question or normalized_question).casefold(),
    )
    mismatched_airflow = len(set(airflow_values)) > 1
    per_cage_counts = re.findall(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"fifteen|twenty|thirty|forty|fifty|sixty)\s+"
        r"(?:aedes|mosquitoes)?\s*per cage\b",
        normalized_question,
    )
    mismatched_per_cage_counts = len(set(per_cage_counts)) > 1
    changed_strain = bool(
        (
            re.search(r"\brockefeller\b", normalized_question)
            and re.search(r"\bliverpool\b", normalized_question)
        )
        or (
            re.search(r"\bone strain\b", normalized_question)
            and re.search(r"\banother strain\b", normalized_question)
        )
        or re.search(r"\bdifferent strains?\b", normalized_question)
    )
    changed_population_source = bool(
        re.search(r"\bcolony\b", normalized_question)
        and re.search(r"\bfield\b", normalized_question)
        and re.search(r"\baedes\b", normalized_question)
    )
    changed_mating_state = bool(
        re.search(r"\bunmated\b", normalized_question)
        and re.search(r"\bmated\b", normalized_question)
    )
    changed_operator = bool(
        re.search(r"\b(?:operators?|observers?)\b", normalized_question)
        and re.search(
            r"\b(?:arm|condition|contact|no contact|noncontact)\b",
            normalized_question,
        )
    )
    named_strains = re.findall(
        r"\b(?:rockefeller|liverpool|new orleans)\s+strain\b",
        normalized_question,
    )
    changed_named_strain = len(set(named_strains)) > 1
    changed_paper_age = bool(
        re.search(r"\bfresh(?:ly)? treated paper\b", normalized_question)
        and re.search(r"\bpaper aged\b", normalized_question)
    )
    lux_values = re.findall(
        r"\b(\d+(?:\.\d+)?)\s+lux\b",
        normalized_question,
    )
    mismatched_illumination = len(set(lux_values)) > 1
    changed_chamber_material = bool(
        re.search(r"\bglass\b", normalized_question)
        and re.search(r"\bacrylic\b", normalized_question)
        and re.search(r"\bchambers?\b", normalized_question)
    )
    treated_paper_areas = re.findall(
        r"\b(\d+(?:\.\d+)?)\s+square centimeters?\b",
        normalized_question,
    )
    mismatched_treated_area = len(set(treated_paper_areas)) > 1
    def clause_has_unsupported_probability(
        raw_clause: str,
        normalized_clause: str,
        symbol: str,
    ) -> bool:
        values = [
            float(value)
            for value in re.findall(
                rf"\b{symbol}\s*(?:>=|=|>)\s*(0?\.\d+)\b",
                raw_clause.casefold(),
            )
        ]
        return any(value >= 0.05 for value in values) and not (
            qualifier_is_noncontact_only(normalized_clause)
        )

    non_significant_contact_estimate = any(
        clause_has_unsupported_probability(raw_clause, clause, "p")
        for raw_clause, clause in zip(
            raw_result_clauses,
            result_clauses,
            strict=True,
        )
    )
    non_significant_adjusted_estimate = any(
        clause_has_unsupported_probability(raw_clause, clause, "q")
        for raw_clause, clause in zip(
            raw_result_clauses,
            result_clauses,
            strict=True,
        )
    )
    explicit_non_aedes_genus = re.search(
        r"\b(?:aedimorphus|anopheles|apis|armigeres|bombyx|coquillettidia|"
        r"culex|culiseta|drosophila|eretmapodites|haemagogus|locusta|"
        r"manduca|mansonia|"
        r"musca|ochlerotatus|plutella|psorophora|sabethes|stegomyia|"
        r"toxorynchites|tribolium|uranotaenia|wyeomyia)\s+[a-z][a-z-]{2,}\b",
        normalized_question,
    )
    explicit_non_aegypti_aedes = re.search(
        r"\baedes\s+(?:africanus|albopictus|camptorhynchus|furcifer|"
        r"japonicus|koreicus|luteocephalus|mcintoshi|mediovittatus|"
        r"notoscriptus|polynesiensis|solicitans|taeniorhynchus|vexans)\b",
        normalized_question,
    )
    non_aedes_binomial = bool(
        explicit_non_aedes_genus or explicit_non_aegypti_aedes
    )
    if (
        design_or_genetics_intent
        or procedural_question
        or passive_knockdown_cause
        or unsupported_contact_increase
        or explicitly_nonsignificant_contact_increase
        or unsupported_statistical_qualification
        or unsupported_interval
        or confounded_arm_comparison
        or contradictory_result_direction
        or explicit_arm_confound
        or explicit_contact_null
        or mismatched_temperatures
        or mismatched_durations
        or mismatched_clock_times
        or mismatched_ages
        or mismatched_airflow
        or mismatched_per_cage_counts
        or mixed_sex_arms
        or mixed_feeding_states
        or mixed_reproductive_states
        or changed_cage_orientation
        or residual_odor_confound
        or incomplete_no_contact_evidence
        or changed_host_odor
        or changed_carbon_dioxide
        or changed_room
        or changed_cage_size
        or changed_escape_opening
        or changed_strain
        or changed_population_source
        or changed_mating_state
        or changed_operator
        or changed_named_strain
        or changed_paper_age
        or mismatched_illumination
        or changed_chamber_material
        or mismatched_treated_area
        or non_significant_contact_estimate
        or non_significant_adjusted_estimate
        or causal_mechanism_question
        or (mechanism_term and causal_question)
        or non_aedes_binomial
    ):
        return False
    escape_context_pattern = re.compile(
        r"\b(?:escap(?:e|es|ed|ing)|exit(?:s|ed|ing)?|left|"
        r"depart(?:s|ed|ing|ure|ures)?|egress|leav(?:e|es|ing)|"
        r"contact component|treatment and control curves|"
        r"treatment curves?|"
        r"paired comparison|treatment control difference|at 30 minutes|"
        r"30 minute endpoint|treatment and control rates|"
        r"treatment matched vehicle)\b"
    )
    if not escape_context_pattern.search(normalized_question):
        return False

    clauses = result_clauses
    noncontact_pattern = re.compile(
        r"\b(?:non contact|noncontact|no contact|contact free|contact barred|"
        r"contact absent|"
        r"absence of contact|"
        r"no surface contact|no surface access|direct surface access (?:was )?absent|"
        r"source (?:was )?inaccessible|"
        r"kept away from (?:the )?treated paper|"
        r"no touch|non touch|no access condition|no access|without access|"
        r"without surface access|"
        r"without (?:(?:direct|surface|paper|residue) )?contact|"
        r"direct touch (?:was )?excluded|preventing direct contact|"
        r"without paper access|without direct access to (?:the )?paper|"
        r"without access to "
        r"(?:the )?(?:paper|surface|substrate)|mesh separated|mesh separation|"
        r"mesh isolated|"
        r"mesh barrier|contact barrier(?: installed)?|mesh protected|mesh protection|"
        r"mesh screen|mesh condition|"
        r"mesh on|with mesh(?=\s+(?:and|while|whereas|but)|[;,]|$)|"
        r"mesh present|mesh in place|"
        r"mesh cover(?:ed|ing) (?:the )?paper|"
        r"mesh prevent(?:s|ed|ing)? contact|"
        r"mesh stop(?:s|ped|ping) touch(?:ing)?|"
        r"(?:paper|surface) (?:was )?separated by mesh|"
        r"mesh between(?:\s+\w+){0,4}\s+paper|"
        r"mesh chambers?|mesh group|mesh arm|mesh assay|mesh treatment|"
        r"through (?:the )?mesh|"
        r"across (?:the )?barrier|screened access|"
        r"chambers fitted with mesh|"
        r"across (?:the )?mesh|"
        r"barrier protected|barrier present|barrier pair|barrier arm|"
        r"a barrier|"
        r"barrier prevent(?:s|ed|ing)? touch(?:ing)?|"
        r"barrier (?:kept|keeps)(?:\s+\w+){0,3}\s+off "
        r"(?:the )?(?:(?:treated|test|dosed|impregnated) )?"
        r"(?:paper|strip|insert|sheet|material|surface|substrate)|"
        r"barrier treatment|barrier separation|separated treatment|separated arm|"
        r"separated(?:\s+\w+){0,4}\s+arm|"
        r"separated condition|separated setup|"
        r"protected exposure|"
        r"remote presentation|remote exposure|distant exposure|"
        r"physically separated treatment|paper isolation|separat(?:e|ed|ing) "
        r"(?:aedes(?: aegypti)? )?from (?:the )?treated surface|"
        r"separated paper|distance only exposure|"
        r"protected paper arm|"
        r"barrier arms|barrier comparison|barrier escape|"
        r"barrier between(?:\s+\w+){0,5}\s+(?:treated )?paper|"
        r"physical divider|physical screen|physically isolated condition|"
        r"(?:nylon|mesh|gauze|screen) (?:partition|stratify)|"
        r"(?:partition|stratify) between(?:\s+\w+){0,6}\s+(?:treated )?"
        r"(?:paper|panel|strip|insert|sheet|material|surface|substrate)|"
        r"gauze stratify|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?unreachable|"
        r"screen(?:ed)? treatment|screened treated|screened test|screened escape|"
        r"screened exposure|screened condition|screened aedes condition|"
        r"screened aedes(?: aegypti)? treatment group|"
        r"contact screen|"
        r"screen(?:ed)? females|"
        r"screened arm|screened pair|screened (?:aedes(?: aegypti)?|"
        r"mosquito|mosquitoes|female|females) pair|"
        r"screened face|screened comparison|"
        r"screened chambers?|"
        r"screen condition|screen separated|"
        r"screen chambers?|"
        r"screen in place|"
        r"screen present|"
        r"screen between|"
        r"screen separat(?:e|ed|es|ing)(?:\s+\w+){0,4}\s+(?:from )?"
        r"(?:the )?paper|"
        r"screen block(?:ed)? (?:the )?treated surface|"
        r"screen den(?:y|ied|ies|ying) physical contact|"
        r"screen stop(?:s|ped|ping) contact|"
        r"residue (?:was )?screened (?:off|away)|"
        r"treated paper screened off|paper screened|screened off|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?screened|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?behind (?:a )?"
        r"(?:screen|guard|barrier|separator)|"
        r"behind (?:(?:a|the) )?(?:mesh|gauze|screen|guard|barrier|separator)|"
        r"shielded treatment|paper (?:was )?shielded|"
        r"(?:treated )?surface (?:was )?shielded|"
        r"shield(?:ed|ing) (?:the )?(?:(?:treated|impregnated) )?"
        r"(?:paper|strip|insert|sheet|material|surface|substrate)|"
        r"shield(?:ed|ing) (?:the )?(?:dose|formulation|sample)|"
        r"(?:dose|formulation|sample|treatment) (?:was )?isolated from "
        r"(?:aedes|mosquitoes|females|insects)|"
        r"remotely exposed (?:aedes|mosquitoes|females|insects)|"
        r"inaccessible paper|"
        r"paper (?:was )?inaccessible|"
        r"residue (?:was )?inaccessible|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?inaccessible|"
        r"shielded (?:aedes |mosquito )?assay|"
        r"(?:treated )?(?:paper|panel|sample|strip|insert|sheet|liner|card|"
        r"material|surface|substrate) (?:was )?physically separated|"
        r"(?:paper|surface|substrate|material|residue) separated|"
        r"physical separation|"
        r"(?:treated )?(?:paper|panel|sample|strip|insert|sheet|liner|material|"
        r"surface|substrate) (?:was )?(?:out of|beyond)"
        r"(?:\s+\w+){0,3}\s+reach|"
        r"separat(?:e|ed|ing)(?:\s+\w+){0,4}\s+from "
        r"(?:the )?(?:dosed|treated) paper|"
        r"(?:physical|paper|surface|substrate|material|residue)?\s*access "
        r"(?:was )?(?:blocked|prevented|denied|closed|prohibited)|"
        r"access to (?:the )?(?:treated )?"
        r"(?:paper|surface|substrate|material|residue) "
        r"(?:was )?(?:blocked|prevented|denied|closed|shut)|"
        r"access to treated paper (?:was )?blocked|"
        r"block(?:ed|ing) paper access|"
        r"block(?:ed|ing) treated paper access|"
        r"block(?:ed|ing) (?:the )?treated paper from contact|"
        r"block(?:ed|ing) access to (?:the )?(?:treated )?paper|"
        r"contact (?:was )?(?:blocked|denied|prevented|prohibited|restricted|"
        r"impossible|excluded|unavailable|disallowed)|"
        r"contact exclusion|"
        r"contact with (?:the )?(?:(?:treated|test) )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate|residue) "
        r"(?:was )?(?:prevented|blocked|closed|denied)|"
        r"prevent(?:ed|ing) contact|preventing touch|"
        r"contact prohibited|contact unavailable|paper contact unavailable|"
        r"contact restricted|"
        r"contact blocking(?:\s+\w+){0,2}\s+(?:chambers?|arms?|conditions?)|"
        r"(?:paper |surface |residue )?contact could not occur|"
        r"could not contact (?:the )?(?:treated )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate)|"
        r"guard prevent(?:s|ed|ing)? contact|through (?:a )?guard|"
        r"den(?:y|ied|ies|ying) (?:substrate|surface) contact|"
        r"prevented from contacting (?:the )?treated paper|"
        r"prevent(?:ed|ing)(?:\s+\w+){0,4}\s+from touch(?:ing)? "
        r"(?:the )?(?:dosed|treated) substrate|"
        r"exposure (?:was )?blocked|"
        r"(?<!no longer )block(?:ed|ing) contact|blocking touch|"
        r"block(?:ed|ing) (?:treated )?paper contact|"
        r"direct touch (?:was )?(?:blocked|ruled out)|"
        r"touch (?:was )?blocked|"
        r"direct access (?:was )?denied|"
        r"distance associated|"
        r"separator prevent(?:ed)? touch|touch(?:ing)? (?:was )?prevented|"
        r"mesh (?:kept|keeps) mosquitoes off (?:the )?treated paper|"
        r"mesh(?:\s+\w+){0,4}\s+kept(?:\s+\w+){0,4}\s+from "
        r"(?:the )?(?:treated )?(?:surface|paper)|"
        r"mesh separated females from (?:the )?paper|"
        r"mesh separat(?:e|ed|ing)(?:\s+\w+){0,3}\s+from (?:the )?paper|"
        r"mesh (?:kept|keeps)(?:\s+\w+){0,3}\s+off "
        r"(?:the )?(?:treated )?paper|"
        r"mesh block(?:s|ed|ing)? touch|mesh prevent(?:s|ed|ing)? touch|"
        r"contact prevention|"
        r"paper touch (?:was )?prevented|"
        r"(?:paper|surface|substrate|residue) could not be contacted|"
        r"(?:blocking|blocked) (?:aedes(?: aegypti)?|mosquitoes|females|"
        r"insects|them) from (?:the )?paper|"
        r"(?:could not|unable to) reach (?:the )?"
        r"(?:treated )?(?:paper|panel|sample|strip|insert|sheet|liner|card|"
        r"material|surface|substrate)|"
        r"prevent(?:ing|ed)? (?:treated )?paper contact|"
        r"kept off (?:the )?(?:treated )?paper|"
        r"keep(?:ing|s)?(?:\s+\w+){0,3}\s+away from (?:the )?(?:treated )?"
        r"(?:paper|surface|residue)|"
        r"could not access (?:the )?paper|"
        r"(?:could not|unable to) touch (?:the )?(?:treated )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate)|"
        r"without contact|without touch(?:ing)?|"
        r"(?:the )?paper could not be reach(?:ed)?|"
        r"(?:the )?(?:(?:dosed|treated) )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) could not be touch(?:ed)?|"
        r"without paper contact|without direct paper contact|excluding paper contact|"
        r"paper contact (?:was )?impossible|"
        r"contact free|indirect exposure(?: arm)?|protected exposure|"
        r"contact (?:was )?not (?:allowed|available|possible)|"
        r"treated paper under mesh|"
        r"barrier chambers?|barrier condition|barrier format|barrier closed|"
        r"separated from (?:the )?treated paper by mesh|"
        r"separated from (?:the )?(?:paper|panel|sample|strip|insert|sheet|"
        r"liner|card|material|surface|substrate|residue)|"
        r"across (?:the )?screen|"
        r"(?:(?:the )?paper|treated paper) could not be touch|"
        r"before (?:paper |surface )?contact|"
        r"nylon screen|netted treatment|perforated divider|mesh sleeve|"
        r"tarsal access denied|screen block(?:ed)? access|"
        r"occlud(?:e|ed|ing) (?:the )?paper|closed face|barrier side|"
        r"source fenced off|protected treatment|fabric barrier|"
        r"isolated format|isolated treatment|barrier enclosed|barrier egress|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?(?:shrouded|covered)|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was |remained )?(?:enclosed|untouchable)|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate|residue) (?:was )?(?:fenced off|blocked|isolated)|"
        r"(?:test |treated )?(?:paper|surface|substrate|material|residue) "
        r"(?:was )?off limits|contact surface (?:was )?closed off|"
        r"physical isolation from (?:the )?(?:paper|surface|residue)|"
        r"(?:surface|residue) (?:was )?(?:out of reach|separated)|"
        r"surface separation|"
        r"without residue access|"
        r"(?:shrouded|covered|shielded|protected) (?:treated )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate)|"
        r"treated paper unavailable for touch|cover(?:ed|ing) (?:the )?paper|"
        r"active sheet (?:was )?covered|"
        r"sheet behind netting|surface screened off|with (?:a )?screen"
        r"(?: denying physical contact)?)\b|"
        r"\b(?:denied|blocked|prevented|inaccessible|"
        r"unreachable|shielded|covered|isolated|protected|closed|"
        r"occluded|netted|fenced|shrouded)"
        r"(?:\s+\w+){0,3}\s+(?:access|contact|touch|reach|surface|paper|"
        r"source|face|arm|chamber|compartment|format|treatment|sheet|"
        r"window|barrier|screen|mesh|residue)\b|"
        r"\brestricted(?:\s+\w+){0,3}\s+access\b"
    )
    contact_pattern = re.compile(
        r"\b(?:contact|contacted|contact access|contact present|"
        r"touch(?:ed|ing)?|touch enabled|"
        r"physical contact|surface contact|physical access|surface access|"
        r"surface accessible|"
        r"direct surface access (?:was )?present|access condition|"
        r"residue contact|residue access|residue (?:was )?exposed for contact|"
        r"accessible residue|residue (?:was )?accessible|"
        r"surface could be touch(?:ed)?|"
        r"paper access|direct paper exposure|access to treated paper|accessible surface|"
        r"source (?:was )?reachable|"
        r"letting(?:\s+\w+){0,3}\s+reach (?:the )?(?:paper|surface|residue)|"
        r"access to (?:the )?treated sheet (?:was )?allowed|"
        r"grant(?:ed|ing) (?:access|contact)|"
        r"(?:paper|surface|substrate|material) access (?:was )?granted|"
        r"giv(?:e|en|ing)(?:\s+\w+){0,4}\s+access to (?:the )?paper|"
        r"(?:had|have|has) access to (?:the )?(?:treated )?paper|"
        r"access to (?:the )?(?:(?:treated|test) )?"
        r"(?:surface|substrate|material|residue) (?:was )?opened|"
        r"access to (?:the )?(?:treated )?(?:surface|substrate|material)|"
        r"contact access (?:was )?restored|"
        r"(?:dose|formulation|sample|treatment) (?:was )?accessible|"
        r"directly exposed (?:aedes|mosquitoes|females|insects)|"
        r"allowed onto (?:the )?paper|"
        r"expos(?:e|ed|ing) (?:the )?(?:paper|strip|insert|sheet|material|"
        r"surface|substrate)|"
        r"exposed paper|paper (?:was )?(?:exposed|accessible)|"
        r"exposed arm|exposed treatment|"
        r"exposed condition|"
        r"open arms?|open chamber|paper open|unblock(?:ed|ing) it|"
        r"touch access|touchable (?:paper|panel|sample|strip|insert|sheet|"
        r"liner|card|treatment|material|surface|substrate)|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|treatment|"
        r"material|surface|substrate) (?:was )?touchable|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|treatment|"
        r"material|surface|substrate) became touchable|"
        r"accessible (?:treated paper|format)|contact capable|"
        r"(?:taking (?:the )?)?divider away|separator (?:was )?removed|"
        r"(?:separation|divider|partition|barrier|cover) (?:was )?removed|"
        r"enclosure (?:was )?opened|"
        r"without (?:the )?screen|no screen|could reach|free to reach|"
        r"giving access|"
        r"opening (?:the )?"
        r"treated paper face|direct paper access|outside (?:the )?sleeve|"
        r"tarsal access permitted|available to (?:the )?feet|"
        r"expos(?:e|ed|ing) (?:it|the paper)|open face|exposed side|"
        r"direct access|window (?:was )?absent|reachable|contact available|"
        r"no mesh|no screen|no guard|guard (?:was )?removed|without mesh|"
        r"mesh (?:was )?absent|"
        r"screen (?:was )?absent|mesh off|"
        r"unscreened(?: pair)?|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?unscreened|"
        r"contact (?:was )?allowed|paper contact (?:was )?available|"
        r"it (?:was )?available|"
        r"contact permission|contact inclusion|enabl(?:e|ed|ing) contact|"
        r"contact unrestricted|"
        r"contact permitting(?:\s+\w+){0,2}\s+(?:chambers?|arms?|conditions?)|"
        r"(?:paper |surface |residue )?contact could occur|"
        r"(?:physical|paper|surface|substrate|material|residue) access "
        r"(?:was )?(?:allowed|permitted|granted|open)|"
        r"access (?:was )?(?:granted|opened)|"
        r"residue contact (?:was )?(?:allowed|permitted|possible)|"
        r"touch (?:was )?(?:allowed|permitted|enabled)|permitting touch|"
        r"allowing touch|"
        r"surface (?:was )?exposed|(?:it |surface )?open to contact|"
        r"(?:paper|surface|substrate|material|residue) accessible|"
        r"\bunrestricted(?:\s+\w+){0,3}\s+access\b|"
        r"contact paper|contact presentation|tactile exposure|"
        r"unprotected exposure|"
        r"contact accessible treatment|"
        r"making it available|contact setup|"
        r"contact permitted|allow(?:ed|ing) surface contact|"
        r"screen out|access (?:was )?allowed|"
        r"mesh removal|barrier removal|mesh (?:was )?removed|"
        r"(?:mesh|screen|barrier) no longer block(?:ed|s)? contact|"
        r"mesh (?:was )?taken away|"
        r"screen (?:was )?removed|"
        r"without (?:the )?barrier|barrier (?:was )?absent|barrier opened|"
        r"no separation|"
        r"able to touch|reach (?:was )?allowed|"
        r"could touch (?:the )?(?:(?:dosed|treated) )?"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate)|"
        r"(?:the )?(?:paper|panel|sample|strip|insert|sheet|liner|material|"
        r"surface|substrate) could be reach(?:ed)?|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?reachable|"
        r"(?:reach|reached|reaching) (?:the )?(?:paper|panel|sample|strip|"
        r"insert|sheet|liner|material|surface|substrate)|"
        r"it could be reach(?:ed)?|"
        r"it could be touch|"
        r"it (?:was )?accessible|"
        r"contact (?:was )?possible|"
        r"touching (?:was )?allowed|"
        r"uncovered (?:treated )?(?:paper|panel|sample|strip|insert|sheet|"
        r"liner|card|material|surface|substrate)|"
        r"paper (?:was )?uncovered|"
        r"uncover(?:ed|ing) (?:it|(?:the )?paper)|"
        r"uncovered treatment|(?:treated )?surface (?:was )?unshielded|"
        r"exposed treated|"
        r"with access(?! (?:blocked|closed|denied|prevented|prohibited))|within reach|"
        r"(?:paper|panel|sample|strip|insert|sheet|liner|card|material|"
        r"surface|substrate) (?:was )?in reach|"
        r"with paper contact|including paper contact|direct paper exposure|"
        r"direct exposure(?: arm)?|"
        r"remov(?:e|ed|ing) (?:the )?mesh|cover (?:was )?removed|"
        r"remov(?:e|ed|ing) (?:that |the )?"
        r"(?:separation|screen|guard|cover|partition|stratify|barrier)\b|"
        r"(?:allow(?:ed|ing)?|permit(?:ted|ting)?|enable(?:d|ing)?|"
        r"open(?:ed|ing)?|remov(?:e|ed|ing)|expos(?:e|ed|ing)|"
        r"reachable|available|accessible|outside|direct)"
        r"(?:\s+\w+){0,4}\s+(?:access|contact|touch|reach|surface|paper|"
        r"source|face|arm|screen|mesh|divider|window|cover)\b"
        r")\b"
    )
    equality_pattern = re.compile(
        r"\b(?:centered on zero|straddled zero|same|equal|equals|equaled|"
        r"equivalent|identical|"
        r"indistinguishable|"
        r"comparable|alike|equally|even with|neutral|matches?|matched|matching|"
        r"tied|tracks?|"
        r"tracked|unchanged|levels?|zero|null|flat|parity|nonsignificant|"
        r"overlaps?|overlapped|"
        r"coincides?|coincided|superimposed|no divergence|control like|"
        r"sat on|curves were together|(?:vehicle|control) escape rate|"
        r"(?:vehicle|control|carrier|reference) value|control baseline|"
        r"(?:vehicle|control|carrier|reference) rate|"
        r"behaved like|looks? like|nil|similar|absent|as often as|just as often|"
        r"(?:escape )?ratio (?:was )?(?:near|approximately|about) one|"
        r"did not differ|does not differ|do not differ|did not change|"
        r"did not increase|not increased|did not exceed|did not raise|"
        r"unable to raise|"
        r"did not favor treatment over control|"
        r"did not elevate|not (?:statistically )?elevated|"
        r"did not show(?:\s+\w+){0,3}\s+higher"
        r"(?:\s+\w+){0,4}\s+than|"
        r"did not produce(?:\s+\w+){0,3}\s+larger"
        r"(?:\s+\w+){0,4}\s+than|"
        r"did not produce(?:\s+\w+){0,3}\s+more"
        r"(?:\s+\w+){0,4}\s+than|"
        r"did not show(?:\s+\w+){0,3}\s+more(?:\s+\w+){0,4}\s+than|"
        r"did not (?:leave|escape|exit)(?:\s+\w+){0,6}\s+more often|"
        r"did not (?:leave|escape|exit)(?:\s+\w+){0,3}\s+more"
        r"(?:\s+\w+){0,4}\s+than|"
        r"did not rise(?:\s+\w+){0,3}\s+above|"
        r"did not separate|"
        r"did not alter|did not affect|did not add|"
        r"failed to (?:raise|increase)|"
        r"negative for (?:an? )?(?:escape )?effect|"
        r"remov(?:e|ed|ing) any treatment effect|"
        r"remov(?:e|ed|ing)(?:\s+\w+){0,4}\s+increase|no change|"
        r"no detectable change|"
        r"no escape change|"
        r"control rate|vehicle rate|(?:stayed|remained|was) at baseline|"
        r"control response|"
        r"control frequency|"
        r"stayed at control|remained at control|"
        r"not (?:significantly )?different|no different|"
        r"no(?:\s+\w+){0,3}\s+(?:difference|separation)|"
        r"remov(?:e|ed|ing)(?:\s+\w+){0,3}\s+difference|"
        r"eras(?:e|ed|es|ing)(?:\s+\w+){0,3}\s+difference|"
        r"no escape response|no increase|no escape gain|"
        r"no(?:\s+\w+){0,2}\s+escape increase|"
        r"no(?:\s+\w+){0,3}\s+elevation|"
        r"no treatment increase|"
        r"no treatment associated (?:escape )?increase|"
        r"no treatment related (?:escape )?increase|"
        r"no treatment over control increase|"
        r"no treatment control (?:escape )?increase|"
        r"not higher(?:\s+\w+){0,6}\s+than (?:controls?|vehicle)|"
        r"no higher than (?:the )?(?:control|vehicle)|"
        r"no greater than (?:the )?(?:control|vehicle)|"
        r"no treatment versus control increase|"
        r"no added|no additional|no extra|"
        r"no(?:\s+\w+){0,3}\s+(?:rise|upward shift)|"
        r"added no(?:\s+\w+){0,3}\s+escape|"
        r"not above (?:the )?(?:paired )?(?:control|vehicle)|"
        r"no(?:\s+\w+){0,3}\s+(?:escape )?advantage|"
        r"no more(?:\s+\w+){0,5}\s+than|"
        r"no evidence of (?:extra|additional|excess)|"
        r"no evidence of higher(?:\s+\w+){0,4}\s+than (?:the )?control|"
        r"no(?:\s+\w+){0,3}\s+excess|"
        r"no(?:\s+\w+){0,4}\s+effect|no excess)\b"
    )
    increase_pattern = re.compile(
        r"\b(?:more|higher|greater|larger|stronger|gain|added|additional|advantage|"
        r"increases?|increased|increasing|rise|"
        r"rose|rises|"
        r"climbed|raise|raised|exceed(?:s|ed|ing)?|elevat(?:e|ed|es|ing|ion)|"
        r"present|positive|upward|"
        r"surplus|excess|extra|"
        r"above|outnumber(?:s|ed|ing)?|surpasses?|surpassed)\b"
    )
    comparator_pattern = re.compile(
        r"\b(?:controls?|vehicle|carrier|solvent|blank|reference|comparator|"
        r"untreated)\b"
    )
    event_endpoint_pattern = re.compile(
        r"\b(?:escap(?:e|es|ed|ing)|exit(?:s|ed|ing)?|left|"
        r"depart(?:s|ed|ing|ure|ures)?|egress|leav(?:e|es|ing))\b"
    )
    non_event_escape_context_pattern = re.compile(
        r"\bescape\s+(?:assay|chambers?)\b"
    )
    competing_endpoint_pattern = re.compile(
        r"\b(?:bite|bites|biting|knockdown|knocked down|"
        r"(?:\d+\s+hours?\s+)?mortality|"
        r"survival|recovery|"
        r"fecundity|grooming|host seeking|landed|landing|landings|"
        r"orientation|occupancy|"
        r"takeoffs?|"
        r"oviposition|eggs?)\b"
        r"|\b(?:feeding attempts?|feeding(?: rate)?|flight activity|"
        r"wing beat(?: frequency| rate)?|"
        r"flight speed|flight velocity|wing movement|time spent|activity|"
        r"dwell time|duration|"
        r"probing|probing attempts?|blood feeding (?:attempts?|rate)|"
        r"walking speed|movement speed|movement rate|average speed|time active|"
        r"amount of time moving|"
        r"distance walked|path length|"
        r"general movement|total movement)\b"
    )
    statement_has_measured_escape_context = bool(
        escape_context_pattern.search(statement_text)
    )
    if not statement_has_measured_escape_context:
        return False

    arm_leading_bare_comparison = any(
        re.match(
            r"^\s*(?:with|without) "
            r"(?:(?:direct|surface|paper|residue) )?contact,?\s+"
            r"(?:(?:aedes(?:\s+aegypti)?|mosquitoes?)\s+)?"
            r"(?:the\s+)?(?:treated (?:group|proportion)|treatment"
            r"(?: rate| estimate| curve| response| effect|-control contrast)?|"
            r"treatment-control contrast)\s+(?:was\s+)?"
            r"(?:above|positive|higher|greater|lower|less|matched|equal(?:ed)?|"
            r"exceed(?:s|ed|ing)?)\b",
            clause,
        )
        and not event_endpoint_pattern.search(clause)
        for clause in result_clauses
    )
    if arm_leading_bare_comparison:
        return False
    ambiguous_generic_relation_pattern = re.compile(
        r"\b(?:positive|greater|higher|larger|upward) treatment control "
        r"(?:contrast|effect)\b|"
        r"\btreatment control (?:contrast|effect)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:positive|greater|higher|larger|upward)\b|"
        r"\btreatment (?:had|showed|gave|produced) (?:the )?"
        r"(?:higher|greater|larger) (?:rate|estimate|proportion|curve|response)\b|"
        r"\b(?:the )?treated group (?:was )?"
        r"(?:above|higher|greater than|exceed(?:s|ed|ing)?) "
        r"(?:the )?control group\b|"
        r"\btreatment effect (?:became|was|is|grew)? ?"
        r"(?:positive|above|higher|greater|larger|exceed(?:s|ed|ing)?)"
        r"(?: than| relative to)? (?:the )?control\b|"
        r"\b(?:positive|greater|higher|larger) treatment effect "
        r"(?:relative to|versus|against) (?:the )?control\b|"
        r"\b(?:contact )?treatment (?:rate|estimate|proportion|curve|response)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:above|exceed(?:s|ed|ing)?|higher|greater|larger)\b|"
        r"\b(?:greater|higher|larger) proportion\b"
        r"(?! (?:was )?(?:left|leav(?:e|es|ing)|escap(?:e|es|ed|ing)|"
        r"exit(?:s|ed|ing)?|egress|depart(?:s|ed|ing|ure|ures)?))"
        r"(?:\s+\w+){0,4}\s+\bunder treatment\b|"
        r"\bresponse (?:was )?(?:above|higher|greater|larger) for treatment\b"
    )
    generic_measure_comparison = any(
        ambiguous_generic_relation_pattern.search(clause)
        and not re.search(
            r"\b(?:treated|treatment) and (?:the )?control "
            r"(?:escap(?:e|ing)|exit(?:ing)?|egress|depart(?:ure|ing)|"
            r"leaving) rates?\b",
            clause,
        )
        for clause in result_clauses
    )
    if generic_measure_comparison:
        return False
    neutral_arm_words = frozenset(
        """
        a about above across after against all also among an analyzed and any arm arms as
        assay assays at aedes aegypti be became before behind being below
        between beyond both but by cage cages can cannot chamber chambers common
        comparison comparisons condition conditions contact contrast control
        controls could cumulative data did direct relation
        directly do does during effect endpoint equal er excito escape escaped escapees
        escapes escaping experiment exposure female females finding findings
        first for format formulation from gap group groups had has have how i if
        in
        insect insects interpretation is it its just kept made matched mean mesh
        minute minutes more mosquito mosquitoes no non noncontact not observed
        of on once one only our over pair paired paper pattern physical
        physically portion produced rate rates readout relative report response
        result results s
        run same seen should show showed source spatial specific stated
        statistically study summary surface test than that
        the their them then there these they thirty this through to together each
        treated treatment two under us using vehicle versus was we were what
        when where whereas which while with within without would yielded yet
        """.split()
    )
    neutral_arm_words |= frozenset(
        """
        able absence absent accessible active actual add added additional assessed
        advantage affect alike allowed allowing alongside alter although appeared
        appropriate approximately associated available away blank blocked
        blocking blocks brief capable card carrier caused chance change
        chemical chemically claim claimed clear climbed closed coincided
        comparable comparator compared comparison compartment compartments
        antennal component conclude concluded conclusion consistent corresponding count counted
        counts cover covered covering curve curves denied denying departed
        departing departure departures describe described despite detectable
        detected differ difference different distance distant diverged
        divergence divider dose dosed egress elevate elevated elicited enabled
        enclosed enclosure endpoint equals equivalent erased estimate estimated evidence
        exceed exceeded exceeding exceeds excess excluded excluding exited
        evaluated experiment explain exposed exposing extra fabric face failed favor feet
        females fenced finding findings fits fitted flat followed follows format formats
        found fraction fractions free frequency gauze gave generated giving
        granted granting greater guard hazard higher holding identical identify
        impossible impregnated inaccessible included including inclusion indicate
        indicated indirect indistinguishable infer inference inferred insert
        inside interpretation interpreted intervened isolated justified keeping
        larger later lay leave leaving led left level levels like liner longer look
        hour hours made making matched matches matching measure measured measurement
        measurements meaning mesh minus minute minutes monitor
        near negative netted netting nil non nonsignificant null number numbers
        nylon observations observed occluding occurred off often onto open
        opened opening outcome outside overlapped paper parity partition
        p q pattern percentage percentages perforated permission permitted permitting physical
        physically place placing positive possible present presentation
        prevented preventing prevention prevents probability produce produced
        prohibited proportion proportions protected protection proved provided
        putting raise raised rather ratio reach reachable reached read recorded
        reference related remained remains remote remotely removal removed
        removing repellency repellent replicates represent residue response restored returned
        reading readings readout readouts revealed rise rose sample sat saw screen screened see separate
        separately separated shared
        separating separation separator setup sheet shielded shielding shrouded
        side significant significantly similar sleeve solvent source spatial
        stayed stopped stronger substrate summarize superimposed support
        supported surface surpassed surplus tactile taken taking tarsal tell
        test tied total totals touch touchable touched touching tracked treated
        timepoint timepoints treatment transfluthrin trials tft unable unavailable
        unblocking unchanged
        uncovered unrestricted
        uncovering unproven unreachable unscreened untouchable untreated upward
        shift value values vehicle warranted window yielded zero
        """.split()
    )
    neutral_arm_prefixes = (
        "access",
        "activ",
        "allow",
        "appear",
        "assay",
        "barrier",
        "baseline",
        "block",
        "carrier",
        "chamber",
        "claim",
        "compar",
        "conclu",
        "contact",
        "control",
        "count",
        "cover",
        "deni",
        "depart",
        "descri",
        "differ",
        "direct",
        "effect",
        "elevat",
        "enclos",
        "equal",
        "escap",
        "estimat",
        "exceed",
        "exit",
        "expos",
        "favor",
        "formulat",
        "frequen",
        "group",
        "guard",
        "identic",
        "impregnat",
        "indicat",
        "indistinguish",
        "infer",
        "interpret",
        "isolat",
        "leav",
        "match",
        "mesh",
        "net",
        "noncontact",
        "observ",
        "pair",
        "panel",
        "paper",
        "partition",
        "permit",
        "physic",
        "prevent",
        "produc",
        "protect",
        "rate",
        "reach",
        "record",
        "referen",
        "remov",
        "repellen",
        "report",
        "response",
        "result",
        "rise",
        "rose",
        "same",
        "screen",
        "separat",
        "sheet",
        "shield",
        "show",
        "spatial",
        "substrate",
        "succeed",
        "support",
        "surface",
        "test",
        "touch",
        "treat",
        "trial",
        "unchang",
        "vehicle",
        "yield",
    )

    def has_unexplained_arm_context(text: str) -> bool:
        scrubbed = text
        for pattern in (
            noncontact_pattern,
            contact_pattern,
            result_qualifier_pattern,
            equality_pattern,
            increase_pattern,
            comparator_pattern,
            event_endpoint_pattern,
            competing_endpoint_pattern,
        ):
            scrubbed = pattern.sub(" ", scrubbed)
        tokens = re.findall(r"[a-z]+", scrubbed)
        return any(
            token not in neutral_arm_words
            and not token.startswith(neutral_arm_prefixes)
            for token in tokens
        )

    if any(has_unexplained_arm_context(clause) for clause in clauses):
        return False

    def span_distance(
        first: tuple[int, int],
        second: tuple[int, int],
    ) -> int:
        if first[1] < second[0]:
            return second[0] - first[1]
        if second[1] < first[0]:
            return first[0] - second[1]
        return 0

    def relation_belongs_to(
        relation: re.Match[str],
        *,
        target: list[re.Match[str]],
        competing: list[re.Match[str]],
    ) -> bool:
        if not target:
            return False
        relation_span = relation.span()
        target_distance = min(
            span_distance(relation_span, match.span()) for match in target
        )
        if not competing:
            return True
        competing_distance = min(
            span_distance(relation_span, match.span()) for match in competing
        )
        return target_distance <= competing_distance

    def relation_has_escape_endpoint(
        relation: re.Match[str],
        clause: str,
    ) -> bool:
        endpoints = [
            match
            for match in event_endpoint_pattern.finditer(clause)
            if not (
                match.group() == "escape"
                and non_event_escape_context_pattern.match(
                    clause,
                    match.start(),
                )
            )
        ]
        competing = list(competing_endpoint_pattern.finditer(clause))
        if endpoints:
            endpoint_distance = min(
                span_distance(relation.span(), match.span()) for match in endpoints
            )
            if competing:
                competing_distance = min(
                    span_distance(relation.span(), match.span())
                    for match in competing
                )
                if competing_distance <= endpoint_distance:
                    return False
            return True
        return not competing and bool(
            escape_context_pattern.search(normalized_question)
        )

    def increase_is_positive(
        relation: re.Match[str],
        clause: str,
    ) -> bool:
        relation_prefix = clause[max(0, relation.start() - 100) : relation.start()]
        scoped_relation_prefix = re.split(
            r"\b(?:and|but|whereas|while|then)\b",
            relation_prefix,
        )[-1]
        prefix_tokens = clause[: relation.start()].split()[-2:]
        if (
            "not" in prefix_tokens
            or "failed" in prefix_tokens
            or "no" in prefix_tokens
        ):
            return False
        if re.search(
            r"\b(?:fail(?:ed|s|ing)?|unable)\s+to"
            r"(?:\s+\w+){0,3}\s*$|"
            r"\b(?:can|could|did|does|was|were|would)\s+not"
            r"(?:\s+\w+){0,4}\s*$|"
            r"\bno(?:\s+\w+){0,2}\s+"
            r"(?:associated|attributable|linked|related)\s*$|"
            r"\b(?:no|without)\s+(?:clear\s+)?"
            r"(?:evidence|indication|sign|support)(?:\s+that)?"
            r"(?:\s+\w+){0,6}\s*$",
            scoped_relation_prefix,
        ):
            return False
        if re.search(
            r"\b(?:did|does|do) not\b(?:\s+\w+){0,3}\s+"
            r"\b(?:increase|exceed|rise|raise)\w*\b"
            r"(?:\s+\w+){0,4}\s*$",
            scoped_relation_prefix,
        ):
            return False
        relation_suffix = clause[relation.end() : relation.end() + 100]
        if re.match(
            r"^(?:\s+\w+){0,4}\s+"
            r"(?:(?:was|were|is|are)\s+)?not\s+"
            r"(?:confirmed|demonstrated|detected|found|observed|seen|shown)\b",
            relation_suffix,
        ):
            return False
        local_start = max(0, relation.start() - 60)
        local = clause[local_start : relation.end()]
        if re.search(
            r"\b(?:decreases?|decreased|lower|lowered|less)\b"
            r"(?:\s+\w+){0,3}\s+\b(?:rather than|not)\b"
            r"(?:\s+\w+){0,2}\s*$",
            local,
        ):
            return False
        return True

    def is_self_comparing_equality(relation: re.Match[str]) -> bool:
        return (
            relation.group().startswith("no ")
            or relation.group().startswith("negative for")
            or relation.group().startswith(("remove", "removing"))
            or relation.group().startswith(("erase", "erasing"))
            or (
                "ratio" in relation.group()
                and relation.group().endswith("one")
            )
            or relation.group()
            in {
                "zero",
                "centered on zero",
                "straddled zero",
                "null",
                "flat",
                "same",
                "equal",
                "equivalent",
                "identical",
                "alike",
                "absent",
                "unchanged",
                "did not change",
                "did not alter",
                "did not affect",
                "did not separate",
                "failed to raise",
                "unable to raise",
                "no change",
                "no escape response",
                "no additional",
                "no extra",
                "stayed at baseline",
                "remained at baseline",
                "was at baseline",
            }
        )

    def noncontact_relation_is_bound(
        relation: re.Match[str],
        *,
        noncontact: list[re.Match[str]],
        contact: list[re.Match[str]],
        clause: str,
    ) -> bool:
        if relation_belongs_to(
            relation,
            target=noncontact,
            competing=contact,
        ):
            return True
        for marker in noncontact:
            if relation.end() <= marker.start():
                between = clause[relation.end() : marker.start()]
                is_bound_transition = bool(
                    re.search(
                        r"\b(?:when|while|with|without|under|behind|in)\b",
                        between,
                    )
                )
                is_adjacent_self_comparison = (
                    relation.group().startswith("no ")
                    and len(between) <= 30
                )
                if (
                    len(between) <= 100
                    and (
                        is_bound_transition
                        or is_adjacent_self_comparison
                    )
                    and not any(
                        candidate.start() >= relation.end()
                        and candidate.end() <= marker.start()
                        for candidate in contact
                    )
                ):
                    return True
            if marker.end() > relation.start():
                continue
            between = clause[marker.end() : relation.start()]
            if len(between) > 100:
                continue
            if not any(
                candidate.start() >= marker.end()
                and candidate.end() <= relation.start()
                for candidate in contact
            ):
                return True
        return False

    def contact_relation_is_bound(
        relation: re.Match[str],
        *,
        contact: list[re.Match[str]],
        noncontact: list[re.Match[str]],
        clause: str,
    ) -> bool:
        if relation_belongs_to(
            relation,
            target=contact,
            competing=noncontact,
        ):
            return True
        for marker in contact:
            if marker.end() <= relation.start():
                between = clause[marker.end() : relation.start()]
                if len(between) <= 100 and not any(
                    candidate.start() >= marker.end()
                    and candidate.end() <= relation.start()
                    for candidate in noncontact
                ):
                    return True
            if marker.start() <= relation.end():
                continue
            between = clause[relation.end() : marker.start()]
            has_contact_transition = re.search(
                r"\b(?:when|while|after|following|once|if|with|under|in|on|for|during|"
                r"permitted|allowed)\b",
                between,
            )
            has_intervening_escape_endpoint = event_endpoint_pattern.search(
                between
            )
            if (
                len(between) <= 100
                and (
                    has_contact_transition
                    or has_intervening_escape_endpoint
                    or re.fullmatch(
                        r"\s*(?:the\s+)?(?:control|vehicle|carrier|solvent|"
                        r"blank|reference|zero|one)\s*",
                        between,
                    )
                )
                and not any(
                    candidate.start() >= relation.end()
                    and candidate.end() <= marker.start()
                    for candidate in noncontact
                )
            ):
                return True
        return False

    elliptical_no_contact_null = re.search(
        r"\bincreas(?:e|ed|es|ing)\b(?:\s+\w+){0,8}\s+\bcontact assay\b"
        r"(?:\s+\w+){0,4}\s+\bbut not\b(?:\s+\w+){0,5}\s+"
        r"\bno contact assay\b",
        normalized_question,
    )
    has_noncontact_equality = bool(
        elliptical_no_contact_null or no_contact_numeric_interval_null
    )
    has_contact_increase = False
    for clause in clauses:
        noncontact_matches = list(noncontact_pattern.finditer(clause))
        contact_matches = [
            match
            for match in contact_pattern.finditer(clause)
            if not any(
                match.start() >= noncontact.start()
                and match.end() <= noncontact.end()
                for noncontact in noncontact_matches
            )
            and clause[max(0, match.start() - 4) : match.start()] != "non "
            and clause[max(0, match.start() - 3) : match.start()] != "no "
        ]
        equality_matches = [
            relation
            for relation in equality_pattern.finditer(clause)
            if relation_has_escape_endpoint(relation, clause)
            and not any(
                relation.start() >= marker.start()
                and relation.end() <= marker.end()
                for marker in (*noncontact_matches, *contact_matches)
            )
        ]
        increase_matches = [
            relation
            for relation in increase_pattern.finditer(clause)
            if relation_has_escape_endpoint(relation, clause)
            and increase_is_positive(relation, clause)
        ]

        self_comparing_equality = any(
            is_self_comparing_equality(relation)
            for relation in equality_matches
        )
        if comparator_pattern.search(clause) or self_comparing_equality:
            has_noncontact_equality = has_noncontact_equality or any(
                noncontact_relation_is_bound(
                    relation,
                    noncontact=noncontact_matches,
                    contact=contact_matches,
                    clause=clause,
                )
                for relation in equality_matches
            )

        has_contact_increase = has_contact_increase or any(
                contact_relation_is_bound(
                    relation,
                    contact=contact_matches,
                    noncontact=noncontact_matches,
                    clause=clause,
                )
                for relation in increase_matches
            )
        raw_increase_matches = list(increase_pattern.finditer(clause))
        if (
            not increase_matches
            and not competing_endpoint_pattern.search(clause)
        ):
            observed_after_contact = re.search(
                r"\b(?:escap(?:e|es|ed|ing)|exit(?:s|ed|ing)?|left)\b"
                r"(?:\s+\w+){0,4}\s+"
                r"\b(?:after|following)\b(?:\s+\w+){0,4}\s+"
                r"\b(?:touch|contact)\b|"
                r"\b(?:after|following)\b(?:\s+\w+){0,4}\s+"
                r"\b(?:touch|contact)\b(?:\s+\w+){0,6}\s+"
                r"\b(?:escap(?:e|es|ed|ing)|exit(?:s|ed|ing)?|left)\b",
                clause,
            )
            repeated_positive_under_contact = (
                contact_pattern.search(clause)
                and re.search(
                    r"\b(?:(?:it|they) did|one appeared)\b",
                    clause,
                )
                and (
                    has_noncontact_equality
                    or re.search(
                        r"\bdid not\b(?:\s+\w+){0,4}\s+"
                        r"\b(?:increase|elevate|raise|exceed|escape more)\b",
                        statement_text,
                    )
                )
            )
            has_contact_increase = bool(
                has_contact_increase
                or observed_after_contact
                or repeated_positive_under_contact
            )

    if not has_noncontact_equality:
        noncontact_matches = list(
            noncontact_pattern.finditer(statement_text)
        )
        contact_matches = [
            match
            for match in contact_pattern.finditer(statement_text)
            if not any(
                match.start() >= noncontact.start()
                and match.end() <= noncontact.end()
                for noncontact in noncontact_matches
            )
            and statement_text[
                max(0, match.start() - 4) : match.start()
            ]
            != "non "
            and statement_text[
                max(0, match.start() - 3) : match.start()
            ]
            != "no "
        ]
        equality_matches = [
            relation
            for relation in equality_pattern.finditer(statement_text)
            if relation_has_escape_endpoint(
                relation,
                statement_text,
            )
            and not any(
                relation.start() >= marker.start()
                and relation.end() <= marker.end()
                for marker in (*noncontact_matches, *contact_matches)
            )
        ]
        if comparator_pattern.search(statement_text) or any(
            is_self_comparing_equality(relation)
            for relation in equality_matches
        ):
            has_noncontact_equality = any(
                noncontact_relation_is_bound(
                    relation,
                    noncontact=noncontact_matches,
                    contact=contact_matches,
                    clause=statement_text,
                )
                for relation in equality_matches
            )

    if not has_contact_increase:
        noncontact_matches = list(
            noncontact_pattern.finditer(statement_text)
        )
        contact_matches = [
            match
            for match in contact_pattern.finditer(statement_text)
            if not any(
                match.start() >= noncontact.start()
                and match.end() <= noncontact.end()
                for noncontact in noncontact_matches
            )
            and statement_text[
                max(0, match.start() - 4) : match.start()
            ]
            != "non "
            and statement_text[
                max(0, match.start() - 3) : match.start()
            ]
            != "no "
        ]
        increase_matches = []
        if not competing_endpoint_pattern.search(statement_text):
            increase_matches = [
                relation
                for relation in increase_pattern.finditer(statement_text)
                if relation_has_escape_endpoint(
                    relation,
                    statement_text,
                )
                and increase_is_positive(relation, statement_text)
            ]
        has_contact_increase = any(
            contact_relation_is_bound(
                relation,
                contact=contact_matches,
                noncontact=noncontact_matches,
                clause=statement_text,
            )
            for relation in increase_matches
        )

    return has_noncontact_equality and has_contact_increase


def _question_intent_matches(
    intent: str,
    normalized_question: str,
    raw_question: str,
) -> bool:
    if intent == "deet_repeat_exposure":
        return _has_deet_repeat_exposure_intent(normalized_question)
    if intent == "er_contact_only_result_pattern":
        return _has_er_contact_only_result_pattern_intent(
            normalized_question,
            raw_question,
        )
    if intent == "movement_inference":
        return _has_movement_inference_intent(normalized_question)
    if intent == "olfactory_experience":
        return _has_olfactory_experience_intent(normalized_question)
    if intent == "sampling_design":
        return _has_sampling_design_intent(normalized_question)
    return False


def _species_matches(
    normalized_question: str,
    species: list[dict[str, object]],
) -> set[str]:
    specific_matches: set[str] = set()
    for item in species:
        aliases = [str(item["scientific_name"]), *_strings(item["aliases"], "aliases")]
        if any(_contains(normalized_question, alias) for alias in aliases):
            specific_matches.add(str(item["id"]))
    if specific_matches:
        return specific_matches

    generic_matches: set[str] = set()
    for item in species:
        aliases = _strings(
            item.get("generic_aliases", []),
            "generic_aliases",
            allow_empty=True,
        )
        if any(_contains(normalized_question, alias) for alias in aliases):
            generic_matches.add(str(item["id"]))
    return generic_matches


def _topic_score(
    topic: dict[str, object],
    *,
    raw_question: str,
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
        implicit_species_excluded_patterns = _strings(
            match.get("implicit_species_excluded_normalized_patterns", []),
            "topic match.implicit_species_excluded_normalized_patterns",
            allow_empty=True,
        )
        if any(
            re.search(pattern, normalized_question, flags=re.IGNORECASE)
            for pattern in implicit_species_excluded_patterns
        ):
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
        question_intent,
        normalized_question,
        raw_question,
    ):
        return None
    excluded = _strings(
        match.get("excluded_any", []), "topic match.excluded_any", allow_empty=True
    )
    if any(_contains(normalized_question, term) for term in excluded):
        return None
    excluded_normalized_patterns = _strings(
        match.get("excluded_normalized_patterns", []),
        "topic match.excluded_normalized_patterns",
        allow_empty=True,
    )
    if any(
        re.search(pattern, normalized_question, flags=re.IGNORECASE)
        for pattern in excluded_normalized_patterns
    ):
        return None
    required_groups = _objects_as_string_groups(
        match["required_any"], "topic match.required_any"
    )
    if question_intent is None and not all(
        any(_contains(normalized_question, term) for term in group)
        for group in required_groups
    ):
        return None
    required_normalized_pattern_groups = _objects_as_string_groups(
        match.get("required_normalized_pattern_groups", []),
        "topic match.required_normalized_pattern_groups",
    )
    if required_normalized_pattern_groups and not all(
        any(
            re.search(pattern, normalized_question, flags=re.IGNORECASE)
            for pattern in group
        )
        for group in required_normalized_pattern_groups
    ):
        return None
    phrases = _strings(match["phrases"], "topic match.phrases", allow_empty=True)
    optional = _strings(match["optional"], "topic match.optional", allow_empty=True)
    score = int(match.get("priority", 0)) + 10 * len(required_groups)
    score += 10 * len(required_normalized_pattern_groups)
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
            raw_question=question,
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
