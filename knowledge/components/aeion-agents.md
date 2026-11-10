---
type: Component
title: "Flue agents"
description: "Every model call of aeion-core runs as a Flue agent (deepseek-v4.1-flash, reasoning at max) behind a loopback gateway that holds the OpenCode key, meters usage and serves the agents' tools."
status: stable
sources:
  - resource: ../../app/aeion/agents.py
    title: "Gateway (relay and tool bridge), launcher, mock agents"
  - resource: ../../app/aeion/llm.py
    title: "Errors, meter, TLS trust, schema shapes"
  - resource: ../../app/flue/src/common.ts
    title: "Input blocks, bridge tools, typed submissions"
  - resource: ../../app/flue/src/provider.ts
    title: "Model registration through the relay"
  - resource: ../../app/flue/src/observe.ts
    title: "Event stream read by the server"
  - resource: ../../app/flue/src/db.ts
    title: "In-memory conversation store per run"
  - resource: ../../app/flue/package.json
    title: "Pinned harness versions"
  - resource: ../../app/flue/src/agents/
    title: "The twelve role agents"
  - resource: ../../app/flue/src/skills/
    title: "The seven skills"
  - resource: ../../app/flue/src/tools/
    title: "Tool definitions"
  - resource: ../../app/tests/test_agents.py
    title: "Contract tests, including a real flue run"
---

# Flue agents

## Intent

Run every piece of model work as a dedicated agent with only the tools and the skill its role needs,
on the [Flue](https://flueframework.com/) harness (`@flue/cli` and `@flue/runtime` 2.3.0, on Pi's
`@earendil-works/pi-ai` 1.4.0), with deepseek-v4.1-flash reasoning at its native maximum. Agents
propose; the Python server validates, decides what is stored, and never lets an agent hold the key.

## Data sources

- The OpenCode Go endpoint (`AEION_LLM_URL`, default `https://opencode.ai/inference/go/openai/v1/chat/completions`)
  and `OPENCODE_API_KEY` from the environment or one line of `.env` / `app/aeion/.env`.
- The agent definitions, skills and tools in `app/flue/src/`, installed with `npm ci` in `app/flue`.
  `package.json` overrides the Model Context Protocol packages the harness pins (unused here) to their
  patched releases, so the dependency scan stays clean.

## Inputs

One run per agent turn: `flue run src/agents/<role>.ts --message=<the turn's new text> --new --json`.
Supporting material (documents, earlier conversation, persona name, submission shapes) goes in one
input file that the agent appends once as tagged signals. The message and the input file never carry
the same text: a duplicated payload doubles tokens and gives the model two versions to reconcile.
`agents.single_payload` refuses a run whose blocks repeat the message, and `app/tests/test_agents.py`
proves it on a real run: each marker appears exactly once in the request.

A submit tool's parameters are the server's JSON Schema, converted to Valibot by the agent (`toValibot`),
so the model sees typed fields; the schema is not repeated in the tool's description. A free-form object
invited the model to send nested values as JSON-encoded strings, which the server then refused.

| Agent | Role | Tools | Skill |
| --- | --- | --- | --- |
| `elephant` | brainstorm conversation | `anchor_hypothesis` | `egm-brainstorm` |
| `goldfish` | one fresh reviewer, vendored persona | none | none |
| `synthesizer` | concepts brief | none | `egm-synthesis` |
| `consolidator` | stage findings | `submit_findings` | `egm-synthesis` |
| `drafter` | design document section | `ask_owner` | `egm-draft` |
| `reconciler` | brief versus draft | `submit_reconciliation` | `egm-draft` |
| `resolver` | answers to findings | `submit_resolution` | `egm-resolve` |
| `analyst` | AxiomSpec obligations | `list_catalog`, `submit_fragment`, `amend_fragment` | `axiomspec-authoring` |
| `patcher` | spec changes | `read_record`, `submit_patch` | `axiomspec-authoring` |
| `discussant` | spec discussion | `read_record`, `run_checks` | `axiomspec-authoring` |
| `illustrator` | feature diagrams | `submit_views` | `aeion-views` |
| `librarian` | documentation answers | `search_docs`, `open_page`, `graph_query` | `docs-research` |

## Outputs

The last model turn's text (Flue's envelope joins every turn; earlier turns are discarded), the
accepted submissions, the run's usage and cost as OpenCode reports it, and a stream of events for the
page: text chunks, `restart` when a later turn replaces streamed text, reasoning progress (character
counts, never content) and tool activity.

## Invariants

- The OpenCode key stays in the server process: the agent receives a per-run token valid only on the
  loopback gateway, which refuses unknown tokens and any other model (test_agents). A body whose
  `Content-Length` is not plain digits (400) or exceeds 16 MB (413) is refused before it is read.
- A submission is accepted only when it matches its schema; the deterministic checks then run on a
  scratch copy and their failures go back to the agent as a tool result, at most `attempts` times. An
  amendment (`amend_fragment`) carries only the items that change and is checked as a whole.
- A run whose upstream finish reason is `length` is an error, never a complete answer.
- A required submission missing at the end of a run is an error; plain text is never taken instead.
- Requests carry `reasoning_effort: "max"` and `thinking: {type: "enabled"}` (test_agents).
- Each server tool may be called at most 12 times per run.

## Determinism

Model output varies; what is stored does not depend on it unchecked. Schemas, gates, export rules and
renderers decide. The mock agents (`AEION_LLM=mock`) make every section testable offline.

## Acceptance checks

- [ ] `python3 -m unittest discover -s app/tests` passes, including the real `flue run` when Node and the harness are installed.
- [ ] A live brainstorm turn streams the Elephant's answer and records a hypothesis through the tool.

## Out of scope

Hosting agents remotely, persisting Flue conversations (each run uses in-memory storage), and any
model other than the one configured with `AEION_MODEL`.
