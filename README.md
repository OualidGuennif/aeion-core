# Æion Core

From a half-baked feature idea to the feature file a build factory implements, in one local web page.

1. **Brainstorm.** The Elephant questions the idea until it is clear, then seven fresh Goldfish
   reviewers attack it and a synthesizer writes the concepts brief
   ([Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model)). Design documents
   are drafted section by section and reviewed in five stages.
2. **Spec studio.** A saved feature document (or one you drop) becomes AxiomSpec obligations in the
   product's canonical `knowledge/spec/spec.json`. The template's deterministic gates check every
   draft; the analyst fixes what fails; you answer what only you can decide, one question at a time.
   On approval it exports the eight-section Markdown file and manifest row that
   [aeion-observability](https://github.com/OualidGuennif/aeion-observability) builds.
3. **Docs.** Every document in one tree with search, pages with their system, process, sequence and
   use-case diagrams, and an assistant that answers from the pages and the AxiomSpec knowledge graph
   with citations it cannot invent.

Every model call runs as a dedicated [Flue](https://flueframework.com/) agent (twelve roles, each with
its own tools and skill) on OpenCode Go's `deepseek-v4.1-flash`, reasoning at its maximum.

## Run it

Requirements: Python 3.11+, Node.js 22.19+ (for the agents), an [OpenCode Go](https://opencode.ai/) key.

```bash
cd app/flue && npm ci && cd ../..          # the agent harness, once
echo 'OPENCODE_API_KEY=...' > .env         # or app/aeion/.env; never committed
python3 app/serve                          # http://127.0.0.1:8765
```

`AEION_LLM=mock python3 app/serve` runs offline with scripted agents. Settings: `AEION_DATA`
(workspace, default `workspace/`), `AEION_OBSERVABILITY` (default `../aeion-observability`, read only),
`AEION_PORT`, `AEION_HOST`, `AEION_MODEL`.

## How it is built

| Part | Where | Spec |
| --- | --- | --- |
| Web server, store, page | `app/aeion/server.py`, `store.py`, `app/web/` | [aeion-engine](knowledge/components/aeion-engine.md) |
| Flue agents, gateway, skills, tools | `app/aeion/agents.py`, `app/flue/` | [aeion-agents](knowledge/components/aeion-agents.md) |
| Brainstorm, design, Goldfish review | `app/aeion/brainstorm.py`, `design.py`, `goldfish/` | [goldfish](knowledge/components/goldfish.md) |
| Spec studio and export | `app/aeion/specstudio.py`, `app/aeion/profiles/` | [spec-studio](knowledge/components/spec-studio.md) |
| Documentation hub | `app/aeion/docshub.py` | [docs-hub](knowledge/components/docs-hub.md) |
| AxiomSpec toolkit (template) | `tools/axiom/` | [axiom-toolkit](knowledge/components/axiom-toolkit.md) |

The key stays in the Python process: agents reach the model through a loopback gateway with a
per-run token. Nothing is ever written into aeion-observability.

## Tests

```bash
python3 -m unittest discover -s app/tests     # includes one real `flue run` against a scripted upstream
./tools/axiom/axiom check                     # this project's own specification and generated docs
```

Built from [Æion Factory](https://github.com/OualidGuennif/aeion-factory) 3.0.0.
