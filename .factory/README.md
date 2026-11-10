# Droid (factory.ai) configuration for Æion Factory

This folder belongs to Factory's Droid CLI, a separate product from Æion Factory. Only
`settings.json` and this file are tracked: its hooks send Droid's events to the shared Æion Factory
adapter, `tools/agents/hook.py droid`. Droid reads `AGENTS.md` and `.agents/skills` natively.

Æion Factory's own local state (context, loop bodies, the knowledge graph) lives in the ignored
`.aeion/`. An `--isolated` OpenCode profile left in `.factory/opencode` by an older release can move
there once (`mkdir -p .aeion && mv .factory/opencode .aeion/`); other old folders are disposable.
Contract and qualification steps: [agent compatibility](../knowledge/operations/agent-compatibility.md).
