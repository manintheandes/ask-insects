from __future__ import annotations

from askinsects.records import EvidenceRecord, Provenance


SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID = "swd_primary_field_evidence"
HOP_FIELD_RECORD_ID = "swd_primary_field:doi:10.1016/j.cropro.2019.05.033"


def build_swd_primary_field_evidence_records(
    *, retrieved_at: str
) -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            record_id=HOP_FIELD_RECORD_ID,
            lane="literature",
            source=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
            title=(
                "Evaluation of hop (Humulus lupulus) as a repellent for the "
                "management of Drosophila suzukii"
            ),
            text=(
                "In a 24-hour greenhouse cage experiment, HOP00 significantly "
                "reduced Drosophila suzukii larval infestation relative to the "
                "untreated control (ratio 0.392, SE 0.095, P=0.0011); HOP03 and "
                "HOP07 showed moderate but nonsignificant reductions. The positive "
                "controls thymol and 1-octen-3-ol also reduced infestation in the "
                "greenhouse. A controlled raspberry field trial did not reproduce "
                "the hop result: neither the hop treatment nor dispenser-applied "
                "positive controls significantly reduced infestation. Across later "
                "commercial raspberry and blackberry trials, soil-applied hop "
                "pellets did not significantly reduce larvae in fruit or trapped-fly "
                "density. Hop varieties had different volatile profiles, and the "
                "reported compound associations were correlational. Short volatile "
                "life, wind dilution, inadequate upper-canopy spread, and fly "
                "adaptation or habituation were proposed as hypotheses rather than "
                "demonstrated causes of field failure. The authors considered larvae "
                "in fruit the reliable infestation endpoint."
            ),
            species="Drosophila suzukii",
            url="https://doi.org/10.1016/j.cropro.2019.05.033",
            media_url=None,
            provenance=Provenance(
                source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
                locator=(
                    "https://bio.kuleuven.be/ento/pdfs/"
                    "reher_etal_cropprot_2019.pdf#page=4"
                ),
                retrieved_at=retrieved_at,
                license="Publisher PDF hosted by KU Leuven; source terms apply",
                source_url="https://doi.org/10.1016/j.cropro.2019.05.033",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        )
    ]
