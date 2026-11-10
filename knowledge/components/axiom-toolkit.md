---
type: Component
title: "Axiom toolkit"
description: "tools/axiom: the AxiomSpec engine in Python's standard library. Strict validation and gates, a deterministic knowledge graph over spec, docs and code, bounded queries, context packets, diagrams, the cockpit and test evidence."
status: stable
generated:
  by: aeion-factory/3.0
  at: 2026-11-10
sources:
  - id: cli
    resource: ../../tools/axiom/axiom
    title: "The command line"
  - resource: ../../tools/axiom/strict.py
    title: "Strict JSON transport"
  - resource: ../../tools/axiom/schema.py
    title: "JSON Schema subset validator"
  - resource: ../../tools/axiom/spec.py
    title: "Canonical model, references and gates G01-G07"
  - resource: ../../tools/axiom/bcir.py
    title: "BCIR static analysis and bounded evaluation"
  - resource: ../../tools/axiom/graph.py
    title: "Knowledge graph snapshot"
  - resource: ../../tools/axiom/query.py
    title: "Bounded queries and context closure"
  - resource: ../../tools/axiom/views.py
    title: "Diagram views rendered to SVG"
  - resource: ../../tools/axiom/docs.py
    title: "Cockpit, generated pages and feature export"
  - resource: ../../tools/axiom/evidence.py
    title: "Evidence receipts and implementation gates"
  - resource: ../../tools/axiom/unittest_adapter.py
    title: "Isolated unittest runner"
  - resource: ../../tools/axiom/common.py
    title: "Shared paths, digests and atomic writes"
  - resource: ../../tools/axiom/tests/
    title: "Invariant tests"
  - resource: ../axiomspec/AxiomSpec/README.md
    title: "The AxiomSpec contracts this implements"
---

# Axiom toolkit

## Intent
Make AxiomSpec usable in every project made from Æion Factory, with nothing but `python3`. One
canonical `knowledge/spec/spec.json` holds goals, terms, requirements, decisions, constraints, scenarios,
tests and bindings. The toolkit checks it, joins it with `knowledge/` and the code into one
graph, answers an agent's questions about that graph exactly, and derives the human
documentation. It realizes the `axiom` interfaces that the AxiomSpec contracts only proposed,
and says which capabilities it does not have.

## Data sources
| Source | What is read | Owner | Freshness |
| --- | --- | --- | --- |
| `knowledge/spec/spec.json` | the canonical specification (`axiomspec/0.1`, `AX-CORE-0.1`) | the project | each command |
| `knowledge/axiomspec/AxiomSpec/schemas/` | the four vendored schemas, edition 0.3.0 | vendored | pinned |
| `knowledge/**/*.md` | frontmatter `sources`, `spec_ids`, links and canonical ID mentions | the project | each graph build |
| project files (`git ls-files` + untracked, or a folder walk) | `Spec:` headers, imports (Python `ast`, ECMAScript lexical), symbols, test names | the project | fingerprint (path, size, mtime) |
| `docs/view-catalog.json`, `docs/views/*.json` | diagram sources (`aeion-view/0.1`) | the project | each `views`/`docs` run |
| `docs/feature-catalog.json` | export metadata per goal (`aeion-feature-catalog/0.1`) | the project | each `export` |
| `knowledge/spec/evidence/*.json` | test receipts (`aeion-test-receipt/0.1`) | `axiom evidence run` | checked against current digests |

## Inputs
`tools/axiom/axiom [--root DIR] <command> [options]`; `--spec PATH` overrides `knowledge/spec/spec.json`.

| Command | Does |
| --- | --- |
| `init [--name N] [--owner-role R]` | writes a draft product skeleton, the view and feature catalogs; refuses to overwrite |
| `validate [--phase design\|implementation] [--json] [--report FILE]` | G01-G07 (and G10/G11 for `implementation`) with every diagnostic |
| `evaluate --observations FILE` | BCIR constraints on observation cases against their expectations |
| `graph [--json]` | rebuilds the snapshot in `.aeion/graph/` when inputs changed; prints its summary |
| `query node\|requirement\|impact\|gaps\|find\|deps\|rdeps\|path\|tests\|untested\|spec\|files\|hubs\|status` | bounded answers; `--json`, `--all` |
| `packet (--ids IDS \| --files PATHS) [--budget-bytes N] [--out FILE]` | the mandatory context closure for a change, split when over budget |
| `views [--check]` | renders `docs/views/*.json` to `docs/generated/diagrams/*.svg` |
| `docs [--check]` | regenerates `docs/README.md` (the cockpit) and `docs/generated/` |
| `export --goal ID \| --all [--profile FILE] [--out DIR]` | one feature Markdown per goal: frontmatter and the eight spec sections |
| `evidence run [--ids TEST-...]` / `evidence check` | runs bound `unittest` tests, writes a receipt; checks receipts are current |
| `check` | the commit/CI gate: no G01/G02 error, no dangling ID in `knowledge/` or `docs/`, generated docs current |

## Outputs
- **Exit codes, `validate` and `check`:** 0 pass, 2 fail, 3 unknown, 4 input or processing error
  (the AxiomSpec proposal). **Queries:** 0 an answer (even empty, stated), 3 ambiguous name with
  candidates, 4 nothing matches, 1 the graph cannot be built. Usage errors: 2.
