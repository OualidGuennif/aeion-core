import json
import time
import unittest

from support import pantry_project
import evidence
import spec as specs


def model_of(root):
    result = specs.Result()
    return specs.Model(specs.load_spec(root / "knowledge/spec/spec.json", result))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.project = pantry_project()
        self.root = self.project.root

    def tearDown(self):
        self.project.close()

    def test_run_writes_a_current_receipt(self):
        model = model_of(self.root)
        self.assertEqual(evidence.run(self.root, model, []), 0)
        receipt = json.loads((self.root / "knowledge/spec/evidence/TEST-001.json").read_text())
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["counts"]["collected"], 1)
        self.assertEqual(list(receipt["results"]), ["tests/test_pantry.py::PantryTests.test_overdraw_refused"])
        self.assertEqual(evidence.receipts_state(self.root, model)["TEST-001"][0], "current")

    def test_unexecuted_is_unknown_not_pass(self):  # V-113
        result = specs.Result()
        evidence.implementation_gates(self.root, model_of(self.root), result)
        self.assertEqual(result.gate_status("G10"), "unknown")
        self.assertEqual(result.gate_status("G12"), "unknown")

    def test_spec_change_invalidates(self):  # V-114
        evidence.run(self.root, model_of(self.root), [])
        spec = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        spec["nodes"][0]["title"] = "Changed goal"
        self.project.write("knowledge/spec/spec.json", spec)
        self.assertEqual(evidence.receipts_state(self.root, model_of(self.root))["TEST-001"][0], "stale")

    def test_code_change_invalidates(self):  # V-115
        evidence.run(self.root, model_of(self.root), [])
        time.sleep(0.01)
        self.project.write("app/util.py", "def positive(value):\n    return value\n")
        state, detail = evidence.receipts_state(self.root, model_of(self.root))["TEST-001"]
        self.assertEqual(state, "stale")
        self.assertIn("code", detail)

    def test_failing_and_missing_tests_fail(self):
        self.project.write("tests/test_pantry.py", (self.root / "tests/test_pantry.py").read_text()
                           .replace("self.assertEqual(p.stock['rice'], 1)", "self.assertEqual(p.stock['rice'], 0)"))
        self.assertEqual(evidence.run(self.root, model_of(self.root), []), 2)
        self.assertEqual(evidence.receipts_state(self.root, model_of(self.root))["TEST-001"][0], "failed")
        spec = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        spec["bindings"][1]["symbol"] = "PantryTests.test_missing"
        self.project.write("knowledge/spec/spec.json", spec)
        self.assertEqual(evidence.run(self.root, model_of(self.root), []), 2)
        receipt = json.loads((self.root / "knowledge/spec/evidence/TEST-001.json").read_text())
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(receipt["counts"]["passed"], 0)
        self.assertEqual(receipt["counts"]["errors"], 1)


if __name__ == "__main__":
    unittest.main()
