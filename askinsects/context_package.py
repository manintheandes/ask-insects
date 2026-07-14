from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from .builder import DEFAULT_ARTIFACT_DIR


PACKAGE_SCHEMA_VERSION = "ask-insects-context-package.v1"
CONFIG_SCHEMA_VERSION = "ask-insects-context-package-config.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT_CONFIG = REPO_ROOT / "config/ask-monarch-context-package.json"
MAX_SELECTOR_LIMIT = 25
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
        _require_string_list(context.get("species_ids"), f"context {context_id} species_ids")
        _require_string_list(
            context.get("private_assay_families"),
            f"context {context_id} private_assay_families",
        )
        _require_string_list(
            context.get("private_assay_modes", []),
            f"context {context_id} private_assay_modes",
            allow_empty=True,
        )
        required_domains = set(
            _require_string_list(context.get("required_domains"), f"context {context_id} required_domains")
        )
        unknown_domains = required_domains - domains
        if unknown_domains:
            raise ValueError(f"context {context_id} names unknown knowledge domains: {sorted(unknown_domains)}")
        for field in ("measures", "does_not_establish", "plausible_explanations", "discriminating_evidence"):
            _require_string_list(context.get(field), f"context {context_id} {field}")
        selectors = context.get("selectors")
        if not isinstance(selectors, list) or not all(isinstance(item, dict) for item in selectors):
            raise ValueError(f"context {context_id} selectors must be a list of objects")
        for selector_index, selector in enumerate(selectors):
            selector_id = _require_string(
                selector.get("id"),
                f"context {context_id} selectors/{selector_index}/id",
            )
            selector_ids.append(selector_id)
            species_id = _require_string(selector.get("species_id"), f"selector {selector_id} species_id")
            if species_id not in context["species_ids"]:
                raise ValueError(f"selector {selector_id} species_id is not supported by context {context_id}")
            _require_string(selector.get("source"), f"selector {selector_id} source")
            _require_string_list(selector.get("query_any"), f"selector {selector_id} query_any")
            limit = selector.get("limit")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SELECTOR_LIMIT:
                raise ValueError(f"selector {selector_id} limit must be between 1 and {MAX_SELECTOR_LIMIT}")
            if not isinstance(selector.get("required"), bool):
                raise ValueError(f"selector {selector_id} required must be true or false")
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