- **Report:** `axiomspec-report/0.2`, valid against the vendored schema; checks sorted by
  `(gate, id, pointer)`; `metadata` holds the only clock value.
- **Diagnostics:** `{gate, code, subject_id, pointer, message}`; codes are stable
  (`DUPLICATE_ID`, `UNKNOWN_TARGET`, `WRONG_EDGE_TYPE`, `UNKNOWN_ACTOR`, `DEPENDENCY_CYCLE`, …).
- **Graph snapshot:** `.aeion/graph/{nodes,edges,symbols,manifest}.json`, sorted, with a
  `snapshot_id` over the deterministic content.
- **Query response:** `snapshot_id`, `items`, `returned_count`, `total_visible_count`,
  `complete`, `omissions`, `analysis_limits` (AX-K-006); text mode prints the same, capped at 40 lines.
- **Generated docs:** `docs/README.md` and `docs/generated/**` with `manifest.json` (input digests,
  generator version, outputs); no timestamp in generated bytes.

## Invariants
| Invariant | Test |
| --- | --- |
| Duplicate keys, floats, NaN, unsafe integers, lone surrogates, non-ASCII keys, trailing data and oversize input are input errors before any schema check (AX-M-001). | `test_strict.StrictTests` |
| The schema subset validator fails closed on an unsupported keyword, never treats `true` as `1`, and anchors `$` at the true end. | `test_schema.SchemaTests` |
| The ten executable conformance vectors V-001..V-010 give their expected gate and outcome. | `test_spec.ConformanceTests` |
| All 45 reference expectations of the ledger observations match; a 500-row uniqueness check exhausts the default budget and is `unknown`, never `pass`. | `test_bcir.LedgerTests` |
| BCIR static analysis rejects unknown paths, shadowing, coercion and unit mismatches before evaluation (AX-C-007). | `test_bcir.StaticTests` |
| A blocking unanswered decision or unvalidated blocking assumption prevents `design_ready` (AX-G-004). | `test_spec.GateTests` |
| Unknown never becomes pass: error > fail > unknown > pass (AX-G-001). | `test_spec.GateTests` |
| The digest of canonical JSON follows AX-G-008, including its escape rules. | `test_common.DigestTests` |
| The same inputs give byte-identical graph files and query answers; the snapshot rebuilds only when an input changed. | `test_graph.GraphTests` |
| A name matches exactly or not at all: ambiguity is exit 3, absence exit 4, nothing is guessed (AX-K-003). | `test_query.QueryTests` |
| Context closure follows AX-K-010; required items are never dropped for budget: the packet splits and stays incomplete until all parts exist. | `test_query.PacketTests` |
| Labels are data: XML and Markdown are escaped, so a requirement title cannot inject markup. | `test_views.ViewTests`, `test_docs.DocsTests` |
| `docs --check` and `views --check` fail when any generated file differs from what the inputs produce. | `test_docs.DocsTests` |
| An exported feature carries `## Acceptance checks` with `- [ ] ` items and stays under the profile's byte limit, or the export fails. | `test_docs.ExportTests` |
| A receipt with zero, duplicate, skipped or failed tests, or with inputs that changed since, cannot satisfy G10/G11. | `test_evidence.EvidenceTests` |
| Malformed input gives a diagnostic or exit 4, never a traceback; gates that did not run are `unknown`; out of an effective window is not pass; a receipt counts for its own test only; `init`, `docs`, `views` and exports never write over, delete or write outside what the generator did not write (dot-files included: only desktop files such as `.DS_Store` or `Thumbs.db`, an editor's swap or backup of a generated file, and the toolkit's own `.axiom-*` temporary files are ignored), and written files keep their mode (a new one gets the umask's); bound tests cannot import a toolkit module. | `test_hardening` |

## Determinism
**deterministic.** Pure functions of the inputs: no clock (except report `metadata` and receipt
`executed_at`), no network, no model. Sorting is by ID, then path, then line. The test runner is
the only process the toolkit starts, and only on `evidence run`: `unittest_adapter.py`, started with
`python -P` so no toolkit module can shadow what the project's tests import, while `PYTHONPATH` and
user site-packages apply as under `python -m unittest`.

## Acceptance checks
```bash
python3 -m unittest discover -s tools/axiom/tests -t . -v
tools/axiom/axiom validate --spec knowledge/axiomspec/AxiomSpec/examples/refund-ledger/spec.json  # G07 fails, as documented
tools/axiom/axiom evaluate --spec knowledge/axiomspec/AxiomSpec/examples/refund-ledger/spec.json \
  --observations knowledge/axiomspec/AxiomSpec/examples/refund-ledger/observations.json
tools/axiom/axiom check
tools/axiom/axiom query status
```

## Out of scope
- A qualified general BCIR compiler beyond the documented subset, or BCIR to OCL/SMT translation.
- Identity, authority and policy attestation (G12) and runtime observation (G13): reported unsupported.
- Type-resolved call graphs: imports and bindings only; reflection and dynamic loading are limits.
- Rendering pixel-identical diagrams across viewers; layout is deterministic, not optimal.
- Any model call. Suggestions from a model enter only as authored `spec.json` changes.
