---
type: Component
title: "Documentation hub"
description: "Section 3: every document in one tree with search, pages with the diagrams that concern them, and the librarian agent that answers from the pages and the AxiomSpec graphs with checked citations."
status: stable
sources:
  - resource: ../../app/aeion/docshub.py
    title: "Corpus, search, pages, assistant tools"
  - resource: ../../tools/axiom/graph.py
    title: "Knowledge graph snapshot"
  - resource: ../../tools/axiom/query.py
    title: "Bounded graph queries"
  - resource: ../../app/tests/test_sections.py
    title: "Docs tests"
---

# Documentation hub

## Intent

Make every document findable and every answer traceable: a tree, a ranked search, readable pages with
their diagrams, and an assistant that cites only what its tools returned.

## Data sources

aeion-core's own knowledge and AxiomSpec pages, the vendored Elephant-Goldfish documents, saved feature
documents, and each product's README, generated pages, exports and diagrams.

## Inputs

A search query, a page id (`<root>:<path>`), or a question for the assistant.

## Outputs

Rendered pages with rewritten links and diagram images; ranked sections; an answer with numbered
sources that link to the page section or graph node they came from.

## Invariants

- Search is BM25 over heading sections; the index rebuilds when files change.
- A page is served only from a configured root; diagram assets only from `docs/generated/diagrams/*.svg`.
- Every citation in an answer refers to an evidence item a tool returned in that run; others are dropped
  (test_sections).
- A long page opens as an outline; the assistant then reads one section.

## Determinism

Search ranking and graph queries are deterministic for the same files.

## Acceptance checks

- [ ] A question about a requirement returns its tests and decisions with graph citations.

## Out of scope

Web search and documents outside the configured roots.
