"""Extracted-facts (paper-depth mining) profiles for the Elicit discovery lanes.

Per the insectsource paper-completeness contract, every literature lane must be
mined. These profiles point the generic extracted-facts engine at the Elicit
discovery sources so each discovered paper gets a depth outcome, reusing the
existing per-species fact families (no engine changes).
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

DROSOPHILA_SUZUKII_ELICIT_EXTRACTED_FACTS_PROFILE = ExtractedFactsProfile(
    source_id="drosophila_suzukii_elicit_extracted_facts",
    input_literature_source_id="drosophila_suzukii_elicit_discovery",
    species_name="Drosophila suzukii",
    label="Drosophila suzukii (spotted wing drosophila) — Elicit discovery",
    record_prefix="swd_elicit_extracted_fact",
    raw_subdir="drosophila_suzukii_elicit_extracted_facts",
    fact_families=DROSOPHILA_SUZUKII_FACT_FAMILIES,
)

AEDES_AEGYPTI_ELICIT_EXTRACTED_FACTS_PROFILE = ExtractedFactsProfile(
    source_id="aedes_aegypti_elicit_extracted_facts",
    input_literature_source_id="aedes_aegypti_elicit_discovery",
    species_name="Aedes aegypti",
    label="Aedes aegypti — Elicit discovery",
    record_prefix="aedes_elicit_extracted_fact",
    raw_subdir="aedes_aegypti_elicit_extracted_facts",
    fact_families=(*FACT_FAMILIES, REPELLENCY_ASSAY_FACT_FAMILY),
)

ELICIT_EXTRACTED_FACTS_PROFILES = (
    DROSOPHILA_SUZUKII_ELICIT_EXTRACTED_FACTS_PROFILE,
    AEDES_AEGYPTI_ELICIT_EXTRACTED_FACTS_PROFILE,
)
