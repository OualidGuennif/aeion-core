"""Refusals and fail-closed paths found by the 3.0.0 independent reviews: one test per finding
(first round: findings 1-14; second round: classes named Second*)."""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import FACTORY, ledger, pantry_project, pantry_spec
import docs
import evidence
import graph
import spec as specs
import strict
import views


def model_of(root):
    result = specs.Result()
    spec = specs.load_spec(Path(root) / "knowledge/spec/spec.json", result)
    model, _ = specs.validate(spec, result=result)
    return model, result


class InitTests(unittest.TestCase):  # finding 1
    def test_init_keeps_a_projects_own_docs(self):
        project = pantry_project()
        try:
            readme = project.write("docs/README.md", "# Our docs\n")
            api = project.write("docs/generated/api.html", "<html></html>")
            (project.root / "knowledge/spec/spec.json").unlink()
            done = project.run("init")
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertEqual(readme.read_text(), "# Our docs\n")
            self.assertTrue(api.is_file())
            self.assertIn("was not generated", done.stdout)
        finally:
            project.close()


class SchemaTests(unittest.TestCase):  # finding 2
    def test_template_update_carries_the_axiomspec_package(self):
        path = FACTORY / "tools/agents/template-update"
        loader = importlib.machinery.SourceFileLoader("template_update", str(path))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader("template_update", loader))
        loader.exec_module(module)
        self.assertFalse(module.owned("knowledge/axiomspec/AxiomSpec/schemas/spec.schema.json"))
        self.assertTrue(module.owned("knowledge/spec/spec.json"))

    def test_a_missing_schema_is_a_g01_error_not_a_crash(self):
        project = pantry_project()
        try:
            shutil.rmtree(project.root / "knowledge/axiomspec/AxiomSpec/schemas")
            done = project.run("validate")
            self.assertEqual(done.returncode, 4, done.stderr)
            self.assertIn("SCHEMA_UNAVAILABLE", done.stdout)
            self.assertNotIn("Traceback", done.stderr)
        finally:
            project.close()


class WindowTests(unittest.TestCase):  # finding 3
    def setUp(self):
        self.spec = ledger()
        self.constraint = next(n for n in self.spec["nodes"] if n["kind"] == "Constraint"
                               and n["data"]["representation"] == "bcir")
        self.scenario = next(n for n in self.spec["nodes"] if n["kind"] == "Scenario" and any(
            e["constraint_id"] == self.constraint["id"] for e in n["data"]["constraint_expectations"]))
        self.expectation = next(e for e in self.scenario["data"]["constraint_expectations"]
                                if e["constraint_id"] == self.constraint["id"])

    def outcome(self, evaluated_at):
        model = specs.Model(self.spec)
        import bcir
        validator = bcir.environment_validator(model.envs[self.scenario["data"]["environment_id"]])
        return specs.expectation_outcome(model, self.scenario, self.expectation, validator, evaluated_at)

    def test_out_of_window_is_not_pass(self):
        self.constraint["data"]["effective_from"] = "2030-01-01T00:00:00Z"
        self.assertEqual(self.outcome("2026-01-01T00:00:00Z")[:2], ("unknown", "NOT_IN_EFFECT"))
        self.assertEqual(self.outcome("garbage")[:2], ("unknown", "APPLICABILITY_UNKNOWN"))
        self.assertIsNone(self.outcome("2031-01-01T00:00:00Z"))

    def test_the_cli_refuses_an_invalid_evaluation_time(self):
        project = pantry_project()
        try:
            done = project.run("validate", "--evaluated-at", "garbage")
            self.assertEqual(done.returncode, 4)
            self.assertIn("EVALUATED_AT", done.stderr)
        finally:
            project.close()


