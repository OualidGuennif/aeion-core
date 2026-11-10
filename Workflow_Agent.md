# How an agent works in this repository

The order of work, every time. Each step names its skill or tool; the reasons are in the
knowledge base.

## 0. Before anything

- Read `AGENTS.md` (it is short). The session starts with a summary from the `SessionStart` hook:
  git status, recent commits, open tasks.
- Instructions that existed before Æion Factory, and the owner's words, win.
- Nothing needs installing beyond Python 3 and the agent. Start through `tools/agents/run <claude|codex|opencode|pi|devin|droid|antigravity|grok>`; Claude also retains `tools/context/run`.

## 1. Plan (skill `plan`)

Enter plan mode. Inspect the code and the docs the task touches (`knowledge/index.md`, then the
area's doc; `tools/knowledge/doc-links --for <file>` names a file's doc). Propose the smallest
change that fits; list what you will not do. Wait for a yes.

## 2. Spec (skill `spec`)

For a feature or a component, change `knowledge/spec/spec.json` first (the requirement, its test case and
oracle, an open decision for any choice that is not yours), run `tools/axiom/axiom validate`, then
update the component doc's spec sections. Before editing code, read the change's context packet:
`tools/axiom/axiom packet --files <files>` (skill `axiom`). The spec is the source of truth.

## 3. Branch

Team flow (`git config aeion.mode team`, set by the owner): work on `develop` (`git switch develop`); a
parallel session uses a worktree on `task/<slug>` cut from `develop` and merges back locally. In local
mode, the default, commit on the current branch and skip sections 3, 6 and 7, as without git.

## 4. Build in thin slices (skills `build`, `test`)

Change a little, then let the feedback speak: language-server diagnostics and the edit hook after
every edit, the tests after every slice. Commit each green slice. Never weaken a test to pass it.
Claude context checkpoints run automatically: at observed 250k finish closure, update the active handover,
current task and affected docs, then verify a checkpoint before compaction. Observed 300k or lost
usage blocks work; transient usage can recover. This is not a strict pre-request ceiling.
Codex/OpenCode have their own native pre-compaction checkpoint adapters; see
`knowledge/operations/agent-compatibility.md` and `knowledge/operations/context-safety.md`.

## 5. Sign off (skill `sign-off`)

Tests for what changed; `tools/knowledge/doc-links --diff origin/develop --worktree`; the docs the
change touches (skill `okf-update`); `work/current.md`; `AGENTS.md` if the map or a command
changed; `/claude-security` on a sensitive diff. The `Stop` hook reminds you once of anything left.

## 6. Review and push (skill `pr-review`)

Before each push of `develop`, a fresh reviewer reviews `origin/develop..HEAD`; every finding is
verified; the verdict `Review: OK` or `Review: NOT OK` is recorded for the exact commit. Fix and repeat
until OK, then push: `tools/git-hooks/pre-push` refuses `develop` without it.

## 7. Release (skill `ship`)

A pull request `develop → main`, reviewed again, merged with a merge commit after a green CI, then
tagged `vX.Y.Z`. Anything that needs a deploy or a human decision waits for that human.
Keep the complete architecture spec and the generated cockpit current (`tools/axiom/axiom check` in CI).

## 8. Learn (skills `pr-taste`, `retro`)

The owner's comments become preferences; the weekly retro turns repeated mistakes into hooks and
repeated procedures into skills.

## Loops that run without you

The outer loop (scheduled, read-only) opens issues; an inner run picks an `agent-ready` issue and
goes through steps 3–7. Commands: `command.md`.
