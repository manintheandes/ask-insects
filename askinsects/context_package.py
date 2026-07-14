from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .builder import DEFAULT_ARTIFACT_DIR
from .sources.literature import abstract_from_inverted_index


PACKAGE_SCHEMA_VERSION = "ask-insects-evidence-package.v2"
CONFIG_SCHEMA_VERSION = "ask-insects-evidence-package-config.v2"
ELIGIBILITY_RULESET_VERSION = "direct-semantic-evidence.v1"
VALIDATION_CONTRACT = {
    "producer_linkage": "verified_in_read_only_source_index_during_build",
    "downstream_validation": "exported_snapshot_internal_consistency_only",
    "snapshot_authentication": "publisher_pinned_content_sha256",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT_CONFIG = REPO_ROOT / "config/insect-evidence-package.json"
MAX_SELECTOR_LIMIT = 25
GENERIC_CONTEXT_FIELDS = frozenset(
    {
        "id",
        "endpoint_family",
        "exposure_routes",
        "species_ids",
        "required_domains",
        "measures",
        "does_not_establish",
        "plausible_explanations",
        "discriminating_evidence",
    }
)
CONTEXT_CONFIG_FIELDS = GENERIC_CONTEXT_FIELDS | {"selectors"}
EXPORTED_CONTEXT_FIELDS = GENERIC_CONTEXT_FIELDS | {"provenance"}
SELECTOR_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "species_id",
        "source",
        "query_any",
        "context_required_term_groups",
        "taxon_field_paths",
        "context_field_paths",
        "context_field_prerequisites",
        "limit",
        "required",
    }
)
SELECTOR_OPTIONAL_FIELDS = frozenset(
    {"parent_record", "fulltext_context", "record_requirements"}
)
PARENT_RECORD_FIELDS = frozenset({"record_id_path", "taxon_field_paths"})
FULLTEXT_CONTEXT_FIELDS = frozenset(
    {
        "unit_id_path",
        "parent_record_id_path",
        "text_field_path",
    }
)
RETAINED_SEMANTIC_FIELD_PATHS = frozenset(
    {
        "payload.title",
        "payload.abstract",
        "payload.assay_types",
        "payload.table_row",
        "payload.fields.table_row",
    }
)
RETAINED_PARENT_TAXON_PATHS = frozenset(
    {
        "payload.raw_openalex_work.display_name",
        "payload.raw_openalex_work.abstract_inverted_index",
    }
)
REFERENCE_ID_PATHS = frozenset(
    {
        "payload.source_record_id",
        "payload.fulltext_unit_id",
        "payload.matched_record_ids",
    }
)
FULLTEXT_TEXT_PATH = "literature_fulltext_units.text"
RECORD_REQUIREMENT_PATHS = frozenset({"payload.atom_type"})
ELIGIBILITY_REJECTION_REASONS = frozenset(
    {
        "taxon_not_directly_confirmed",
        "context_not_directly_confirmed",
        "upstream_record_missing",
        "trusted_field_missing",
        "fulltext_unit_link_invalid",
        "record_requirement_not_met",
    }
)
PRIVATE_SOURCE_MARKERS = (
    "gs://monarch-videos-new",
    "/ask-monarch/",
    "ask_monarch",
    "ask-monarch-server",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_package_hash(package: dict[str, object]) -> str:
    payload = deepcopy(package)
    payload.pop("generated_at", None)
    payload.pop("content_sha256", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _require_string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    values = [item.strip() for item in value]
    if not allow_empty and not values:
        raise ValueError(f"{label} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")
    return values


def _require_term_groups(value: object, label: str) -> list[list[str]]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError(f"{label} must contain at least two term groups")
    groups = [
        _require_string_list(group, f"{label}/{index}")
        for index, group in enumerate(value)
    ]
    markers = [canonical_json(group) for group in groups]
    if len(markers) != len(set(markers)):
        raise ValueError(f"{label} must not contain duplicate term groups")
    normalized_groups = [
        {
            re.sub(r"[\s_-]+", " ", term).strip().casefold()
            for term in group
        }
        for group in groups
    ]
    for index, normalized_group in enumerate(normalized_groups):
        prior_terms = set().union(*normalized_groups[:index]) if index else set()
        if normalized_group.intersection(prior_terms):
            raise ValueError(f"{label} term groups must be disjoint after normalization")
    return groups


def _validate_generic_context(
    context: dict[str, object],
    *,
    context_id: str,
    expected_fields: frozenset[str],
) -> tuple[list[str], set[str]]:
    unexpected_fields = set(context) - expected_fields
    if unexpected_fields:
        raise ValueError(f"context {context_id} contains unsupported fields: {sorted(unexpected_fields)}")
    missing_fields = expected_fields - set(context)
    if missing_fields:
        raise ValueError(f"context {context_id} is missing fields: {sorted(missing_fields)}")
    _require_string(context.get("endpoint_family"), f"context {context_id} endpoint_family")
    _require_string_list(context.get("exposure_routes"), f"context {context_id} exposure_routes")
    species_ids = _require_string_list(context.get("species_ids"), f"context {context_id} species_ids")
    required_domains = set(
        _require_string_list(context.get("required_domains"), f"context {context_id} required_domains")
    )
    for field in ("measures", "does_not_establish", "plausible_explanations", "discriminating_evidence"):
        _require_string_list(context.get(field), f"context {context_id} {field}")
    return species_ids, required_domains


def _validate_path(path: str, *, label: str, allowed: frozenset[str]) -> None:
    if path not in allowed:
        raise ValueError(f"{label} path is not allowlisted: {path}")


def _validate_selector(selector: dict[str, object], *, selector_id: str) -> None:
    unsupported_fields = set(selector) - SELECTOR_REQUIRED_FIELDS - SELECTOR_OPTIONAL_FIELDS
    if unsupported_fields:
        raise ValueError(f"selector {selector_id} contains unsupported fields: {sorted(unsupported_fields)}")
    missing_fields = SELECTOR_REQUIRED_FIELDS - set(selector)
    if missing_fields:
        raise ValueError(f"selector {selector_id} is missing fields: {sorted(missing_fields)}")

    _require_string(selector.get("source"), f"selector {selector_id} source")
    _require_string_list(selector.get("query_any"), f"selector {selector_id} query_any")
    _require_term_groups(
        selector.get("context_required_term_groups"),
        f"selector {selector_id} context_required_term_groups",
    )
    taxon_paths = _require_string_list(
        selector.get("taxon_field_paths"),
        f"selector {selector_id} taxon_field_paths",
        allow_empty=True,
    )
    context_paths = _require_string_list(
        selector.get("context_field_paths"),
        f"selector {selector_id} context_field_paths",
        allow_empty=True,
    )
    for field_path in [*taxon_paths, *context_paths]:
        _validate_path(
            field_path,
            label=f"selector {selector_id} trusted field",
            allowed=RETAINED_SEMANTIC_FIELD_PATHS,
        )

    prerequisites = selector.get("context_field_prerequisites")
    if not isinstance(prerequisites, dict):
        raise ValueError(f"selector {selector_id} context_field_prerequisites must be an object")
    for field_path, raw_paths in prerequisites.items():
        if not isinstance(field_path, str) or field_path not in context_paths:
            raise ValueError(
                f"selector {selector_id} context field prerequisite must name a configured context field path"
            )
        paths = _require_string_list(
            raw_paths,
            f"selector {selector_id} prerequisite for {field_path}",
        )
        for prerequisite_path in paths:
            _validate_path(
                prerequisite_path,
                label=f"selector {selector_id} prerequisite reference",
                allowed=REFERENCE_ID_PATHS,
            )

    parent = selector.get("parent_record")
    if parent is not None:
        if not isinstance(parent, dict) or set(parent) != PARENT_RECORD_FIELDS:
            raise ValueError(
                f"selector {selector_id} parent_record must contain record_id_path and taxon_field_paths"
            )
        record_id_path = _require_string(
            parent.get("record_id_path"),
            f"selector {selector_id} parent record_id_path",
        )
        _validate_path(
            record_id_path,
            label=f"selector {selector_id} parent id",
            allowed=REFERENCE_ID_PATHS,
        )
        parent_paths = _require_string_list(
            parent.get("taxon_field_paths"),
            f"selector {selector_id} parent taxon_field_paths",
        )
        for field_path in parent_paths:
            _validate_path(
                field_path,
                label=f"selector {selector_id} parent trusted field",
                allowed=RETAINED_PARENT_TAXON_PATHS,
            )

    fulltext = selector.get("fulltext_context")
    if fulltext is not None:
        if not isinstance(fulltext, dict) or set(fulltext) != FULLTEXT_CONTEXT_FIELDS:
            raise ValueError(
                f"selector {selector_id} fulltext_context must contain unit_id_path, "
                "parent_record_id_path, and text_field_path"
            )
        if not isinstance(parent, dict):
            raise ValueError(f"selector {selector_id} fulltext_context requires parent_record")
        unit_id_path = _require_string(
            fulltext.get("unit_id_path"),
            f"selector {selector_id} fulltext unit_id_path",
        )
        parent_record_id_path = _require_string(
            fulltext.get("parent_record_id_path"),
            f"selector {selector_id} fulltext parent_record_id_path",
        )
        text_field_path = _require_string(
            fulltext.get("text_field_path"),
            f"selector {selector_id} fulltext text_field_path",
        )
        _validate_path(
            unit_id_path,
            label=f"selector {selector_id} fulltext unit id",
            allowed=frozenset({"payload.fulltext_unit_id"}),
        )
        _validate_path(
            parent_record_id_path,
            label=f"selector {selector_id} fulltext parent id",
            allowed=frozenset({"payload.source_record_id"}),
        )
        _validate_path(
            text_field_path,
            label=f"selector {selector_id} fulltext text",
            allowed=frozenset({FULLTEXT_TEXT_PATH}),
        )
        if parent_record_id_path != parent.get("record_id_path"):
            raise ValueError(
                f"selector {selector_id} fulltext parent path must match parent_record record_id_path"
            )
        if context_paths:
            raise ValueError(
                f"selector {selector_id} fulltext_context requires empty context_field_paths"
            )
        if prerequisites:
            raise ValueError(
                f"selector {selector_id} fulltext_context requires empty context_field_prerequisites"
            )

    requirements = selector.get("record_requirements")
    if requirements is not None:
        if not isinstance(requirements, dict) or not requirements:
            raise ValueError(f"selector {selector_id} record_requirements must be a non-empty object")
        for field_path, expected in requirements.items():
            _validate_path(
                str(field_path),
                label=f"selector {selector_id} record requirement",
                allowed=RECORD_REQUIREMENT_PATHS,
            )
            _require_string(expected, f"selector {selector_id} record requirement {field_path}")

    limit = selector.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SELECTOR_LIMIT:
        raise ValueError(f"selector {selector_id} limit must be between 1 and {MAX_SELECTOR_LIMIT}")
    if not isinstance(selector.get("required"), bool):
        raise ValueError(f"selector {selector_id} required must be true or false")


def _validate_config(config: dict[str, object]) -> None:
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(f"context config schema_version must be {CONFIG_SCHEMA_VERSION}")
    _require_string(config.get("package_version"), "context config package_version")
    _require_string(config.get("last_reviewed"), "context config last_reviewed")
    _require_string(config.get("objective"), "context config objective")
    domains = set(_require_string_list(config.get("knowledge_domains"), "context config knowledge_domains"))
    contexts = config.get("contexts")
    if not isinstance(contexts, list) or not contexts or not all(isinstance(item, dict) for item in contexts):
        raise ValueError("context config contexts must be a non-empty list of objects")
    context_ids: list[str] = []
    selector_ids: list[str] = []
    for context_index, context in enumerate(contexts):
        context_id = _require_string(context.get("id"), f"contexts/{context_index}/id")
        context_ids.append(context_id)
        species_ids, required_domains = _validate_generic_context(
            context,
            context_id=context_id,
            expected_fields=CONTEXT_CONFIG_FIELDS,
        )
        unknown_domains = required_domains - domains
        if unknown_domains:
            raise ValueError(f"context {context_id} names unknown knowledge domains: {sorted(unknown_domains)}")
        selectors = context.get("selectors")
        if not isinstance(selectors, list) or not all(isinstance(item, dict) for item in selectors):
            raise ValueError(f"context {context_id} selectors must be a list of objects")
        context_term_groups: str | None = None
        for selector_index, selector in enumerate(selectors):
            selector_id = _require_string(
                selector.get("id"),
                f"context {context_id} selectors/{selector_index}/id",
            )
            selector_ids.append(selector_id)
            species_id = _require_string(selector.get("species_id"), f"selector {selector_id} species_id")
            if species_id not in species_ids:
                raise ValueError(f"selector {selector_id} species_id is not supported by context {context_id}")
            _validate_selector(selector, selector_id=selector_id)
            selector_term_groups = canonical_json(selector["context_required_term_groups"])
            if context_term_groups is None:
                context_term_groups = selector_term_groups
            elif selector_term_groups != context_term_groups:
                raise ValueError(
                    f"context {context_id} selectors must use the same context_required_term_groups"
                )
    if len(context_ids) != len(set(context_ids)):
        raise ValueError("context ids must be unique")
    if len(selector_ids) != len(set(selector_ids)):
        raise ValueError("selector ids must be unique across the package")


def load_context_config(path: Path = DEFAULT_CONTEXT_CONFIG) -> dict[str, object]:
    config = _load_json_object(Path(path))
    _validate_config(config)
    return config


def _json_or_empty(value: object) -> dict[str, object]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _flatten_semantic_value(value: object) -> list[str]:
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return [cleaned] if cleaned else []
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [item for value_item in value for item in _flatten_semantic_value(value_item)]
    if isinstance(value, dict):
        return [
            item
            for key in sorted(value)
            for item in [*_flatten_semantic_value(key), *_flatten_semantic_value(value[key])]
        ]
    return []


def _value_at_path(record: dict[str, object], path: str) -> list[str]:
    values: list[object] = [record]
    for part in path.split("."):
        next_values: list[object] = []
        for value in values:
            if isinstance(value, dict) and part in value:
                next_values.append(value[part])
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and part in item:
                        next_values.append(item[part])
        values = next_values
        if not values:
            return []

    if path.endswith("abstract_inverted_index"):
        reconstructed = [
            abstract_from_inverted_index(value)
            for value in values
            if isinstance(value, dict)
        ]
        return [value for value in reconstructed if value]
    return [item for value in values for item in _flatten_semantic_value(value)]


def _trusted_semantic_values(
    record: dict[str, object],
    field_paths: list[str],
    *,
    field_prefix: str = "",
    link: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    link_fields = link or {}
    return [
        {
            "field_path": f"{field_prefix}{field_path}",
            "value": value,
            "retained_store": "record_payloads",
            "retained_source": str(record.get("source") or ""),
            "retained_path": field_path,
            **link_fields,
        }
        for field_path in field_paths
        for value in _value_at_path(record, field_path)
    ]


def _term_match(value: str, term: str) -> re.Match[str] | None:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", value, flags=re.IGNORECASE)


def _matching_excerpt(value: str, match: re.Match[str], *, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    start = max(0, match.start() - limit // 2)
    end = min(len(compact), start + limit)
    start = max(0, end - limit)
    return compact[start:end].strip()


def _direct_assertion(
    values: list[dict[str, str]], terms: list[str], *, status: str
) -> dict[str, object] | None:
    for semantic_value in values:
        compact = re.sub(r"\s+", " ", semantic_value["value"]).strip()
        for term in terms:
            match = _term_match(compact, term)
            if match:
                return {
                    "status": status,
                    "basis": [_assertion_basis(semantic_value, term, match)],
                }
    return None


def _assertion_basis(
    semantic_value: dict[str, str], term: str, match: re.Match[str]
) -> dict[str, str]:
    compact = re.sub(r"\s+", " ", semantic_value["value"]).strip()
    snapshot = _matching_excerpt(compact, match, limit=1000)
    snapshot_match = _term_match(snapshot, term)
    if snapshot_match is None:
        raise ValueError("retained evidence snapshot lost its matched term")
    return {
        key: value
        for key, value in semantic_value.items()
        if key != "value"
    } | {
        "matched_term": term,
        "excerpt": _matching_excerpt(snapshot, snapshot_match),
        "evidence_snapshot": snapshot,
        "evidence_sha256": hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
    }


def _required_groups_assertion(
    values: list[dict[str, str]],
    required_groups: list[list[str]],
    *,
    status: str,
) -> dict[str, object] | None:
    basis: list[dict[str, str]] = []
    for terms in required_groups:
        matched_basis: dict[str, str] | None = None
        for semantic_value in values:
            compact = re.sub(r"\s+", " ", semantic_value["value"]).strip()
            for term in terms:
                match = _term_match(compact, term)
                if match:
                    matched_basis = _assertion_basis(semantic_value, term, match)
                    break
            if matched_basis is not None:
                break
        if matched_basis is None:
            return None
        basis.append(matched_basis)
    return {"status": status, "basis": basis}


def _direct_taxon_terms(
    scientific_name: str,
    common_name: str,
    aliases: list[str],
) -> list[str]:
    genus = scientific_name.split()[0].casefold()
    generic_common_name = common_name.split()[-1].casefold()
    terms: list[str] = []
    seen: set[str] = set()
    for term in [scientific_name, common_name, *aliases]:
        normalized = re.sub(r"\s+", " ", term).strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        if key in {genus, generic_common_name}:
            continue
        words = re.findall(r"[A-Za-z0-9]+", normalized)
        is_acronym = normalized.isupper() and 2 <= len(normalized) <= 6
        if len(words) < 2 and not is_acronym:
            continue
        seen.add(key)
        terms.append(normalized)
    return terms


def _export_record(row: sqlite3.Row | dict[str, object]) -> dict[str, object]:
    values = dict(row)
    return {
        "record_id": str(values["record_id"]),
        "lane": str(values["lane"]),
        "source": str(values["source"]),
        "title": str(values["title"]),
        "text": str(values["text"]),
        "species": values.get("species"),
        "url": values.get("url"),
        "media_url": values.get("media_url"),
        "payload": _json_or_empty(values.get("payload_json")),
        "provenance": _json_or_empty(values.get("provenance_json")),
    }


def _program_records(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT r.*, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.source = 'insect_intelligence_programs'
        ORDER BY r.record_id
        """
    ).fetchall()
    if not rows:
        raise ValueError("insect_intelligence_programs records are missing from the source index")
    return [_export_record(row) for row in rows]


def _species_profiles(program_records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    profiles: dict[str, dict[str, object]] = {}
    for record in program_records:
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("atom_type") != "species_profile":
            continue
        species_id = _require_string(payload.get("species_id"), "species profile species_id")
        scientific_name = _require_string(payload.get("scientific_name"), f"species {species_id} scientific_name")
        common_name = _require_string(payload.get("common_name"), f"species {species_id} common_name")
        aliases = _require_string_list(payload.get("aliases"), f"species {species_id} aliases")
        if species_id in profiles:
            raise ValueError(f"duplicate species profile: {species_id}")
        taxon_terms = _direct_taxon_terms(scientific_name, common_name, aliases)
        if not taxon_terms:
            raise ValueError(f"species {species_id} has no unambiguous direct taxon aliases")
        profiles[species_id] = {
            "scientific_name": scientific_name,
            "common_name": common_name,
            "taxon_terms": taxon_terms,
        }
    if not profiles:
        raise ValueError("no species_profile program records were found")
    return profiles


def _select_record_ids_for_group(
    conn: sqlite3.Connection,
    *,
    source: str,
    scientific_name: str,
    selectors: list[dict[str, object]],
) -> dict[str, list[str]]:
    prepared = [
        (
            str(selector["id"]),
            [str(value).casefold() for value in selector["query_any"]],
        )
        for selector in selectors
    ]
    score_buckets: dict[str, dict[int, list[str]]] = {
        selector_id: {} for selector_id, _ in prepared
    }
    rows = conn.execute(
        """
        SELECT r.record_id, r.title, r.text
        FROM records AS r INDEXED BY idx_records_source
        WHERE r.source = ? AND r.species = ?
        ORDER BY r.record_id
        """,
        (source, scientific_name),
    )
    for row in rows:
        record_id = str(row["record_id"])
        haystack = f"{row['title']} {row['text']}".casefold()
        for selector_id, terms in prepared:
            score = sum(term in haystack for term in terms)
            if not score:
                continue
            bucket = score_buckets[selector_id].setdefault(score, [])
            bucket.append(record_id)

    selected: dict[str, list[str]] = {}
    for selector_id, _ in prepared:
        record_ids: list[str] = []
        for score in sorted(score_buckets[selector_id], reverse=True):
            record_ids.extend(score_buckets[selector_id][score])
        selected[selector_id] = record_ids
    return selected


def _records_by_id(conn: sqlite3.Connection, record_ids: list[str]) -> dict[str, dict[str, object]]:
    if not record_ids:
        return {}
    placeholders = ",".join("?" for _ in record_ids)
    rows = conn.execute(
        f"""
        SELECT r.*, p.payload_json
        FROM records r
        LEFT JOIN record_payloads p ON p.record_id = r.record_id
        WHERE r.record_id IN ({placeholders})
        """,
        record_ids,
    ).fetchall()
    return {str(row["record_id"]): _export_record(row) for row in rows}


def _fulltext_unit_by_id(
    conn: sqlite3.Connection, unit_id: str
) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT unit_id, record_id, source, unit_index, text, url, license, provenance_json
        FROM literature_fulltext_units
        WHERE unit_id = ?
        """,
        (unit_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _context_semantic_values(
    record: dict[str, object], selector: dict[str, object]
) -> list[dict[str, str]]:
    prerequisites = dict(selector["context_field_prerequisites"])
    field_paths = [
        str(field_path)
        for field_path in selector["context_field_paths"]
        if all(
            _value_at_path(record, str(prerequisite_path))
            for prerequisite_path in prerequisites.get(field_path, [])
        )
    ]
    return _trusted_semantic_values(record, field_paths)


def _record_requirements_match(
    record: dict[str, object], selector: dict[str, object]
) -> bool:
    requirements = selector.get("record_requirements")
    if not isinstance(requirements, dict):
        return True
    return all(
        str(expected) in _value_at_path(record, str(field_path))
        for field_path, expected in requirements.items()
    )


def _candidate_eligibility(
    conn: sqlite3.Connection,
    *,
    record: dict[str, object],
    selector: dict[str, object],
    context_id: str,
    species_id: str,
    scientific_name: str,
    taxon_terms: list[str],
) -> tuple[dict[str, object] | None, str | None]:
    selector_id = str(selector["id"])
    if not _record_requirements_match(record, selector):
        return None, "record_requirement_not_met"

    fulltext_config = selector.get("fulltext_context")
    fulltext_unit: dict[str, object] | None = None
    fulltext_unit_id: str | None = None
    fulltext_parent_id: str | None = None
    if isinstance(fulltext_config, dict):
        unit_ids = _value_at_path(record, str(fulltext_config["unit_id_path"]))
        linked_parent_ids = _value_at_path(
            record, str(fulltext_config["parent_record_id_path"])
        )
        if len(unit_ids) != 1 or len(linked_parent_ids) != 1:
            return None, "fulltext_unit_link_invalid"
        fulltext_unit_id = unit_ids[0]
        fulltext_parent_id = linked_parent_ids[0]
        fulltext_unit = _fulltext_unit_by_id(conn, fulltext_unit_id)
        if (
            fulltext_unit is None
            or str(fulltext_unit["record_id"]) != fulltext_parent_id
        ):
            return None, "fulltext_unit_link_invalid"

    taxon_values = _trusted_semantic_values(
        record,
        [str(path) for path in selector["taxon_field_paths"]],
    )

    parent_config = selector.get("parent_record")
    parent_ids: list[str] = []
    if isinstance(parent_config, dict):
        parent_ids = list(
            dict.fromkeys(
                _value_at_path(record, str(parent_config["record_id_path"]))
            )
        )
        if not parent_ids:
            return None, "upstream_record_missing"
        parents = _records_by_id(conn, parent_ids)
        if any(parent_id not in parents for parent_id in parent_ids):
            return None, "upstream_record_missing"
        parent_paths = [str(path) for path in parent_config["taxon_field_paths"]]
        for parent_id in parent_ids:
            taxon_values.extend(
                _trusted_semantic_values(
                    parents[parent_id],
                    parent_paths,
                    field_prefix="parent.",
                    link={"parent_record_id": parent_id},
                )
            )

    if not taxon_values:
        return None, "trusted_field_missing"
    taxon = _direct_assertion(taxon_values, taxon_terms, status="direct_focal_taxon")
    if taxon is None:
        return None, "taxon_not_directly_confirmed"

    if isinstance(fulltext_config, dict):
        assert fulltext_unit is not None
        assert fulltext_unit_id is not None and fulltext_parent_id is not None
        context_values: list[dict[str, str]] = []
        text = re.sub(r"\s+", " ", str(fulltext_unit.get("text") or "")).strip()
        if text:
            context_values.append(
                {
                    "field_path": str(fulltext_config["text_field_path"]),
                    "value": text,
                    "retained_store": "literature_fulltext_units",
                    "retained_source": str(fulltext_unit.get("source") or ""),
                    "retained_path": str(fulltext_config["text_field_path"]),
                    "fulltext_unit_id": str(fulltext_unit_id),
                    "parent_record_id": str(fulltext_parent_id),
                }
            )
    else:
        context_values = _context_semantic_values(record, selector)
    if not context_values:
        return None, "trusted_field_missing"
    context = _required_groups_assertion(
        context_values,
        [
            [str(term) for term in group]
            for group in selector["context_required_term_groups"]
        ],
        status="direct_context",
    )
    if context is None:
        return None, "context_not_directly_confirmed"

    for basis in taxon["basis"]:
        basis["selector_id"] = selector_id
    for basis in context["basis"]:
        basis["selector_id"] = selector_id
        basis["context_id"] = context_id
    taxon.update(
        {
            "species_id": species_id,
            "scientific_name": scientific_name,
        }
    )
    context["context_ids"] = [context_id]
    return {
        "ruleset_version": ELIGIBILITY_RULESET_VERSION,
        "taxon": taxon,
        "context": context,
    }, None


def _merge_basis(existing: list[dict[str, object]], additional: list[dict[str, object]]) -> None:
    seen = {canonical_json(item) for item in existing}
    for item in additional:
        marker = canonical_json(item)
        if marker not in seen:
            existing.append(item)
            seen.add(marker)


def _merge_eligibility(existing: dict[str, object], additional: dict[str, object]) -> None:
    if existing.get("ruleset_version") != additional.get("ruleset_version"):
        raise ValueError("cannot merge evidence produced by different eligibility rulesets")
    existing_taxon = existing["taxon"]
    additional_taxon = additional["taxon"]
    if (
        existing_taxon.get("species_id") != additional_taxon.get("species_id")
        or existing_taxon.get("scientific_name") != additional_taxon.get("scientific_name")
    ):
        raise ValueError("cannot merge eligibility assertions for different taxa")
    _merge_basis(existing_taxon["basis"], additional_taxon["basis"])

    existing_context = existing["context"]
    additional_context = additional["context"]
    for context_id in additional_context["context_ids"]:
        if context_id not in existing_context["context_ids"]:
            existing_context["context_ids"].append(context_id)
    _merge_basis(existing_context["basis"], additional_context["basis"])


def _context_export(context: dict[str, object], *, index: int, config: dict[str, object]) -> dict[str, object]:
    last_reviewed = _require_string(config.get("last_reviewed"), "context config last_reviewed")
    exported = {key: deepcopy(value) for key, value in context.items() if key != "selectors"}
    exported["provenance"] = {
        "source_id": "ask_insects_context_config",
        "locator": f"config/insect-evidence-package.json#contexts/{index}",
        "retrieved_at": f"{last_reviewed}T00:00:00Z",
        "license": "Repository interpretation policy",
    }
    return exported


def build_context_package(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    config_path: Path = DEFAULT_CONTEXT_CONFIG,
    generated_at: str | None = None,
) -> dict[str, object]:
    artifact_dir = Path(artifact_dir)
    config_path = Path(config_path)
    config = load_context_config(config_path)
    status_path = artifact_dir / "source_status.json"
    if not status_path.exists():
        raise ValueError("source_status.json is required to identify the public source snapshot")
    status_bytes = status_path.read_bytes()
    status = json.loads(status_bytes)
    if not isinstance(status, dict):
        raise ValueError("source_status.json must contain a JSON object")
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise ValueError("source_index.sqlite is required to build the context package")

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        program_records = _program_records(conn)
        species_profiles = _species_profiles(program_records)
        contexts = config["contexts"]
        exported_contexts: list[dict[str, object]] = []
        selector_results: list[dict[str, object]] = []
        gaps: list[dict[str, object]] = []
        selected_by_id: dict[str, dict[str, object]] = {}
        selector_jobs: list[dict[str, object]] = []
        for context_index, raw_context in enumerate(contexts):
            context = dict(raw_context)
            context_id = str(context["id"])
            for species_id in context["species_ids"]:
                if species_id not in species_profiles:
                    raise ValueError(f"context {context_id} names unknown species profile: {species_id}")
            exported_contexts.append(_context_export(context, index=context_index, config=config))
            for selector in context["selectors"]:
                species_id = str(selector["species_id"])
                profile = species_profiles[species_id]
                selector_jobs.append(
                    {
                        "context_id": context_id,
                        "selector": selector,
                        "species_id": species_id,
                        "scientific_name": profile["scientific_name"],
                        "taxon_terms": profile["taxon_terms"],
                    }
                )

        grouped_jobs: dict[tuple[str, str], list[dict[str, object]]] = {}
        for job in selector_jobs:
            selector = job["selector"]
            key = (str(selector["source"]), str(job["scientific_name"]))
            grouped_jobs.setdefault(key, []).append(job)

        selected_ids: dict[str, list[str]] = {}
        records_by_id: dict[str, dict[str, object]] = {}
        for (source, scientific_name), jobs in grouped_jobs.items():
            group_selected = _select_record_ids_for_group(
                conn,
                source=source,
                scientific_name=scientific_name,
                selectors=[dict(job["selector"]) for job in jobs],
            )
            selected_ids.update(group_selected)
            group_ids = sorted({record_id for values in group_selected.values() for record_id in values})
            records_by_id.update(_records_by_id(conn, group_ids))

        for job in selector_jobs:
            context_id = str(job["context_id"])
            selector = dict(job["selector"])
            selector_id = str(selector["id"])
            species_id = str(job["species_id"])
            scientific_name = str(job["scientific_name"])
            candidate_rows = [records_by_id[record_id] for record_id in selected_ids[selector_id]]
            eligible: list[tuple[dict[str, object], dict[str, object]]] = []
            rejection_counts: dict[str, int] = {}
            for row in candidate_rows:
                eligibility, rejection_reason = _candidate_eligibility(
                    conn,
                    record=row,
                    selector=selector,
                    context_id=context_id,
                    species_id=species_id,
                    scientific_name=scientific_name,
                    taxon_terms=[str(term) for term in job["taxon_terms"]],
                )
                if eligibility is None:
                    reason = str(rejection_reason)
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                else:
                    eligible.append((row, eligibility))
            selected = eligible[: int(selector["limit"])]
            result = {
                "context_id": context_id,
                "selector_id": selector_id,
                "species_id": species_id,
                "scientific_name": scientific_name,
                "source": selector["source"],
                "query_any": selector["query_any"],
                "context_required_term_groups": selector[
                    "context_required_term_groups"
                ],
                "taxon_field_paths": selector["taxon_field_paths"],
                "context_field_paths": selector["context_field_paths"],
                "context_field_prerequisites": selector["context_field_prerequisites"],
                "parent_record": deepcopy(selector.get("parent_record")),
                "fulltext_context": deepcopy(selector.get("fulltext_context")),
                "record_requirements": deepcopy(selector.get("record_requirements")),
                "limit": selector["limit"],
                "required": selector["required"],
                "candidate_count": len(candidate_rows),
                "eligible_count": len(eligible),
                "selected_count": len(selected),
                "selected_record_ids": [row["record_id"] for row, _ in selected],
                "rejection_counts": dict(sorted(rejection_counts.items())),
            }
            selector_results.append(result)
            if not selected:
                gaps.append(
                    {
                        "gap_type": "selector_no_direct_evidence",
                        **result,
                    }
                )
            for row, eligibility in selected:
                record_id = str(row["record_id"])
                existing = selected_by_id.get(record_id)
                if existing is None:
                    exported_row = deepcopy(row)
                    exported_row["species_id"] = species_id
                    exported_row["context_ids"] = [context_id]
                    exported_row["selector_ids"] = [selector_id]
                    exported_row["eligibility"] = eligibility
                    selected_by_id[record_id] = exported_row
                else:
                    if existing["species_id"] != species_id:
                        raise ValueError(f"record {record_id} was selected for more than one species")
                    if context_id not in existing["context_ids"]:
                        existing["context_ids"].append(context_id)
                    if selector_id not in existing["selector_ids"]:
                        existing["selector_ids"].append(selector_id)
                    _merge_eligibility(existing["eligibility"], eligibility)
        evidence_records = [selected_by_id[key] for key in sorted(selected_by_id)]
    finally:
        conn.close()

    package: dict[str, object] = {
        "ok": True,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_version": config["package_version"],
        "generated_at": generated_at or utc_now(),
        "objective": config["objective"],
        "validation_contract": deepcopy(VALIDATION_CONTRACT),
        "knowledge_domains": config["knowledge_domains"],
        "upstream_snapshot": {
            "source_id": "ask_insects_hosted_source_index",
            "source_status_sha256": hashlib.sha256(status_bytes).hexdigest(),
            "source_status_generated_at": status.get("generated_at"),
            "record_count": status.get("record_count"),
        },
        "contexts": exported_contexts,
        "program_records": program_records,
        "evidence_records": evidence_records,
        "selector_results": selector_results,
        "gaps": gaps,
    }
    package["content_sha256"] = canonical_package_hash(package)
    validate_context_package(package)
    return package


def _unique(items: list[dict[str, object]], key: str, label: str) -> None:
    values = [str(item.get(key) or "") for item in items]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must have unique non-empty {key} values")


def _validate_public_provenance(item: dict[str, object], label: str) -> None:
    provenance = item.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(f"{label} is missing provenance")
    source_id = _require_string(provenance.get("source_id"), f"{label} provenance source_id")
    locator = _require_string(provenance.get("locator"), f"{label} provenance locator")
    combined = f"{source_id} {locator}".lower()
    if any(marker in combined for marker in PRIVATE_SOURCE_MARKERS):
        raise ValueError(f"{label} references a private Monarch source")


def _validate_assertion_basis(
    value: object,
    *,
    label: str,
    require_context: bool = False,
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} basis must be a non-empty list of objects")
    basis = [dict(item) for item in value]
    for index, item in enumerate(basis):
        field_path = _require_string(item.get("field_path"), f"{label} basis/{index} field_path")
        matched_term = _require_string(item.get("matched_term"), f"{label} basis/{index} matched_term")
        excerpt = _require_string(item.get("excerpt"), f"{label} basis/{index} excerpt")
        retained_source = _require_string(
            item.get("retained_source"),
            f"{label} basis/{index} retained_source",
        )
        retained_store = _require_string(
            item.get("retained_store"),
            f"{label} basis/{index} retained_store",
        )
        retained_path = _require_string(
            item.get("retained_path"),
            f"{label} basis/{index} retained_path",
        )
        snapshot = _require_string(
            item.get("evidence_snapshot"),
            f"{label} basis/{index} evidence_snapshot",
        )
        evidence_sha256 = _require_string(
            item.get("evidence_sha256"),
            f"{label} basis/{index} evidence_sha256",
        )
        _require_string(item.get("selector_id"), f"{label} basis/{index} selector_id")
        if require_context:
            _require_string(item.get("context_id"), f"{label} basis/{index} context_id")
        if retained_store not in {"record_payloads", "literature_fulltext_units"}:
            raise ValueError(f"{label} basis/{index} retained_store is invalid")
        if not retained_source or not retained_path:
            raise ValueError(f"{label} basis/{index} retained source/path identity is missing")
        if hashlib.sha256(snapshot.encode("utf-8")).hexdigest() != evidence_sha256:
            raise ValueError(f"{label} basis/{index} evidence_sha256 does not match evidence_snapshot")
        if excerpt not in snapshot:
            raise ValueError(f"{label} basis/{index} excerpt is not in evidence_snapshot")
        if _term_match(excerpt, matched_term) is None or _term_match(snapshot, matched_term) is None:
            raise ValueError(f"{label} basis/{index} excerpt does not contain matched_term")
        if not field_path:
            raise ValueError(f"{label} basis/{index} field_path is missing")
    return basis


def _record_snapshot_matches(
    record: dict[str, object], field_path: str, snapshot: str, matched_term: str
) -> bool:
    return any(
        snapshot in re.sub(r"\s+", " ", value).strip()
        and _term_match(value, matched_term)
        for value in _value_at_path(record, field_path)
    )


def validate_context_package(package: dict[str, object], *, verify_hash: bool = True) -> None:
    """Validate exported snapshot consistency, not the producer's source database.

    Source-record and fulltext links are re-queried only by build_context_package.
    Downstream validation checks the exported IDs, receipts, basis data, and
    internal hash. Authenticating the snapshot requires a publisher-pinned
    content_sha256 outside this standalone validator.
    """
    if package.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise ValueError(f"context package schema_version must be {PACKAGE_SCHEMA_VERSION}")
    if package.get("validation_contract") != VALIDATION_CONTRACT:
        raise ValueError("context package validation_contract is invalid")
    _require_string(package.get("package_version"), "context package package_version")
    domains = set(_require_string_list(package.get("knowledge_domains"), "context package knowledge_domains"))
    program_records = package.get("program_records")
    evidence_records = package.get("evidence_records")
    contexts = package.get("contexts")
    selector_results = package.get("selector_results")
    gaps = package.get("gaps")
    for label, values in (
        ("program_records", program_records),
        ("evidence_records", evidence_records),
        ("contexts", contexts),
        ("selector_results", selector_results),
        ("gaps", gaps),
    ):
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            raise ValueError(f"context package {label} must be a list of objects")
    _unique(contexts, "id", "contexts")
    _unique(program_records, "record_id", "program_records")
    _unique(evidence_records, "record_id", "evidence_records")

    for record in program_records:
        _validate_public_provenance(record, f"program record {record.get('record_id')}")
    species_profiles = _species_profiles(program_records)

    context_by_id = {str(context["id"]): context for context in contexts}
    for context_id, context in context_by_id.items():
        species_ids, required_domains = _validate_generic_context(
            context,
            context_id=context_id,
            expected_fields=EXPORTED_CONTEXT_FIELDS,
        )
        for species_id in species_ids:
            if species_id not in species_profiles:
                raise ValueError(f"context {context_id} names unknown species: {species_id}")
        unknown_domains = required_domains - domains
        if unknown_domains:
            raise ValueError(f"context {context_id} names unknown knowledge domains: {sorted(unknown_domains)}")
        _validate_public_provenance(context, f"context {context_id}")

    selector_receipts: dict[str, dict[str, object]] = {}
    selected_record_species: dict[str, str] = {}
    receipts_by_record: dict[str, list[dict[str, object]]] = {}
    selector_keys: list[str] = []
    for result in selector_results:
        selector_id = _require_string(result.get("selector_id"), "selector result selector_id")
        selector_keys.append(selector_id)
        context_id = _require_string(result.get("context_id"), f"selector {selector_id} context_id")
        species_id = _require_string(result.get("species_id"), f"selector {selector_id} species_id")
        if context_id not in context_by_id:
            raise ValueError(f"selector {selector_id} names unknown context: {context_id}")
        if species_id not in species_profiles:
            raise ValueError(f"selector {selector_id} names unknown species: {species_id}")
        if species_id not in context_by_id[context_id]["species_ids"]:
            raise ValueError(f"selector {selector_id} species is not supported by context {context_id}")
        scientific_name = _require_string(
            result.get("scientific_name"),
            f"selector {selector_id} scientific_name",
        )
        if scientific_name != species_profiles[species_id]["scientific_name"]:
            raise ValueError(f"selector {selector_id} scientific_name does not match its species profile")

        selector_contract = {
            field: result.get(field)
            for field in SELECTOR_REQUIRED_FIELDS | SELECTOR_OPTIONAL_FIELDS
        }
        selector_contract["id"] = selector_id
        for optional_field in SELECTOR_OPTIONAL_FIELDS:
            if selector_contract.get(optional_field) is None:
                selector_contract.pop(optional_field)
        _validate_selector(selector_contract, selector_id=selector_id)

        limit = result.get("limit")
        candidate_count = result.get("candidate_count")
        eligible_count = result.get("eligible_count")
        count = result.get("selected_count")
        ids = result.get("selected_record_ids")
        rejection_counts = result.get("rejection_counts")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SELECTOR_LIMIT:
            raise ValueError(f"selector {selector_id} has invalid limit")
        if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 0:
            raise ValueError(f"selector {selector_id} has invalid candidate_count")
        if isinstance(eligible_count, bool) or not isinstance(eligible_count, int) or eligible_count < 0:
            raise ValueError(f"selector {selector_id} has invalid eligible_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > limit:
            raise ValueError(f"selector {selector_id} selected_count exceeds its limit")
        if (
            not isinstance(ids, list)
            or len(ids) != count
            or len(ids) != len(set(ids))
            or not all(isinstance(item, str) and item for item in ids)
        ):
            raise ValueError(f"selector {selector_id} selected_record_ids do not match selected_count")
        if count > eligible_count:
            raise ValueError(f"selector {selector_id} selected_count exceeds eligible_count")
        if not isinstance(rejection_counts, dict):
            raise ValueError(f"selector {selector_id} rejection_counts must be an object")
        rejection_total = 0
        for reason, rejection_count in rejection_counts.items():
            if reason not in ELIGIBILITY_REJECTION_REASONS:
                raise ValueError(f"selector {selector_id} has unknown rejection reason: {reason}")
            if isinstance(rejection_count, bool) or not isinstance(rejection_count, int) or rejection_count <= 0:
                raise ValueError(f"selector {selector_id} has invalid rejection count for {reason}")
            rejection_total += rejection_count
        if candidate_count != eligible_count + rejection_total:
            raise ValueError(f"selector {selector_id} rejection_counts are incomplete")

        selector_receipts[selector_id] = result
        for record_id in ids:
            owner = selected_record_species.get(record_id)
            if owner and owner != species_id:
                raise ValueError(f"record {record_id} is assigned to more than one species")
            selected_record_species[record_id] = species_id
            receipts_by_record.setdefault(record_id, []).append(result)
    if len(selector_keys) != len(set(selector_keys)):
        raise ValueError("selector results must have unique selector ids")

    evidence_by_id = {str(record["record_id"]): record for record in evidence_records}
    for result in selector_results:
        selector_id = str(result["selector_id"])
        for record_id in result["selected_record_ids"]:
            if record_id not in evidence_by_id:
                raise ValueError(f"selector {selector_id} selects missing evidence record {record_id}")

    for record in evidence_records:
        record_id = str(record["record_id"])
        _validate_public_provenance(record, f"evidence record {record_id}")
        species_id = _require_string(record.get("species_id"), f"evidence record {record_id} species_id")
        profile = species_profiles.get(species_id)
        if profile is None:
            raise ValueError(f"evidence record {record_id} names unknown species: {species_id}")
        scientific_name = str(profile["scientific_name"])
        if record.get("species") != scientific_name:
            raise ValueError(f"evidence record {record_id} is not exact-species evidence for {scientific_name}")
        if selected_record_species.get(record_id) != species_id:
            raise ValueError(f"evidence record {record_id} is not backed by a selector result")
        context_ids = _require_string_list(record.get("context_ids"), f"evidence record {record_id} context_ids")
        selector_ids = _require_string_list(record.get("selector_ids"), f"evidence record {record_id} selector_ids")
        selecting_receipts = receipts_by_record.get(record_id, [])
        expected_selector_ids = [str(receipt["selector_id"]) for receipt in selecting_receipts]
        expected_context_ids = list(
            dict.fromkeys(str(receipt["context_id"]) for receipt in selecting_receipts)
        )
        if selector_ids != expected_selector_ids:
            raise ValueError(
                f"evidence record {record_id} selector_ids do not exactly match selecting receipts"
            )
        if context_ids != expected_context_ids:
            raise ValueError(
                f"evidence record {record_id} context_ids do not exactly match selecting receipts"
            )
        if any(context_id not in context_by_id for context_id in context_ids):
            raise ValueError(f"evidence record {record_id} names an unknown context")
        if any(selector_id not in selector_receipts for selector_id in selector_ids):
            raise ValueError(f"evidence record {record_id} names an unknown selector")

        receipt_contexts: list[str] = []
        for selector_id in selector_ids:
            receipt = selector_receipts[selector_id]
            if record_id not in receipt["selected_record_ids"]:
                raise ValueError(f"evidence record {record_id} is not selected by receipt {selector_id}")
            if receipt["species_id"] != species_id:
                raise ValueError(f"evidence record {record_id} selector species does not match")
            receipt_contexts.append(str(receipt["context_id"]))
        if set(context_ids) != set(receipt_contexts):
            raise ValueError(f"evidence record {record_id} contexts do not match selector receipts")

        eligibility = record.get("eligibility")
        if not isinstance(eligibility, dict):
            raise ValueError(f"evidence record {record_id} is missing eligibility")
        if eligibility.get("ruleset_version") != ELIGIBILITY_RULESET_VERSION:
            raise ValueError(f"evidence record {record_id} has an invalid eligibility ruleset_version")

        taxon = eligibility.get("taxon")
        if not isinstance(taxon, dict) or taxon.get("status") != "direct_focal_taxon":
            raise ValueError(f"evidence record {record_id} taxon assertion is not direct")
        if taxon.get("species_id") != species_id or taxon.get("scientific_name") != scientific_name:
            raise ValueError(f"evidence record {record_id} taxon assertion disagrees with selector receipt")
        taxon_basis = _validate_assertion_basis(
            taxon.get("basis"),
            label=f"evidence record {record_id} taxon assertion",
        )
        direct_taxon_terms = {str(term).casefold() for term in profile["taxon_terms"]}
        taxon_basis_selectors: set[str] = set()
        for basis in taxon_basis:
            selector_id = str(basis["selector_id"])
            receipt = selector_receipts.get(selector_id)
            if receipt is None or record_id not in receipt["selected_record_ids"]:
                raise ValueError(f"evidence record {record_id} taxon basis names an invalid selector")
            matched_term = str(basis["matched_term"])
            if matched_term.casefold() not in direct_taxon_terms:
                raise ValueError(f"evidence record {record_id} taxon basis uses an ambiguous alias")
            field_path = str(basis["field_path"])
            retained_store = str(basis["retained_store"])
            retained_source = str(basis["retained_source"])
            retained_path = str(basis["retained_path"])
            snapshot = str(basis["evidence_snapshot"])
            if field_path.startswith("parent."):
                parent = receipt.get("parent_record")
                parent_path = field_path.removeprefix("parent.")
                if not isinstance(parent, dict) or parent_path not in parent.get("taxon_field_paths", []):
                    raise ValueError(f"evidence record {record_id} taxon basis field_path is not trusted")
                parent_record_id = _require_string(
                    basis.get("parent_record_id"),
                    f"evidence record {record_id} taxon basis parent_record_id",
                )
                linked_parent_ids = _value_at_path(record, str(parent["record_id_path"]))
                if parent_record_id not in linked_parent_ids:
                    raise ValueError(
                        f"evidence record {record_id} taxon basis parent_record_id is not linked"
                    )
                if retained_store != "record_payloads":
                    raise ValueError(f"evidence record {record_id} taxon basis retained_store is invalid")
                if retained_path != parent_path:
                    raise ValueError(f"evidence record {record_id} taxon basis retained_path is invalid")
            else:
                if field_path not in receipt["taxon_field_paths"]:
                    raise ValueError(f"evidence record {record_id} taxon basis field_path is not trusted")
                if retained_store != "record_payloads":
                    raise ValueError(f"evidence record {record_id} taxon basis retained_store is invalid")
                if retained_source != record.get("source"):
                    raise ValueError(f"evidence record {record_id} taxon basis retained_source is invalid")
                if retained_path != field_path:
                    raise ValueError(f"evidence record {record_id} taxon basis retained_path is invalid")
                if not _record_snapshot_matches(record, field_path, snapshot, matched_term):
                    raise ValueError(f"evidence record {record_id} taxon basis is not present in its field")
            taxon_basis_selectors.add(selector_id)
        if set(selector_ids) != taxon_basis_selectors:
            raise ValueError(f"evidence record {record_id} taxon assertion is missing selector basis")

        context = eligibility.get("context")
        if not isinstance(context, dict) or context.get("status") != "direct_context":
            raise ValueError(f"evidence record {record_id} context assertion is not direct")
        asserted_context_ids = _require_string_list(
            context.get("context_ids"),
            f"evidence record {record_id} context assertion context_ids",
        )
        if set(asserted_context_ids) != set(context_ids):
            raise ValueError(f"evidence record {record_id} context assertion does not match record contexts")
        context_basis = _validate_assertion_basis(
            context.get("basis"),
            label=f"evidence record {record_id} context assertion",
            require_context=True,
        )
        covered_groups: dict[tuple[str, str], set[int]] = {}
        for basis in context_basis:
            selector_id = str(basis["selector_id"])
            context_id = str(basis["context_id"])
            receipt = selector_receipts.get(selector_id)
            if receipt is None or record_id not in receipt["selected_record_ids"]:
                raise ValueError(f"evidence record {record_id} context basis names an invalid selector")
            if receipt["context_id"] != context_id:
                raise ValueError(f"evidence record {record_id} context basis disagrees with selector receipt")
            field_path = str(basis["field_path"])
            matched_term = str(basis["matched_term"])
            snapshot = str(basis["evidence_snapshot"])
            retained_store = str(basis["retained_store"])
            retained_source = str(basis["retained_source"])
            retained_path = str(basis["retained_path"])
            required_groups = [
                [str(term) for term in group]
                for group in receipt["context_required_term_groups"]
            ]
            matching_groups = {
                index
                for index, terms in enumerate(required_groups)
                if matched_term.casefold() in {term.casefold() for term in terms}
            }
            if not matching_groups:
                raise ValueError(f"evidence record {record_id} context basis term is not configured")

            if field_path in receipt["context_field_paths"]:
                for prerequisite_path in receipt["context_field_prerequisites"].get(field_path, []):
                    if not _value_at_path(record, str(prerequisite_path)):
                        raise ValueError(f"evidence record {record_id} context basis prerequisite is missing")
                if retained_store != "record_payloads":
                    raise ValueError(f"evidence record {record_id} context basis retained_store is invalid")
                if retained_source != record.get("source"):
                    raise ValueError(f"evidence record {record_id} context basis retained_source is invalid")
                if retained_path != field_path:
                    raise ValueError(f"evidence record {record_id} context basis retained_path is invalid")
                if not _record_snapshot_matches(record, field_path, snapshot, matched_term):
                    raise ValueError(f"evidence record {record_id} context basis is not present in its field")
            else:
                fulltext = receipt.get("fulltext_context")
                if not isinstance(fulltext, dict) or field_path != fulltext.get("text_field_path"):
                    raise ValueError(f"evidence record {record_id} context basis field_path is not trusted")
                fulltext_unit_id = _require_string(
                    basis.get("fulltext_unit_id"),
                    f"evidence record {record_id} context basis fulltext_unit_id",
                )
                parent_record_id = _require_string(
                    basis.get("parent_record_id"),
                    f"evidence record {record_id} context basis parent_record_id",
                )
                if fulltext_unit_id not in _value_at_path(record, str(fulltext["unit_id_path"])):
                    raise ValueError(
                        f"evidence record {record_id} context basis fulltext_unit_id is not linked"
                    )
                if parent_record_id not in _value_at_path(
                    record, str(fulltext["parent_record_id_path"])
                ):
                    raise ValueError(
                        f"evidence record {record_id} context basis parent_record_id is not linked"
                    )
                if retained_store != "literature_fulltext_units":
                    raise ValueError(f"evidence record {record_id} context basis retained_store is invalid")
                if retained_path != field_path:
                    raise ValueError(f"evidence record {record_id} context basis retained_path is invalid")
            covered_groups.setdefault((selector_id, context_id), set()).update(matching_groups)
        for selector_id in selector_ids:
            context_id = str(selector_receipts[selector_id]["context_id"])
            required_count = len(selector_receipts[selector_id]["context_required_term_groups"])
            if covered_groups.get((selector_id, context_id), set()) != set(range(required_count)):
                raise ValueError(
                    f"evidence record {record_id} context assertion is missing basis for "
                    f"{context_id} receipt {selector_id}"
                )

    zero_selected = {
        str(result["selector_id"]): result
        for result in selector_results
        if result["selected_count"] == 0
    }
    gap_selectors: set[str] = set()
    for gap in gaps:
        if gap.get("gap_type") != "selector_no_direct_evidence":
            raise ValueError("context package contains an unsupported selector gap type")
        selector_id = _require_string(gap.get("selector_id"), "selector gap selector_id")
        receipt = zero_selected.get(selector_id)
        if receipt is None or selector_id in gap_selectors:
            raise ValueError(f"selector {selector_id} has an invalid direct-evidence gap")
        gap_receipt = {key: value for key, value in gap.items() if key != "gap_type"}
        if gap_receipt != receipt:
            raise ValueError(f"selector {selector_id} gap receipt does not match selector result")
        gap_selectors.add(selector_id)
    if gap_selectors != set(zero_selected):
        raise ValueError("every empty selector must emit a matching direct-evidence gap receipt")

    if verify_hash:
        expected = canonical_package_hash(package)
        if package.get("content_sha256") != expected:
            raise ValueError("context package content_sha256 does not match canonical content")