class DanglingTests(unittest.TestCase):  # finding 4
    def test_only_knowledge_and_docs_cite_the_spec(self):
        project = pantry_project()
        try:
            project.write("knowledge/components/pantry.md", (project.root / "knowledge/components/pantry.md").read_text()
                          .replace("see also `REQ-999` as an example", "nothing else"))
            project.write("notes/meeting.md", "# Meeting\n\nJira ticket CON-1234 and REQ-404.\n")
            model, _ = model_of(project.root)
            self.assertEqual(docs.dangling_ids(project.root, model), [])
            project.write("docs/authored/plan.md", "# Plan\n\nSee REQ-404.\n")
            self.assertEqual(docs.dangling_ids(project.root, model),
                             ["docs/authored/plan.md: cites REQ-404, not in knowledge/spec/spec.json"])
        finally:
            project.close()


class BindingTests(unittest.TestCase):  # finding 5
    def test_a_binding_without_a_symbol_names_the_file(self):
        project = pantry_project()
        try:
            spec = pantry_spec()
            spec["bindings"][0]["symbol"] = None
            project.write("knowledge/spec/spec.json", spec)
            snapshot = graph.snapshot(project.root, project.root / "knowledge/spec/spec.json")
            bound = next(n for n in snapshot["nodes"] if n["id"] == "BIND-001")
            self.assertEqual(bound["resolution"]["status"], "resolved")
            spec["bindings"][1]["symbol"] = None
            project.write("knowledge/spec/spec.json", spec)
            model = specs.Model(spec)
            self.assertEqual(evidence.run(project.root, model, ["TEST-001"]), 2)
            receipt = json.loads((project.root / "knowledge/spec/evidence/TEST-001.json").read_text())
            self.assertIn("names none", receipt["problems"][0])
        finally:
            project.close()


class EnvironmentTests(unittest.TestCase):  # finding 6
    def test_unwalkable_environment_schemas_are_diagnostics(self):
        for broken in ({"type": "object", "additionalProperties": False, "required": ["a"], "properties": {"a": 5}},
                       {"type": "object", "additionalProperties": False, "required": [], "properties": {},
                        "patternProperties": {"(": {"type": "integer"}}}):
            spec = ledger()
            spec["environments"][0]["schema"] = broken
            result = specs.Result()
            specs.validate(spec, result=result)
            self.assertEqual(result.gate_status("G03"), "error")
            self.assertIn(result.gate_status("G06"), ("unknown", "error", "pass"))

    def test_a_relative_unit_pointer_is_a_diagnostic(self):
        spec = ledger()
        if not spec["environments"][0].get("units"):
            self.skipTest("the ledger environment declares no units")
        spec["environments"][0]["units"][0]["pointer"] = "no-leading-slash"
        result = specs.Result()
        specs.validate(spec, result=result)
        self.assertEqual(result.gate_status("G03"), "error")


class StrictTests(unittest.TestCase):  # finding 7
    def test_a_huge_integer_is_an_input_error(self):
        with self.assertRaises(strict.InputError) as caught:
            strict.loads(("[" + "7" * 5000 + "]").encode())
        self.assertEqual(caught.exception.code, "UNSAFE_INTEGER")


class AdapterTests(unittest.TestCase):  # finding 8
    def test_a_project_module_named_like_a_toolkit_module_is_imported(self):
        folder = Path(tempfile.mkdtemp(prefix="axiom-adapter-"))
        try:
            (folder / "tests").mkdir()
            (folder / "tests/common.py").write_text("def helper():\n    return 42\n")
            (folder / "tests/test_x.py").write_text("import unittest\nfrom common import helper\n\n\n"
                                                    "class Case(unittest.TestCase):\n    def test_ok(self):\n"
                                                    "        self.assertEqual(helper(), 42)\n")
            done = subprocess.run(evidence.adapter_command("tests/test_x.py", "Case.test_ok"),
                                  cwd=folder, capture_output=True, text=True, timeout=60)
            self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])["results"], {"Case.test_ok": "pass"}, done.stderr)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class ReportTests(unittest.TestCase):  # finding 9
    def test_gates_after_a_g01_failure_are_not_run(self):
        result = specs.Result()
        result.add("G01", "error", "TOO_DEEP", "nesting too deep")
        report = specs.report(result, "design_ready", list(specs.DESIGN_GATES), None, "2026-11-10T00:00:00Z")
        later = [c for c in report["checks"] if c["gate"] != "G01"]
        self.assertTrue(later and all(c["status"] == "unknown" for c in later))
        self.assertEqual(report["status"], "error")


