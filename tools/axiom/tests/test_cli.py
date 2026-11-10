import json
import unittest

from support import LEDGER, pantry_project


class CliTests(unittest.TestCase):
    def setUp(self):
        self.project = pantry_project()

    def tearDown(self):
        self.project.close()

    def test_exit_codes_follow_the_contract(self):
        done = self.project.run("validate")
        self.assertEqual(done.returncode, 0, done.stdout)
        spec = json.loads((self.project.root / "knowledge/spec/spec.json").read_text())
        spec["nodes"][-1]["data"]["answer"] = None
        self.project.write("knowledge/spec/spec.json", spec)
        done = self.project.run("validate")
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("OPEN_BLOCKING_DECISION", done.stdout)
        self.project.write("knowledge/spec/spec.json", '{"format": "axiomspec/0.1", "format": "x"}')
        done = self.project.run("validate")
        self.assertEqual(done.returncode, 4)
        self.assertIn("DUPLICATE_KEY", done.stdout)

    def test_report_is_schema_valid(self):
        report = self.project.root / "report.json"
        self.project.run("validate", "--report", str(report))
        import spec as specs
        from strict import load
        self.assertEqual(specs.schema_validator("report").errors(load(report)), [])

    def test_ledger_end_to_end(self):
        spec = str(LEDGER / "spec.json")
        done = self.project.run("--spec", spec, "evaluate", "--observations", str(LEDGER / "observations.json"))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("45 of 45 expectations match", done.stdout)

    def test_check_init_and_queries(self):
        done = self.project.run("check")
        self.assertEqual(done.returncode, 2)
        self.assertIn("docs/README.md is missing", done.stdout)
        self.assertEqual(self.project.run("docs").returncode, 0)
        done = self.project.run("check")
        self.assertEqual(done.returncode, 0, done.stdout)
        done = self.project.run("query", "--json", "spec", "app/pantry.py")
        self.assertEqual(json.loads(done.stdout)["query"]["kind"], "spec")
        done = self.project.run("query", "node", "REQ-404")
        self.assertEqual(done.returncode, 4)
        done = self.project.run("packet", "--files", "app/pantry.py")
        self.assertEqual(done.returncode, 0)
        self.assertIn("# Context packet (complete)", done.stdout)

    def test_init_never_overwrites(self):
        before = (self.project.root / "knowledge/spec/spec.json").read_text()
        done = self.project.run("init", "--name", "X")
        self.assertIn("kept knowledge/spec/spec.json (exists)", done.stdout)
        self.assertEqual((self.project.root / "knowledge/spec/spec.json").read_text(), before)


if __name__ == "__main__":
    unittest.main()
