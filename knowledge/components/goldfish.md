---
type: Component
title: "Brainstorm and design (Elephant-Goldfish Model)"
description: "Section 1: the Elephant brainstorms with the owner, seven Goldfish review the anchored hypothesis, the synthesizer writes the concepts brief; design documents are drafted section by section and reviewed in five stages."
status: stable
sources:
  - resource: ../../app/aeion/brainstorm.py
    title: "Brainstorm flow"
  - resource: ../../app/aeion/design.py
    title: "Drafting, staged review, resolution"
  - resource: ../../app/aeion/goldfish/__init__.py
    title: "Reviewers, stages, presets, findings"
  - resource: ../../app/aeion/goldfish/upstream/NOTICE.md
    title: "Vendored Elephant-Goldfish Model (Apache-2.0)"
  - resource: ../../app/tests/test_sections.py
    title: "Section tests"
---

# Brainstorm and design

## Intent

Bring the [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model) into a web page
as a guided menu: the Elephant holds the conversation and stress-tests the idea; each Goldfish is a fresh
agent that sees only the document, so its critique is not anchored by the conversation.

## Data sources

The vendored upstream (personas, document standards, skills) in `app/aeion/goldfish/upstream`, pinned
to the commit named in its `NOTICE.md`; the owner's messages; saved feature documents.

## Inputs

- Brainstorm: an idea, then one owner message per turn. The readiness gate opens when the Elephant
  anchors a hypothesis with its tool; the owner then chooses a Goldfish review or more clarification.
- Design: a saved brief or notes; four sections (Overview & Goals, Technical Plan, Alternatives
  Considered, Detailed Implementation Plan), each approved by the owner.
- Review: a saved document and a preset: interactive (stages 5-9 with a gate after each),
  consolidated, feature spec only (5-8) or implementation plan only (9).

## Outputs

The concepts brief, saved as a feature document; design documents; per-stage reports with
deduplicated findings; resolutions in four categories (CONTEST, ESCALATE, PROPOSE FIX, DECLINE).

## Invariants

- A Goldfish receives its persona, the mode, the standard when one applies and the document, never the
  conversation (test_sections).
- A reviewer that fails twice is reported as "not run", never as zero findings.
- A proposed edit is applied only when its exact text occurs once in the document; the resolver is told
  and corrects it otherwise (test_sections).
- A stage is re-audited at most once after the owner's edits.

## Determinism

Stage order, reviewer sets, standards, line ranges and report layout are fixed in code; only the
reviewers' text varies.

## Acceptance checks

- [ ] A brainstorm reaches an anchored hypothesis, a seven-reviewer brief and a saved feature.
- [ ] A review stage reports findings with their reviewers and line references.

## Out of scope

Editing the upstream personas or standards in place; they are vendored verbatim.