class SpecPathTests(unittest.TestCase):  # finding 10
    def test_implementation_gates_read_the_given_spec(self):
        project = pantry_project()
        try:
            other = pantry_spec()
            other["bindings"][0]["path"] = "app/missing.py"
            path = project.write("alt/spec.json", other)
            done = project.run("--spec", str(path), "validate", "--phase", "implementation")
            self.assertIn("G09 fail", done.stdout)
        finally:
            project.close()


class ExportTests(unittest.TestCase):  # finding 11
    def test_a_profile_cannot_rename_the_exported_file(self):
        project = pantry_project()
        try:
            model, _ = model_of(project.root)
            profile = project.write("profile.json", {"format": "aeion-export-profile/0.1", "name": "evil",
                                                     "frontmatter": {"file": "../../ESCAPED.md", "id": "999"}})
            # ../../ESCAPED.md from root/a/out would land in root itself: inside this test's own folder.
            out = project.root / "a/out"
            self.assertEqual(docs.export(project.root, model, None, True, profile, out), 0)
            self.assertFalse((project.root / "ESCAPED.md").exists())
            row = json.loads((out / "features.json").read_text())["features"][0]
            self.assertEqual((row["file"], row["id"]), ("001-never-overdraw-stock.md", "001"))
        finally:
            project.close()


class ObservationTests(unittest.TestCase):  # finding 12
    def test_malformed_observation_files_are_input_errors(self):
        project = pantry_project()
        try:
            for value in ([], {"cases": [{"scenario_id": "SCN-001"}]}, {"cases": "x"}):
                path = project.write("obs.json", value)
                done = project.run("evaluate", "--observations", str(path))
                self.assertEqual(done.returncode, 4, (value, done.stderr))
                self.assertNotIn("Traceback", done.stderr)
        finally:
            project.close()


class SequenceTests(unittest.TestCase):  # finding 13
    def test_malformed_steps_are_view_errors(self):
        base = {"format": views.FORMAT, "kind": "sequence",
                "participants": [{"id": "a", "label": "A", "type": "actor"}, {"id": "b", "label": "B", "type": "participant"}]}
        for steps in ([{"note": 5, "over": ["a"]}], [{"fragment": "alt", "branches": ["x"]}], ["x"],
                      [{"from": ["a"], "to": "b"}]):
            with self.assertRaises(views.ViewError, msg=steps):
                views.render(dict(base, steps=steps), "T", "Q")


class ReceiptTests(unittest.TestCase):  # finding 14
    def test_a_receipt_counts_only_for_its_own_test(self):
        project = pantry_project()
        try:
            spec = pantry_spec()
            model = specs.Model(spec)
            self.assertEqual(evidence.run(project.root, model, []), 0)
            folder = project.root / "knowledge/spec/evidence"
            receipt = json.loads((folder / "TEST-001.json").read_text())
            receipt["test_id"] = "TEST-002"
            (folder / "TEST-001.json").write_text(json.dumps(receipt))
            self.assertEqual(evidence.receipts_state(project.root, model)["TEST-001"][0], "failed")
            (folder / "TEST-001.json").write_text("[1, 2]")
            self.assertEqual(evidence.receipts_state(project.root, model)["TEST-001"][0], "failed")
        finally:
            project.close()


