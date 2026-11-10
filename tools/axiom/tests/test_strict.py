import unittest

from support import FACTORY  # noqa: F401  (sets the import path)
from strict import InputError, loads


class StrictTests(unittest.TestCase):
    def code(self, raw, limit=1048576):
        with self.assertRaises(InputError) as caught:
            loads(raw, limit)
        return caught.exception.code

    def test_valid_document(self):
        self.assertEqual(loads(b'{"a": [1, true, null, "x"]}'), {"a": [1, True, None, "x"]})

    def test_refusals(self):
        # V-101: duplicate keys are refused before any schema evaluation.
        self.assertEqual(self.code(b'{"a": 1, "a": 2}'), "DUPLICATE_KEY")
        # V-102: the byte limit applies before decoding.
        self.assertEqual(self.code(b'{"a": "' + b"x" * 64 + b'"}', limit=32), "TOO_LARGE")
        self.assertEqual(self.code(b'{"a": 1.5}'), "NON_INTEGER_NUMBER")
        self.assertEqual(self.code(b'{"a": 1e3}'), "NON_INTEGER_NUMBER")
        self.assertEqual(self.code(b'{"a": NaN}'), "NON_FINITE_NUMBER")
        self.assertEqual(self.code(b'{"a": 9007199254740992}'), "UNSAFE_INTEGER")
        self.assertEqual(self.code(b'{"a": "\\ud800"}'), "LONE_SURROGATE")
        self.assertEqual(self.code('{"é": 1}'.encode()), "NON_ASCII_KEY")
        self.assertEqual(self.code(b'{"a": 1} {}'), "TRAILING_DATA")
        self.assertEqual(self.code(b'\xef\xbb\xbf{}'), "BOM")
        self.assertEqual(self.code(b'{"a": "\xff"}'), "INVALID_UTF8")
        self.assertEqual(self.code(b"[" * 200 + b"]" * 200), "TOO_DEEP")

    def test_safe_boundary_and_surrogate_pairs(self):
        self.assertEqual(loads(b"9007199254740991"), 9007199254740991)
        self.assertEqual(loads(b'"\\ud83d\\ude00"'), "\U0001F600")


if __name__ == "__main__":
    unittest.main()
