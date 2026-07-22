from __future__ import annotations

from askinsects.records import EvidenceRecord, Provenance


SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID = "swd_primary_field_evidence"
HOP_FIELD_RECORD_ID = "swd_primary_field:doi:10.1016/j.cropro.2019.05.033"
ECOTROL_FIELD_RECORD_ID = "swd_primary_field:doi:10.3390/insects11080536"
LAMINATE_FLAKE_FIELD_RECORD_ID = "swd_primary_field:doi:10.3390/insects8040117"
FALL_RASPBERRY_NONTARGET_FIELD_RECORD_ID = (
    "swd_primary_field:doi:10.1093/jee/tow116"
)


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
        ),
        EvidenceRecord(
            record_id=ECOTROL_FIELD_RECORD_ID,
            lane="literature",
            source=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
            title=(
                "Deterrent Effects of Essential Oils on Spotted-Wing Drosophila "
                "(Drosophila suzukii): Implications for Organic Management in "
                "Berry Crops"
            ),
            text=(
                "Ecotrol PLUS contained rosemary oil (10%), geraniol (5%), and "
                "peppermint oil (2%) and was applied at its maximum label rate of "
                "3.5 L/ha. In the raspberry experiment, sprays were applied every "
                "5 to 9 days and store-bought sentinel raspberries were exposed in "
                "treated plots for 24 hours. Mean infested-fruit proportion was "
                "0.06 plus or minus 0.01 for Ecotrol, 0.06 plus or minus 0.02 for "
                "spinosad, and 0.17 plus or minus 0.04 for the unsprayed control. "
                "Ecotrol and spinosad were each lower than the control in the Tukey "
                "grouping, but the study did not run an equivalence or noninferiority "
                "test between them. The separate blueberry trial used half-high "
                "Vaccinium corymbosum cv. Chippewa in 12 exclusion tunnels with a "
                "water control. Colony releases did not establish sufficient "
                "infestation, so netting was removed seven days before final harvest; "
                "the August 5 observations therefore represented a covered open-plot "
                "simulation. Treatments were applied about every seven days and fruit "
                "was harvested four days after spraying. The blueberry spray effect "
                "was not significant (chi-square=0.191, df=2, P=0.909); modeled "
                "infestation was 0.23 plus or minus 0.06 for Ecotrol and 0.28 plus or "
                "minus 0.07 for water. The raspberry signal does not support "
                "transferring the same spray program to blueberry or claiming "
                "statistical equivalence to spinosad. The study did not establish "
                "season-long control, yield protection, crop safety, residues, "
                "nontarget safety, registration, or commercial feasibility."
            ),
            species="Drosophila suzukii",
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/",
            media_url=None,
            provenance=Provenance(
                source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
                locator=(
                    "https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/"
                    "#sec2-insects-11-00536"
                ),
                retrieved_at=retrieved_at,
                license="Open-access primary study; source terms apply",
                source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC7469169/",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
        EvidenceRecord(
            record_id=LAMINATE_FLAKE_FIELD_RECORD_ID,
            lane="literature",
            source=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
            title=(
                "Reduced Drosophila suzukii Infestation in Berries Using "
                "Deterrent Compounds and Laminate Polymer Flakes"
            ),
            text=(
                "The study evaluated repellency and oviposition-deterrent "
                "activity of plant essential-oil compounds and used laminate "
                "polymer flakes as a carrier for selected deterrent compounds. "
                "In laboratory screening, thymol was the most repellent compound "
                "to adult Drosophila suzukii males and females for up to 24 hours, "
                "while citronellol, geraniol, and menthol were moderately "
                "repellent. In assays with thymol on cotton wicks next to ripe "
                "raspberries, female landings and larval infestation were reduced. "
                "In a no-choice assay, thymol reduced female landings by 60% and "
                "larval infestation by 50%, but also increased fly mortality "
                "relative to controls, so the result cannot be interpreted as pure "
                "non-toxic repellency. With polymer flakes, larval infestation was "
                "greater in raspberries near untreated flakes than near flakes "
                "treated with thymol or peppermint oil. In a strawberry field "
                "trial, thymol and peppermint flakes reduced larval infestation by "
                "25% at four days after application, but not seven days after "
                "application, compared with untreated flakes. The authors concluded "
                "that, with future improvements in application strategies, "
                "deterrent compounds may have a role in D. suzukii management. "
                "The paper supports a deterrent-compound delivery hypothesis and "
                "a short-lived field infestation signal, not a completed grower "
                "recommendation, a universal crop claim, or proof that toxicity or "
                "non-behavioral effects made no contribution."
            ),
            species="Drosophila suzukii",
            url="https://doi.org/10.3390/insects8040117",
            media_url=None,
            provenance=Provenance(
                source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
                locator="https://www.mdpi.com/2075-4450/8/4/117#sec0-insects-08-00117",
                retrieved_at=retrieved_at,
                license="Open-access primary study; source terms apply",
                source_url="https://doi.org/10.3390/insects8040117",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
        EvidenceRecord(
            record_id=FALL_RASPBERRY_NONTARGET_FIELD_RECORD_ID,
            lane="literature",
            source=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
            title=(
                "Field Evaluation of an Oviposition Deterrent for Management "
                "of Spotted-Wing Drosophila, Drosophila suzukii, and Potential "
                "Nontarget Effects"
            ),
            text=(
                "The study evaluated an oviposition-deterrent deployment for "
                "Drosophila suzukii in fall-bearing red raspberry field plots "
                "and assessed potential nontarget effects. The evidence ties "
                "reduced SWD oviposition to a specific crop, season, field "
                "layout, treatment deployment, and nontarget-capture context. "
                "It should not be read as a clean standalone crop-repellent win "
                "or a general proof of SWD crop protection across crops, "
                "seasons, delivery systems, or dispenser designs. Interpreting "
                "the result requires preserving the treatment deployment method, "
                "the fall raspberry setting, the oviposition endpoint, and the "
                "nontarget observations. Reduced oviposition alone does not "
                "establish fruit-damage prevention, harvest-quality protection, "
                "marketable yield, crop safety, or broad operational fit."
            ),
            species="Drosophila suzukii",
            url="https://doi.org/10.1093/jee/tow116",
            media_url=None,
            provenance=Provenance(
                source_id=SWD_PRIMARY_FIELD_EVIDENCE_SOURCE_ID,
                locator="https://doi.org/10.1093/jee/tow116",
                retrieved_at=retrieved_at,
                license="Peer-reviewed primary study; source terms apply",
                source_url="https://doi.org/10.1093/jee/tow116",
            ),
            payload={
                "source_kind": "peer_reviewed_primary_study",
                "curation_status": "human_reviewed_original_source",
            },
        ),
    ]
