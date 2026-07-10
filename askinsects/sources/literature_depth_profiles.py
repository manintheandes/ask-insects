"""Paper-depth (extracted-facts) profiles for every literature lane that lacks
a primary miner, per the insectsource mandatory-mining rule.

One profile per literature source (its own output source id, the source's species,
and the species-appropriate fact families). Reuses the generic extracted-facts
engine with no engine changes. Registry is keyed by output source id so a generic
ingest can run any one (or all) of them.
"""

from __future__ import annotations

from askinsects.sources.extracted_facts import (
    ExtractedFactsProfile,
    FACT_FAMILIES,
)
from askinsects.sources.repellency_facts import REPELLENCY_ASSAY_FACT_FAMILY
from askinsects.sources.drosophila_suzukii_extracted_facts import (
    DROSOPHILA_SUZUKII_FACT_FAMILIES,
)


def _profile(
    *, output: str, input_source: str, species: str, families, prefix: str
) -> ExtractedFactsProfile:
    return ExtractedFactsProfile(
        source_id=output,
        input_literature_source_id=input_source,
        species_name=species,
        label=f"{species} — depth mining of {input_source}",
        record_prefix=prefix,
        raw_subdir=output,
        fact_families=families,
    )


MOSQUITO_REPELLENT_FACT_FAMILIES = (*FACT_FAMILIES, REPELLENCY_ASSAY_FACT_FAMILY)


LITERATURE_DEPTH_PROFILES = {
    "mosquito_repellent_literature_extracted_facts": _profile(
        output="mosquito_repellent_literature_extracted_facts",
        input_source="mosquito_repellent_literature",
        species="Culicidae",
        families=MOSQUITO_REPELLENT_FACT_FAMILIES,
        prefix="mosq_repellent_lit_fact",
    ),
    "mosquito_repellent_external_discovery_extracted_facts": _profile(
        output="mosquito_repellent_external_discovery_extracted_facts",
        input_source="mosquito_repellent_external_discovery",
        species="Culicidae",
        families=MOSQUITO_REPELLENT_FACT_FAMILIES,
        prefix="mosq_repellent_ext_fact",
    ),
    "aedes_crossref_literature_audit_extracted_facts": _profile(
        output="aedes_crossref_literature_audit_extracted_facts",
        input_source="aedes_crossref_literature_audit",
        species="Aedes aegypti",
        families=FACT_FAMILIES,
        prefix="aedes_crossref_fact",
    ),
    "aedes_olfaction_literature_extracted_facts": _profile(
        output="aedes_olfaction_literature_extracted_facts",
        input_source="aedes_olfaction_literature",
        species="Aedes aegypti",
        families=FACT_FAMILIES,
        prefix="aedes_olfaction_fact",
    ),
    "drosophila_suzukii_pubmed_literature_extracted_facts": _profile(
        output="drosophila_suzukii_pubmed_literature_extracted_facts",
        input_source="drosophila_suzukii_pubmed_literature",
        species="Drosophila suzukii",
        families=DROSOPHILA_SUZUKII_FACT_FAMILIES,
        prefix="swd_pubmed_fact",
    ),
}
