---
type: Reference
title: "Sources behind Æion Factory"
description: "The research, docs and tools the guide's recommendations rest on, with links."
status: stable
review_after: 2027-01-29
generated:
  by: aeion-factory/1.0
  at: 2026-10-20T00:00:00Z
sources:
  - id: credits
    resource: ../../CREDITS.md
    title: "Credits"
---

Æion Factory is an orchestration layer over other people's ideas and tools. Thank you.

## Tools and plugins

- **Anthropic, Claude Code and its official plugins** — `hookify` (hook rules from Markdown and from
  conversation corrections), `skill-creator` (skill drafting, evals, description optimization),
  `claude-security` (verified security scans of a codebase or a change), and the LSP plugin format.
  https://github.com/anthropics/claude-plugins-official · https://code.claude.com/docs
- **Addy Osmani, `agent-skills`** (MIT) — the skill anatomy (overview, when to use, process,
  rationalizations, red flags, verification) and the DEFINE → PLAN → BUILD → VERIFY → REVIEW → SHIP
  lifecycle that Æion Factory's skills follow. https://github.com/addyosmani/agent-skills ·
  "Own the Outer Loop" (2026).
- **Vectorize, Hindsight** (MIT) — agent memory with retain, recall and reflect.
  https://github.com/vectorize-io/hindsight
- **The language servers:** Microsoft TypeScript 7 (native `tsc --lsp`), Deno's built-in server,
  Eclipse JDT Language Server.
- **Superpowers** informs the focused debugging, planning, test, verification and review updates;
  **context-mode** informs bounded output and recovery without bundling its runtime.
- **AxiomSpec** (edition 0.3.0, vendored in [knowledge/axiomspec](../axiomspec/index.md)) supplies
  the canonical specification format, gates, graph and query contracts that `tools/axiom` implements.

## Research and practice

- Chroma, *Context Rot* (2025) — long inputs degrade every model measured.
- Gloaguen et al., context files and agent success (arXiv 2602.11988, 2026).
- Lulla et al., AGENTS.md and agent runtime (arXiv 2601.20404, 2026).
- Anthropic, *Effective context engineering for AI agents* (2025).
- Doc-to-code trace links with LLMs (arXiv 2506.16440, 2025).
- Microsoft Learn, the developer inner and outer loop.
- Cyrille Martraire, *Living Documentation*.
- Robert C. Martin, *ub-mode* — the three passes and the build principles of the engineering
  policy, adapted in our own words. https://github.com/unclebob/ub-mode
- OWASP cheat sheets: secrets management, database security.
- GitHub docs: security policies, CODEOWNERS.

Mistakes in how these ideas are combined here are ours, not theirs.

## Bounded skill maintenance sources

Native skill enrichment and the passive, versioned `skills/` pool use only ECC, Addy Osmani
agent-skills, Anthropic claude-plugins-official and knowledge-work-plugins. The pool catalog
records exact commits, copied resource hashes and nearest license files. CREDITS retains
attribution; plugin-specific restrictions override repository-level licenses. Ten proprietary
Claude Security definitions are metadata-only, not materialized for cross-host use.
No model, automatic agent-launch obligation or generic quality threshold is imported.

Three ECC resource lines have reviewed, rule-specific scanner annotation comments. Their
exact original file hashes, locations and reasoning are in tools/skills/annotations.json;
the catalog retains original and materialized hashes. Other findings and changed source
files are not suppressed, and the complete pool remains in SAST scope.

Two resources change behavior through reviewed security patches in tools/skills/patches.json,
each bound to the exact original file hash and marked "Æion Factory security patch" in the code:
the skill-creator eval viewer, its server and its page (Apache-2.0), and the continuous-learning-v2
instinct import (MIT).
