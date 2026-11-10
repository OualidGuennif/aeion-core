"""The vendored AxiomSpec package stays verbatim, and its own links resolve."""
import hashlib
import json
import re
import unittest

from support import PACKAGE

PLAYBOOKS = PACKAGE.parent / "playbooks"
# Supplied by the owner's playbook but not by the package: recorded in knowledge/axiomspec/index.md.
KNOWN_MISSING = {("02_EXISTING_PROJECT_NVIDIA_TO_AXIOMSPEC.md", "../research/auto-ontology-comparison-2026-11-09.md")}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


class PackageTests(unittest.TestCase):
    def test_every_manifest_entry_is_byte_identical(self):
        manifest = json.loads((PACKAGE / "validation/package-manifest.json").read_text())
        for entry in manifest["entries"]:
            raw = (PACKAGE / entry["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"], entry["path"])
        self.assertEqual(len(manifest["entries"]), 46)

    def test_local_links_resolve_outside_code(self):
        for path in [*PACKAGE.rglob("*.md"), *PLAYBOOKS.glob("*.md")]:
            text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
            for target in LINK.findall(text):
                target = target.split("#")[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if (path.name, target) in KNOWN_MISSING:
                    continue
                self.assertTrue((path.parent / target).exists(), f"{path.relative_to(PACKAGE.parent)}: {target}")


if __name__ == "__main__":
    unittest.main()
