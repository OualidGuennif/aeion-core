---
name: axiomspec-authoring
description: How to write, check and change AxiomSpec obligations for one feature - structured EARS requirements, tests with oracles, terms, decisions and assumptions - so the template's deterministic gates pass and the exported feature file fits the build factory. Use before drafting, patching or discussing a specification.
---

# Author AxiomSpec obligations

A feature becomes one Goal with its Requirements, TestCases, Terms, Components, Decisions and
Assumptions in the product's canonical `knowledge/spec/spec.json`. You propose; code assigns IDs and
links; deterministic gates decide; the owner answers decisions and approves. Local keys (`r1`, `t1`,
`x1`, `d1`, `a1`, `c1`) link items inside one submission; refer to existing records by their IDs.

## Requirements: one obligation each, structured EARS

Code joins the fields into one sentence, so each field must read as part of it:

| Pattern | Sentence | Fields used |
| --- | --- | --- |
| ubiquitous | The <subject> shall <response>. | subject, response |
| event | When <trigger>, the <subject> shall <response>. | + trigger |
| state | While <conditions>, the <subject> shall <response>. | + conditions |
| unwanted | If <trigger>, then the <subject> shall <response>. | + trigger (a refusal or failure) |
| optional | Where <feature>, the <subject> shall <response>. | + feature |
| composite | While <conditions>, when <trigger>, the <subject> shall <response>. | + conditions, trigger |

- `subject`: a short noun phrase without "the" (`digest sender`).
- `response`: a lowercase verb phrase completing "shall" (`make exactly one provider call per member and week`).
- `trigger`, `conditions`, `feature`: lowercase clauses (`a run reaches the send step`); no final period.
- Unused `conditions` is `[]`; unused `trigger` and `feature` are `null`. Gate G04 PATTERN_FIELDS
  fails when a pattern's fields are missing or extra.
- The response is observable: what a caller sees or what state results. No technology unless the
  document requires it.

## Tests (gate G07)

- Every `must` requirement has at least one test with an oracle (MISSING_TEST).
- A `high` or `critical` requirement has a normal test (`negative: false`, MISSING_NORMAL_TEST), a refusal
  test (`negative: true`, MISSING_NEGATIVE_TEST) and one `integration` or `e2e` test
  (MISSING_INTEGRATION_TEST). One test may cover several of these.
- An oracle is one sentence derived from the requirement, never from an implementation. A refusal
  oracle asserts that nothing changed.

## Decisions and assumptions (gate G04, the owner's)

- A choice that changes behaviour, rights, data or compatibility and that the document does not settle
  is a Decision: a one-sentence question, 2-4 options, your recommendation, `blocking` when the feature
  cannot be built without it. You never answer it.
- A fact the document assumes but does not establish is an Assumption with a validation method.
- OPEN_BLOCKING_DECISION and UNVALIDATED_ASSUMPTION wait for the owner; they are not yours to fix.
- Never invent product facts: prefer a decision or an assumption to a guess.

## Size: the exported file must stay under 12,000 bytes

At most 7 requirements, 12 tests and 6 terms. One sentence per oracle, definition and claim. A
decision's question is one sentence; its context goes in the rationale, which is not exported.
To shorten, reword long fields first, merge tests that check the same behaviour, and drop only
`should` or `could` items.

## Export fields (the build factory's rules)

2-4 delivery steps of at most 220 characters, each one a concrete, checkable slice; out-of-scope
lines from the document's non-goals; one test-scenario sentence; `area`, `size` and `phase` among the
allowed values given to you. Never name a superseded stack (FastAPI, pytest, "no client framework").

## Changes

A change touches only this feature's records. Update editable fields, replace links (`verifies`,
`implements`, `terms`, `depends_on`, `governs`, `assumed_by`) with complete ID lists, add records with
new local keys, or drop records by ID. Never set a decision's answer or an assumption's state.
