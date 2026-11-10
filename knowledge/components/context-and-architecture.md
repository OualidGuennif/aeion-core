---
type: Reference
title: "Æion Factory integration choices"
description: "The narrow upstream practices retained for context safety and skills, and the AxiomSpec method that replaced Graphify and Archify in 3.0."
status: stable
generated:
  by: aeion-factory/3.0
  at: 2026-11-10
sources:
  - id: context
    resource: ../operations/context-safety.md
    title: "Actual context contract"
  - id: architecture
    resource: factory-architecture.md
    title: "Complete architecture specification"
  - id: method
    resource: ../axiomspec/index.md
    title: "The AxiomSpec method and its implementation"
---

# Integration choices

The approved plan preserves Doc / OKF / Knowledge, frontmatter/tags, Æion Factory skill entry points,
existing hooks and the reviewed task flow. Current behavior belongs to the linked runbooks and
architecture specification; this file records the integration choices rather than a second policy.

## Context-mode

[Inspected source](https://github.com/mksglu/context-mode/tree/8b74cbba68a79e45170dd5866dee949fd6ddd8e1).
Retain bounded output, processing large results in code, file artifacts and handover restoration.
No upstream code/MCP/memory store is installed. Its best-effort snapshot is not a deterministic
250k/300k token guard. Æion Factory uses native compaction at 250k, explicit closure and a verified
checkpoint; the 300k forced compaction is not qualified pre-request admission. Strict execution
refuses instead of claiming an unsupported guarantee.

## Superpowers

[Inspected source](https://github.com/obra/superpowers/tree/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b).
Add focused debugging; strengthen the existing plan, test, sign-off and review procedures.
Reproduction, one falsifiable hypothesis, meaningful regression evidence and fresh verification
add value. Existing build/spec/review/ship behavior already covers much of the rest. Do not add
the global bootstrap, mandatory implementer/reviewer rounds or a second task ledger. Worktrees
and additional agents remain justified by actual independent work, not enabled by default.
Adapted material retains its MIT attribution in CREDITS and the accompanying notice.

## AxiomSpec instead of Graphify and Archify (3.0)

Up to 2.1, a pinned Graphify extracted a structural code graph and Archify rendered source-backed
diagrams; both needed a virtual environment, Node 18+ and a Chrome browser. 3.0 removes them. The
[AxiomSpec](../axiomspec/index.md) method supplies what they were for, from declared data instead of
extraction alone, and [`tools/axiom`](axiom-toolkit.md) implements it with Python's standard library:

- **The canonical source** is `knowledge/spec/spec.json`: goals, terms, requirements, decisions, constraints,
  scenarios, tests and bindings with stable IDs. Knowledge docs keep their eight sections and
  `sources`, code keeps its `Spec:` header, and both now point at canonical IDs.
- **The graph** joins spec, docs and code: declared links, bindings resolved to `file:line` in a hashed
  snapshot, Python imports from `ast`, ECMAScript imports from a lexical scan. Every edge says how it
  is known (declared, resolved, static); calls and dynamic loading are a stated limit.
- **Diagrams** are structured JSON views rendered to SVG by the toolkit: the system, process,
  sequence and use-case families of the playbook, plus state models taken from the spec. Each states
  whether it is proposed, intended or observed.
- **No model** enters validation, the graph or the docs. A model proposes `spec.json` changes; the
  gates decide.

Rejected: keeping Graphify as an optional extra (two graphs that disagree, and an install the owner
asked to drop); Mermaid or PlantUML rendering (a browser or Java at build time, and label text that is
diagram syntax). The cost of the choice is a lexical extractor for ECMAScript and no type-resolved
call graph; both are named in every query's limits.

No new database, service, scheduler, provider router or agent orchestration layer is introduced.
