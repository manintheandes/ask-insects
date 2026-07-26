from __future__ import annotations

from askinsects.records import EvidenceRecord, Provenance


ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID = "anopheles_primary_evidence"
ZANZIBAR_INFECTIOUS_BITING_RECORD_ID = (
    "anopheles_primary:doi:10.1186/s12936-025-05333-6"
)
TANZANIA_INFECTIOUS_BITING_RECORD_ID = (
    "anopheles_primary:doi:10.1371/journal.pgph.0003864"
)
KNOWLESI_DIRUS_RECORD_ID = "anopheles_primary:doi:10.1186/s13071-024-06500-5"


def build_anopheles_primary_evidence_records(
    *, retrieved_at: str
) -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            record_id=ZANZIBAR_INFECTIOUS_BITING_RECORD_ID,
            lane="literature",
            source=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
            title=(
                "Early evening outdoor biting by malaria-infected Anopheles "
                "arabiensis vectors threatens malaria elimination efforts in Zanzibar"
            ),
            text=(
                "At ten Zanzibar sentinel sites, mosquitoes were collected monthly "
                "for two consecutive nights from October 2022 through September 2023 "
                "using hourly indoor and outdoor human landing catches from 18:00 to "
                "06:00. Malaria-parasite-infected Anopheles arabiensis bites were "
                "observed outdoors in the early evening (n=10, 18:00-21:00) and "
                "indoors later at night (n=4, 22:00-02:00). These setting-specific "
                "observations support measuring local hourly infectious biting rather "
                "than transferring one universal intervention schedule."
            ),
            species="Anopheles arabiensis",
            url="https://doi.org/10.1186/s12936-025-05333-6",
            media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
                locator=(
                    "https://link.springer.com/article/10.1186/"
                    "s12936-025-05333-6#Sec2"
                ),
                retrieved_at=retrieved_at,
                license="Open-access primary study; source terms apply",
                source_url="https://doi.org/10.1186/s12936-025-05333-6",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
        EvidenceRecord(
            record_id=TANZANIA_INFECTIOUS_BITING_RECORD_ID,
            lane="literature",
            source=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
            title=(
                "A matter of timing: Biting by malaria-infected Anopheles mosquitoes "
                "and the use of interventions during the night in rural south-eastern "
                "Tanzania"
            ),
            text=(
                "In south-eastern Tanzania, hourly indoor and outdoor human landing "
                "catches ran from 18:00 to 06:00. Plasmodium falciparum sporozoites "
                "were detected by ELISA. For Anopheles arabiensis, 17 of 7,442 tested "
                "indoor mosquitoes were infected and 0 of 1,044 tested outdoor "
                "mosquitoes were infected. Small infected counts and local human and "
                "vector behavior limit transfer of this schedule to other settings."
            ),
            species="Anopheles arabiensis",
            url="https://doi.org/10.1371/journal.pgph.0003864",
            media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
                locator=(
                    "https://journals.plos.org/globalpublichealth/article"
                    "?id=10.1371/journal.pgph.0003864#sec013"
                ),
                retrieved_at=retrieved_at,
                license="CC BY 4.0",
                source_url="https://doi.org/10.1371/journal.pgph.0003864",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
        EvidenceRecord(
            record_id=KNOWLESI_DIRUS_RECORD_ID,
            lane="literature",
            source=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
            title=(
                "Human-to-Anopheles dirus mosquito transmission of the "
                "anthropozoonotic malaria parasite, Plasmodium knowlesi"
            ),
            text=(
                "Laboratory-reared female Anopheles dirus were fed through a membrane "
                "on Plasmodium knowlesi-infected blood from one symptomatic patient. "
                "On day 7, 2 of 745 dissected mosquitoes had midgut oocysts (0.27%). "
                "On day 14, 3 of 694 had salivary-gland sporozoites (0.43%), confirmed "
                "as P. knowlesi by nested PCR. This demonstrates low-frequency "
                "infection under one laboratory feed; it does not show that reducing "
                "approaches to human odor blocks transmission."
            ),
            species="Anopheles dirus",
            url="https://doi.org/10.1186/s13071-024-06500-5",
            media_url=None,
            provenance=Provenance(
                source_id=ANOPHELES_PRIMARY_EVIDENCE_SOURCE_ID,
                locator=(
                    "https://link.springer.com/article/10.1186/"
                    "s13071-024-06500-5#Sec8"
                ),
                retrieved_at=retrieved_at,
                license="CC BY 4.0",
                source_url="https://doi.org/10.1186/s13071-024-06500-5",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
    ]
