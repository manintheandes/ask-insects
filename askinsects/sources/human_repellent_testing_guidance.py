from __future__ import annotations

from askinsects.records import EvidenceRecord, Provenance


HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID = "human_repellent_testing_guidance"


def build_human_repellent_testing_guidance_records(
    *, retrieved_at: str
) -> list[EvidenceRecord]:
    sources = (
        {
            "record_id": "human_repellent_guidance:who:2009.4",
            "title": "Guidelines for efficacy testing of mosquito repellents for human skin",
            "text": (
                "WHO/HTM/NTD/WHOPES/2009.4 provides standardized laboratory and field "
                "procedures for human-skin mosquito-repellent efficacy, application rate, "
                "single-dose evaluation, and comparable protection measurements."
            ),
            "url": "https://www.who.int/publications/i/item/WHO-HTM-NTD-WHOPES-2009.4",
            "locator": (
                "https://iris.who.int/server/api/core/bitstreams/"
                "bf0c03d6-ccf4-428d-a299-23c6a74b2b04/content#page=15"
            ),
            "license": "CC BY-NC-SA 3.0 IGO",
            "source_kind": "official_guideline",
        },
        {
            "record_id": "human_repellent_guidance:epa:810.3700",
            "title": "Product Performance Test Guidelines OPPTS 810.3700: Insect Repellents to be Applied to Human Skin",
            "text": (
                "US EPA OPPTS 810.3700 defines complete protection time and human-subject "
                "efficacy testing. Its subject-preparation controls direct participants to avoid "
                "perspiration and abrading, rubbing, touching, or wetting the treated area, so "
                "the baseline protocol does not itself establish performance after those stresses."
            ),
            "url": "https://www.epa.gov/system/files/documents/2023-12/1d.-oppts-810.3700-guidelines-july-7-2010.pdf",
            "locator": "https://www.epa.gov/system/files/documents/2023-12/1d.-oppts-810.3700-guidelines-july-7-2010.pdf#page=11",
            "license": "United States government publication",
            "source_kind": "official_guideline",
        },
    )
    return [
        EvidenceRecord(
            record_id=str(source["record_id"]),
            lane="guidance",
            source=HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
            title=str(source["title"]),
            text=str(source["text"]),
            species="Aedes aegypti",
            url=str(source["url"]),
            media_url=None,
            provenance=Provenance(
                source_id=HUMAN_REPELLENT_TESTING_GUIDANCE_SOURCE_ID,
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
