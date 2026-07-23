# Public Repellent Evidence Comparison Design

## Objective

Make Ask Insects publish a bounded, structured, source-backed catalog that a
private downstream system can use to compare its own compound list with public
repellent literature without sending private data to Ask Insects.

The first production acceptance question is:

```text
compare the monarch tested compounds we assessed in the last week to repellents identified in the literature
```

Ask Insects does not answer the private part of that question. It publishes the
public evidence needed for a downstream system to make the comparison locally.

## Privacy Boundary

The data flow remains one-way:

```text
public literature
-> hosted Ask Insects source index
-> generic public evidence package
-> private downstream comparison
```

Ask Insects must never receive:

- a private compound list
- a private experiment date or identifier
- a private assay, formulation, result, video, or decision
- a consumer name or consumer-specific mapping

The generic package must be identical for every consumer. The package request
has no body, query parameters, or private headers.

## Public Source Lane

Add a source lane named `reviewed_repellent_evidence`. It contains one atomic
record per reviewed public claim, not one prose answer per question.

Each claim records:

- canonical material identity and exact aliases
- material kind: pure compound, essential oil, defined mixture, or product
- focal species and life stage
- exposure route and assay
- endpoint and effect direction
- reported result and statistical evidence when available
- dose, duration, control, and formulation when available
- directness and evidence relation
- limitations that block overclaiming
- the exact upstream public source id and locator
- DOI, PMID, or other stable public identifier when available
- review status and review date

The lane may include identity records without efficacy evidence, but an identity
record must never be rendered as proof of repellency.

## Chemical Identity Rules

Matching is deterministic and exact after conservative normalization.

- Case, repeated whitespace, and harmless punctuation may be normalized.
- Declared aliases may match their canonical identity.
- `1,4-cineole` must not match `1,8-cineole` or eucalyptol.
- A branded oil must not become a pure constituent.
- A generic essential-oil study may be shown as material-class evidence for a
  branded oil only when it is labeled `related_material`, never `exact_match`.
- Product names with ambiguous composition remain unmatched.
- No edit-distance or embedding-only chemical match is allowed.

## Evidence Relations

Every public claim uses one of these relations:

- `exact_material`: the tested public material matches the canonical material.
- `declared_alias`: the public material uses a verified alias.
- `related_material`: the public evidence concerns the same material class but
  not the same formulation, brand, chemotype, or composition.
- `constituent_only`: the public evidence concerns one constituent of a mixture.
- `identity_only`: identity is established but repellent efficacy is not.

Cross-species evidence is allowed only when the public species is explicit. It
must never be presented as direct efficacy evidence for another species.

## Package Contract

Keep `ask-insects-evidence-package.v3` and add a generic context named
`repellent_compound_comparison`. The package version changes whenever the
reviewed catalog changes.

The context exports reviewed records from `reviewed_repellent_evidence`.
`payload.evidence` is retained as one bounded structured object. It includes the
chemical identity, assay dimensions, result, limitations, and exact supporting
public provenance.

The package continues to fail closed for:

- missing upstream records
- missing exact public locators
- unreviewed claims
- ambiguous species or material identity
- unsafe paths, credentials, or private markers
- selector overflow or package size overflow

## Source Gaps

A downstream consumer may report:

- `no_exact_catalog_match`
- `identity_only_no_repellency_evidence`
- `related_material_only`
- `cross_species_only`
- `assay_not_comparable`

These statuses describe the checked public catalog. They do not prove that no
paper exists anywhere.

## Verification

Tests must prove:

- exact aliases resolve deterministically
- cineole isomers remain distinct
- oils, constituents, and products remain distinct
- every efficacy claim has exact upstream public provenance
- identity-only rows cannot become efficacy evidence
- private or consumer-specific fields cannot enter the source lane or package
- the package retains the structured evidence object
- the existing package and Ask Insects completion checks still pass
- the hosted package returns the new context and reviewed records

## Release Gate

The Ask Insects side is complete only when:

- the reviewed public lane is ingested on the hosted source plane
- the package is generated from that hosted index
- the package is committed and pinned by exact content and file hashes
- the hosted endpoint serves that exact package
- the downstream private system imports it without sending private data
- the original natural-language acceptance question is answered completely
  downstream with exact public and private provenance in under 60 seconds
