# Current-Year Repellent Literature Repair

## Objective

Make the normal Ask Insects route answer date-bounded repellent-literature
questions such as:

```text
list the most repellent compounds in the literature from papers published this year
```

The answer must resolve the relative date, use only source-plane records from
that publication year, cite exact original sources and locators, distinguish
measured results from metadata candidates, avoid invalid rankings across
incompatible assays, and return through the normal hosted route in under 60
seconds.

## Repair

1. Follow `matched_record_ids` from the repellent metadata lane to public
   full-text units already held under canonical literature records.
2. Mine those full-text units into repellent assay facts while retaining the
   repellent metadata record as the parent and the full-text unit as exact
   provenance.
3. Add a date-aware answer route for current-year repellent compound questions.
4. Return named compounds, outcome-bearing assay facts, bounded coverage, and a
   clear warning that incompatible assays cannot be ranked globally.
5. Refresh the hosted repellent metadata and depth lanes after deployment.

## Verification

- The matched-record full-text regression test passes.
- The exact failed question excludes prior-year papers and returns a sourced
  current-year answer.
- Focused tests, the complete test suite, and `scripts/verify_complete.py` pass.
- The branch is merged and deployed.
- The installed client matches production.
- The exact question and realistic variants succeed through normal hosted
  `ask-insects ask --question-stdin --answer-only` in under 60 seconds.
