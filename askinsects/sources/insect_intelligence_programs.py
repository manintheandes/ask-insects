from __future__ import annotations

from datetime import UTC, datetime
from importlib.resources import files as resource_files
import json
from pathlib import Path
import re

from askinsects.records import EvidenceRecord, Provenance


INSECT_INTELLIGENCE_SOURCE_ID = "insect_intelligence_programs"
PUBLIC_PROGRAM_LEDGER_URL = (
    "https://github.com/manintheandes/ask-insects/blob/main/"
    "config/insect-intelligence-programs.json"
)
_REPOSITORY_PROGRAM_LEDGER = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "insect-intelligence-programs.json"
)
DEFAULT_PROGRAM_LEDGER = (
    _REPOSITORY_PROGRAM_LEDGER
    if _REPOSITORY_PROGRAM_LEDGER.is_file()
    else Path(
        str(
            resource_files("askinsects.resources").joinpath(
                "insect-intelligence-programs.json"
            )
        )
    )
)

REQUIRED_KNOWLEDGE_DOMAINS = {
    "sensory_world",
    "brain_neurobiology",
    "receptors_signaling",
    "anatomy_physiology",
    "genetics_gene_activity",
    "life_cycle_development",
    "behavior",
    "reproduction_oviposition",
    "feeding_host_finding",
    "movement_flight_navigation",
    "learning_memory_internal_state",
    "ecology_interactions",
    "chemical_responses_metabolism",
    "adaptation_resistance",
}

REQUIRED_READINESS_DIMENSIONS = {
    "efficacy",
    "mode_of_action",
    "formulation_delivery",
    "persistence_reapplication",
    "human_or_crop_safety",
    "non_target_ecological_effects",
    "field_or_human_use_performance",
    "regulatory_commercialization",
}

REQUIRED_EVIDENCE_GATES = {
    "species_confirmed",
    "context_preserved",
    "directness_labeled",
    "verification_labeled",
    "uncertainty_visible",
    "disagreements_visible",
    "provenance_exact",
}

ALLOWED_STATUSES = {"source_grade", "partial_source_grade", "source_gap", "not_started"}
ALLOWED_EVIDENCE_SCOPES = {"direct", "inferred", "mixed", "none"}
ALLOWED_VERIFICATION_STATUSES = {"human_verified", "mixed", "unverified", "not_applicable"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_.:-]+", "_", text).strip("_") or "unknown"


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    values = payload.get(key)
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise ValueError(f"program ledger {key} must be a list of objects")
    return values


def _strings(payload: dict[str, object], key: str, *, allow_empty: bool = True) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{key} must be a list of non-empty strings")
    if not allow_empty and not values:
        raise ValueError(f"{key} must not be empty")
    return [value.strip() for value in values]


def _unique_ids(items: list[dict[str, object]], label: str) -> set[str]:
    identifiers = [str(item.get("id") or "").strip() for item in items]
    if any(not identifier for identifier in identifiers):
        raise ValueError(f"every {label} must have an id")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"{label} ids must be unique")
    return set(identifiers)


def _validate_coverage_entry(entry: dict[str, object], *, subject: str) -> None:
    status = str(entry.get("status") or "")
    evidence_scope = str(entry.get("evidence_scope") or "")
    verification_status = str(entry.get("verification_status") or "")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"{subject} has invalid status: {status or 'missing'}")
    if evidence_scope not in ALLOWED_EVIDENCE_SCOPES:
        raise ValueError(f"{subject} has invalid evidence_scope: {evidence_scope or 'missing'}")
    if verification_status not in ALLOWED_VERIFICATION_STATUSES:
        raise ValueError(f"{subject} has invalid verification_status: {verification_status or 'missing'}")
    summary = entry.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError(f"{subject} must have a summary")
    current_sources = _strings(entry, "current_sources")
    gaps = _strings(entry, "gaps")
    _strings(entry, "uncertainties")
    _strings(entry, "disagreements")
    if status in {"source_gap", "not_started"}:
        if current_sources:
            raise ValueError(f"{subject} cannot carry current sources while status is {status}")
        if evidence_scope != "none":
            raise ValueError(f"{subject} must use evidence_scope=none while status is {status}")
        if verification_status != "not_applicable":
            raise ValueError(f"{subject} must use verification_status=not_applicable while status is {status}")
    if status != "source_grade" and not gaps:
        raise ValueError(f"{subject} must list explicit gaps until it is source grade")
    if status in {"source_grade", "partial_source_grade"} and not current_sources:
        raise ValueError(f"{subject} must list current sources for status {status}")


