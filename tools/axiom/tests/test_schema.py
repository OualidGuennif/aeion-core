import unittest

from support import PACKAGE, ledger
from schema import SchemaError, Validator, same
from strict import load


class SchemaTests(unittest.TestCase):
    def test_vendored_schemas_load_and_examples_pass(self):
        for name, example in (("spec", "examples/refund-ledger/spec.json"),
                              ("execution", "examples/refund-ledger/execution.json"),
                              ("croa-readiness", "examples/refund-ledger/croa-readiness.json"),
                              ("report", "validation/package-report.json")):
            validator = Validator(load(PACKAGE / f"schemas/{name}.schema.json"))
            self.assertEqual(validator.errors(load(PACKAGE / example)), [], name)

    def test_unsupported_keyword_fails_closed(self):
        with self.assertRaises(SchemaError):
            Validator({"type": "object", "if": {"type": "object"}})
        with self.assertRaises(SchemaError):
            Validator({"$ref": "https://example.org/remote.json"})

    def test_strict_equality(self):
        self.assertFalse(same(True, 1))
        self.assertFalse(same(1, "1"))
        self.assertTrue(same({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]}))
        self.assertEqual(Validator({"enum": [1]}).errors(True)[0][0], "")
        self.assertEqual(Validator({"type": "integer"}).errors(False)[0][1], "expected integer, found boolean")
        self.assertTrue(Validator({"type": "array", "uniqueItems": True}).errors([1, True]) == [])

    def test_dollar_anchors_at_the_true_end(self):
        validator = Validator({"type": "string", "pattern": "^[A-Z]+-[0-9]{3}$"})
        self.assertEqual(validator.errors("REQ-001"), [])
        self.assertNotEqual(validator.errors("REQ-001\n"), [])

    def test_unknown_field_is_reported_with_pointer(self):
        spec = ledger()
        spec["project"]["is_ready"] = True
        validator = Validator(load(PACKAGE / "schemas/spec.schema.json"))
        self.assertIn(("/project/is_ready", "unknown field 'is_ready'"), validator.errors(spec))


if __name__ == "__main__":
    unittest.main()
