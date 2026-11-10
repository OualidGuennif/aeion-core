---
type: Component
title: "Spec studio"
description: "Section 2: a feature document becomes one goal of a product's AxiomSpec specification, checked by the template's gates, completed through an interview with the owner, and exported as the eight-section feature file aeion-observability builds."
status: stable
sources:
  - resource: ../../app/aeion/specstudio.py
    title: "Drafting, checks, interview, patches, approval, export"
  - resource: ../../app/aeion/profiles/aeion-observability.json
    title: "Export profile (frontmatter and section texts)"
  - resource: ../../app/aeion/profiles/aeion-observability-target.json
    title: "Build-factory rules (areas, phases, scopes, delivery steps)"
  - resource: ../../tools/axiom/spec.py
    title: "The template's gates"
  - resource: ../../tools/axiom/docs.py
    title: "Feature export and product documentation"
  - resource: ../../app/tests/test_sections.py
    title: "Studio tests"
---

# Spec studio

## Intent

Turn an agreed feature into a contract a build factory can implement and verify without asking anyone.
Deterministic gates decide whether it is ready; the owner decides what only the owner can.

## Data sources

The saved feature document; the product's `knowledge/spec/spec.json` in the workspace; the build
factory's catalog `demo/forum/features/MANIFEST.json` and `demo/forum/ARCHITECTURE.md` in
aeion-observability, read only, to choose the next free ID, check dependencies and bind the
architecture digest.

## Inputs

The analyst agent's fragment (goal, terms, requirements, decisions, assumptions, tests, components,
export fields); the owner's answers, one question at a time; export settings; discussion and changes.

## Outputs

Draft nodes and typed edges in the product specification; on approval, the nodes become active and
`exports/<id>-<slug>.md` plus its `.manifest-row.json` are written in the product folder; the product's
pages and diagrams regenerate.

## Invariants

- Code assigns IDs and edges; a fragment's local keys never become IDs.
- Every fragment and patch is merged into a scratch copy and checked before it is accepted.
- No agent answers a decision or validates an assumption; only the owner's answer does.
- The export is refused unless the design gates pass, every blocking question is answered, the file is
  at most 12,000 bytes, carries acceptance checks, has the eight sections and follows the build
  factory's scope rules (literal paths under its product roots, no hidden or parent components).
- aeion-core never writes into aeion-observability.

## Determinism

The same specification and export settings always produce the same feature file and manifest row.

## Acceptance checks

- [ ] An approved feature's file loads in aeion-observability's own catalog loader with its contract current.
- [ ] A blocking decision keeps the feature out of `ready`.

## Out of scope

Implementing the feature, which is aeion-observability's work.