def validate_program_ledger(payload: dict[str, object]) -> None:
    if payload.get("schema_version") != "insect-intelligence-programs.v1":
        raise ValueError("program ledger schema_version must be insect-intelligence-programs.v1")
    if not isinstance(payload.get("objective"), str) or not str(payload["objective"]).strip():
        raise ValueError("program ledger objective must be a non-empty string")
    evidence_gates = set(_strings(payload, "evidence_gates", allow_empty=False))
    if evidence_gates != REQUIRED_EVIDENCE_GATES:
        raise ValueError("program ledger evidence gates do not match the required evidence contract")

    knowledge_domains = _objects(payload, "knowledge_domains")
    readiness_dimensions = _objects(payload, "readiness_dimensions")
    products = _objects(payload, "products")
    species_profiles = _objects(payload, "species")
    knowledge_ids = _unique_ids(knowledge_domains, "knowledge domains")
    readiness_ids = _unique_ids(readiness_dimensions, "readiness dimensions")
    product_ids = _unique_ids(products, "products")
    species_ids = _unique_ids(species_profiles, "species")
    if knowledge_ids != REQUIRED_KNOWLEDGE_DOMAINS:
        raise ValueError("program ledger knowledge domains do not match the required shared model")
    if readiness_ids != REQUIRED_READINESS_DIMENSIONS:
        raise ValueError("program ledger readiness dimensions do not match the required product model")
    if not product_ids or not species_ids:
        raise ValueError("program ledger must define at least one product and one species")

    for definition in [*knowledge_domains, *readiness_dimensions]:
        if not isinstance(definition.get("name"), str) or not str(definition["name"]).strip():
            raise ValueError(f"definition {definition.get('id')} must have a name")
        _strings(definition, "aliases", allow_empty=False)

    seen_species_aliases: dict[str, str] = {}
    for profile in species_profiles:
        species_id = str(profile["id"])
        scientific_name = profile.get("scientific_name")
        common_name = profile.get("common_name")
        if not isinstance(scientific_name, str) or not scientific_name.strip():
            raise ValueError(f"species {species_id} must have a scientific_name")
        if not isinstance(common_name, str) or not common_name.strip():
            raise ValueError(f"species {species_id} must have a common_name")
        aliases = _strings(profile, "aliases", allow_empty=False)
        for alias in [scientific_name, common_name, *aliases]:
            normalized = re.sub(r"\s+", " ", alias).strip().lower()
            owner = seen_species_aliases.get(normalized)
            if owner and owner != species_id:
                raise ValueError(f"species alias {alias!r} is shared by {owner} and {species_id}")
            seen_species_aliases[normalized] = species_id
        references = set(_strings(profile, "product_ids"))
        unknown_products = references - product_ids
        if unknown_products:
            raise ValueError(f"species {species_id} references unknown products: {sorted(unknown_products)}")
        domains = profile.get("domains")
        if not isinstance(domains, list) or not all(isinstance(domain, dict) for domain in domains):
            raise ValueError(f"species {species_id} domains must be a list of objects")
        domain_ids = [str(domain.get("id") or "") for domain in domains]
        missing_domains = REQUIRED_KNOWLEDGE_DOMAINS - set(domain_ids)
        extra_domains = set(domain_ids) - REQUIRED_KNOWLEDGE_DOMAINS
        if missing_domains:
            raise ValueError(f"species {species_id} is missing knowledge domains: {sorted(missing_domains)}")
        if extra_domains or len(domain_ids) != len(set(domain_ids)):
            raise ValueError(f"species {species_id} has invalid or duplicate knowledge domains")
        for domain in domains:
            _validate_coverage_entry(domain, subject=f"species {species_id} domain {domain.get('id')}")

    for product in products:
        product_id = str(product["id"])
        if not isinstance(product.get("name"), str) or not str(product["name"]).strip():
            raise ValueError(f"product {product_id} must have a name")
        _strings(product, "aliases", allow_empty=False)
        targets = set(_strings(product, "target_species", allow_empty=False))
        unknown_species = targets - species_ids
        if unknown_species:
            raise ValueError(f"product {product_id} references unknown species: {sorted(unknown_species)}")
        readiness = product.get("readiness")
        if not isinstance(readiness, list) or not all(isinstance(item, dict) for item in readiness):
            raise ValueError(f"product {product_id} readiness must be a list of objects")
        dimension_ids = [str(item.get("id") or "") for item in readiness]
        missing_dimensions = REQUIRED_READINESS_DIMENSIONS - set(dimension_ids)
        if missing_dimensions:
            raise ValueError(f"product {product_id} is missing readiness dimensions: {sorted(missing_dimensions)}")
        if set(dimension_ids) != REQUIRED_READINESS_DIMENSIONS or len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError(f"product {product_id} has invalid or duplicate readiness dimensions")
        for item in readiness:
            _validate_coverage_entry(item, subject=f"product {product_id} readiness {item.get('id')}")

    species_products = {
        str(profile["id"]): set(_strings(profile, "product_ids"))
        for profile in species_profiles
    }
    product_targets = {
        str(product["id"]): set(_strings(product, "target_species", allow_empty=False))
        for product in products
    }
    for product_id, targets in product_targets.items():
        for species_id in targets:
            if product_id not in species_products[species_id]:
                raise ValueError(f"product {product_id} and species {species_id} must reference each other")
    for species_id, references in species_products.items():
        for product_id in references:
            if species_id not in product_targets[product_id]:
                raise ValueError(f"species {species_id} and product {product_id} must reference each other")


