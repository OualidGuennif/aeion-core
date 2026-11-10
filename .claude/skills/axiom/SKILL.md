---
name: axiom
description: Knows a change's obligations and structure before touching code - the canonical spec (knowledge/spec/spec.json) and its gates, then tools/axiom/axiom for exact, deterministic answers (which requirement and doc cover a file, what depends on it, which tests reach it, the mandatory context packet of a change), then targeted reads. Use before changing code, when tracing a flow, choosing tests, or checking design readiness. No language model is involved.
---

# Axiom: the spec, the graph and the gates

## Overview
`knowledge/spec/spec.json` (AxiomSpec) says what the product must do; `tools/axiom/axiom` joins it with
`knowledge/` and the code into one graph and answers exactly, with `file:line`. Every answer names
its snapshot and its limits. Method: `knowledge/axiomspec/index.md`; tool: `knowledge/components/axiom-toolkit.md`.

## When to use
Before editing code you did not just write; before choosing which tests to run; when a feature,
contract or refusal changes; before sign-off. Not for a question the open file already answers.

## Process
1. **Obligations first.** `tools/axiom/axiom query spec <file>`: the docs and canonical IDs covering
   it. `tools/axiom/axiom query requirement REQ-...`: the sentence, its tests, decisions and bindings.
2. **Mandatory context.** `tools/axiom/axiom packet --files <a,b>` (or `--ids REQ-...`): requirements,
   hard project rules, decisions, tests and oracles the change must respect. Read every part. An
   `incomplete` packet names unmapped files: investigate them, never assume no impact.
3. **Structure.** `query rdeps <file> --depth 2` (what breaks), `query tests <file>` (direct import,
   reach, or literal path), `query path <A> <B>` (each hop), `query find <symbol>`, `query hubs`.
   Imports only: a call through an object, reflection or configuration is not an edge; read the code.
4. **Change the spec before the code** when behaviour changes (skill `spec`): then
   `tools/axiom/axiom validate`. A blocking open decision is a question for the owner, never a guess.
5. **After the code.** Bind new code and tests in `spec.json`, run `tools/axiom/axiom evidence run
   --ids TEST-...` for the bound unittest tests, `tools/axiom/axiom docs`, then `tools/axiom/axiom check`.

## Exit codes
Queries: 0 an answer (even empty), 3 ambiguous (candidates listed), 4 not found, 1 graph unavailable.
`validate`/`check`: 0 pass, 2 fail, 3 unknown, 4 input error.

## Rationalizations
| Excuse | Rebuttal |
| --- | --- |
| "I'll grep for it" | Grep finds text, not the requirement, the tests that reach it or the decision that governs it. |
| "The packet is too long" | Required rules are never cut; it splits into parts. Read them all. |
| "Unknown is basically pass" | Unknown blocks the phase that needs it. Say what is missing. |

## Red flags
Editing code a requirement covers without reading the requirement; a dangling ID in a doc;
hand-editing `docs/generated/`; claiming a test ran because it is `implemented` in the spec.

## Verification
- [ ] The packet or the covering requirement was read before the edit.
- [ ] `tools/axiom/axiom check` passes; `validate` states the design readiness honestly.
