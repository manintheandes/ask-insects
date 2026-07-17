from __future__ import annotations

from askinsects.records import EvidenceRecord, Provenance


AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID = "aedes_primary_behavior_evidence"


def build_aedes_primary_behavior_evidence_records(
    *, retrieved_at: str
) -> list[EvidenceRecord]:
    sources = (
        {
            "record_id": "aedes_primary_behavior:pubmed:544697",
            "title": (
                "Abdominal distention terminates subsequent host-seeking behaviour "
                "of Aedes aegypti following a blood meal"
            ),
            "text": (
                "The primary study found that abdominal distention immediately "
                "inhibited host-seeking after a replete blood meal. Saline enemas "
                "produced the effect, and anterior abdominal distention was more "
                "effective than posterior distention, implicating anterior stretch "
                "receptors. This source establishes immediate distention-induced "
                "inhibition, not a universal 24-hour duration."
            ),
            "url": "https://doi.org/10.1016/0022-1910(79)90073-8",
            "locator": (
                "https://www.sciencedirect.com/science/article/abs/pii/"
                "0022191079900738#preview-section-abstract"
            ),
            "license": "Publisher abstract metadata; source terms apply",
            "source_kind": "peer_reviewed_primary_study",
        },
        {
            "record_id": "aedes_primary_behavior:pubmed:469272",
            "title": (
                "Humoral inhibition of host-seeking in Aedes aegypti during "
                "oöcyte maturation"
            ),
            "text": (
                "The primary study separated egg development from a blood meal by "
                "using blood enemas. Females that developed eggs were inhibited from "
                "host seeking during egg development, and surgical manipulation plus "
                "haemolymph transfer implicated a haemolymph-borne inhibitory factor."
            ),
            "url": "https://doi.org/10.1016/0022-1910(79)90048-9",
            "locator": (
                "https://www.sciencedirect.com/science/article/abs/pii/"
                "0022191079900489#preview-section-abstract"
            ),
            "license": "Publisher abstract metadata; source terms apply",
            "source_kind": "peer_reviewed_primary_study",
        },
        {
            "record_id": "aedes_primary_behavior:pmc:PMC3794971",
            "title": (
                "Functional and Genetic Characterization of Neuropeptide Y-Like "
                "Receptors in Aedes aegypti"
            ),
            "text": (
                "The study describes three days of post-blood-meal host-seeking "
                "suppression, identifies Head Peptide-I as a candidate signal, and "
                "shows that NPYLR1 null mutants retain normal suppression. NPYLR1 is "
                "therefore a Head Peptide-I receptor but was not required for the "
                "in-vivo behavioral inhibition in this experiment."
            ),
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3794971/",
            "locator": (
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC3794971/#abstract1"
            ),
            "license": "CC BY",
            "source_kind": "peer_reviewed_primary_study",
        },
        {
            "record_id": "aedes_primary_behavior:pmc:PMC9866038:table8",
            "title": (
                "Development of a Nanotechnology Matrix-Based Citronella Oil Insect "
                "Repellent to Obtain a Prolonged Effect and Evaluation of the Safety "
                "and Efficacy"
            ),
            "text": (
                "Table 8 labels N=6 for its Aedes aegypti protection-time results, while "
                "Methods says that four formulations were evaluated on three participants; "
                "the human sample size is unresolved. "
                "F3, a 10 percent total citronella oil formulation containing a 1:1 "
                "mixture of free oil and citronella-loaded nanostructured lipid "
                "carrier, averaged 4.0 +/- 0.0 hours. F1, 10 percent free citronella "
                "oil in the same oil-in-water emulsion base, averaged 0.3 +/- 0.5 "
                "hours. The paper also reports thermal, mass-balance, and skin-permeation "
                "work, but it does not directly measure volatile release rate."
            ),
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9866038/",
            "locator": (
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC9866038/"
                "#life-13-00141-t008"
            ),
            "license": "CC BY 4.0",
            "source_kind": "peer_reviewed_primary_table",
        },
    )
    return [
        EvidenceRecord(
            record_id=str(source["record_id"]),
            lane="literature",
            source=AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
            title=str(source["title"]),
            text=str(source["text"]),
            species="Aedes aegypti",
            url=str(source["url"]),
            media_url=None,
            provenance=Provenance(
                source_id=AEDES_PRIMARY_BEHAVIOR_EVIDENCE_SOURCE_ID,
                locator=str(source["locator"]),
                retrieved_at=retrieved_at,
                license=str(source["license"]),
                source_url=str(source["url"]),
            ),
            payload={
                "source_kind": source["source_kind"],
                "curation_status": "human_reviewed_original_source",
            },
        )
        for source in sources
    ]
