import json
import unittest

from support import LEDGER, ledger
import bcir
import spec as specs


def environment():
    return ledger()["environments"][0]


def constraint(constraint_id):
    return next(n for n in ledger()["nodes"] if n["id"] == constraint_id)["data"]["expression"]


def analyze(expression):
    env = environment()
    units, _ = bcir.unit_table(env, {"TERM-001", "TERM-002", "TERM-003", "TERM-004", "TERM-005"})
    return bcir.Analyzer(env, units).boolean_predicate(expression)


def path(pointer, root="env"):
    return {"kind": "path", "root": root, "pointer": pointer}


def apply(operator, *arguments):
    return {"kind": "apply", "operator": operator, "arguments": list(arguments)}


class LedgerTests(unittest.TestCase):
    def test_forty_five_reference_expectations(self):
        cases = json.loads((LEDGER / "observations.json").read_text())["cases"]
        model = specs.Model(ledger())
        validator = bcir.environment_validator(environment())
        checked = 0
        for case in cases:
            for constraint_id, expected in case["expected"].items():
                outcome = bcir.evaluate(model.nodes[constraint_id]["data"]["expression"], case["environment"],
                                        validator)
                self.assertEqual(outcome["result"], "pass" if expected else "fail",
                                 f"{case['scenario_id']} {constraint_id}")
                checked += 1
        self.assertEqual(checked, 45)

    def test_quadratic_uniqueness_exhausts_budget_at_500_rows(self):
        # V-107: the declared environment admits 1,000 rows; 500 already exceed the default budget.
        given = json.loads((LEDGER / "observations.json").read_text())["cases"][0]["environment"]
        given["state"]["refunds"] = [{"id": f"r{i}", "key": f"k{i}", "amount_minor": 1, "status": "released"}
                                     for i in range(500)]
        outcome = bcir.evaluate(constraint("CON-004"), given, bcir.environment_validator(environment()))
        self.assertEqual(outcome["result"], "unknown")
        self.assertIn("budget", outcome["reason"])
        smaller = dict(given, state=dict(given["state"], refunds=given["state"]["refunds"][:100]))
        self.assertEqual(bcir.evaluate(constraint("CON-004"), smaller,
                                       bcir.environment_validator(environment()))["result"], "pass")

    def test_missing_observation_is_unknown_not_empty(self):
        # V-108: an absent collection is not an empty one.
        given = json.loads((LEDGER / "observations.json").read_text())["cases"][0]["environment"]
        del given["state"]["refunds"]
        outcome = bcir.evaluate(constraint("CON-001"), given, bcir.environment_validator(environment()))
        self.assertEqual(outcome["result"], "unknown")

    def test_malformed_observation_is_an_error(self):
        given = json.loads((LEDGER / "observations.json").read_text())["cases"][0]["environment"]
        given["state"]["captured_minor"] = "1000"
        outcome = bcir.evaluate(constraint("CON-001"), given, bcir.environment_validator(environment()))
        self.assertEqual(outcome["result"], "error")

    def test_duplicates_are_preserved_in_sums(self):
        given = json.loads((LEDGER / "observations.json").read_text())["cases"][0]["environment"]
        given["state"].update(captured_minor=1000, refunds=[
            {"id": "a", "key": "a", "amount_minor": 600, "status": "reserved"},
            {"id": "a", "key": "a", "amount_minor": 600, "status": "reserved"}])
        outcome = bcir.evaluate(constraint("CON-001"), given, bcir.environment_validator(environment()))
        self.assertEqual(outcome["result"], "fail")


class StaticTests(unittest.TestCase):
    def assert_static_error(self, expression, fragment):
        with self.assertRaises(bcir.AnalysisError) as caught:
            analyze(expression)
        self.assertIn(fragment, str(caught.exception))

    def test_ledger_constraints_are_well_typed(self):
        for constraint_id in ("CON-001", "CON-002", "CON-003", "CON-004", "CON-005"):
            self.assertEqual(analyze(constraint(constraint_id))["t"], "boolean")

    def test_unknown_path(self):  # V-104
        self.assert_static_error(apply("gt", path("/state/missing"), {"kind": "literal", "value": 0}),
                                 "not declared")

    def test_boolean_in_arithmetic(self):  # V-105
        self.assert_static_error(apply("lt", apply("add", path("/auth/verified"), {"kind": "literal", "value": 1}),
                                       path("/state/captured_minor")), "integers")

    def test_unit_mismatch(self):  # V-106
        self.assert_static_error(apply("le", path("/state/captured_minor"), {"kind": "literal", "value": 5}), "unit")

    def test_literal_zero_takes_the_expected_unit(self):
        self.assertEqual(analyze(apply("gt", path("/state/captured_minor"), {"kind": "literal", "value": 0}))["t"],
                         "boolean")

    def test_shadowing_and_non_boolean_results(self):
        inner = {"kind": "quantifier", "operator": "all", "bind": "r", "collection": path("/state/refunds"),
                 "predicate": {"kind": "literal", "value": True}}
        outer = {"kind": "quantifier", "operator": "all", "bind": "r", "collection": path("/state/refunds"),
                 "predicate": inner}
        self.assert_static_error(outer, "fresh")
        self.assert_static_error(path("/state/captured_minor"), "must be Boolean")

    def test_count_needs_literal_one(self):
        count = {"kind": "aggregate", "operator": "count", "bind": "r", "collection": path("/state/refunds"),
                 "filter": {"kind": "literal", "value": True}, "projection": {"kind": "literal", "value": 2}}
        self.assert_static_error(apply("le", count, {"kind": "literal", "value": 1}), "literal integer 1")

    def test_environment_must_be_restricted(self):
        self.assertTrue(bcir.check_environment({"type": "object", "properties": {"a": {"type": "integer"}}}))
        self.assertEqual(bcir.check_environment(environment()["schema"]), [])


if __name__ == "__main__":
    unittest.main()
