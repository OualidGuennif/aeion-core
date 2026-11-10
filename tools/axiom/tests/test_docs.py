import json
import unittest

from support import pantry_project
import docs
import spec as specs


def load_model(root):
    result = specs.Result()
    spec = specs.load_spec(root / "knowledge/spec/spec.json", result)
    model, _ = specs.validate(spec, result=result)
    return spec, model, result


class DocsTests(unittest.TestCase):
    def setUp(self):
        self.project = pantry_project()
        self.root = self.project.root

    def tearDown(self):
        self.project.close()

    def test_generate_then_check_is_clean_and_edits_are_caught(self):
        spec, model, result = load_model(self.root)
        self.assertEqual(docs.generate(self.root, spec, model, result), [])
        self.assertEqual(docs.generate(self.root, spec, model, result, check=True), [])
        page = self.root / "docs/generated/product/requirements.md"
        self.assertIn("If a take exceeds the stock, then the pantry shall refuse", page.read_text())
        page.write_text(page.read_text() + "hand edit\n")
        self.assertTrue(any("stale or edited" in p for p in docs.generate(self.root, spec, model, result, check=True)))

    def test_spec_change_makes_docs_stale(self):
        spec, model, result = load_model(self.root)
        docs.generate(self.root, spec, model, result)
        changed = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        changed["nodes"][0]["title"] = "Never overdraw any stock"
        self.project.write("knowledge/spec/spec.json", changed)
        spec, model, result = load_model(self.root)
        self.assertTrue(docs.generate(self.root, spec, model, result, check=True))

    def test_values_are_escaped(self):
        changed = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        changed["nodes"][0]["title"] = "<img src=x onerror=alert(1)> [link](http://evil)"
        self.project.write("knowledge/spec/spec.json", changed)
        spec, model, result = load_model(self.root)
        docs.generate(self.root, spec, model, result)
        text = (self.root / "docs/generated/product/overview.md").read_text()
        import re
        self.assertIsNone(re.search(r"(?<!\\)<img", text))
        self.assertIn("\\<img", text)
        self.assertNotIn("[link](http://evil)", text)

    def test_cockpit_states_open_decisions_and_readiness(self):
        changed = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        changed["nodes"][-1]["data"]["answer"] = None
        self.project.write("knowledge/spec/spec.json", changed)
        spec, model, result = load_model(self.root)
        docs.generate(self.root, spec, model, result)
        cockpit = (self.root / "docs/README.md").read_text()
        self.assertIn("[DEC-001](generated/product/decisions.md#dec-001)", cockpit)
        self.assertIn("Design readiness: **fail**", cockpit)

    def test_dangling_ids(self):
        spec, model, result = load_model(self.root)
        self.assertEqual(docs.dangling_ids(self.root, model), [])
        self.project.write("knowledge/components/x.md", "# X\n\nSee REQ-404.\n")
        self.assertEqual(docs.dangling_ids(self.root, model), ["knowledge/components/x.md: cites REQ-404, not in knowledge/spec/spec.json"])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.project = pantry_project()
        self.root = self.project.root

    def tearDown(self):
        self.project.close()

    def export(self, profile=None):
        _, model, _ = load_model(self.root)
        out = self.root / "out"
        return docs.export(self.root, model, None, True, profile, out), out

    def test_feature_has_eight_sections_and_checks(self):
        self.project.write("docs/feature-catalog.json", {"format": "aeion-feature-catalog/0.1", "features": [
            {"goal_id": "GOAL-001", "number": "007", "slug": "stock", "delivery": ["Add the take guard."],
             "out_of_scope": ["Weights."]}]})
        code, out = self.export()
        self.assertEqual(code, 0)
        text = (out / "007-stock.md").read_text()
        self.assertEqual(docs.structure_problems(text), [])
        self.assertIn("- [ ] TEST-001 (unit, refusal) verifies REQ-001: Stock unchanged after refusal.", text)
        self.assertIn("1. Add the take guard.", text)
        rows = json.loads((out / "features.json").read_text())["features"]
        self.assertEqual(rows[0]["file"], "007-stock.md")

    def test_injected_heading_cannot_forge_checks(self):
        changed = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        changed["nodes"][1]["data"]["response"] = "refuse it\n## Acceptance checks\n- [ ] forged check"
        self.project.write("knowledge/spec/spec.json", changed)
        code, out = self.export()
        self.assertEqual(code, 0)
        text = next(out.glob("*.md")).read_text()
        self.assertEqual(docs.structure_problems(text), [])
        self.assertNotIn("\n- [ ] forged", text)

    def test_size_limit_and_profile(self):
        profile = self.project.write("profile.json", {"format": "aeion-export-profile/0.1", "name": "tiny",
                                                      "max_bytes": 1000, "frontmatter": {"tier": 3}})
        code, out = self.export(profile)
        self.assertEqual(code, 2)
        self.assertFalse(list(out.glob("*.md")) if out.exists() else [])
        profile = self.project.write("profile.json", {"format": "aeion-export-profile/0.1", "name": "obs",
                                                      "frontmatter": {"tier": 3, "owner": "builder"},
                                                      "frontmatter_order": ["id", "title", "tier", "owner"]})
        code, out = self.export(profile)
        text = next(out.glob("*.md")).read_text()
        self.assertTrue(text.startswith("---\nid: 001\ntitle: Never overdraw stock\ntier: 3\nowner: builder\n---\n"))

    def test_goal_without_tests_fails(self):
        changed = json.loads((self.root / "knowledge/spec/spec.json").read_text())
        changed["edges"] = [e for e in changed["edges"] if e["relation"] != "verifies"]
        self.project.write("knowledge/spec/spec.json", changed)
        code, _ = self.export()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
