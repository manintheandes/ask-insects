# Ask Insects to Ask Monarch Context Bridge Design

## Objective

Give private Monarch experiments the public insect context needed to interpret
behavior without sending private experiment data to Ask Insects.

The first live bridge covers:

- spotted wing drosophila contact, non-contact, DART, and oviposition work
- `Aedes aegypti` contact, non-contact, DART, arm-in-cage, spatial-affect, and
  post-exposure work
- diamondback moth oviposition as the first reusable expansion case

## Boundary

The data flow is one-way:

```text
public Ask Insects records
-> versioned context package
-> private Ask Monarch source lane
-> private experiment interpretation
```

Ask Insects never receives an experiment id, compound, formulation, result,
video, decision, or other private Monarch field. Ask Monarch stores a copy of
the public package and joins it to private experiments locally.

## Public Package

Ask Insects exposes a read-only `context-package` command and hosted endpoint.
The package is deterministic for a given source index and configuration. It
contains:

- schema and package versions
- source-index snapshot metadata and a canonical content hash
- the public product and species program records
- assay-context definitions that say which knowledge domains matter
- bounded, exact-species public evidence selected for each assay context
- exact source id and locator provenance for every included record
- explicit selector gaps, uncertainty, and directness labels

The package does not claim that selected records prove a private result. It is
context for interpretation, not an efficacy verdict or a mechanism proof.

## Assay Contexts

Each assay context declares:

- supported private assay families and modes
- focal species ids
- measured behavior or endpoint
- required public knowledge domains
- interpretation cautions
- alternative explanations to keep open
- missing evidence that would distinguish those explanations
- bounded public-record selectors

The first contexts are:

- `contact_no_contact`
- `dart_choice`
- `oviposition_choice`
- `arm_in_cage`
- `spatial_affect`
- `post_exposure`

Contact, non-contact, landing, feeding, choice, and egg laying remain distinct.
No context card may turn an observed effect into proof of a receptor, neural
circuit, toxicity pathway, or commercial product claim.

## Species Safety

Every selected scientific record must name the focal species exactly. Records
about another species may only appear in a separately labeled inference section.
The first version omits cross-species inference entirely.

The package includes diamondback moth program gaps even when no exact-species
scientific records satisfy a selector. An empty evidence set is therefore an
explicit source gap, not permission to substitute another moth.

## Determinism And Integrity

Selection uses indexed fields and bounded ordered queries. It never performs an
unbounded literature scan during a request. Duplicate records are removed by
record id. Canonical JSON is hashed with SHA-256 after volatile generation time
fields are excluded.

The package validator rejects:

- an unknown schema version
- duplicate species, context, or record ids
- a record whose species differs from its context
- missing source id or locator provenance
- a selector that silently exceeds its declared limit
- a context that names an unknown species or knowledge domain
- any field reserved for private Monarch data

## Ask Monarch Import Contract

Ask Monarch treats the package as a separate source lane named
`ask_insects_context`. The imported lane must pass the normal source gates:

1. mapped
2. accessible
3. atomically queryable
4. wired to the hosted Ask Monarch surface

Ask Monarch verifies the package hash before parsing it. It preserves every
public locator and records the package version in its receipt.

## Experiment Interpretation

Ask Monarch resolves a private experiment to a scientific species only through
an explicit, versioned assay-family map. An unmapped or ambiguous organism fails
closed.

The interpretation response contains:

- the exact private experiment, treatment, observation, result, and artifact
  provenance used
- the confirmed scientific species and mapping provenance
- what the assay can directly show
- what it cannot establish
- plausible explanations labeled as hypotheses
- known species and product context from Ask Insects
- mismatches and missing metadata for sex, life stage, dose, duration,
  formulation, environment, host or crop, and endpoint
- the next evidence that would separate competing explanations
- exact public source id and locator provenance

The endpoint supports hiding result values. That mode is required for blinded
historical evaluation.

## Evaluation

The historical evaluation uses real registered experiments across SWD,
mosquito, and diamondback moth assay families. Outcomes are hidden while the
baseline and bridge interpretations are produced.

The deterministic rubric scores whether each interpretation:

- names the correct species and assay endpoint
- preserves contact, non-contact, choice, landing, feeding, and egg-laying
  distinctions
- avoids claiming a mechanism is proven
- exposes important missing metadata and confounders
- proposes evidence that could distinguish explanations
- carries complete private and public provenance
- avoids private-data leakage into the public package

The bridge passes only when it improves the aggregate score over the current
Ask Monarch baseline, improves more cases than it worsens, introduces no
unsupported mechanism claims, and has complete provenance in every case.

## Release Gate

The bridge is complete only when:

- the public package endpoint is deployed and returns a valid package
- Ask Monarch has imported and receipted the package
- the hosted interpretation endpoint joins real private experiments locally
- SWD and mosquito cases return useful public context
- the DBM case returns either direct context or an exact, honest gap
- the blinded historical evaluation proves measurable improvement
- both repositories pass their completion and regression checks
