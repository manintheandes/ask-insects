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
    "stiff": "hardness",
    "stiffer": "harder",
    "stiffest": "harder",
    "stiffness": "hardness",
}
FORBIDDEN_SCIENTIFIC_SOURCE_PREFIXES = (
    "insect_intelligence_programs:",
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
        if not isinstance(topic.get("answer"), str) or not str(
            topic["answer"]
        ).strip():
            raise ReviewedScienceError(f"topic {topic_id}.answer must be non-empty")
        source_record_ids = _strings(
            topic.get("source_record_ids"),
            f"topic {topic_id}.source_record_ids",
        )
        if any(
            record_id.startswith(FORBIDDEN_SCIENTIFIC_SOURCE_PREFIXES)
            for record_id in source_record_ids
        ):
            raise ReviewedScienceError(
                f"topic {topic_id} must cite an original scientific or official source; "
                "the internal insect-intelligence program ledger cannot substitute for evidence"
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
    if not matched_species and match.get("species_may_be_implicit") is not True:
        return None
    required_groups = _objects_as_string_groups(
        match["required_any"], "topic match.required_any"
    )
    if not all(
        any(_contains(normalized_question, term) for term in group)
        for group in required_groups
    ):
        return None
    phrases = _strings(match["phrases"], "topic match.phrases", allow_empty=True)
    optional = _strings(match["optional"], "topic match.optional", allow_empty=True)
    score = int(match.get("priority", 0)) + 10 * len(required_groups)
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


def _record_to_evidence(record: EvidenceRecord) -> dict[str, object]:
    provenance = record.provenance.to_dict()
    provenance["locator"] = public_provenance_locator(
        str(provenance.get("locator") or ""),
        record.provenance.source_id,
    )
    return {
        "record_id": record.record_id,
        "lane": record.lane,
        "source": record.source,
        "title": record.title,
        "text": record.text,
        "species": record.species,
        "url": record.url,
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
    return {
        "ok": True,
        "answer_shape": "reviewed_science",
        "answer": str(topic["answer"]).strip(),
        "evidence": [_record_to_evidence(record) for record in records],
        "source_gap": None,
    }