def _species_profiles(program_records: list[dict[str, object]]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for record in program_records:
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("atom_type") != "species_profile":
            continue
        species_id = _require_string(payload.get("species_id"), "species profile species_id")
        scientific_name = _require_string(payload.get("scientific_name"), f"species {species_id} scientific_name")
        if species_id in profiles:
            raise ValueError(f"duplicate species profile: {species_id}")
        profiles[species_id] = scientific_name
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
            int(selector["limit"]),
        )
        for selector in selectors
    ]
    score_buckets: dict[str, dict[int, list[str]]] = {
        selector_id: {} for selector_id, _, _ in prepared
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
        for selector_id, terms, limit in prepared:
            score = sum(term in haystack for term in terms)
            if not score:
                continue
            bucket = score_buckets[selector_id].setdefault(score, [])
            if len(bucket) < limit:
                bucket.append(record_id)

    selected: dict[str, list[str]] = {}
    for selector_id, _, limit in prepared:
        record_ids: list[str] = []
        for score in sorted(score_buckets[selector_id], reverse=True):
            record_ids.extend(score_buckets[selector_id][score])
            if len(record_ids) >= limit:
                break
        selected[selector_id] = record_ids[:limit]
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


def _context_export(context: dict[str, object], *, index: int, config: dict[str, object]) -> dict[str, object]:
    last_reviewed = _require_string(config.get("last_reviewed"), "context config last_reviewed")
    exported = {key: deepcopy(value) for key, value in context.items() if key != "selectors"}
    exported["provenance"] = {
        "source_id": "ask_insects_context_config",
        "locator": f"config/ask-monarch-context-package.json#contexts/{index}",
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
                selector_jobs.append(
                    {
                        "context_id": context_id,
                        "selector": selector,
                        "species_id": species_id,
                        "scientific_name": species_profiles[species_id],
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
            rows = [records_by_id[record_id] for record_id in selected_ids[selector_id]]
            result = {
                "context_id": context_id,
                "selector_id": selector_id,
                "species_id": species_id,
                "scientific_name": scientific_name,
                "source": selector["source"],
                "query_any": selector["query_any"],
                "limit": selector["limit"],
                "required": selector["required"],
                "selected_count": len(rows),
                "selected_record_ids": [row["record_id"] for row in rows],
            }
            selector_results.append(result)
            if not rows:
                gaps.append(
                    {
                        "gap_type": "selector_no_exact_species_records",
                        **result,
                    }
                )
            for row in rows:
                record_id = str(row["record_id"])
                existing = selected_by_id.get(record_id)
                if existing is None:
                    row["species_id"] = species_id
                    row["context_ids"] = [context_id]
                    row["selector_ids"] = [selector_id]
                    selected_by_id[record_id] = row
                else:
                    if existing["species_id"] != species_id:
                        raise ValueError(f"record {record_id} was selected for more than one species")
                    if context_id not in existing["context_ids"]:
                        existing["context_ids"].append(context_id)
                    if selector_id not in existing["selector_ids"]:
                        existing["selector_ids"].append(selector_id)
        evidence_records = [selected_by_id[key] for key in sorted(selected_by_id)]
    finally:
        conn.close()

    package: dict[str, object] = {
        "ok": True,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_version": config["package_version"],
        "generated_at": generated_at or utc_now(),
        "objective": config["objective"],
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


def validate_context_package(package: dict[str, object], *, verify_hash: bool = True) -> None:
    if package.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise ValueError(f"context package schema_version must be {PACKAGE_SCHEMA_VERSION}")
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

    species_profiles: dict[str, str] = {}
    for record in program_records:
        _validate_public_provenance(record, f"program record {record.get('record_id')}")
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("atom_type") == "species_profile":
            species_id = _require_string(payload.get("species_id"), "species profile species_id")
            scientific_name = _require_string(payload.get("scientific_name"), f"species {species_id} scientific_name")
            if species_id in species_profiles:
                raise ValueError(f"duplicate species profile: {species_id}")
            species_profiles[species_id] = scientific_name
    if not species_profiles:
        raise ValueError("context package has no species profiles")

    context_by_id = {str(context["id"]): context for context in contexts}
    for context_id, context in context_by_id.items():
        for species_id in _require_string_list(context.get("species_ids"), f"context {context_id} species_ids"):
            if species_id not in species_profiles:
                raise ValueError(f"context {context_id} names unknown species: {species_id}")
        unknown_domains = set(
            _require_string_list(context.get("required_domains"), f"context {context_id} required_domains")
        ) - domains
        if unknown_domains:
            raise ValueError(f"context {context_id} names unknown knowledge domains: {sorted(unknown_domains)}")
        _validate_public_provenance(context, f"context {context_id}")

    selector_species: dict[str, str] = {}
    selected_record_species: dict[str, str] = {}
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
        limit = result.get("limit")
        count = result.get("selected_count")
        ids = result.get("selected_record_ids")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SELECTOR_LIMIT:
            raise ValueError(f"selector {selector_id} has invalid limit")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > limit:
            raise ValueError(f"selector {selector_id} selected_count exceeds its limit")
        if not isinstance(ids, list) or len(ids) != count or not all(isinstance(item, str) for item in ids):
            raise ValueError(f"selector {selector_id} selected_record_ids do not match selected_count")
        selector_species[selector_id] = species_id
        for record_id in ids:
            owner = selected_record_species.get(record_id)
            if owner and owner != species_id:
                raise ValueError(f"record {record_id} is assigned to more than one species")
            selected_record_species[record_id] = species_id
    if len(selector_keys) != len(set(selector_keys)):
        raise ValueError("selector results must have unique selector ids")

    for record in evidence_records:
        record_id = str(record["record_id"])
        _validate_public_provenance(record, f"evidence record {record_id}")
        species_id = _require_string(record.get("species_id"), f"evidence record {record_id} species_id")
        scientific_name = species_profiles.get(species_id)
        if scientific_name is None:
            raise ValueError(f"evidence record {record_id} names unknown species: {species_id}")
        if record.get("species") != scientific_name:
            raise ValueError(f"evidence record {record_id} is not exact-species evidence for {scientific_name}")
        if selected_record_species.get(record_id) != species_id:
            raise ValueError(f"evidence record {record_id} is not backed by a selector result")
        context_ids = _require_string_list(record.get("context_ids"), f"evidence record {record_id} context_ids")
        selector_ids = _require_string_list(record.get("selector_ids"), f"evidence record {record_id} selector_ids")
        if any(context_id not in context_by_id for context_id in context_ids):
            raise ValueError(f"evidence record {record_id} names an unknown context")
        if any(selector_id not in selector_species for selector_id in selector_ids):
            raise ValueError(f"evidence record {record_id} names an unknown selector")

    if verify_hash:
        expected = canonical_package_hash(package)
        if package.get("content_sha256") != expected:
            raise ValueError("context package content_sha256 does not match canonical content")