def load_program_ledger(path: Path = DEFAULT_PROGRAM_LEDGER) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("program ledger must be a JSON object")
    validate_program_ledger(payload)
    return payload


def _definition_map(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in items}


def _status_counts(items: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _list_text(values: object, *, empty: str = "none") -> str:
    if not isinstance(values, list) or not values:
        return empty
    return "; ".join(str(value) for value in values)


def _provenance(program_path: Path, fragment: str, retrieved_at: str) -> Provenance:
    parts = fragment.split("/")
    if parts == ["portfolio"]:
        jsonpath = "$.objective"
    else:
        jsonpath = "$"
        for part in parts:
            if part.isdigit():
                jsonpath += f"[{part}]"
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                jsonpath += f".{part}"
            else:
                raise ValueError(f"unsupported program-ledger locator segment: {part}")
    locator_path = (
        Path("config/insect-intelligence-programs.json")
        if program_path == DEFAULT_PROGRAM_LEDGER
        else program_path
    )
    return Provenance(
        source_id=INSECT_INTELLIGENCE_SOURCE_ID,
        locator=f"{locator_path.as_posix()}#jsonpath={jsonpath}",
        retrieved_at=retrieved_at,
        license="Repository program ledger",
        source_url=PUBLIC_PROGRAM_LEDGER_URL if program_path == DEFAULT_PROGRAM_LEDGER else None,
    )


def build_insect_intelligence_records(
    program_path: Path = DEFAULT_PROGRAM_LEDGER,
    *,
    retrieved_at: str | None = None,
) -> list[EvidenceRecord]:
    path = Path(program_path)
    payload = load_program_ledger(path)
    retrieved = retrieved_at or utc_now()
    domains = _objects(payload, "knowledge_domains")
    readiness_dimensions = _objects(payload, "readiness_dimensions")
    products = _objects(payload, "products")
    species_profiles = _objects(payload, "species")
    domain_definitions = _definition_map(domains)
    readiness_definitions = _definition_map(readiness_dimensions)

    records: list[EvidenceRecord] = [
        EvidenceRecord(
            record_id="insect_intelligence_programs:portfolio",
            lane="insect_intelligence",
            source=INSECT_INTELLIGENCE_SOURCE_ID,
            title="Ask Insects product and species intelligence portfolio",
            text=(
                f"Ask Insects supports {len(products)} initial repellent product programs across {len(species_profiles)} insect profiles. "
                f"Each species is tracked across {len(domains)} shared biological knowledge domains and each product across "
                f"{len(readiness_dimensions)} readiness dimensions. Objective: {payload['objective']}"
            ),
            species=None,
            url=None,
            media_url=None,
            provenance=_provenance(path, "portfolio", retrieved),
            payload={
                "atom_type": "portfolio_overview",
                "schema_version": payload["schema_version"],
                "objective": payload["objective"],
                "product_count": len(products),
                "species_count": len(species_profiles),
                "knowledge_domain_count": len(domains),
                "readiness_dimension_count": len(readiness_dimensions),
                "products": [{"id": item["id"], "name": item["name"]} for item in products],
                "species_profiles": [
                    {
                        "id": item["id"],
                        "scientific_name": item["scientific_name"],
                        "common_name": item["common_name"],
                        "role": item.get("role"),
                    }
                    for item in species_profiles
                ],
                "evidence_gates": payload["evidence_gates"],
                "last_reviewed": payload.get("last_reviewed"),
                "ledger_path": path.as_posix(),
            },
        )
    ]

    for product_index, product in enumerate(products):
        product_id = str(product["id"])
        readiness = product["readiness"]
        status_counts = _status_counts(readiness)
        target_names = [
            str(profile["scientific_name"])
            for profile in species_profiles
            if str(profile["id"]) in set(product["target_species"])
        ]
        records.append(
            EvidenceRecord(
                record_id=f"insect_intelligence_programs:product:{_safe_id(product_id)}",
                lane="insect_intelligence",
                source=INSECT_INTELLIGENCE_SOURCE_ID,
                title=str(product["name"]),
                text=(
                    f"{product['name']} supports {', '.join(target_names)}. Objective: {product['objective']} "
                    f"Ask Insects tracks {len(readiness)} readiness dimensions. Status counts: "
                    + "; ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
                    + ". These are evidence-coverage statuses, not proof that the product works."
                ),
                species=None,
                url=None,
                media_url=None,
                provenance=_provenance(path, f"products/{product_index}", retrieved),
                payload={
                    "atom_type": "product_program",
                    "product_id": product_id,
                    "name": product["name"],
                    "aliases": product["aliases"],
                    "objective": product["objective"],
                    "target_species": product["target_species"],
                    "target_species_names": target_names,
                    "status_counts": status_counts,
                    "readiness_dimension_count": len(readiness),
                    "ledger_path": path.as_posix(),
                },
            )
        )
        for readiness_index, item in enumerate(readiness):
            dimension_id = str(item["id"])
            definition = readiness_definitions[dimension_id]
            records.append(
                EvidenceRecord(
                    record_id=f"insect_intelligence_programs:product:{_safe_id(product_id)}:readiness:{_safe_id(dimension_id)}",
                    lane="insect_intelligence",
                    source=INSECT_INTELLIGENCE_SOURCE_ID,
                    title=f"{product['name']} readiness: {definition['name']}",
                    text=(
                        f"{product['name']} {definition['name']} status is {item['status']}. {item['summary']} "
                        f"Evidence scope: {item['evidence_scope']}. Verification: {item['verification_status']}. "
                        f"Current public sources: {_list_text(item['current_sources'])}. "
                        f"Missing evidence: {_list_text(item['gaps'])}."
                    ),
                    species=None,
                    url=None,
                    media_url=None,
                    provenance=_provenance(path, f"products/{product_index}/readiness/{readiness_index}", retrieved),
                    payload={
                        "atom_type": "readiness_dimension",
                        "product_id": product_id,
                        "product_name": product["name"],
                        "dimension": dimension_id,
                        "dimension_name": definition["name"],
                        "aliases": definition["aliases"],
                        "status": item["status"],
                        "evidence_scope": item["evidence_scope"],
                        "verification_status": item["verification_status"],
                        "summary": item["summary"],
                        "current_sources": item["current_sources"],
                        "gaps": item["gaps"],
                        "uncertainties": item["uncertainties"],
                        "disagreements": item["disagreements"],
                        "ledger_path": path.as_posix(),
                    },
                )
            )
            for gap_index, gap in enumerate(item["gaps"]):
                records.append(
                    EvidenceRecord(
                        record_id=(
                            f"insect_intelligence_programs:product:{_safe_id(product_id)}:"
                            f"readiness-gap:{_safe_id(dimension_id)}:{gap_index + 1}"
                        ),
                        lane="insect_intelligence",
                        source=INSECT_INTELLIGENCE_SOURCE_ID,
                        title=f"{product['name']} missing readiness evidence: {definition['name']}",
                        text=(
                            f"Missing public evidence for {product['name']} {definition['name']}: {gap}. "
                            "This is an explicit evidence gap, not proof of readiness or failure."
                        ),
                        species=None,
                        url=None,
                        media_url=None,
                        provenance=_provenance(
                            path,
                            f"products/{product_index}/readiness/{readiness_index}/gaps/{gap_index}",
                            retrieved,
                        ),
                        payload={
                            "atom_type": "readiness_gap",
                            "product_id": product_id,
                            "product_name": product["name"],
                            "dimension": dimension_id,
                            "dimension_name": definition["name"],
                            "status": item["status"],
                            "gap": gap,
                            "ledger_path": path.as_posix(),
                        },
                    )
                )

    for species_index, profile in enumerate(species_profiles):
        species_id = str(profile["id"])
        scientific_name = str(profile["scientific_name"])
        common_name = str(profile["common_name"])
        profile_domains = profile["domains"]
        status_counts = _status_counts(profile_domains)
        aliases = list(dict.fromkeys([scientific_name, common_name, *profile["aliases"]]))
        records.append(
            EvidenceRecord(
                record_id=f"insect_intelligence_programs:species:{_safe_id(species_id)}",
                lane="insect_intelligence",
                source=INSECT_INTELLIGENCE_SOURCE_ID,
                title=f"{common_name} ({scientific_name}) intelligence profile",
                text=(
                    f"Ask Insects tracks {scientific_name}, {common_name}, as {profile['role']}. "
                    f"The profile covers {len(profile_domains)} shared biological knowledge domains. Status counts: "
                    + "; ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
                    + ". Missing domains remain explicit and are not filled with evidence from another species."
                ),
                species=scientific_name,
                url=None,
                media_url=None,
                provenance=_provenance(path, f"species/{species_index}", retrieved),
                payload={
                    "atom_type": "species_profile",
                    "species_id": species_id,
                    "scientific_name": scientific_name,
                    "common_name": common_name,
                    "aliases": aliases,
                    "role": profile["role"],
                    "product_ids": profile["product_ids"],
                    "status_counts": status_counts,
                    "knowledge_domain_count": len(profile_domains),
                    "ledger_path": path.as_posix(),
                },
            )
        )
        for domain_index, item in enumerate(profile_domains):
            domain_id = str(item["id"])
            definition = domain_definitions[domain_id]
            records.append(
                EvidenceRecord(
                    record_id=f"insect_intelligence_programs:species:{_safe_id(species_id)}:domain:{_safe_id(domain_id)}",
                    lane="insect_intelligence",
                    source=INSECT_INTELLIGENCE_SOURCE_ID,
                    title=f"{common_name} intelligence: {definition['name']}",
                    text=(
                        f"{common_name} ({scientific_name}) {definition['name']} status is {item['status']}. {item['summary']} "
                        f"Evidence scope: {item['evidence_scope']}. Verification: {item['verification_status']}. "
                        f"Current public sources: {_list_text(item['current_sources'])}. "
                        f"Missing evidence: {_list_text(item['gaps'])}."
                    ),
                    species=scientific_name,
                    url=None,
                    media_url=None,
                    provenance=_provenance(path, f"species/{species_index}/domains/{domain_index}", retrieved),
                    payload={
                        "atom_type": "knowledge_domain",
                        "species_id": species_id,
                        "scientific_name": scientific_name,
                        "common_name": common_name,
                        "domain": domain_id,
                        "domain_name": definition["name"],
                        "aliases": definition["aliases"],
                        "status": item["status"],
                        "evidence_scope": item["evidence_scope"],
                        "verification_status": item["verification_status"],
                        "summary": item["summary"],
                        "current_sources": item["current_sources"],
                        "gaps": item["gaps"],
                        "uncertainties": item["uncertainties"],
                        "disagreements": item["disagreements"],
                        "ledger_path": path.as_posix(),
                    },
                )
            )
            for gap_index, gap in enumerate(item["gaps"]):
                records.append(
                    EvidenceRecord(
                        record_id=(
                            f"insect_intelligence_programs:species:{_safe_id(species_id)}:"
                            f"knowledge-gap:{_safe_id(domain_id)}:{gap_index + 1}"
                        ),
                        lane="insect_intelligence",
                        source=INSECT_INTELLIGENCE_SOURCE_ID,
                        title=f"{common_name} missing knowledge: {definition['name']}",
                        text=(
                            f"Missing {common_name} ({scientific_name}) evidence for {definition['name']}: {gap}. "
                            "This gap must not be filled with another species' evidence unless that evidence is explicitly labeled as an inference."
                        ),
                        species=scientific_name,
                        url=None,
                        media_url=None,
                        provenance=_provenance(
                            path,
                            f"species/{species_index}/domains/{domain_index}/gaps/{gap_index}",
                            retrieved,
                        ),
                        payload={
                            "atom_type": "knowledge_gap",
                            "species_id": species_id,
                            "scientific_name": scientific_name,
                            "common_name": common_name,
                            "domain": domain_id,
                            "domain_name": definition["name"],
                            "status": item["status"],
                            "gap": gap,
                            "ledger_path": path.as_posix(),
                        },
                    )
                )
    return records
