from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .builder import DEFAULT_ARTIFACT_DIR
from .sources.literature import abstract_from_inverted_index


PACKAGE_SCHEMA_VERSION = "ask-insects-evidence-package.v2"
CONFIG_SCHEMA_VERSION = "ask-insects-evidence-package-config.v2"
ELIGIBILITY_RULESET_VERSION = "direct-semantic-evidence.v2"
VALIDATION_CONTRACT = {
    "producer_linkage": (
        "status_record_count_selected_rows_and_links_verified_in_read_only_source_index"
    ),
    "downstream_validation": "exported_snapshot_internal_consistency_only",
    "snapshot_authentication": "publisher_pinned_content_sha256",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT_CONFIG = REPO_ROOT / "config/insect-evidence-package.json"
MAX_SELECTOR_LIMIT = 25
MAX_SELECTOR_CANDIDATE_FRONTIER = 2_000
MAX_LINKED_RECORD_IDS = 16
REQUIRED_SOURCE_TABLES = frozenset(
    {"records", "record_payloads", "literature_fulltext_units"}
)
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_STRING_LENGTH = 100_000
MAX_LIST_ITEMS = 10_000
MAX_NESTING_DEPTH = 20
PUBLIC_PROGRAM_CONFIG_URL = (
    "https://raw.githubusercontent.com/manintheandes/ask-insects/"
    "175605e32adb6aea14a4664b75e913042d748055/"
    "config/insect-intelligence-programs.json"
)
PUBLIC_CONTEXT_CONFIG_URL = (
    "https://raw.githubusercontent.com/manintheandes/ask-insects/"
    "175605e32adb6aea14a4664b75e913042d748055/"
    "config/insect-evidence-package.json"
)
PACKAGE_FIELDS = frozenset(
    {
        "ok",
        "schema_version",
        "package_version",
        "generated_at",
        "objective",
        "validation_contract",
        "knowledge_domains",
        "upstream_snapshot",
        "contexts",
        "program_records",
        "evidence_records",
        "selector_results",
        "gaps",
        "content_sha256",
    }
)
UPSTREAM_SNAPSHOT_FIELDS = frozenset(
    {
        "source_id",
        "source_status_sha256",
        "source_status_generated_at",
        "record_count",
    }
)
PROGRAM_RECORD_FIELDS = frozenset(
    {"record_id", "lane", "source", "title", "text", "species", "payload", "provenance"}
)
EVIDENCE_RECORD_FIELDS = PROGRAM_RECORD_FIELDS | {
    "species_id",
    "context_ids",
    "selector_ids",
    "eligibility",
}
PUBLIC_PROVENANCE_FIELDS = frozenset(
    {"source_id", "locator", "index_record_id", "retrieved_at", "license"}
)
SELECTOR_RESULT_FIELDS = frozenset(
    {
        "context_id",
        "selector_id",
        "species_id",
        "scientific_name",
        "source",
        "query_any",
        "context_required_term_groups",
        "taxon_field_paths",
        "context_field_paths",
        "context_field_prerequisites",
        "parent_record",
        "fulltext_context",
        "record_requirements",
        "limit",
        "required",
        "candidate_count",
        "eligible_count",
        "selected_count",
        "selected_record_ids",
        "rejection_counts",
    }
)
GAP_FIELDS = SELECTOR_RESULT_FIELDS | {"gap_type"}
ELIGIBILITY_FIELDS = frozenset({"ruleset_version", "taxon", "context"})
TAXON_ASSERTION_FIELDS = frozenset({"status", "basis", "species_id", "scientific_name"})
CONTEXT_ASSERTION_FIELDS = frozenset({"status", "basis", "context_ids"})
ASSERTION_BASIS_FIELDS = frozenset(
    {
        "field_path",
        "matched_term",
        "excerpt",
        "retained_source",
        "retained_store",
        "retained_path",
        "evidence_snapshot",
        "evidence_sha256",
        "selector_id",
        "provenance",
    }
)
ASSERTION_BASIS_LINK_FIELDS = frozenset(
    {"context_id", "parent_record_id", "fulltext_unit_id"}
)
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
        "public_provenance_missing",
        "invalid_candidate_shape",
        "unsafe_export_boundary",
    }
)
SAFE_LOCATOR_FRAGMENT_RE = re.compile(
    r"^(?:row|page|cell|sheet|result|works|jsonpath)(?:$|[/=:.\[])",
    flags=re.IGNORECASE,
)
DOI_RE = re.compile(r"^(?:doi:\s*)?(10\.\d{4,9}/\S+)$", flags=re.IGNORECASE)
NON_HTTPS_AUTHORITY_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])(?!https://)[A-Za-z][A-Za-z0-9+.-]*://",
    flags=re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
POSIX_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:/])/(?!/)[A-Za-z0-9._~-]+(?:/[^\s,;)\]}\"']+)+"
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"']+"
)
CREDENTIAL_KEY_TOKENS = frozenset(
    {
        "apikey",
        "auth",
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "passwd",
        "password",
        "secret",
        "token",
    }
)
QUERY_CREDENTIAL_KEY_TOKENS = frozenset(
    {"key", "session", "sig", "signature"}
)
CONSUMER_KEY_TOKENS = frozenset({"consumer", "customer", "private", "tenant"})
PRIVATE_DNS_SUFFIXES = (".internal", ".local", ".localhost", ".home.arpa")
PRIVATE_DNS_NAME_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9-])(?:localhost|"
    r"(?:[A-Za-z0-9-]+\.)+(?:internal|local|localhost)|"
    r"(?:[A-Za-z0-9-]+\.)*home\.arpa)(?![A-Za-z0-9-])"
)
IPV4_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![A-Za-z0-9.])")
IPV6_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9:])\[?[0-9A-Fa-f:]*:[0-9A-Fa-f:]+\]?(?![A-Za-z0-9:])"
)
SECRET_VALUE_RE = r"[A-Za-z0-9._~+/=-]{12,}"
STANDALONE_CREDENTIAL_RE = re.compile(
    rf"(?ix)(?:"
    rf"\bauthorization\s*[:=]\s*(?:bearer|basic|token)\s+{SECRET_VALUE_RE}|"
    rf"\b(?:bearer|basic)\s+{SECRET_VALUE_RE}|"
    rf"\b(?:api[ _-]?key|access[ _-]?token|auth[ _-]?token|password|secret|token)"
    rf"\s*[:=]\s*[\"']?{SECRET_VALUE_RE}|"
    rf"\bsk-[A-Za-z0-9_-]{{16,}}|"
    rf"\bgh[pousr]_[A-Za-z0-9]{{20,}}|"
    rf"\bxox[baprs]-[A-Za-z0-9-]{{16,}}|"
    rf"\bAKIA[0-9A-Z]{{16}}|"
    rf"\bAIza[0-9A-Za-z_-]{{20,}}"
    rf")"
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_package_hash(package: dict[str, object]) -> str:
    payload = deepcopy(package)
    payload.pop("generated_at", None)
    payload.pop("content_sha256", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _key_tokens(key: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [token for token in re.split(r"[^A-Za-z0-9]+", expanded.casefold()) if token]


def _is_credential_key(key: str) -> bool:
    if key.casefold() == "snapshot_authentication":
        return False
    tokens = _key_tokens(key)
    if any(token in CREDENTIAL_KEY_TOKENS for token in tokens):
        return True
    return any(left == "api" and right == "key" for left, right in zip(tokens, tokens[1:]))


def _is_consumer_key(key: str) -> bool:
    return bool(set(_key_tokens(key)).intersection(CONSUMER_KEY_TOKENS))


def _is_credential_query_key(key: str) -> bool:
    return _is_credential_key(key) or bool(
        set(_key_tokens(key)).intersection(QUERY_CREDENTIAL_KEY_TOKENS)
    )


def _is_machine_bookkeeping_key(key: str) -> bool:
    tokens = set(_key_tokens(key))
    if key.casefold() in {"payload_json", "provenance_json"}:
        return True
    if "path" in tokens and tokens.intersection(
        {"artifact", "cache", "ledger", "local", "machine", "raw"}
    ):
        return True
    return bool(
        tokens.intersection({"original", "raw", "internal"})
        and tokens.intersection({"payload", "provenance"})
    )


def _is_unsafe_key(key: str) -> bool:
    return _is_credential_key(key) or _is_consumer_key(key) or _is_machine_bookkeeping_key(key)


def _url_has_credentials(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        return True
    return any(
        _is_credential_query_key(key)
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _is_public_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.rstrip(".").casefold()
    if (
        normalized in {"localhost", "home.arpa"}
        or normalized.endswith(PRIVATE_DNS_SUFFIXES)
    ):
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return True
    return address.is_global


def _string_has_credentials(value: str) -> bool:
    if STANDALONE_CREDENTIAL_RE.search(value):
        return True
    for match in URL_RE.finditer(value):
        if _url_has_credentials(match.group(0).rstrip(".,);]")):
            return True
    return False


def _string_has_private_network_reference(value: str) -> bool:
    if PRIVATE_DNS_NAME_RE.search(value):
        return True
    for match in URL_RE.finditer(value):
        candidate = match.group(0).rstrip(".,);]")
        parsed = urlsplit(candidate)
        if parsed.hostname and not _is_public_hostname(parsed.hostname):
            return True
    for match in IPV4_LITERAL_RE.finditer(value):
        try:
            address = ipaddress.ip_address(match.group(0))
        except ValueError:
            continue
        if not address.is_global:
            return True
    for match in IPV6_LITERAL_RE.finditer(value):
        candidate = match.group(0).strip("[]")
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not address.is_global:
            return True
    return False


def _unsafe_string_reason(value: str) -> str | None:
    if _string_has_credentials(value):
        return "credential or credentialed URL"
    if NON_HTTPS_AUTHORITY_RE.search(value) or re.search(
        r"(?i)(?<![A-Za-z0-9+.-])file:/", value
    ):
        return "non-HTTPS or private scheme"
    if _string_has_private_network_reference(value):
        return "private network reference"
    if POSIX_ABSOLUTE_PATH_RE.search(value):
        return "absolute POSIX path"
    if WINDOWS_ABSOLUTE_PATH_RE.search(value):
        return "absolute Windows path"
    return None


def _validate_recursive_boundary(value: object, *, label: str, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(f"{label} exceeds maximum nesting depth {MAX_NESTING_DEPTH}")
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise ValueError(f"{label} contains a string longer than {MAX_STRING_LENGTH} characters")
        reason = _unsafe_string_reason(value)
        if reason == "credential or credentialed URL":
            raise ValueError(f"{label} contains URL credentials")
        if reason is not None:
            raise ValueError(f"{label} contains an unsafe value ({reason})")
        return
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError(f"{label} contains a list longer than {MAX_LIST_ITEMS} items")
        for index, item in enumerate(value):
            _validate_recursive_boundary(item, label=f"{label}/{index}", depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} contains a non-string object key")
            if len(key) > MAX_STRING_LENGTH:
                raise ValueError(f"{label} contains a key longer than {MAX_STRING_LENGTH} characters")
            if _is_unsafe_key(key):
                raise ValueError(f"{label} contains unsafe key: {key}")
            _validate_recursive_boundary(item, label=f"{label}/{key}", depth=depth + 1)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite float")
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError(f"{label} contains an unsupported value type: {type(value).__name__}")


def _require_exact_fields(
    value: object, expected: frozenset[str], *, label: str
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unsupported = set(value) - expected
    if unsupported:
        raise ValueError(f"{label} contains unsupported fields: {sorted(unsupported)}")
    missing = expected - set(value)
    if missing:
        raise ValueError(f"{label} is missing fields: {sorted(missing)}")
    return value


def _safe_locator_fragment(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    fragment = value.removeprefix("#").strip()
    if not fragment or len(fragment) > MAX_STRING_LENGTH:
        return None
    if SAFE_LOCATOR_FRAGMENT_RE.match(fragment) is None:
        return None
    if _unsafe_string_reason(fragment) is not None:
        return None
    fragment_keys = re.findall(r"(?:^|[?&;/])([A-Za-z0-9_.-]+)=", fragment)
    if any(_is_credential_query_key(key) for key in fragment_keys):
        return None
    return fragment


def _public_source_base(value: object) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("record provenance requires a public HTTPS source_url")
    source_url = value.strip()
    doi_match = DOI_RE.fullmatch(source_url)
    if doi_match is not None:
        return f"https://doi.org/{doi_match.group(1)}", None

    parsed = urlsplit(source_url)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or not _is_public_hostname(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or any(
            _is_credential_query_key(key)
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        )
    ):
        raise ValueError("record provenance requires a public HTTPS source_url without credentials")
    base = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))
    return base, _safe_locator_fragment(parsed.fragment)


def _public_provenance(record: dict[str, object]) -> dict[str, object]:
    """Return source id, stable public locator, record id, retrieval time, and license."""
    raw = record.get("provenance")
    if not isinstance(raw, dict):
        raise ValueError("record is missing source provenance")
    source_id = _require_string(raw.get("source_id"), "record provenance source_id")
    record_id = _require_string(record.get("record_id"), "record record_id")
    retrieved_at = _require_string(raw.get("retrieved_at"), "record provenance retrieved_at")
    base, source_fragment = _public_source_base(raw.get("source_url"))
    indexed_locator = raw.get("locator")
    indexed_fragment = None
    if isinstance(indexed_locator, str) and "#" in indexed_locator:
        indexed_fragment = _safe_locator_fragment(indexed_locator.split("#", 1)[1])
    fragment = indexed_fragment or source_fragment
    locator = f"{base}#{fragment}" if fragment else base
    license_value = raw.get("license")
    if license_value is not None:
        license_value = _require_string(license_value, "record provenance license")
    public = {
        "source_id": source_id,
        "locator": locator,
        "index_record_id": record_id,
        "retrieved_at": retrieved_at,
        "license": license_value,
    }
    _validate_recursive_boundary(public, label="public provenance")
    return public


def _contributing_public_provenance(
    record: dict[str, object], *, expected_source: str
) -> dict[str, object]:
    provenance = _public_provenance(record)
    if provenance["source_id"] != expected_source:
        raise ValueError("contributing row provenance source_id does not match its source")
    return provenance


def _sanitize_program_payload(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _sanitize_program_payload(item)
            for key, item in value.items()
            if isinstance(key, str) and not _is_unsafe_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_program_payload(item) for item in value]
    return deepcopy(value)


def _public_program_record(record: dict[str, object]) -> dict[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"program record {record.get('record_id')} payload must be an object")
    provenance_record = deepcopy(record)
    provenance = provenance_record.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(f"program record {record.get('record_id')} is missing provenance")
    provenance["source_url"] = PUBLIC_PROGRAM_CONFIG_URL
    return {
        key: deepcopy(record.get(key))
        for key in ("record_id", "lane", "source", "title", "text", "species")
    } | {
        "payload": _sanitize_program_payload(payload),
        "provenance": _public_provenance(provenance_record),
    }


def _selector_payload_paths(selector: dict[str, object]) -> set[str]:
    paths = {
        path
        for field in ("taxon_field_paths", "context_field_paths")
        for path in selector.get(field, [])
    }
    prerequisites = selector.get("context_field_prerequisites")
    if isinstance(prerequisites, dict):
        paths.update(
            path
            for prerequisite_paths in prerequisites.values()
            if isinstance(prerequisite_paths, list)
            for path in prerequisite_paths
        )
    parent = selector.get("parent_record")
    if isinstance(parent, dict):
        paths.add(parent["record_id_path"])
    fulltext = selector.get("fulltext_context")
    if isinstance(fulltext, dict):
        paths.update(
            {
                fulltext["unit_id_path"],
                fulltext["parent_record_id_path"],
            }
        )
    requirements = selector.get("record_requirements")
    if isinstance(requirements, dict):
        paths.update(requirements)
    return {path for path in paths if path.startswith("payload.")}


def _copy_record_path(record: dict[str, object], path: str, target: dict[str, object]) -> None:
    parts = path.split(".")
    current: object = record
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]

    output_parts = parts[1:]
    if not output_parts:
        return
    output = target
    for part in output_parts[:-1]:
        existing = output.get(part)
        if not isinstance(existing, dict):
            existing = {}
            output[part] = existing
        output = existing
    output[output_parts[-1]] = deepcopy(current)


def _minimal_evidence_payload(
    record: dict[str, object], selectors: list[dict[str, object]]
) -> dict[str, object]:
    payload: dict[str, object] = {}
    paths = sorted({path for selector in selectors for path in _selector_payload_paths(selector)})
    for path in paths:
        _copy_record_path(record, path, payload)
    return payload


def _public_evidence_record(
    record: dict[str, object], selectors: list[dict[str, object]]
) -> dict[str, object]:
    return {
        key: deepcopy(record.get(key))
        for key in (
            "record_id",
            "lane",
            "source",
            "title",
            "text",
            "species",
            "species_id",
            "context_ids",
            "selector_ids",
            "eligibility",
        )
    } | {
        "payload": _minimal_evidence_payload(record, selectors),
        "provenance": _public_provenance(record),
    }


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


def _raw_values_at_path(record: dict[str, object], path: str) -> list[object]:
    values: list[object] = [record]
    for part in path.split("."):
        next_values: list[object] = []
        for value in values:
            if isinstance(value, dict) and part in value:
                next_values.append(value[part])
            elif isinstance(value, list):
                next_values.extend(
                    item[part]
                    for item in value
                    if isinstance(item, dict) and part in item
                )
        values = next_values
        if not values:
            return []
    return values


def _path_is_present(record: dict[str, object], path: str) -> bool:
    return bool(_raw_values_at_path(record, path))


def _identifier_values_at_path(
    record: dict[str, object], path: str
) -> list[str] | None:
    raw_values = _raw_values_at_path(record, path)
    flattened: list[object] = []
    for value in raw_values:
        if isinstance(value, list):
            flattened.extend(value)
        else:
            flattened.append(value)
    if not flattened:
        return []
    if not all(isinstance(value, str) and value.strip() for value in flattened):
        return None
    return [value.strip() for value in flattened if isinstance(value, str)]


def _trusted_semantic_values(
    record: dict[str, object],
    field_paths: list[str],
    *,
    provenance: dict[str, object],
    field_prefix: str = "",
    link: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    link_fields = link or {}
    return [
        {
            "field_path": f"{field_prefix}{field_path}",
            "value": value,
            "retained_store": "record_payloads",
            "retained_source": str(record.get("source") or ""),
            "retained_path": field_path,
            "provenance": deepcopy(provenance),
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
    values: list[dict[str, object]], terms: list[str], *, status: str
) -> dict[str, object] | None:
    for semantic_value in values:
        compact = re.sub(r"\s+", " ", str(semantic_value["value"])).strip()
        for term in terms:
            match = _term_match(compact, term)
            if match:
                return {
                    "status": status,
                    "basis": [_assertion_basis(semantic_value, term, match)],
                }
    return None


def _assertion_basis(
    semantic_value: dict[str, object], term: str, match: re.Match[str]
) -> dict[str, object]:
    compact = re.sub(r"\s+", " ", str(semantic_value["value"])).strip()
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
    values: list[dict[str, object]],
    required_groups: list[list[str]],
    *,
    status: str,
) -> dict[str, object] | None:
    basis: list[dict[str, str]] = []
    for terms in required_groups:
        matched_basis: dict[str, object] | None = None
        for semantic_value in values:
            compact = re.sub(r"\s+", " ", str(semantic_value["value"])).strip()
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


def _record_by_id(
    conn: sqlite3.Connection, record_id: str
) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT r.*, p.payload_json
        FROM records AS r
        LEFT JOIN record_payloads AS p ON p.record_id = r.record_id
        WHERE r.record_id = ?
        """,
        (record_id,),
    ).fetchone()
    return _export_record(row) if row is not None else None


def _source_records(
    conn: sqlite3.Connection, source: str
):
    return conn.execute(
        """
        SELECT r.*, p.payload_json
        FROM records AS r INDEXED BY idx_records_source
        LEFT JOIN record_payloads AS p ON p.record_id = r.record_id
        WHERE r.source = ?
        ORDER BY r.record_id
        """,
        (source,),
    )


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


def _fulltext_public_provenance(unit: dict[str, object]) -> dict[str, object]:
    provenance = _json_or_empty(unit.get("provenance_json"))
    if not provenance.get("source_url") and unit.get("url"):
        provenance["source_url"] = unit["url"]
    if provenance.get("license") is None and unit.get("license") is not None:
        provenance["license"] = unit["license"]
    unit_id = _require_string(unit.get("unit_id"), "fulltext unit_id")
    source = _require_string(unit.get("source"), f"fulltext unit {unit_id} source")
    return _contributing_public_provenance(
        {"record_id": unit_id, "provenance": provenance},
        expected_source=source,
    )


def _active_context_field_paths(
    record: dict[str, object], selector: dict[str, object]
) -> list[str]:
    prerequisites = dict(selector["context_field_prerequisites"])
    return [
        field_path
        for field_path in selector["context_field_paths"]
        if all(
            _path_is_present(record, prerequisite_path)
            for prerequisite_path in prerequisites.get(field_path, [])
        )
    ]


def _context_semantic_values(
    record: dict[str, object],
    selector: dict[str, object],
    *,
    provenance: dict[str, object],
) -> list[dict[str, object]]:
    return _trusted_semantic_values(
        record,
        _active_context_field_paths(record, selector),
        provenance=provenance,
    )


def _trusted_candidate_search_values(
    conn: sqlite3.Connection,
    *,
    record: dict[str, object],
    selector: dict[str, object],
) -> tuple[list[str], bool]:
    values = [
        value
        for field_path in [
            *selector["taxon_field_paths"],
            *_active_context_field_paths(record, selector),
        ]
        for value in _value_at_path(record, field_path)
    ]
    reference_paths: list[str] = []

    parent = selector.get("parent_record")
    if isinstance(parent, dict):
        parent_id_path = parent["record_id_path"]
        reference_paths.append(parent_id_path)
        parent_ids = _identifier_values_at_path(record, parent_id_path)
        if parent_ids is not None:
            for parent_id in parent_ids[:MAX_LINKED_RECORD_IDS]:
                parent_record = _record_by_id(conn, parent_id)
                if parent_record is None:
                    continue
                for field_path in parent["taxon_field_paths"]:
                    values.extend(_value_at_path(parent_record, field_path))

    fulltext = selector.get("fulltext_context")
    if isinstance(fulltext, dict):
        unit_id_path = fulltext["unit_id_path"]
        parent_id_path = fulltext["parent_record_id_path"]
        reference_paths.extend([unit_id_path, parent_id_path])
        unit_ids = _identifier_values_at_path(record, unit_id_path)
        parent_ids = _identifier_values_at_path(record, parent_id_path)
        if unit_ids is not None and parent_ids is not None and len(unit_ids) == len(parent_ids) == 1:
            unit = _fulltext_unit_by_id(conn, unit_ids[0])
            if unit is not None and unit.get("record_id") == parent_ids[0]:
                values.extend(_flatten_semantic_value(unit.get("text")))

    requirements = selector.get("record_requirements")
    if isinstance(requirements, dict):
        for field_path in requirements:
            values.extend(_value_at_path(record, field_path))

    has_reference_prerequisites = bool(reference_paths) and all(
        _path_is_present(record, path) for path in reference_paths
    )
    return values, has_reference_prerequisites


def _trusted_candidate_score(
    conn: sqlite3.Connection,
    *,
    record: dict[str, object],
    selector: dict[str, object],
) -> tuple[int, bool]:
    values, has_reference_prerequisites = _trusted_candidate_search_values(
        conn,
        record=record,
        selector=selector,
    )
    normalized_values = [value.casefold() for value in values]
    score = sum(
        any(term.casefold() in value for value in normalized_values)
        for term in selector["query_any"]
    )
    return score, has_reference_prerequisites


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
    selector_id = _require_string(selector.get("id"), "selector id")
    record_source = _require_string(record.get("source"), f"candidate {record.get('record_id')} source")
    try:
        record_provenance = _contributing_public_provenance(
            record,
            expected_source=record_source,
        )
    except ValueError:
        return None, "public_provenance_missing"
    if not _record_requirements_match(record, selector):
        return None, "record_requirement_not_met"

    fulltext_config = selector.get("fulltext_context")
    fulltext_unit: dict[str, object] | None = None
    fulltext_provenance: dict[str, object] | None = None
    fulltext_unit_id: str | None = None
    fulltext_parent_id: str | None = None
    if isinstance(fulltext_config, dict):
        unit_ids = _identifier_values_at_path(
            record, fulltext_config["unit_id_path"]
        )
        linked_parent_ids = _identifier_values_at_path(
            record, fulltext_config["parent_record_id_path"]
        )
        if (
            unit_ids is None
            or linked_parent_ids is None
            or len(unit_ids) != 1
            or len(linked_parent_ids) != 1
        ):
            return None, "fulltext_unit_link_invalid"
        fulltext_unit_id = unit_ids[0]
        fulltext_parent_id = linked_parent_ids[0]
        fulltext_unit = _fulltext_unit_by_id(conn, fulltext_unit_id)
        if (
            fulltext_unit is None
            or str(fulltext_unit["record_id"]) != fulltext_parent_id
        ):
            return None, "fulltext_unit_link_invalid"
        try:
            fulltext_provenance = _fulltext_public_provenance(fulltext_unit)
        except ValueError:
            return None, "public_provenance_missing"

    taxon_values = _trusted_semantic_values(
        record,
        list(selector["taxon_field_paths"]),
        provenance=record_provenance,
    )

    parent_config = selector.get("parent_record")
    parent_ids: list[str] = []
    if isinstance(parent_config, dict):
        raw_parent_ids = _identifier_values_at_path(
            record, parent_config["record_id_path"]
        )
        if raw_parent_ids is None or len(raw_parent_ids) > MAX_LINKED_RECORD_IDS:
            return None, "invalid_candidate_shape"
        parent_ids = list(dict.fromkeys(raw_parent_ids))
        if not parent_ids:
            return None, "upstream_record_missing"
        parent_paths = list(parent_config["taxon_field_paths"])
        for parent_id in parent_ids:
            parent_record = _record_by_id(conn, parent_id)
            if parent_record is None:
                return None, "upstream_record_missing"
            try:
                parent_source = _require_string(
                    parent_record.get("source"),
                    f"parent record {parent_id} source",
                )
                parent_provenance = _contributing_public_provenance(
                    parent_record,
                    expected_source=parent_source,
                )
            except ValueError:
                return None, "public_provenance_missing"
            taxon_values.extend(
                _trusted_semantic_values(
                    parent_record,
                    parent_paths,
                    provenance=parent_provenance,
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
        assert fulltext_provenance is not None
        assert fulltext_unit_id is not None and fulltext_parent_id is not None
        context_values: list[dict[str, object]] = []
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
                    "provenance": deepcopy(fulltext_provenance),
                }
            )
    else:
        context_values = _context_semantic_values(
            record,
            selector,
            provenance=record_provenance,
        )
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


def _prepare_candidate_for_export(
    *,
    record: dict[str, object],
    selector: dict[str, object],
    context_id: str,
    selector_id: str,
    species_id: str,
    scientific_name: str,
    eligibility: dict[str, object],
) -> dict[str, object]:
    prepared = deepcopy(record)
    prepared["species"] = scientific_name
    prepared["species_id"] = species_id
    prepared["context_ids"] = [context_id]
    prepared["selector_ids"] = [selector_id]
    prepared["eligibility"] = eligibility
    exported = _public_evidence_record(prepared, [selector])
    _validate_recursive_boundary(exported, label=f"candidate {prepared.get('record_id')}")
    _require_exact_fields(
        exported,
        EVIDENCE_RECORD_FIELDS,
        label=f"candidate {prepared.get('record_id')}",
    )
    record_id = _require_string(exported.get("record_id"), "candidate record_id")
    for field in ("lane", "source", "title", "text", "species", "species_id"):
        _require_string(exported.get(field), f"candidate {record_id} {field}")
    _require_string_list(exported.get("context_ids"), f"candidate {record_id} context_ids")
    _require_string_list(exported.get("selector_ids"), f"candidate {record_id} selector_ids")
    if not isinstance(exported.get("payload"), dict):
        raise ValueError(f"candidate {record_id} payload must be an object")
    canonical_json(exported)
    return prepared


def _stream_candidate_states(
    conn: sqlite3.Connection,
    selector_jobs: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    grouped_jobs: dict[str, list[dict[str, object]]] = {}
    for job in selector_jobs:
        selector = job["selector"]
        selector_id = _require_string(selector.get("id"), "selector id")
        states[selector_id] = {
            "candidate_count": 0,
            "eligible_count": 0,
            "rejection_counts": {},
            "selected": [],
        }
        source = _require_string(selector.get("source"), f"selector {selector_id} source")
        grouped_jobs.setdefault(source, []).append(job)

    for source, jobs in grouped_jobs.items():
        for raw_row in _source_records(conn, source):
            record = _export_record(raw_row)
            for job in jobs:
                selector = job["selector"]
                selector_id = selector["id"]
                score, has_reference_prerequisites = _trusted_candidate_score(
                    conn,
                    record=record,
                    selector=selector,
                )
                if score == 0 and not has_reference_prerequisites:
                    continue

                state = states[selector_id]
                state["candidate_count"] += 1
                if state["candidate_count"] > MAX_SELECTOR_CANDIDATE_FRONTIER:
                    raise ValueError(
                        f"selector {selector_id} candidate frontier exceeds "
                        f"{MAX_SELECTOR_CANDIDATE_FRONTIER}; narrow its source or query_any terms"
                    )

                eligibility, rejection_reason = _candidate_eligibility(
                    conn,
                    record=record,
                    selector=selector,
                    context_id=job["context_id"],
                    species_id=job["species_id"],
                    scientific_name=job["scientific_name"],
                    taxon_terms=job["taxon_terms"],
                )
                if eligibility is None:
                    reason = _require_string(rejection_reason, "candidate rejection reason")
                    rejection_counts = state["rejection_counts"]
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue

                try:
                    prepared = _prepare_candidate_for_export(
                        record=record,
                        selector=selector,
                        context_id=job["context_id"],
                        selector_id=selector_id,
                        species_id=job["species_id"],
                        scientific_name=job["scientific_name"],
                        eligibility=eligibility,
                    )
                except ValueError:
                    rejection_counts = state["rejection_counts"]
                    reason = "unsafe_export_boundary"
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue

                state["eligible_count"] += 1
                selected = state["selected"]
                selected.append((score, prepared["record_id"], prepared, eligibility))
                selected.sort(key=lambda item: (-item[0], item[1]))
                del selected[int(selector["limit"]):]
    return states


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
    exported["provenance"] = _public_provenance(
        {
            "record_id": str(context["id"]),
            "provenance": {
                "source_id": "ask_insects_context_config",
                "source_url": PUBLIC_CONTEXT_CONFIG_URL,
                "locator": f"config/insect-evidence-package.json#jsonpath=$.contexts[{index}]",
                "retrieved_at": f"{last_reviewed}T00:00:00Z",
                "license": "Repository interpretation policy",
            },
        }
    )
    return exported


def _verify_bounded_source_index_contract(conn: sqlite3.Connection) -> int:
    conn.execute("PRAGMA query_only = ON")
    query_only = conn.execute("PRAGMA query_only").fetchone()
    if query_only is None or int(query_only[0]) != 1:
        raise ValueError("source_index.sqlite did not enter query_only mode")

    table_names = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing_tables = sorted(REQUIRED_SOURCE_TABLES - table_names)
    if missing_tables:
        raise ValueError(
            f"source_index.sqlite is missing required tables: {missing_tables}"
        )
    return int(conn.execute("SELECT COUNT(*) FROM records").fetchone()[0])


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
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(status, dict):
        raise ValueError("source_status.json must contain a JSON object")
    status_generated_at = _require_string(
        status.get("generated_at"),
        "source_status.json generated_at",
    )
    status_record_count = status.get("record_count")
    if (
        isinstance(status_record_count, bool)
        or not isinstance(status_record_count, int)
        or status_record_count < 0
    ):
        raise ValueError("source_status.json record_count must be a non-negative integer")
    canonical_status = canonical_json(status)
    source_status_sha256 = hashlib.sha256(canonical_status.encode("utf-8")).hexdigest()
    db_path = artifact_dir / "source_index.sqlite"
    if not db_path.exists():
        raise ValueError("source_index.sqlite is required to build the context package")

    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        database_record_count = _verify_bounded_source_index_contract(conn)
        if database_record_count != status_record_count:
            raise ValueError(
                "source_status.json record_count does not match the read-only database "
                f"({status_record_count} != {database_record_count})"
            )

        raw_program_records = _program_records(conn)
        species_profiles = _species_profiles(raw_program_records)
        program_records = [_public_program_record(record) for record in raw_program_records]
        contexts = config["contexts"]
        exported_contexts: list[dict[str, object]] = []
        selector_results: list[dict[str, object]] = []
        gaps: list[dict[str, object]] = []
        selected_by_id: dict[str, dict[str, object]] = {}
        selector_jobs: list[dict[str, object]] = []
        for context_index, raw_context in enumerate(contexts):
            context = dict(raw_context)
            context_id = _require_string(context.get("id"), "context id")
            for species_id in context["species_ids"]:
                if species_id not in species_profiles:
                    raise ValueError(f"context {context_id} names unknown species profile: {species_id}")
            exported_contexts.append(_context_export(context, index=context_index, config=config))
            for selector in context["selectors"]:
                species_id = _require_string(selector.get("species_id"), "selector species_id")
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

        candidate_states = _stream_candidate_states(conn, selector_jobs)

        for job in selector_jobs:
            context_id = job["context_id"]
            selector = dict(job["selector"])
            selector_id = selector["id"]
            species_id = job["species_id"]
            scientific_name = job["scientific_name"]
            state = candidate_states[selector_id]
            selected = state["selected"]
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
                "candidate_count": state["candidate_count"],
                "eligible_count": state["eligible_count"],
                "selected_count": len(selected),
                "selected_record_ids": [record_id for _, record_id, _, _ in selected],
                "rejection_counts": dict(sorted(state["rejection_counts"].items())),
            }
            selector_results.append(result)
            if not selected:
                gaps.append(
                    {
                        "gap_type": "selector_no_direct_evidence",
                        **result,
                    }
                )
            for _, record_id, row, eligibility in selected:
                existing = selected_by_id.get(record_id)
                if existing is None:
                    exported_row = deepcopy(row)
                    selected_by_id[record_id] = exported_row
                else:
                    if existing["species_id"] != species_id:
                        raise ValueError(f"record {record_id} was selected for more than one species")
                    if context_id not in existing["context_ids"]:
                        existing["context_ids"].append(context_id)
                    if selector_id not in existing["selector_ids"]:
                        existing["selector_ids"].append(selector_id)
                    _merge_eligibility(existing["eligibility"], eligibility)
        selectors_by_id = {
            job["selector"]["id"]: dict(job["selector"])
            for job in selector_jobs
        }
        evidence_records = [
            _public_evidence_record(
                selected_by_id[key],
                [
                    selectors_by_id[selector_id]
                    for selector_id in selected_by_id[key]["selector_ids"]
                ],
            )
            for key in sorted(selected_by_id)
        ]
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
            "source_status_sha256": source_status_sha256,
            "source_status_generated_at": status_generated_at,
            "record_count": status_record_count,
        },
        "contexts": exported_contexts,
        "program_records": program_records,
        "evidence_records": evidence_records,
        "selector_results": selector_results,
        "gaps": gaps,
    }
    _validate_recursive_boundary(package, label="context package")
    package["content_sha256"] = canonical_package_hash(package)
    validate_context_package(package)
    return package


def _unique(items: list[dict[str, object]], key: str, label: str) -> None:
    values = [
        _require_string(item.get(key), f"{label} {key}")
        for item in items
    ]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must have unique non-empty {key} values")


def _validate_public_provenance(
    item: dict[str, object],
    label: str,
    *,
    expected_source_id: str | None = None,
    expected_locator: str | None = None,
    expected_record_id: str | None = None,
) -> None:
    provenance = _require_exact_fields(
        item.get("provenance"),
        PUBLIC_PROVENANCE_FIELDS,
        label=f"{label} provenance",
    )
    source_id = _require_string(provenance.get("source_id"), f"{label} provenance source_id")
    locator = _require_string(provenance.get("locator"), f"{label} provenance locator")
    index_record_id = _require_string(
        provenance.get("index_record_id"),
        f"{label} provenance index_record_id",
    )
    _require_string(provenance.get("retrieved_at"), f"{label} provenance retrieved_at")
    license_value = provenance.get("license")
    if license_value is not None:
        _require_string(license_value, f"{label} provenance license")

    parsed = urlsplit(locator)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or not _is_public_hostname(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or any(
            _is_credential_query_key(key)
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        )
    ):
        raise ValueError(f"{label} provenance locator must be public HTTPS without credentials")
    if parsed.fragment and _safe_locator_fragment(parsed.fragment) != parsed.fragment:
        raise ValueError(f"{label} provenance locator has an unsafe fragment")
    if expected_source_id is not None and source_id != expected_source_id:
        raise ValueError(f"{label} provenance source_id does not match its public source")
    if expected_locator is not None and locator != expected_locator:
        raise ValueError(f"{label} provenance locator does not match its public source")
    if expected_record_id is not None and index_record_id != expected_record_id:
        raise ValueError(f"{label} provenance index_record_id does not match its record")


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
        item_label = f"{label} basis/{index}"
        unsupported = set(item) - ASSERTION_BASIS_FIELDS - ASSERTION_BASIS_LINK_FIELDS
        if unsupported:
            raise ValueError(f"{item_label} contains unsupported fields: {sorted(unsupported)}")
        required_fields = ASSERTION_BASIS_FIELDS | ({"context_id"} if require_context else set())
        missing = required_fields - set(item)
        if missing:
            raise ValueError(f"{item_label} is missing fields: {sorted(missing)}")
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
        _validate_public_provenance(item, item_label)
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
    if not isinstance(package, dict):
        raise ValueError("context package top-level must be an object")
    _validate_recursive_boundary(package, label="context package")
    if len(canonical_json(package).encode("utf-8")) > MAX_PACKAGE_BYTES:
        raise ValueError("context package exceeds maximum size of 16 MiB")
    _require_exact_fields(package, PACKAGE_FIELDS, label="context package top-level")
    if package.get("ok") is not True:
        raise ValueError("context package ok must be true")
    if package.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise ValueError(f"context package schema_version must be {PACKAGE_SCHEMA_VERSION}")
    if package.get("validation_contract") != VALIDATION_CONTRACT:
        raise ValueError("context package validation_contract is invalid")
    _require_string(package.get("package_version"), "context package package_version")
    _require_string(package.get("generated_at"), "context package generated_at")
    _require_string(package.get("objective"), "context package objective")
    content_sha256 = _require_string(package.get("content_sha256"), "context package content_sha256")
    if re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None:
        raise ValueError("context package content_sha256 must be a lowercase SHA-256 digest")
    domains = set(_require_string_list(package.get("knowledge_domains"), "context package knowledge_domains"))
    upstream_snapshot = _require_exact_fields(
        package.get("upstream_snapshot"),
        UPSTREAM_SNAPSHOT_FIELDS,
        label="context package upstream_snapshot",
    )
    if upstream_snapshot.get("source_id") != "ask_insects_hosted_source_index":
        raise ValueError("context package upstream_snapshot source_id is invalid")
    source_status_sha256 = _require_string(
        upstream_snapshot.get("source_status_sha256"),
        "context package upstream_snapshot source_status_sha256",
    )
    if re.fullmatch(r"[0-9a-f]{64}", source_status_sha256) is None:
        raise ValueError("context package upstream_snapshot source_status_sha256 is invalid")
    _require_string(
        upstream_snapshot.get("source_status_generated_at"),
        "context package upstream_snapshot source_status_generated_at",
    )
    record_count = upstream_snapshot.get("record_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 0:
        raise ValueError("context package upstream_snapshot record_count is invalid")
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
        record_id = _require_string(record.get("record_id"), "program record record_id")
        _require_exact_fields(record, PROGRAM_RECORD_FIELDS, label=f"program record {record_id}")
        for field in ("lane", "source", "title", "text"):
            _require_string(record.get(field), f"program record {record_id} {field}")
        species = record.get("species")
        if species is not None:
            _require_string(species, f"program record {record_id} species")
        if record.get("source") != "insect_intelligence_programs":
            raise ValueError(f"program record {record_id} source is invalid")
        if not isinstance(record.get("payload"), dict):
            raise ValueError(f"program record {record_id} payload must be an object")
        _validate_public_provenance(
            record,
            f"program record {record_id}",
            expected_source_id="insect_intelligence_programs",
            expected_locator=PUBLIC_PROGRAM_CONFIG_URL,
            expected_record_id=record_id,
        )
    species_profiles = _species_profiles(program_records)

    context_by_id = {context["id"]: context for context in contexts}
    for context_index, context in enumerate(contexts):
        context_id = _require_string(context.get("id"), f"contexts/{context_index}/id")
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
        _validate_public_provenance(
            context,
            f"context {context_id}",
            expected_source_id="ask_insects_context_config",
            expected_locator=(
                f"{PUBLIC_CONTEXT_CONFIG_URL}#jsonpath=$.contexts[{context_index}]"
            ),
            expected_record_id=context_id,
        )

    selector_receipts: dict[str, dict[str, object]] = {}
    selected_record_species: dict[str, str] = {}
    receipts_by_record: dict[str, list[dict[str, object]]] = {}
    selector_keys: list[str] = []
    for result in selector_results:
        _require_exact_fields(
            result,
            SELECTOR_RESULT_FIELDS,
            label="selector result",
        )
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
        expected_selected_count = min(limit, eligible_count)
        if count != expected_selected_count:
            raise ValueError(
                f"selector {selector_id} selected_count must equal "
                f"min(limit, eligible_count) ({expected_selected_count})"
            )
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

    evidence_by_id = {record["record_id"]: record for record in evidence_records}
    for result in selector_results:
        selector_id = result["selector_id"]
        for record_id in result["selected_record_ids"]:
            if record_id not in evidence_by_id:
                raise ValueError(f"selector {selector_id} selects missing evidence record {record_id}")

    for record in evidence_records:
        record_id = _require_string(record.get("record_id"), "evidence record record_id")
        _require_exact_fields(record, EVIDENCE_RECORD_FIELDS, label=f"evidence record {record_id}")
        for field in ("lane", "source", "title", "text"):
            _require_string(record.get(field), f"evidence record {record_id} {field}")
        if not isinstance(record.get("payload"), dict):
            raise ValueError(f"evidence record {record_id} payload must be an object")
        _validate_public_provenance(
            record,
            f"evidence record {record_id}",
            expected_source_id=record["source"],
            expected_record_id=record_id,
        )
        species_id = _require_string(record.get("species_id"), f"evidence record {record_id} species_id")
        profile = species_profiles.get(species_id)
        if profile is None:
            raise ValueError(f"evidence record {record_id} names unknown species: {species_id}")
        scientific_name = profile["scientific_name"]
        if record.get("species") != scientific_name:
            raise ValueError(f"evidence record {record_id} is not exact-species evidence for {scientific_name}")
        if selected_record_species.get(record_id) != species_id:
            raise ValueError(f"evidence record {record_id} is not backed by a selector result")
        context_ids = _require_string_list(record.get("context_ids"), f"evidence record {record_id} context_ids")
        selector_ids = _require_string_list(record.get("selector_ids"), f"evidence record {record_id} selector_ids")
        selecting_receipts = receipts_by_record.get(record_id, [])
        expected_selector_ids = [receipt["selector_id"] for receipt in selecting_receipts]
        expected_context_ids = list(
            dict.fromkeys(receipt["context_id"] for receipt in selecting_receipts)
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
        expected_payload = _minimal_evidence_payload(record, selecting_receipts)
        if record["payload"] != expected_payload:
            raise ValueError(
                f"evidence record {record_id} payload contains fields outside its trusted selector paths"
            )

        receipt_contexts: list[str] = []
        for selector_id in selector_ids:
            receipt = selector_receipts[selector_id]
            if record_id not in receipt["selected_record_ids"]:
                raise ValueError(f"evidence record {record_id} is not selected by receipt {selector_id}")
            if receipt["species_id"] != species_id:
                raise ValueError(f"evidence record {record_id} selector species does not match")
            if receipt["source"] != record["source"]:
                raise ValueError(f"evidence record {record_id} selector source does not match")
            if not _record_requirements_match(record, receipt):
                raise ValueError(f"evidence record {record_id} does not satisfy selector record requirements")
            receipt_contexts.append(receipt["context_id"])
        if set(context_ids) != set(receipt_contexts):
            raise ValueError(f"evidence record {record_id} contexts do not match selector receipts")

        eligibility = record.get("eligibility")
        if not isinstance(eligibility, dict):
            raise ValueError(f"evidence record {record_id} is missing eligibility")
        _require_exact_fields(
            eligibility,
            ELIGIBILITY_FIELDS,
            label=f"evidence record {record_id} eligibility",
        )
        if eligibility.get("ruleset_version") != ELIGIBILITY_RULESET_VERSION:
            raise ValueError(f"evidence record {record_id} has an invalid eligibility ruleset_version")

        taxon = eligibility.get("taxon")
        if not isinstance(taxon, dict) or taxon.get("status") != "direct_focal_taxon":
            raise ValueError(f"evidence record {record_id} taxon assertion is not direct")
        _require_exact_fields(
            taxon,
            TAXON_ASSERTION_FIELDS,
            label=f"evidence record {record_id} taxon assertion",
        )
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
                _require_exact_fields(
                    basis,
                    ASSERTION_BASIS_FIELDS | {"parent_record_id"},
                    label=f"evidence record {record_id} taxon basis",
                )
                parent = receipt.get("parent_record")
                parent_path = field_path.removeprefix("parent.")
                if not isinstance(parent, dict) or parent_path not in parent.get("taxon_field_paths", []):
                    raise ValueError(f"evidence record {record_id} taxon basis field_path is not trusted")
                parent_record_id = _require_string(
                    basis.get("parent_record_id"),
                    f"evidence record {record_id} taxon basis parent_record_id",
                )
                linked_parent_ids = _identifier_values_at_path(
                    record, parent["record_id_path"]
                )
                if linked_parent_ids is None or parent_record_id not in linked_parent_ids:
                    raise ValueError(
                        f"evidence record {record_id} taxon basis parent_record_id is not linked"
                    )
                if retained_store != "record_payloads":
                    raise ValueError(f"evidence record {record_id} taxon basis retained_store is invalid")
                if retained_path != parent_path:
                    raise ValueError(f"evidence record {record_id} taxon basis retained_path is invalid")
                _validate_public_provenance(
                    basis,
                    f"evidence record {record_id} taxon basis",
                    expected_source_id=retained_source,
                    expected_record_id=parent_record_id,
                )
            else:
                _require_exact_fields(
                    basis,
                    ASSERTION_BASIS_FIELDS,
                    label=f"evidence record {record_id} taxon basis",
                )
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
                _validate_public_provenance(
                    basis,
                    f"evidence record {record_id} taxon basis",
                    expected_source_id=retained_source,
                    expected_record_id=record_id,
                )
                if basis["provenance"] != record["provenance"]:
                    raise ValueError(
                        f"evidence record {record_id} taxon basis provenance "
                        "does not match record provenance"
                    )
            taxon_basis_selectors.add(selector_id)
        if set(selector_ids) != taxon_basis_selectors:
            raise ValueError(f"evidence record {record_id} taxon assertion is missing selector basis")

        context = eligibility.get("context")
        if not isinstance(context, dict) or context.get("status") != "direct_context":
            raise ValueError(f"evidence record {record_id} context assertion is not direct")
        _require_exact_fields(
            context,
            CONTEXT_ASSERTION_FIELDS,
            label=f"evidence record {record_id} context assertion",
        )
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
                _require_exact_fields(
                    basis,
                    ASSERTION_BASIS_FIELDS | {"context_id"},
                    label=f"evidence record {record_id} context basis",
                )
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
                _validate_public_provenance(
                    basis,
                    f"evidence record {record_id} context basis",
                    expected_source_id=retained_source,
                    expected_record_id=record_id,
                )
                if basis["provenance"] != record["provenance"]:
                    raise ValueError(
                        f"evidence record {record_id} context basis provenance "
                        "does not match record provenance"
                    )
            else:
                _require_exact_fields(
                    basis,
                    ASSERTION_BASIS_FIELDS
                    | {"context_id", "fulltext_unit_id", "parent_record_id"},
                    label=f"evidence record {record_id} context basis",
                )
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
                linked_unit_ids = _identifier_values_at_path(
                    record, fulltext["unit_id_path"]
                )
                if linked_unit_ids is None or fulltext_unit_id not in linked_unit_ids:
                    raise ValueError(
                        f"evidence record {record_id} context basis fulltext_unit_id is not linked"
                    )
                linked_parent_ids = _identifier_values_at_path(
                    record, fulltext["parent_record_id_path"]
                )
                if linked_parent_ids is None or parent_record_id not in linked_parent_ids:
                    raise ValueError(
                        f"evidence record {record_id} context basis parent_record_id is not linked"
                    )
                if retained_store != "literature_fulltext_units":
                    raise ValueError(f"evidence record {record_id} context basis retained_store is invalid")
                if retained_path != field_path:
                    raise ValueError(f"evidence record {record_id} context basis retained_path is invalid")
                _validate_public_provenance(
                    basis,
                    f"evidence record {record_id} context basis",
                    expected_source_id=retained_source,
                    expected_record_id=fulltext_unit_id,
                )
            covered_groups.setdefault((selector_id, context_id), set()).update(matching_groups)
        for selector_id in selector_ids:
            context_id = selector_receipts[selector_id]["context_id"]
            required_count = len(selector_receipts[selector_id]["context_required_term_groups"])
            if covered_groups.get((selector_id, context_id), set()) != set(range(required_count)):
                raise ValueError(
                    f"evidence record {record_id} context assertion is missing basis for "
                    f"{context_id} receipt {selector_id}"
                )

    zero_selected = {
        result["selector_id"]: result
        for result in selector_results
        if result["selected_count"] == 0
    }
    gap_selectors: set[str] = set()
    for gap in gaps:
        _require_exact_fields(gap, GAP_FIELDS, label="selector gap")
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
