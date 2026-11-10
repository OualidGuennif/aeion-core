---
type: Component
title: "Updating a project to a new release"
description: "tools/agents/template-update: moves an adopted project's factory files to a release, file by file, keeping the project's own instructions, knowledge and edits."
status: stable
review_after: 2027-01-29
generated:
  by: aeion-factory/3.0
  at: 2026-11-10
sources:
  - resource: ../../tools/agents/template-update
    title: "The update tool"
  - resource: ../../tools/agents/connectors.py
    title: "The connector and merge file lists"
  - resource: ../../tools/agents/refs.py
    title: "Reading a git reference without a checkout"
  - resource: ../../tools/agents/tests/test_template_update.py
    title: "Update tests, from a synthetic factory and from the v2.1.1 tag"
  - resource: ../../.agents/skills/template-update/SKILL.md
    title: "The skill that runs it"
---

# Updating a project to a new release

An adopted project carries its own copies of the factory's files next to its own instructions,
settings and knowledge. An update must move every factory file the release changed, keep each edit
the project made, and leave the project's own text alone.

## Intent

Move a project from the factory release it adopted to another reference, deciding each file the
factory changed between the two, and each factory file the project still holds as an older
release's untouched copy, on its own, so a connector matches its release byte for byte, an
untouched factory file follows the release, a project edit survives, and a conflict or a project-owned
file goes to a human. The application's `VERSION` is not factory provenance: it is neither read as
the baseline nor written.

## Data sources

| Source | What is read | Owner | Freshness |
| --- | --- | --- | --- |
| `--from-ref`, else the project's `.aeion-factory` marker | the factory release or commit the project adopted | the caller; the last update or `release --new-project` | at each update |
| the factory's `vX.Y.Z` tags | every tagged tree's object ids, against the project's files | the releases | at each update: the inferred baseline, and the release an untouched older copy came from |
| the project's tree and git state | file bytes, executable modes, links, tracked changes, `develop`, `aeion.mode` | the project | at each update |
| the baseline and target trees | every changed file's bytes and git mode, the target's `CHANGELOG.md` | the factory | at each update |

## Inputs

```bash
tools/agents/template-update --ref v2.0.1 --root ../app --check
tools/agents/template-update --ref v2.0.1 --root ../app
tools/agents/template-update --from-ref v1.8.5 --ref main --root ../app
```

- `--from-ref`: the factory reference the project adopted. Optional: without it the tool reads the
  project's `.aeion-factory` (`<ref> [<commit>]`, the commit preferred because a branch moves), and
  without a marker it infers the release tag whose files the project matches best, newest on ties.
  A write on an inferred baseline needs every contract connector to match it; a partial match runs
  `--check` only. It is never read from the project's `VERSION`.
- `--ref`: the target tag, `main`, `develop` or a commit id.
- `--root`: the project that adopted the factory; `--repo`: the factory repository holding both
  references (default: the checkout the tool runs from). A project's own copy of the tool cannot
  see a newer release, so `--root` and `--repo` must differ and `--repo` must not hold an
  `.aeion-factory` marker: run it from the factory clone. That refusal comes before `--root` is
  checked, since a relative `--root` typed inside a project names a folder that does not exist.
- `--check` writes nothing; `--force` permits moving to an older factory release.

## Outputs

The header names the baseline and how it was found (`--from-ref`, `.aeion-factory` or
`inferred: <n>/<m> factory files and <c>/<k> connectors match`), a `MAJOR a.x → b.x` banner when the
major version grows, and the target's `CHANGELOG.md` sections newer than the baseline (80 lines at
most). Then one line per file, in these classes:

| Class | Files | Line |
| --- | --- | --- |
| contract | `connectors.CONTRACT` | `written`, `mode`, `skipped — not in <ref>`; `DRIFT`/`MODE` under `--check` |
| project-owned | `VERSION`, `CHANGELOG.md`, `.aeion-factory`, `work/`, `knowledge/spec/`, `demo/`, the AxiomSpec cockpit, views and catalogs in `docs/` | never written |
| knowledge | the factory's other `knowledge/` docs | follows the factory while the project has not edited it (`updated`, `removed`, `added`); an edited doc is `review <file>`, kept byte for byte and never merged; the vendored `knowledge/axiomspec/` is three-way |
| merge | `connectors.MERGE` (`AGENTS.md`, merged settings) | never written; `merge <file> — proposal: <path>` |
| three-way | every other changed file, and every factory file still an older release's copy | `updated` (the project kept the baseline, or an older release's copy: `— untouched since <tag>`), `added` (new, in a folder the project has or one new in the factory), `removed` (deleted upstream, untouched here), `merged` (`git merge-file` was clean), `conflict` (left as it is, with a proposal), `review` (removed upstream but edited here, or a link the project changed), `link`, `mode` |

