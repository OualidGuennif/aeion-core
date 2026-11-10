import json
import os
import time
import unittest

from support import pantry_project
import graph


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.project = pantry_project()
        self.root = self.project.root

    def tearDown(self):
        self.project.close()

    def snapshot(self, **kw):
        return graph.snapshot(self.root, self.root / "knowledge/spec/spec.json", **kw)

    def edges(self, snapshot, relation):
        return {(e["from"], e["to"]) for e in snapshot["edges"] if e["relation"] == relation}

    def test_layers_are_joined(self):
        s = self.snapshot()
        self.assertIn(("file:app/pantry.py", "file:app/util.py"), self.edges(s, "imports"))
        self.assertIn(("file:tests/test_pantry.py", "file:app/pantry.py"), self.edges(s, "imports"))
        self.assertIn(("file:app/pantry.py", "file:knowledge/components/pantry.md"), self.edges(s, "specified_by"))
        self.assertIn(("file:knowledge/components/pantry.md", "file:app/pantry.py"), self.edges(s, "specifies"))
        self.assertIn(("REQ-001", "GOAL-001"), self.edges(s, "satisfies"))
        self.assertIn(("BIND-001", "file:app/pantry.py"), self.edges(s, "resolves_to"))
        self.assertIn(("file:knowledge/components/pantry.md", "REQ-001"), self.edges(s, "mentions"))
        binding = next(n for n in s["nodes"] if n["id"] == "BIND-001")
        self.assertEqual(binding["resolution"]["status"], "resolved")
        self.assertEqual(binding["resolution"]["line"], 13)

    def test_code_examples_are_not_references(self):
        dangling = self.snapshot()["manifest"]["spec"]["dangling_mentions"]
        self.assertEqual(dangling, {})
        self.project.write("knowledge/components/extra.md", "# Extra\n\nCites REQ-404 in prose.\n")
        self.assertEqual(self.snapshot()["manifest"]["spec"]["dangling_mentions"],
                         {"knowledge/components/extra.md": ["REQ-404"]})

    def test_deterministic_and_rebuilt_only_on_change(self):
        first = self.snapshot()
        nodes = (self.root / ".aeion/graph/nodes.json").read_bytes()
        again = self.snapshot()
        self.assertTrue(first["rebuilt"])
        self.assertFalse(again["rebuilt"])
        self.assertEqual(first["manifest"]["snapshot_id"], again["manifest"]["snapshot_id"])
        forced = self.snapshot(force=True)
        self.assertEqual((self.root / ".aeion/graph/nodes.json").read_bytes(), nodes)
        self.assertEqual(forced["manifest"]["snapshot_id"], first["manifest"]["snapshot_id"])
        time.sleep(0.01)
        self.project.write("app/util.py", "def positive(value):\n    return value\n")
        changed = self.snapshot()
        self.assertTrue(changed["rebuilt"])
        self.assertNotEqual(changed["manifest"]["snapshot_id"], first["manifest"]["snapshot_id"])

    def test_unresolved_must_binding_is_a_limit(self):
        spec = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        spec["bindings"][0]["symbol"] = "Pantry.vanish"
        self.project.write("knowledge/spec/spec.json", spec)
        s = self.snapshot()
        self.assertTrue(any("must_resolve" in limit for limit in s["manifest"]["analysis_limits"]))

    def test_foreign_graph_folder_is_replaced(self):
        folder = self.root / ".aeion/graph"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text("[1, 2]")
        self.assertTrue(self.snapshot()["rebuilt"])

    def test_secret_files_are_never_read(self):
        self.project.write(".env", "TOKEN=x")
        paths = {n.get("path") for n in self.snapshot()["nodes"]}
        self.assertNotIn(".env", paths)

    def test_ecmascript_imports_and_symbols(self):
        self.project.write("web/a.ts", "// import x from './nope'\nimport { b } from './b'\nexport class Cart {\n"
                                       "  total(): number {\n    return 1\n  }\n}\n")
        self.project.write("web/b.ts", "export const b = 1\n")
        s = self.snapshot()
        self.assertIn(("file:web/a.ts", "file:web/b.ts"), self.edges(s, "imports"))
        self.assertIn({"name": "Cart.total", "kind": "method", "line": 4}, s["symbols"]["web/a.ts"])


if __name__ == "__main__":
    unittest.main()
