# Generic Insect Evidence Package Design

## Objective

Publish a small, versioned package of public insect evidence that any consumer
can use without knowing who the consumer is or what private work it performs.
The package must remain useful for spotted wing drosophila, `Aedes aegypti`,
and diamondback moth, while failing closed when direct evidence is absent.

## Chosen Approach

Three approaches were considered:

1. Keep consumer-specific assay names in Ask Insects. This is rejected because
   it couples the public repository to one private system and makes independent
   reuse difficult.
2. Publish a generic evidence package and let each consumer own its mappings.
   This is the selected approach because the boundary is one-way, inspectable,
   and independently testable.
3. Let consumers send private experiment details to Ask Insects at request
   time. This is rejected because it creates a privacy path and makes private
   workflows depend on public-service availability.

## Boundary

The only supported data flow is:

```text
public Ask Insects source index
-> generic signed evidence package
-> any downstream consumer
```

Ask Insects does not contain consumer names, private identifiers, private assay
families, private mappings, private source paths, or consumer-specific routing.
The package request has no experiment parameters and the service receives no
consumer data.

The public repository owns:

- public insect and product-program records
- generic biological and assay concepts
- direct-evidence eligibility rules
- public provenance
- package schema, validation, and signing

Each consumer owns:

- private experiment identifiers and records
- mappings from private labels to public concepts
- private metric definitions and interpretation rules
- rollout flags and private release decisions

## Public Contract

The new schema is `ask-insects-evidence-package.v2`. The CLI command and hosted
endpoint remain `context-package` during migration, but their output is generic.
The package contains:

- `schema_version`, `package_version`, and `content_sha256`
- `generated_at` and a source-index snapshot receipt
- public knowledge domains
- generic evidence contexts
- public insect-program records
- eligible public evidence records
- selector receipts and explicit gaps

Generic evidence contexts describe observable concepts, not private assay
names. The initial contexts are:

- `treated_area_contact_avoidance`
- `treated_area_noncontact_avoidance`
- `bounded_choice_orientation`
- `oviposition_choice`
- `human_landing_response`
- `spatial_behavior`
- `post_exposure_behavior`

Each context declares its endpoint family, exposure routes, required knowledge
domains, what it measures, what it cannot establish, alternative explanations,
and the evidence that could distinguish those explanations.

## Direct Evidence Eligibility

A record is exportable only when both its focal taxon and its context relevance
are directly confirmed from trusted semantic fields.

The exporter must not treat any of these as direct confirmation by themselves:

- the `records.species` database label
- a search query, search term, topic tag, or inclusion path
- a source name that contains a species name
- a generated title that was added by the extractor
- a hard-coded `primary_taxon` field without supporting source text

Each selector declares trusted field paths. The exporter reads only those paths
when deciding eligibility. Examples include an upstream paper title, abstract,
source-table row, dataset title, or extracted evidence passage. Search metadata,
references, and raw payload fields outside the allowlist are ignored.

### Taxon Assertion

At least one trusted field must contain a configured exact scientific name or
common-name alias for the focal taxon. The assertion records:

- focal species id and scientific name
- matched alias
- exact trusted field path
- a short supporting excerpt
- assertion method and ruleset version

For derived facts, the exporter checks both the fact passage and the upstream
source record. A derived fact is rejected when its upstream paper is about a
different organism, even if the derived row was stored under the focal species.

### Context Assertion

At least one trusted field must also contain a term or structured value that
directly matches the public context. A paper found by a repellency search does
not qualify unless the paper title, abstract, fact passage, or structured assay
fields actually describe the required behavior or assay concept.

Each exported evidence record contains an `eligibility` object with separate
`taxon` and `context` assertions. The package validator independently checks
their shape and confirms that the asserted species and context match the
selector receipt.

### Rejected Records

Rejected candidates are not silently dropped. Each selector reports counts by
rejection reason, including:

- `taxon_not_directly_confirmed`
- `context_not_directly_confirmed`
- `upstream_record_missing`
- `trusted_field_missing`
- `public_provenance_missing`

If no eligible records remain, the package contains an explicit selector gap.
Evidence from another species is never substituted.

## Public Provenance And Privacy

Every exported record must include a public source id and a stable, externally
meaningful locator. Absolute machine paths such as `/home/...` and private URI
schemes are forbidden in the package.

When an indexed record has both a local raw-artifact path and a public source
URL, the exporter uses the public URL and preserves the useful row, page, cell,
or JSON fragment. It also includes the Ask Insects record id so the exact
indexed atom remains identifiable.

The validator walks the complete package and rejects:

- absolute filesystem paths
- non-public network schemes
- credentials, bearer tokens, or secret-shaped fields
- consumer-specific fields or names
- missing public source ids or locators
- unknown top-level fields
- strings, arrays, or packages above declared size limits

The canonical SHA-256 excludes only `generated_at`. All scientific content,
eligibility assertions, selector receipts, and provenance are signed.

## Determinism

Selection remains bounded and ordered. Candidates are scored only from trusted
semantic fields, then sorted by score and record id. Grouped selectors may read
a source once, but each selector keeps its own limit and receipt.

The same source index, config, and package version must produce the same hash.
Changing an eligibility rule requires a new package version and ruleset version.

## Compatibility And Migration

The old v1 schema and consumer-specific config are removed from active product
surfaces. The generic config becomes `config/insect-evidence-package.json`.
Active README, source-map, query docs, CLI help, and completion checks describe
only the generic package.

Downstream consumers must explicitly adopt v2. A v1 consumer receives a schema
mismatch and keeps its previously verified snapshot. There is no silent schema
translation.

## Verification

Tests must prove:

- the known tick, beetle, generic fruit-fly, and unrelated-insect records are
  rejected from SWD output
- direct SWD, Aedes, and DBM evidence is retained when available
- taxon and context assertions name exact trusted fields
- a false database species label cannot bypass semantic checks
- selector gaps include rejection counts and reasons
- local machine paths and consumer-specific strings cannot enter the package
- public locators retain row, page, cell, or record grain
- package hashes are deterministic
- a clean public clone builds and validates the package without any private
  repository, credential, configuration, or service
- the full Ask Insects regression suite and `scripts/verify_complete.py` pass

The hosted release is complete only after the generic package endpoint returns
v2, its hash matches the deployed source snapshot, and live SWD, Aedes, and DBM
package inspections show direct evidence or explicit honest gaps.
