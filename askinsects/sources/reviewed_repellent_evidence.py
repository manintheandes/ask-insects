from __future__ import annotations

from datetime import UTC, datetime
from importlib.resources import files as resource_files
import json
from pathlib import Path
import re

from askinsects.records import EvidenceRecord, Provenance


CATALOG_SCHEMA_VERSION = "ask-insects-reviewed-repellent-evidence.v1"
REVIEWED_REPELLENT_SOURCE_ID = "reviewed_repellent_evidence"
REPO_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_CATALOG = REPO_ROOT / "config" / "reviewed-repellent-evidence.json"
PUBLIC_CATALOG_URL = (
    "https://raw.githubusercontent.com/manintheandes/ask-insects/"
    "171218bb6ad08f4d41254ffbd7a4c3eca368f1cd/"
    "config/reviewed-repellent-evidence.json"
)
ALLOWED_MATERIAL_TYPES = frozenset(
    {
        "pure_compound",
        "essential_oil",
        "natural_material",
        "mixture",
        "commercial_product",
    }
)
ALLOWED_EVIDENCE_RELATIONS = frozenset(
    {"exact_material", "mixture_component", "related_material"}
)
ALLOWED_EVIDENCE_CLASSES = frozenset(
    {
        "repellent_effect",
        "deterrent_effect",
        "no_significant_repellent_effect",
        "host_cue_or_attractant",
        "identity_only",
    }
)
ALLOWED_EXPOSURE_ROUTES = frozenset(
    {"contact", "non_contact", "mixed_or_unclear", "not_applicable"}
)
EXACT_PUBLIC_SOURCE_PREFIXES = ("doi:", "pubmed:", "pmc:", "epa:", "who:")
FORBIDDEN_PROVENANCE_MARKERS = (
    "config/",
    "jsonpath=",
    "reviewed-repellent-evidence",
    "insect_intelligence_programs",
)
FORBIDDEN_CONSUMER_KEYS = frozenset(
    {
        "company",
        "consumer_id",
        "experiment_id",
        "private_experiment_id",
        "private_result",
        "private_results",
        "result_status",
        "tested_at",
        "tested_date",
    }
)


class ReviewedRepellentEvidenceError(ValueError):
    pass


def default_reviewed_repellent_catalog() -> Path:
    if _REPOSITORY_CATALOG.is_file():
        return _REPOSITORY_CATALOG
    return Path(
        str(
            resource_files("askinsects.resources").joinpath(
                "reviewed-repellent-evidence.json"
            )
        )
    )


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ReviewedRepellentEvidenceError(f"{label} must be a list of objects")
    return value


