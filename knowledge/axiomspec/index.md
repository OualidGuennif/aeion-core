---
type: Reference
title: "AxiomSpec: the specification method"
description: "The vendored AxiomSpec package (edition 0.3.0) and its two playbooks: what each part is for, how Æion Factory implements it, and what the toolkit found in the example."
status: stable
generated:
  by: aeion-factory/3.0
  at: 2026-11-10
sources:
  - id: package
    resource: AxiomSpec/README.md
    title: "AxiomSpec edition 0.3.0, vendored verbatim"
  - id: toolkit
    resource: ../components/axiom-toolkit.md
    title: "The implementation in tools/axiom"
---

# AxiomSpec

AxiomSpec turns an idea into **one canonical `knowledge/spec/spec.json`**: goals, terms, structured requirements,
decisions, constraints, state models, scenarios, test cases and implementation bindings, each with a
stable ID and typed links. Documentation, diagrams and the knowledge graph are derived from it. Gates
G01-G13 say what has actually been checked; unknown is never pass.

The package below is a verbatim copy (its own manifest hashes are checked by
`tools/axiom/tests/test_package.py`). Æion Factory makes it executable: the commands the package names
`axiom ...` as proposals exist here as [`tools/axiom/axiom`](../components/axiom-toolkit.md), in Python's
standard library only.

## Read by task

| Task | Read |
| --- | --- |
| Start a new product | [New-project playbook](playbooks/01_NEW_PROJECT_AXIOMSPEC.md), then `tools/axiom/axiom init` |
| Recover the meaning of an existing data-heavy product | [Existing-project playbook](playbooks/02_EXISTING_PROJECT_NVIDIA_TO_AXIOMSPEC.md) |
| Write requirements, terms, decisions | [Authoring workflow](AxiomSpec/docs/04_AUTHORING_WORKFLOW.md), [templates](AxiomSpec/docs/15_TEMPLATES_AND_PROMPTS.md) |
| Know every field | [Canonical model](AxiomSpec/docs/03_CANONICAL_MODEL.md), [schema](AxiomSpec/schemas/spec.schema.json) |
| Formalize a rule | [BCIR constraints](AxiomSpec/docs/05_CONSTRAINTS_AND_SEMANTICS.md) |
| Know what a gate proves | [Gates and evidence](AxiomSpec/docs/06_GATES_AND_EVIDENCE.md) |
| Get context for a coding task | [Graph and queries](AxiomSpec/docs/07_KNOWLEDGE_GRAPH_AND_QUERIES.md), [agent contract](AxiomSpec/docs/08_AGENT_CODING_CONTRACT.md) |
| Test and close the loop | [Tests and feedback](AxiomSpec/docs/09_TEST_STRATEGY_AND_CLOSED_LOOP.md) |
| Every normative rule | [Rule index](AxiomSpec/RULE_INDEX.md) |
| The package's own verdict and limits | [Review](AxiomSpec/REVIEW.md), [assurance matrix](AxiomSpec/review/ASSURANCE_MATRIX.md) |

## How the factory implements it

| AxiomSpec increment | Here |
| --- | --- |
| S1 strict parsing, schema, IDs, references, cycles | `axiom validate` (G01, G02) |
| S2 BCIR analysis and bounded evaluation | G03, `axiom evaluate`, G06 |
| S3 decisions, state topology, verification plan | G04, G05, G07 |
| S4 views, graph snapshots, bounded queries | `axiom docs`, `axiom views`, `axiom graph`, `axiom query` |
| S5 change packets and conservative closure | `axiom packet` (AX-K-010) |
| S6 one real test adapter and evidence freshness | `axiom evidence run/check` (unittest), G09-G11 |
| S7 a scoped pilot | the [Holiday Planner demo](https://github.com/OualidGuennif/aeion-factory/tree/main/demo) (in the factory repository; new projects do not ship it) |

Not provided, and reported as unsupported or unknown: trusted identity and policy (G08, G12), runtime
observation (G13), solver adapters and exhaustive state exploration.

## What the toolkit found in the example

Run on the package's refund-ledger example, the toolkit reproduces the package's own results: the
specification digest `1ea4f944…` matches the package report byte for byte, the ten executable
conformance vectors give their expected gate and outcome, and all 45 reference expectations match.
G07 then fails, as the walkthrough says it should. It also reports a rule the package QA never
checked: "its referenced scenarios must illustrate the requirement being verified" (docs/06). Twelve
witness references break it (for example TEST-004 verifies REQ-002 and REQ-003 but cites SCN-003,
which illustrates only REQ-001). These are findings about the example, left unchanged in the copy.

## Known gap in the playbooks

The existing-project playbook links a research note (`../research/auto-ontology-comparison-2026-11-09.md`)
that was not supplied with it. The link is kept as written.

## The package's own QA script

`AxiomSpec/qa/check_package.py` is the package author's release check; it imports `jsonschema` and
`referencing`, pinned in `AxiomSpec/qa/requirements-qa.txt`. It is part of the verbatim copy and
nothing in the template runs it: the toolkit and its tests use the standard library only, and
`tools/axiom/tests/test_package.py` checks the copy's manifest digests and links instead.