class SecondEvaluateTests(unittest.TestCase):  # second round, finding 2
    def test_evaluate_on_a_rejected_environment_is_unknown_not_a_traceback(self):
        example = FACTORY / "knowledge/axiomspec/AxiomSpec/examples/refund-ledger"
        project = pantry_project()
        try:
            for mutate_schema in (lambda s: s.update(patternProperties={"^x": {"type": "integer"}}),
                                  lambda s: (s.setdefault("$defs", {}).update(loop={"$ref": "#/$defs/loop"}),
                                             s["properties"].update({next(iter(s["properties"])): {"$ref": "#/$defs/loop"}}))):
                spec = ledger()
                mutate_schema(spec["environments"][0]["schema"])
                path = project.write("broken.json", spec)
                done = project.run("evaluate", "--spec", str(path), "--observations", str(example / "observations.json"))
                self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
                self.assertNotIn("Traceback", done.stderr)
                self.assertIn("failed G03; not evaluated", done.stdout)
        finally:
            project.close()


class SecondViewsTests(unittest.TestCase):  # second round, finding 3
    VIEW = {"format": views.FORMAT, "kind": "sequence",
            "participants": [{"id": "a", "label": "A", "type": "actor"}, {"id": "b", "label": "B", "type": "participant"}],
            "steps": [{"from": "a", "to": "b", "label": "asks"}]}

    def catalogued(self, project):
        project.write("docs/views/one.json", self.VIEW)
        project.write("docs/view-catalog.json", {"format": views.CATALOG_FORMAT, "views": [
            {"id": "VIEW-ONE", "kind": "sequence", "title": "One", "question": "Who asks?", "claim": "intended",
             "canonical_ids": [], "source_path": "docs/views/one.json", "scope": "test"}]})

    def test_a_projects_own_diagram_is_never_flagged_or_deleted(self):
        project = pantry_project()
        try:
            (project.root / "knowledge/spec/spec.json").unlink()
            own = project.write("docs/generated/diagrams/architecture.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
            self.assertEqual(project.run("check").returncode, 0)
            self.assertEqual(project.run("views").returncode, 0)
            self.assertTrue(own.is_file())
        finally:
            project.close()

    def test_a_view_never_overwrites_a_file_it_did_not_write(self):
        project = pantry_project()
        try:
            self.catalogued(project)
            own = project.write("docs/generated/diagrams/VIEW-ONE.svg", "<svg>ours</svg>")
            done = project.run("views")
            self.assertEqual(done.returncode, 2)
            self.assertIn("was not generated", done.stderr)
            self.assertEqual(own.read_text(), "<svg>ours</svg>")
        finally:
            project.close()

    def test_views_then_docs_publish_and_a_retired_view_goes(self):
        project = pantry_project()
        try:
            self.catalogued(project)
            self.assertEqual(project.run("views").returncode, 0)
            self.assertIn(views.MARK, (project.root / "docs/generated/diagrams/VIEW-ONE.svg").read_text())
            done = project.run("docs")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            project.write("docs/view-catalog.json", {"format": views.CATALOG_FORMAT, "views": []})
            self.assertEqual(project.run("views").returncode, 0)
            self.assertFalse((project.root / "docs/generated/diagrams/VIEW-ONE.svg").exists())
        finally:
            project.close()


class SecondAdapterTests(unittest.TestCase):  # second round, finding 4
    def test_pythonpath_still_reaches_the_bound_test(self):
        folder = Path(tempfile.mkdtemp(prefix="axiom-adapter-"))
        try:
            (folder / "lib").mkdir()
            (folder / "lib/sharedlib.py").write_text("VALUE = 7\n")
            (folder / "tests").mkdir()
            (folder / "tests/test_y.py").write_text("import unittest\nimport sharedlib\n\n\n"
                                                    "class Case(unittest.TestCase):\n    def test_ok(self):\n"
                                                    "        self.assertEqual(sharedlib.VALUE, 7)\n")
            done = subprocess.run(evidence.adapter_command("tests/test_y.py", "Case.test_ok"), cwd=folder,
                                  capture_output=True, text=True, timeout=60,
                                  env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "lib"})
            self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])["results"], {"Case.test_ok": "pass"}, done.stderr)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class SecondInitTests(unittest.TestCase):  # second round, finding 5
    def test_init_reports_a_missing_schema(self):
        project = pantry_project()
        try:
            (project.root / "knowledge/spec/spec.json").unlink()
            shutil.rmtree(project.root / "knowledge/axiomspec/AxiomSpec/schemas")
            done = project.run("init")
            self.assertEqual(done.returncode, 4, done.stdout + done.stderr)
            self.assertIn("SCHEMA_UNAVAILABLE", done.stdout)
        finally:
            project.close()


