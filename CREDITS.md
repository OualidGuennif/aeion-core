# Credits

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

## Research and practice

- **Jesse Vincent / obra, Superpowers** (MIT) — investigation, evidence before completion,
  precise plans and verified review feedback inspired the focused Æion Factory skill updates.
  https://github.com/obra/superpowers · [license notice](docs/licenses/superpowers-MIT.txt).
- **Mert Koseoğlu, context-mode** (Elastic-2.0) — bounded output and pre-compaction recovery
  informed the context design. No context-mode code or MCP runtime is bundled.
  https://github.com/mksglu/context-mode
- **Robert C. Martin, ub-mode** — the three passes and the build principles (the data's shape first,
  a design fitted to the change, idempotent operations, one writer for shared state) are adapted in
  our own words; no ub-mode text is copied. https://github.com/unclebob/ub-mode
- **AxiomSpec**, edition 0.3.0, and its two playbooks — the specification method, schemas,
  conformance fixtures and reference example, authored for the Æion project and vendored verbatim in
  `knowledge/axiomspec/`. Its optional CROA profile adapts selected inputs of the CROA public review
  draft (The CROA Project, CC BY 4.0), with the attribution stated in that profile.

- Chroma, *Context Rot* (2025) — long inputs degrade every model measured.
- Gloaguen et al., context files and agent success (arXiv 2602.11988, 2026).
- Lulla et al., AGENTS.md and agent runtime (arXiv 2601.20404, 2026).
- Anthropic, *Effective context engineering for AI agents* (2025).
- Doc-to-code trace links with LLMs (arXiv 2506.16440, 2025).
- Microsoft Learn, the developer inner and outer loop.
- Cyrille Martraire, *Living Documentation*.
- OWASP cheat sheets: secrets management, database security.
- GitHub docs: security policies, CODEOWNERS.

Mistakes in how these ideas are combined here are ours, not theirs.

## Selective skill maintenance

- **affaan-m / ECC contributors** (MIT): review evidence, false-positive filtering and scoped
  engineering checks informed the native review checklist. Source: https://github.com/affaan-m/ECC
- **Addy Osmani / agent-skills contributors** (MIT): task-specific debugging, behavioral test
  selection and source-based workflow discovery. Existing attribution above is retained.
- **Anthropic official plugins / security-guidance contributors** (Apache-2.0 for that plugin):
  data-flow-oriented security inspection. Plugin-specific terms still apply; proprietary
  `claude-security` definitions are not transplanted into the cross-host pool.
- **Anthropic knowledge-work-plugins contributors** (upstream component terms apply): passive
  specialist workflow references. https://github.com/anthropics/knowledge-work-plugins

The versioned skills/catalog.json records exact source commits, entrypoint fingerprints and license
files. Native Factory text is selectively adapted, not a wholesale copy of upstream prompts. The separate passive pool contains upstream skill/agent files and supporting resources,
with three source-hash-bound scanner annotation comments recorded in tools/skills/annotations.json, with license texts under skills/licenses/.
Three of those files are modified by source-hash-bound security patches recorded in tools/skills/patches.json: the
skill-creator eval-viewer/generate_review.py and eval-viewer/viewer.html (Apache-2.0) and the continuous-learning-v2
scripts/instinct-cli.py (MIT);
each changed line is marked "Æion Factory security patch".
No upstream agent-launch mandate, model setting or generic threshold is adopted.
