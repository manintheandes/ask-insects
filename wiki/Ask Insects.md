---
title: Ask Insects
type: home
status: current
publish: true
tags:
  - open-insects
  - insects-wiki
  - ask-insects
  - codex
aliases:
  - Open Insects
  - Ask Insects Wiki
  - Ask Insects
sources:
  - ../README.md
  - ../AGENTS.md
  - ../config/insect-intelligence-programs.json
  - ../config/source-map.yaml
  - ../config/reviewed-scientific-evidence.json
  - ../docs/source-lanes.md
  - ../docs/production-path-evaluation.md
---

# Open Insects

Ask Insects is the first tool in Open Insects: an open-source, source-backed insect intelligence system.

Its job is to help researchers understand insects deeply and turn that understanding into safer, better repellents. The first product programs are:

- **SWD crop repellent:** protect crops from spotted wing drosophila, `Drosophila suzukii`.
- **Human mosquito repellent:** protect people from mosquitoes, starting with `Aedes aegypti`.

Diamondback moth, `Plutella xylostella`, is the next crop-pest expansion. It is the proof that the same source-backed system can extend beyond SWD and mosquitoes.

Ask Insects follows a simple contract:

```text
public source artifacts -> mapped source lanes -> parsed indexes -> receipts -> sourced answers or explicit gaps
```

It does not use private Monarch experiment data as evidence. Private R&D systems can use Ask Insects as public context, but private results stay outside Ask Insects.

## What It Contains

Ask Insects is both a Python codebase and a growing public insect evidence system.

- **Ask Insects: a CLI and hosted source plane:** `ask-insects` answers questions from a hosted public source index.
- **Source lanes:** mapped public data sources for taxonomy, literature, observations, images, videos, genomics, neurobiology, behavior, ecology, resistance, surveillance, repellents, and source gaps.
- **Reviewed scientific evidence:** a fast, human-reviewed interpretation layer for ordinary research questions about SWD, Aedes, and DBM.
- **Product portfolio model:** `config/insect-intelligence-programs.json` tracks focal insects, fourteen biology domains per species, eight product-readiness dimensions per product, and explicit evidence gaps.
- **Public evidence package:** a hash-checked generic package that downstream tools can use without receiving private data.
- **Reality Eval gate:** a 50-question black-box evaluation through normal Codex, requiring complete sourced answers under 60 seconds.

The current focal insects are:

- `Drosophila suzukii`: SWD crop-protection and repellency evidence.
- `Aedes aegypti`: human mosquito-repellent and mosquito-intelligence evidence.
- `Anopheles`: a developing malaria-vector intelligence program across major vector species. See [[Anopheles Intelligence]].
- `Plutella xylostella`: diamondback moth expansion evidence.

## Biology Domains

Ask Insects tracks more than "does a compound repel?" It is designed to help explain why an insect behaves the way it does.

The shared biology model includes:

- taxonomy and identity
- sensory world
- brain and neurobiology
- genes and proteins
- body and physiology
- behavior
- egg laying and reproduction
- feeding and host finding
- movement, flight, and navigation
- ecology and species interactions
- chemical response and metabolism
- learning, memory, and internal state
- development and life stage
- adaptation, resistance, and variation

That structure matters because a useful repellent program needs more than a hit in one assay. It needs to distinguish attraction from repellency, contact from non-contact exposure, movement impairment from avoidance, egg-laying effects from survival effects, and lab signals from field protection.

## Product Programs

### SWD Crop Repellent

Ask Insects supports crop R&D questions about:

- oviposition and fruit-choice behavior
- fruit texture, ripeness, injury, microbes, and fermentation cues
- volatile and contact exposure boundaries
- dose response and possible attraction at low dose
- assay controls for mating state, hunger, age, prior egg laying, mortality, and activity
- canopy airflow and plume delivery
- crop-safety and non-target measurements
- field translation from eggs to larvae, crop damage, and marketable fruit

It also indexes SWD source lanes for literature, genomics, monitoring, ecology, flight assays, crop damage, susceptibility, biocontrol, guidance, videos, and source gaps.

### Human Mosquito Repellent

Ask Insects supports mosquito R&D questions about:

- `Aedes aegypti` host seeking
- carbon dioxide, odor, heat, humidity, infrared, and visual cues
- contact irritancy versus spatial repellency
- vapor repellency versus knockdown or toxicity
- internal state after blood feeding
- circadian timing and assay state
- DEET, transfluthrin, citronella, controlled release, and human-skin testing guidance
- dose, release rate, air concentration, distance, duration, sweat, abrasion, washing, and real-use durability

It also indexes Aedes source lanes for public observations, images, videos, literature, neurobiology, genomics, expression, traits, vector competence, resistance, surveillance, public-health guidance, and source gaps.

### Diamondback Moth

DBM is the next expansion proof. Ask Insects currently maps a reviewed public literature lane and scientific topics around:

- host cues and oviposition
- odorant receptors such as PxylOR11 and PxylOR16
- adult and larval endpoint separation
- insecticide-resistance-linked behavior
- plant-extract and semiochemical evidence
- field and crop-damage endpoint design
- gaps that must be closed before calling a DBM repellent crop-protective

## What A Good Answer Should Do

A good Ask Insects answer should:

- answer the research question directly
- cite the exact underlying public source
- include source ID and atomic locator
- separate direct evidence from inference
- keep species, life stage, sex, assay, endpoint, dose, exposure route, duration, and environment distinct
- state source gaps honestly
- avoid turning one assay into a commercial product claim

Examples of questions Ask Insects is built to handle:

```text
What evidence would distinguish learned habituation from inherited resistance to an SWD repellent?

How do we distinguish spatial repellency from contact irritancy in Aedes aegypti?

If an adult diamondback moth repellent changes landing, which larval and crop endpoints should follow before calling it crop protection?
```

## How To Use It

For Josh's current Codex setup, normal questions go through the installed Ask Insects skill and the hosted source plane. The user should ask naturally in Codex.

For local development, the command is:

```bash
ask-insects ask "How do we distinguish spatial repellency from contact irritancy in Aedes aegypti?"
ask-insects ask "where has Aedes aegypti been spotted this year?"
```

Maintenance and development use:

```bash
bash scripts/install_local_runtime.sh
python3 scripts/verify_complete.py
```

`verify_complete.py` checks the repository contract. It does not replace the private 50-question Reality Eval pass and recording.

## Current Boundary

Ask Insects is not a private R&D database and does not claim a finished repellent product.

It is a public evidence system for insect science and product reasoning. It can help decide what to test next, what a result does or does not prove, which source gaps matter, and how to interpret insect behavior without overclaiming.

<!-- publish-bump: 2026-07-22T15:45:00-07:00 -->
