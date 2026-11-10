# Commands

Everything you can run here, grouped by loop. Skills are invoked by name in a Claude Code session
(`/plan`, or "run the skill plan"); tools and loops from a shell.

## Skills (`.claude/skills/`, also `.agents/skills/<name>/SKILL.md`)

| Skill | When |
| --- | --- |
| `plan` | start any non-trivial task: inspect, propose, wait for a yes |
| `spec` | a feature or component changes: its requirement and test case in `knowledge/spec/spec.json`, then its spec sections |
| `build` | implement in thin, tested slices |
| `test` | add or fix tests; never weaken an assertion |
| `axiom` | before changing or tracing code: the requirement and context packet, then `tools/axiom/axiom query`, then the language server |
| `debug` | reproduce a failure, test one hypothesis, fix its root cause and prove the regression |
| `sign-off` | end a task: tests, docs and links, task state, security on sensitive diffs |
| `pr-review` | a pull request is open: fresh reviewer, verified findings, one verdict comment |
| `ship` | merge and release behind green CI and the deploy's own guards |
| `okf-update` | a documented fact changed: the right doc, its links, its caps |
| `security-scan` | a sensitive diff, or the weekly job: `/claude-security` |
| `tech-watch` | the monthly technical watch |
| `pr-taste` | the owner commented on a PR: keep the durable preferences |
| `retro` | weekly or after a long session: lessons into hooks, skills and preferences |
| `loop-triage` | an outer-loop finding: turn it into an issue an inner loop can fix |
| `adopt` | apply Æion Factory to an existing repository, one phase at a time |

## Tools

```bash
tools/knowledge/knowledge-check                       # the knowledge base: frontmatter, links, caps
tools/knowledge/doc-links                             # docs <-> code links resolve (L1, L2)
tools/knowledge/doc-links --diff origin/develop --worktree   # also: code changed without its doc (L3)
tools/knowledge/doc-links --for path/to/file          # the docs covering a file
tools/repo-health/repo-health [--json]                # comment blocks, file sizes, AGENTS.md and work caps
tools/factory-tests                                   # every factory test suite below, as CI runs them
python3 tools/knowledge/tests/test_doc_links.py       # tool tests
python3 .claude/hooks/test_hooks.py                   # hook tests
python3 tools/context/tests/test_budget.py            # context boundary/recovery regressions
python3 -m unittest discover -s tools/axiom/tests -t tools/axiom/tests   # the axiom toolkit's tests
tools/axiom/axiom check                               # the commit gate: spec structure, dangling IDs, docs current
tools/axiom/axiom validate [--phase implementation]   # design gates G01-G07 (G08-G12 for implementation)
tools/axiom/axiom query spec|tests|rdeps|path|impact|gaps|requirement|node ...   # bounded graph answers
tools/axiom/axiom packet --files a.py,b.py            # the mandatory context of a change
tools/axiom/axiom docs | views | export --all | evidence run   # cockpit, diagrams, feature export, receipts
tools/axiom/axiom init                                # a new project's spec skeleton, catalogs and brief
tools/agents/run claude                             # existing Claude integration
tools/agents/run codex                              # trust project/hooks first
tools/agents/run opencode                           # native plugin, shared skills
tools/agents/run opencode --isolated                # separate local profile on database conflict
tools/agents/run pi                                 # Pi 1.4.0+, project extension in .pi/
tools/agents/run devin                              # Devin CLI: .devin/ hooks, shared skills
tools/agents/run droid                              # Droid (factory.ai): .factory/ hooks, shared skills
tools/agents/run antigravity                        # Google Antigravity CLI (agy): .agents/hooks.json
tools/agents/run grok                               # Grok Build: .grok/hooks/factory.json
git config aeion.mode team                          # team flow: develop, review before push, release PR
git config --unset aeion.mode                       # back to local mode, the default
python3 tools/agents/tests/test_hooks.py
node --test tools/agents/tests/test_opencode.mjs
node --test tools/agents/tests/test_pi.mjs
python3 tools/loops/tests/test_loops.py
tools/context/run                                    # original Claude entry, native compact at 250k
tools/context/run --strict                           # refuses: strict pre-request control unqualified
python3 tools/context/budget.py checkpoint --session <id> --base origin/develop --verify
```

## Loops (`loops/orchestrator.sh`)

```bash
loops/orchestrator.sh <job> [--dry-run] [--issue N]
#   inner     fix one `agent-ready` issue: branch, PR, review (needs --issue)
#   middle    review the open pull requests that have no verdict yet
#   outer     daily read-only health: production (read-only path), CI, open findings -> issues
#   docs      daily docs drift: doc-links, knowledge-check, stale dates -> issues
#   security  weekly codebase scan with /claude-security -> issues
#   watch     monthly technical watch -> a tech-watch package via PR
#   retro     weekly lessons from sessions and PR comments -> a PR of hooks, skills, preferences
```

Every job reads `env.local`, refuses to run while `LOOPS_ENABLED=false` (except `--dry-run`), and
prints the managed command it runs. Schedules: `loops/schedules/`.
The command uses `tools/context/run` so enabled loops get the same native compaction profile. Dry-run still launches no agent or integration.

## Plugins (Claude Code)

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install hookify@claude-plugins-official --scope project
claude plugin install skill-creator@claude-plugins-official --scope project
claude plugin install claude-security@claude-plugins-official --scope project
claude plugin marketplace add ./tools/claude-plugins --scope project      # local language servers
claude plugin install native-lsp@aeion-local --scope project
```

## Git flow

The team flow below runs once the user sets `git config aeion.mode team` (README "Team git flow").
In local mode, the default, commit on the current branch; pushing is the user's call (pre-push lets
it through), and the safety guards still apply. Only the user switches the mode.

```bash
git switch develop
git commit -m "<what changed and why>"            # the pre-commit runs the checks
# in a session: run the skill pr-review, which records Review: OK for HEAD
git push origin develop                           # pre-push refuses it without that verdict
# release: skill ship (pull request develop -> main, merge commit, tag vX.Y.Z)
```
