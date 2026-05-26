---
type: guide
status: guided
publish: true
tags:
  - insects-wiki
  - questions
---
# Question Cookbook

## Species Questions
- "What do we know about Aedes aegypti? Show where the answer came from."
- "Which source records best answer this species question?"
- "Separate proven source facts from source gaps."

## Observation Questions
- "Where has Aedes aegypti been observed this year?"
- "Show Aedes aegypti observations with images in Brazil."
- "Which public source produced these observation records?"

## Image And Video Questions
- "Show indexed Aedes aegypti images with licenses and source URLs."
- "Show OSF FlightTrackAI Aedes aegypti videos."
- "Which behavior datasets include public video or media locators?"

## Genomics Questions
- "What VectorBase genes are indexed for Aedes aegypti?"
- "Which proteins or transcripts are queryable?"
- "What BioSample records include geography, strain, or linked SRA metadata?"

## Neurobiology Questions
- "What neurobiology sources are indexed for Aedes aegypti?"
- "Can we bulk download CATMAID skeleton IDs for Aedes aegypti?"
- "What is still missing for a complete public whole-brain connectome?"

## Research Paper Questions
- "Search Aedes aegypti papers for olfactory receptors."
- "Show mosquito repellent papers since 2020 and separate already indexed papers from new metadata-only candidates."
- "Which repellent datasets or preprints are indexed outside PubMed and Crossref?"
- "What does Ask Insects know about Google Scholar, CABI, PatentsView, and USPTO coverage for mosquito repellents?"
- "Which legal full-text units mention vector competence?"
- "What does the literature say, and what source gaps remain?"

## Public Health Questions
- "What official Aedes aegypti dengue prevention guidance exists?"
- "What does PAHO surveillance say in the indexed report evidence?"
- "Which public-health evidence is guidance, and which is surveillance?"

## Source Questions
- "Which Ask Insects sources are available?"
- "Which source lanes are partial?"
- "What explicit gaps exist for videos, SRA reanalysis, voxel parsing, or connectome data?"

## Richer Multi-Lane Questions
- "Build an evidence map for this question: observations, literature, genomics, and public-health guidance."
- "Explain Aedes aegypti host seeking using behavior, neurobiology, and literature records."
- "Trace this public-health claim back to official guidance, paper evidence, and observation records."
- "Compare what Ask Insects knows from public datasets against what it still cannot prove."

## How A Question Becomes An Answer

```text
User
  asks a normal insect question in Claude Code or Codex
        |
        v
Claude Code or Codex local agent
  sends the chat to its model provider
  Codex -> OpenAI
  Claude -> Anthropic
        |
        v
Model response
  may request local tool use
        |
        v
Local Claude Code or Codex agent
  chooses the Ask Insects path
  uses the installed Ask Insects tool
        |
        v
Ask Insects local tool
  reads local config and token
  builds request JSON
  sends a request to Ask Insects
        |
        v
Ask Insects server
  authenticates the token
  applies routing
  reads verified source indexes
        |
        v
Ask Insects source indexes
  source rows
  locators
  observations
  media
  receipts
  freshness status
  source gaps
        |
        v
JSON result
  source ids + rows/locators + routing + source gaps
        |
        v
Claude Code or Codex local agent
  gives the model the JSON result
  writes a readable answer
        |
        v
User
  sees plain English plus sources
```