def _strings(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ReviewedRepellentEvidenceError(
            f"{label} must be a list of non-empty strings"
        )
    if not allow_empty and not value:
        raise ReviewedRepellentEvidenceError(f"{label} must not be empty")
    return [item.strip() for item in value]


def _required_string(item: dict[str, object], key: str, label: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReviewedRepellentEvidenceError(f"{label}.{key} must be non-empty")
    return value.strip()


def _normalized_alias(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _reject_consumer_coupling(value: object, *, path: str = "catalog") -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONSUMER_KEYS.intersection(value)
        if forbidden:
            raise ReviewedRepellentEvidenceError(
                f"private or consumer-specific fields are forbidden at {path}: "
                + ", ".join(sorted(forbidden))
            )
        for key, child in value.items():
            _reject_consumer_coupling(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_consumer_coupling(child, path=f"{path}[{index}]")


def validate_reviewed_repellent_catalog(payload: dict[str, object]) -> None:
    _reject_consumer_coupling(payload)
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise ReviewedRepellentEvidenceError(
            f"schema_version must be {CATALOG_SCHEMA_VERSION}"
        )
    if not isinstance(payload.get("last_reviewed"), str) or not str(
        payload["last_reviewed"]
    ).strip():
        raise ReviewedRepellentEvidenceError("last_reviewed must be non-empty")

    materials = _objects(payload.get("materials"), "materials")
    material_by_id: dict[str, dict[str, object]] = {}
    alias_owner: dict[str, str] = {}
    for index, material in enumerate(materials):
        label = f"materials[{index}]"
        material_id = _required_string(material, "id", label)
        if material_id in material_by_id:
            raise ReviewedRepellentEvidenceError("material ids must be unique")
        canonical_name = _required_string(material, "canonical_name", label)
        material_type = _required_string(material, "material_type", label)
        if material_type not in ALLOWED_MATERIAL_TYPES:
            raise ReviewedRepellentEvidenceError(
                f"{label}.material_type must be one of {sorted(ALLOWED_MATERIAL_TYPES)}"
            )
        aliases = _strings(material.get("exact_aliases"), f"{label}.exact_aliases")
        related_aliases = _strings(
            material.get("related_aliases", []),
            f"{label}.related_aliases",
            allow_empty=True,
        )
        normalized_canonical = _normalized_alias(canonical_name)
        normalized_aliases = {_normalized_alias(alias) for alias in aliases}
        if not normalized_canonical or normalized_canonical not in normalized_aliases:
            raise ReviewedRepellentEvidenceError(
                f"{label}.exact_aliases must include canonical_name"
            )
        for alias in normalized_aliases:
            owner = alias_owner.get(alias)
            if owner and owner != material_id:
                raise ReviewedRepellentEvidenceError(
                    f"exact alias {alias!r} is shared by {owner} and {material_id}"
                )
            alias_owner[alias] = material_id
        if any(not _normalized_alias(alias) for alias in related_aliases):
            raise ReviewedRepellentEvidenceError(
                f"{label}.related_aliases must contain searchable names"
            )
        material_by_id[material_id] = material

    evidence_ids: set[str] = set()
    for index, evidence in enumerate(_objects(payload.get("evidence"), "evidence")):
        label = f"evidence[{index}]"
        evidence_id = _required_string(evidence, "id", label)
        if evidence_id in evidence_ids:
            raise ReviewedRepellentEvidenceError("evidence ids must be unique")
        evidence_ids.add(evidence_id)
        material_id = _required_string(evidence, "material_id", label)
        if material_id not in material_by_id:
            raise ReviewedRepellentEvidenceError(
                f"{label}.material_id references an unknown material"
            )
        for key in (
            "species_id",
            "scientific_name",
            "assay_family",
            "endpoint",
            "finding",
        ):
            _required_string(evidence, key, label)
        target_species_id = evidence.get("comparison_target_species_id")
        target_scientific_name = evidence.get("comparison_target_scientific_name")
        if (target_species_id is None) != (target_scientific_name is None):
            raise ReviewedRepellentEvidenceError(
                f"{label} must provide both comparison target species fields"
            )
        if target_species_id is not None:
            _required_string(evidence, "comparison_target_species_id", label)
            _required_string(evidence, "comparison_target_scientific_name", label)
        relation = _required_string(evidence, "evidence_relation", label)
        if relation not in ALLOWED_EVIDENCE_RELATIONS:
            raise ReviewedRepellentEvidenceError(
                f"{label}.evidence_relation must be one of "
                f"{sorted(ALLOWED_EVIDENCE_RELATIONS)}"
            )
        evidence_class = _required_string(evidence, "evidence_class", label)
        if evidence_class not in ALLOWED_EVIDENCE_CLASSES:
            raise ReviewedRepellentEvidenceError(
                f"{label}.evidence_class must be one of "
                f"{sorted(ALLOWED_EVIDENCE_CLASSES)}"
            )
        exposure_route = _required_string(evidence, "exposure_route", label)
        if exposure_route not in ALLOWED_EXPOSURE_ROUTES:
            raise ReviewedRepellentEvidenceError(
                f"{label}.exposure_route must be one of "
                f"{sorted(ALLOWED_EXPOSURE_ROUTES)}"
            )
        _strings(evidence.get("limitations"), f"{label}.limitations")
        provenance_rows = _objects(
            evidence.get("supporting_provenance"),
            f"{label}.supporting_provenance",
        )
        if not provenance_rows:
            raise ReviewedRepellentEvidenceError(
                f"{label}.supporting_provenance must not be empty"
            )
        for source_index, source in enumerate(provenance_rows):
            source_label = f"{label}.supporting_provenance[{source_index}]"
            for key in ("title", "public_url", "source_id", "locator"):
                _required_string(source, key, source_label)
            public_url = str(source["public_url"]).strip()
            if not public_url.startswith(("https://", "http://")):
                raise ReviewedRepellentEvidenceError(
                    f"{source_label}.public_url must be public HTTP(S)"
                )
            source_id = str(source["source_id"]).strip().casefold()
            locator = str(source["locator"]).strip().casefold()
            if not source_id.startswith(EXACT_PUBLIC_SOURCE_PREFIXES):
                raise ReviewedRepellentEvidenceError(
                    f"{source_label} requires an exact public source"
                )
            if any(marker in locator for marker in FORBIDDEN_PROVENANCE_MARKERS):
                raise ReviewedRepellentEvidenceError(
                    f"{source_label} requires a claim-level source locator"
                )


def load_reviewed_repellent_catalog(
    path: Path | None = None,
) -> dict[str, object]:
    catalog_path = Path(path) if path is not None else default_reviewed_repellent_catalog()
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewedRepellentEvidenceError(
            f"could not load reviewed repellent catalog: {catalog_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReviewedRepellentEvidenceError(
            "reviewed repellent catalog must be an object"
        )
    validate_reviewed_repellent_catalog(payload)
    return payload


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_reviewed_repellent_records(
    *,
    catalog_path: Path | None = None,
    retrieved_at: str | None = None,
) -> list[EvidenceRecord]:
    path = Path(catalog_path) if catalog_path is not None else default_reviewed_repellent_catalog()
    catalog = load_reviewed_repellent_catalog(path)
    materials = {
        str(item["id"]): item
        for item in _objects(catalog["materials"], "materials")
    }
    timestamp = retrieved_at or _utc_now()
    records: list[EvidenceRecord] = []
    for index, row in enumerate(_objects(catalog["evidence"], "evidence")):
        material = materials[str(row["material_id"])]
        evidence = {
            "material_id": str(material["id"]),
            "canonical_name": str(material["canonical_name"]),
            "material_type": str(material["material_type"]),
            "exact_aliases": list(material["exact_aliases"]),
            "related_aliases": list(material.get("related_aliases", [])),
            **row,
        }
        evidence["comparison_target_species_id"] = str(
            row.get("comparison_target_species_id") or row["species_id"]
        )
        evidence["comparison_target_scientific_name"] = str(
            row.get("comparison_target_scientific_name") or row["scientific_name"]
        )
        source = row["supporting_provenance"][0]
        text = " ".join(
            [
                str(row["finding"]).strip(),
                "Limitations:",
                " ".join(str(item).strip() for item in row["limitations"]),
            ]
        )
        records.append(
            EvidenceRecord(
                record_id=f"{REVIEWED_REPELLENT_SOURCE_ID}:{row['id']}",
                lane="reviewed_science",
                source=REVIEWED_REPELLENT_SOURCE_ID,
                title=(
                    f"{material['canonical_name']}: {row['scientific_name']} "
                    f"{row['evidence_class']}"
                ),
                text=text,
                species=str(evidence["comparison_target_scientific_name"]),
                url=str(source["public_url"]),
                media_url=None,
                provenance=Provenance(
                    source_id=REVIEWED_REPELLENT_SOURCE_ID,
                    locator=f"jsonpath=$.evidence[{index}]",
                    retrieved_at=timestamp,
                    license="catalog metadata; upstream source terms apply",
                    source_url=PUBLIC_CATALOG_URL,
                ),
                payload={
                    "atom_type": "reviewed_repellent_evidence",
                    "evidence": evidence,
                },
            )
        )
    return records
