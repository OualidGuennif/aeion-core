import json
import unittest

from support import PACKAGE, ledger, mutate
import spec as specs

VECTOR_CODES = {"V-006": "UNKNOWN_TARGET", "V-007": "WRONG_EDGE_TYPE", "V-008": "DUPLICATE_ID",
                "V-009": "UNKNOWN_ACTOR", "V-010": "DEPENDENCY_CYCLE"}


def run(document):
    """Schema, then gates: the same order as tools/axiom/axiom validate."""
    result = specs.Result()
    errors = specs.schema_validator().errors(document)
    for pointer, message in errors:
        result.add("G01", "error", "SCHEMA", message, pointer=pointer)
    if not errors:
        specs.validate(document, result=result)
    return result


def codes(result, gate):
    return {d["code"] for d in result.diagnostics if d["gate"] == gate}


def node(document, node_id):
    return next(n for n in document["nodes"] if n["id"] == node_id)


class ConformanceTests(unittest.TestCase):
    def test_ten_executable_vectors(self):
        vectors = json.loads((PACKAGE / "fixtures/conformance.json").read_text())["vectors"]
        executable = [v for v in vectors if v["layer"] in ("schema", "references")]
        self.assertEqual(len(executable), 10)
        for vector in executable:
            with self.subTest(vector["id"]):
                result = run(mutate(ledger(), vector["mutation"]))
                self.assertEqual(result.gate_status(vector["expected_gate"]), vector["expected_outcome"])
                if vector["id"] in VECTOR_CODES:
                    self.assertIn(VECTOR_CODES[vector["id"]], codes(result, "G02"))

    def test_unmutated_ledger_passes_g01_to_g06(self):
        result = run(ledger())
        for gate in ("G01", "G02", "G03", "G04", "G05", "G06"):
            self.assertEqual(result.gate_status(gate), "pass", gate)
        # The walkthrough says G07 is not satisfied: the plan lacks normal cases for REQ-003/004.
        self.assertEqual(result.gate_status("G07"), "fail")
        self.assertIn("MISSING_NORMAL_TEST", codes(result, "G07"))


class GateTests(unittest.TestCase):
    def test_open_blocking_decision_prevents_design_ready(self):
        document = ledger()
        node(document, "DEC-001")["data"]["answer"] = None  # V-109
        result = run(document)
        self.assertEqual(result.gate_status("G04"), "fail")
        self.assertIn("OPEN_BLOCKING_DECISION", codes(result, "G04"))

    def test_unvalidated_blocking_assumption(self):
        document = ledger()
        assumption = node(document, "ASM-001")["data"]
        assumption.update(blocking=True, state="unverified")  # V-110
        self.assertIn("UNVALIDATED_ASSUMPTION", codes(run(document), "G04"))

    def test_transition_to_unknown_state(self):
        document = ledger()
        node(document, "MODEL-001")["data"]["transitions"][0]["to"] = "nowhere"  # V-111
        result = run(document)
        self.assertEqual(result.gate_status("G05"), "fail")
        self.assertIn("UNKNOWN_STATE", codes(result, "G05"))

    def test_active_link_to_retired_requirement(self):
        document = ledger()
        node(document, "REQ-007")["status"] = "retired"  # V-127
        self.assertIn("ACTIVE_TO_RETIRED", codes(run(document), "G02"))

    def test_pattern_fields(self):
        document = ledger()
        node(document, "REQ-001")["data"]["trigger"] = None
        self.assertIn("PATTERN_FIELDS", codes(run(document), "G04"))

    def test_aggregation_never_promotes_unknown(self):
        result = specs.Result()
        result.add("G06", "unknown", "X", "budget")
        self.assertEqual(result.phase(specs.DESIGN_GATES), "unknown")
        result.add("G07", "fail", "Y", "missing")
        self.assertEqual(result.phase(specs.DESIGN_GATES), "fail")
        result.add("G01", "error", "Z", "schema")
        self.assertEqual(result.phase(specs.DESIGN_GATES), "error")

    def test_witness_cannot_expect_hard_invariant_false(self):
        document = ledger()
        scenario = node(document, "SCN-001")["data"]
        scenario["constraint_expectations"][0]["expected"] = False
        self.assertIn("WITNESS_VIOLATES_INVARIANT", codes(run(document), "G06"))

    def test_rendering_patterns(self):
        base = {"conditions": [], "trigger": None, "feature": None, "subject": "ledger", "response": "refuse it"}
        self.assertEqual(specs.render_requirement(dict(base, pattern="ubiquitous")), "The ledger shall refuse it.")
        self.assertEqual(specs.render_requirement(dict(base, pattern="unwanted", trigger="x")),
                         "If x, then the ledger shall refuse it.")
        self.assertEqual(specs.render_requirement(dict(base, pattern="composite", conditions=["a", "b"], trigger="t")),
                         "While a and b, when t, the ledger shall refuse it.")


if __name__ == "__main__":
    unittest.main()