class SecondWitnessTests(unittest.TestCase):  # second round, finding 6
    setUp, outcome = WindowTests.setUp, WindowTests.outcome

    def test_a_witness_binds_only_an_applicable_hard_invariant(self):
        data = self.constraint["data"]
        data["predicate_role"], data["classification"]["strength"] = "invariant", "hard"
        data["effective_from"] = "2030-01-01T00:00:00Z"
        self.scenario["data"]["intent"] = "witness"
        self.expectation["expected"] = False
        self.assertEqual(self.outcome("2026-01-01T00:00:00Z")[:2], ("unknown", "NOT_IN_EFFECT"))
        self.assertEqual(self.outcome("2031-01-01T00:00:00Z")[:2], ("fail", "WITNESS_VIOLATES_INVARIANT"))


class SecondCliTests(unittest.TestCase):  # found with the second round: AxiomSpec's own interface
    def test_spec_works_before_and_after_the_command(self):
        project = pantry_project()
        try:
            path = str(project.root / "knowledge/spec/spec.json")
            before = project.run("--spec", path, "validate")
            after = project.run("validate", "--spec", path)
            self.assertEqual((before.returncode, before.stdout), (after.returncode, after.stdout))
            self.assertNotIn("unrecognized", after.stderr)
        finally:
            project.close()


class ThirdDocsTests(unittest.TestCase):  # third round
    def test_docs_never_deletes_a_projects_dot_files(self):
        project = pantry_project()
        try:
            self.assertEqual(project.run("docs").returncode, 0)
            kept = [project.write("docs/generated/.nojekyll", ""), project.write("docs/generated/.drafts/.wip", "wip\n")]
            # Desktop files, and an editor's swap or backup of a generated file, never block a commit.
            for incidental in (".DS_Store", "views/Thumbs.db", "desktop.ini", ".traceability.md.swp", "traceability.md~"):
                project.write(f"docs/generated/{incidental}", "x")
            # An editor file of anything else is the project's, like any file the generator did not write.
            kept += [project.write("docs/generated/plan~", "my own notes\n"),
                     project.write("docs/generated/#ideas.md#", "unsaved own draft\n")]
            checked = project.run("check").stdout
            for name in (".nojekyll", "plan~", "#ideas.md#"):
                self.assertIn(name, checked)
            for name in ("Thumbs.db", ".swp", "traceability.md~"):
                self.assertNotIn(name, checked)
            done = project.run("docs")
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertTrue(all(path.is_file() for path in kept))
        finally:
            project.close()

    def test_written_files_keep_a_readable_mode(self):
        project = pantry_project()
        try:
            self.assertEqual(project.run("docs").returncode, 0)
            # A new file gets what the umask gives (mkstemp alone would leave 0600); a rewritten one keeps its mode.
            manifest = project.root / "docs/generated/manifest.json"
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o666 & ~_umask())
            cockpit = project.root / "docs/README.md"
            cockpit.chmod(0o640)
            self.assertEqual(project.run("docs").returncode, 0)
            self.assertEqual(cockpit.stat().st_mode & 0o777, 0o640)
        finally:
            project.close()


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


if __name__ == "__main__":
    unittest.main()
