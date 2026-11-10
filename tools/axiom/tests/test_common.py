import json
import unittest

from support import PACKAGE, ledger
from common import canonical_bytes, canonical_digest, confined, relative_safe


class DigestTests(unittest.TestCase):
    def test_ledger_digest_matches_the_package_report(self):
        report = json.loads((PACKAGE / "validation/package-report.json").read_text())
        self.assertEqual(canonical_digest(ledger()), report["subject"]["spec_sha256"])

    def test_escapes_follow_ax_g_008(self):
        self.assertEqual(canonical_bytes({"b": 1, "a": [True, None]}), b'{"a":[true,null],"b":1}')
        self.assertEqual(canonical_bytes("\b\t\n\f\r\"\\"), b'"\\b\\t\\n\\f\\r\\"\\\\"')
        self.assertEqual(canonical_bytes("\x01\x1f"), b'"\\u0001\\u001f"')
        self.assertEqual(canonical_bytes("/ é"), '"/ é"'.encode())
        with self.assertRaises(ValueError):
            canonical_bytes(1.5)


class PathTests(unittest.TestCase):
    def test_relative_safe(self):
        for bad in ("/etc/passwd", "../x", "a/../b", "a\\b", "https://x", "a\0b", ""):
            self.assertFalse(relative_safe(bad), bad)
        self.assertTrue(relative_safe("src/app/main.py"))

    def test_confined_rejects_symlink_escape(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, Path(folder) / "link")
            self.assertIsNone(confined(folder, "link/secret.txt"))
            self.assertIsNotNone(confined(folder, "inside.txt"))


if __name__ == "__main__":
    unittest.main()