An update before 2.0.1 moved only the connectors, so a project can hold a factory file byte for byte
as an older release had it; such a file diffs from that release, not from the baseline, and takes
the target even when the factory left it alone since the baseline. Files the project deleted, and
new files in a folder the baseline had but the project left out, stay out and are counted on one
`untouched` line; a folder new in the factory (3.0.0's `tools/axiom/`) comes in whole. A rename is
both of its paths, so the old copy is removed and a folder the removal empties goes with it.
A proposal (the three-way result, conflict markers included) is written under
`.aeion/template-update/<ref>/` on a write; that folder carries its own `.gitignore`, so a project
that does not ignore `.aeion/` never sees the proposals as files to commit. A `migrate` line names what
the owner must run for a release crossed, such as `git config aeion.mode team` for 2.0.0 when the
project has a `develop` branch and no team mode, or `tools/axiom/axiom init` for 3.0.0 when the
project has no `knowledge/spec/spec.json`; the tool never runs it. A write ends by recording
`<ref> <commit>` in `.aeion-factory` and naming the verification and the commit.

Exit code 0 when nothing needs a human, 1 when a merge, conflict, review or migration remains (and,
under `--check`, when anything would change or the inferred baseline is partial), and 2 on a refusal:
`no such reference: <ref>`, `.aeion-factory names <ref>, unknown in <repo>`,
`baseline <tag> inferred: …; confirm it with --from-ref <tag>`, `no VERSION at the baseline <ref>`,
`<root> has uncommitted changes`, `not an adopted project: no factory connector in <path>`,
`refusing linked [connector] destination <path> below <root>`,
`refusing non-regular [connector] destination <relative>`, `refusing to downgrade <a> to <b>`, and
`refusing to update a project from its own repository <repo>; run template-update from the Æion
Factory clone` (its hint names `--root <project>` when `--root` is no folder).

## Invariants

1. The project's `AGENTS.md`, `knowledge/spec/`, cockpit, `CHANGELOG.md` and `VERSION` are never
   written, and an edited `knowledge/` doc is only listed; an untouched one follows the factory —
   `test_writes_the_reference_and_keeps_the_project_text`,
   `test_the_application_version_is_never_written`, `test_the_project_cockpit_and_spec_are_never_written`,
   `test_knowledge_the_project_lacks_stays_out`, `test_untouched_knowledge_follows_the_factory`,
   `test_edited_knowledge_is_listed_never_merged`.
2. `--check` writes nothing — `test_check_writes_nothing`.
3. Both references are validated and a branch is valid on either side —
   `test_a_branch_is_a_valid_reference`.
4. A downgrade needs `--force` —
   `test_it_refuses_a_downgrade`, `test_a_downgrade_with_force_is_allowed`.
5. The baseline comes from the flag, then the marker, then an exact inference; an unknown marker or
   a partial inference never writes — `test_the_marker_is_written_then_used`,
   `test_a_new_project_marker_names_its_release`, `test_an_unknown_marker_is_refused`,
   `test_an_exact_inference_writes`, `test_a_partial_inference_only_checks`.
6. Repeating the same from/to pair keeps naming an unpaid merge even when every connector matches —
   `test_a_merge_only_check_keeps_naming_the_merge`.
7. A linked destination file or parent, or a linked proposal folder, is refused before the first
   write — `test_a_linked_connector_is_refused_before_any_write`, `test_a_linked_parent_is_refused`,
   `test_a_linked_proposal_folder_is_refused`.
8. A created or repaired launcher carries the reference's executable mode —
   `test_a_missing_launcher_is_written_executable`,
   `test_a_launcher_that_lost_its_mode_is_repaired`.
9. A directory with no connector is not an adopted project, and a repository never updates itself
   (the factory, or a project running its own copy, even with a mistyped `--root`) —
   `test_it_refuses_a_project_with_no_connector`, `test_it_refuses_to_update_a_repository_from_itself`,
   `test_a_project_copy_names_the_factory_clone_before_a_mistyped_root`.
10. An untouched factory file takes the target, an edit merges, a conflict keeps the project's file
    with a proposal in a folder that ignores itself, and a file the project deleted stays deleted —
    `test_an_untouched_factory_file_takes_the_target`, `test_a_project_edit_merges_with_the_target`,
    `test_a_conflicting_edit_is_kept_with_a_proposal`, `test_a_file_the_project_deleted_stays_deleted`.
11. A write refuses tracked uncommitted changes, so the update is one revertible commit —
    `test_a_dirty_project_refuses_a_write`.
12. The notes, the major banner and a migration hint are printed, and the mode switch is left to
    the owner — `test_notes_major_and_the_mode_migration`.
13. A factory file the project holds as an older release's untouched copy takes the target, even
    when the factory left it alone since the baseline; an edited one is never caught up —
    `test_an_older_untouched_copy_takes_the_target`, `test_an_edited_older_copy_is_never_caught_up`.
14. A factory link the release removed is removed, a folder new in the factory comes in while one the
    project left out stays out, and a renamed file moves — `test_a_removed_factory_link_is_removed`,
    `test_a_new_factory_folder_comes_in_and_a_left_out_one_does_not`,
    `test_a_renamed_factory_file_moves_and_its_empty_folder_goes`.
15. An untouched project adopted at v2.1.1 commits again after the update and the two steps it names
    (the `AGENTS.md` proposal, `axiom init`) — `ReleaseUpdateTests` (needs the tag; skipped without it),
    `test_the_axiomspec_migration_is_named_until_the_project_has_a_spec`.

## Determinism

The same project tree and references always give the same decisions and the same output: bytes,
object ids and modes come from git objects, `git merge-file` is deterministic, destination links are
checked before the first write, paths are sorted, and only the marker records the target commit.

## Acceptance checks

```bash
python3 tools/agents/tests/test_template_update.py
python3 tools/agents/tests/test_adapter_check.py
python3 tools/release/tests/test_release.py
tools/factory-tests
```

## Out of scope

- resolving a conflict or a merge file for the project: each gets a proposal, never an edit.
- running a migration step such as `git config aeion.mode team`: the owner runs it.
- fetching: the factory checkout must already hold both references (`git fetch --tags`).
- committing, pushing or opening a pull request; creating the tag: `tools/release/release` owns the version.
