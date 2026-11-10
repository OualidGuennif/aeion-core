# Task: architecture-answer

## Starting point

- Commit: the develop head when the run starts; record the real one in `BASELINE.md`
- Factory: `3.0.0` (the 1.7.0 baseline below used the earlier structural tool)
- Branch: `task/architecture-answer` from that commit

## Prompt (send this text unchanged)

> Answer two structural questions about this repository with `tools/axiom/axiom query`, no language
> model: what does `tools/evals/record` depend on (`deps tools/evals/record`), and which tests reach
> it (`tests tools/evals/record`). Give every path the tool returns, say what it could not see, and
> change no file.

## Scope

- In scope: the answer only.
- Out of scope: the graph index, any source file, a commit, a push.

## Stop

The run is over when `CHECK.md` passes or you decide it fails; record either outcome.
