import json
import unittest
import xml.etree.ElementTree as ET

from support import LEDGER, ledger, pantry_project
import spec as specs
import views

FLOW = {"format": "aeion-view/0.1", "kind": "flow", "direction": "LR",
        "nodes": [{"id": "a", "label": "Client <script>alert(1)</script>", "shape": "actor"},
                  {"id": "b", "label": "Service & store", "shape": "decision"}, {"id": "c", "label": "Store", "shape": "store"}],
        "edges": [{"from": "a", "to": "b", "label": "asks \"why\""}, {"from": "b", "to": "c"}, {"from": "c", "to": "a",
                                                                                              "style": "dashed"}]}
SEQUENCE = {"format": "aeion-view/0.1", "kind": "sequence",
            "participants": [{"id": "u", "label": "User", "type": "actor"}, {"id": "s", "label": "Server"}],
            "steps": [{"from": "u", "to": "s", "label": "request"},
                      {"fragment": "alt", "branches": [{"label": "ok", "steps": [{"from": "s", "to": "u", "label": "200",
                                                                                   "kind": "reply"}]},
                                                       {"label": "no", "steps": [{"note": "refused", "over": ["s"]}]}]}]}
USECASE = {"format": "aeion-view/0.1", "kind": "usecase", "system": "Board",
           "actors": [{"id": "v", "label": "Visitor"}, {"id": "o", "label": "Operator", "side": "right"}],
           "usecases": [{"id": "see", "label": "See ideas"}, {"id": "run", "label": "Run it"}],
           "links": [{"actor": "v", "usecase": "see"}, {"actor": "o", "usecase": "run"}],
           "relations": [{"from": "run", "to": "see", "kind": "include"}]}


class ViewTests(unittest.TestCase):
    def parse(self, svg):
        return ET.fromstring(svg)

    def test_every_family_is_well_formed_and_deterministic(self):
        model = specs.Model(ledger())
        state = {"format": "aeion-view/0.1", "kind": "state", "model_id": "MODEL-001"}
        for source in (FLOW, SEQUENCE, USECASE, state):
            first = views.render(source, "Title", "Question?", model)
            self.assertEqual(first, views.render(json.loads(json.dumps(source)), "Title", "Question?", model))
            root = self.parse(first)
            self.assertTrue(root.tag.endswith("svg"))
            self.assertEqual(root.find("{http://www.w3.org/2000/svg}title").text, "Title")

    def test_labels_are_data_not_markup(self):
        svg = views.render(FLOW, "T <b>", "Q", None)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn("Service &amp; store", svg)
        self.parse(svg)

    def test_invalid_sources_are_refused(self):
        with self.assertRaises(views.ViewError):
            views.render(dict(FLOW, edges=[{"from": "a", "to": "zzz"}]), "T", "Q")
        with self.assertRaises(views.ViewError):
            views.render(dict(FLOW, kind="pie"), "T", "Q")
        with self.assertRaises(views.ViewError):
            views.render({"format": "aeion-view/0.1", "kind": "state", "model_id": "MODEL-999"}, "T", "Q",
                         specs.Model(ledger()))

    def test_check_detects_stale_and_orphan_diagrams(self):
        project = pantry_project()
        try:
            project.write("docs/views/flow.json", FLOW)
            project.write("docs/view-catalog.json", {"format": "project-doc-views/0.1", "views": [
                {"id": "VIEW-FLOW", "kind": "system", "title": "Flow", "question": "Who talks to whom?",
                 "claim": "proposed", "canonical_ids": [], "source_path": "docs/views/flow.json", "scope": "all"}]})
            root = project.root
            self.assertTrue(views.render_all(root, check=True))
            self.assertEqual(views.render_all(root), [])
            self.assertEqual(views.render_all(root, check=True), [])
            # A hand edit of a generated diagram keeps its mark, so it is the generator's and stale.
            svg = root / "docs/generated/diagrams/VIEW-FLOW.svg"
            svg.write_text(svg.read_text().replace("Who talks to whom?", "Edited by hand"))
            self.assertIn("stale", views.render_all(root, check=True)[0])
            (root / "docs/generated/diagrams/VIEW-OLD.svg").write_text(f"<svg {views.MARK}/>")
            self.assertTrue(any("no catalogued view" in p for p in views.render_all(root, check=True)))
        finally:
            project.close()


if __name__ == "__main__":
    unittest.main()
