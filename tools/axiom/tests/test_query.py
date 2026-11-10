import json
import unittest

from support import pantry_project
import graph
import query


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = pantry_project()
        cls.snapshot = graph.snapshot(cls.project.root, cls.project.root / "knowledge/spec/spec.json")

    @classmethod
    def tearDownClass(cls):
        cls.project.close()

    def ask(self, kind, *args, **kw):
        return query.run(self.snapshot, kind, list(args), **kw)

    def test_exact_names_only(self):
        _, code = self.ask("deps", "app/pantry.py")
        self.assertEqual(code, 0)
        _, code = self.ask("deps", "app/pant")
        self.assertEqual(code, 4)
        self.project.write("lib/pantry2.py", "def take():\n    pass\n")
        snapshot = graph.snapshot(self.project.root, self.project.root / "knowledge/spec/spec.json")
        response, code = query.run(snapshot, "rdeps", ["take"])
        self.assertEqual(code, 3)
        self.assertEqual(len(response["items"]), 2)

    def test_tests_and_untested(self):
        response, _ = self.ask("tests", "app/util.py")
        self.assertEqual([(i["test"], i["how"]) for i in response["items"]], [("tests/test_pantry.py", "reaches")])
        response, _ = self.ask("untested")
        self.assertIn("app/orphan.py", [i["path"] for i in response["items"]])
        self.assertNotIn("app/util.py", [i["path"] for i in response["items"]])

    def test_spec_links_both_ways_and_canonical(self):
        response, _ = self.ask("spec", "app/pantry.py")
        hows = [i["how"] for i in response["items"]]
        self.assertIn("frontmatter sources", hows)
        self.assertIn("Spec: header", hows)
        self.assertTrue(any(i.get("canonical") == "COMP-001" for i in response["items"]))

    def test_requirement_and_impact(self):
        response, _ = self.ask("requirement", "REQ-001")
        self.assertIn("If a take exceeds the stock, then the pantry shall refuse", response["items"][0]["sentence"])
        ids = {i["id"] for i in response["items"]}
        self.assertTrue({"GOAL-001", "COMP-001", "TEST-001", "DEC-001", "BIND-001"} <= ids)
        response, _ = self.ask("impact", "app/pantry.py", "app/orphan.py")
        kinds = {(i["kind"], i["id"]) for i in response["items"]}
        self.assertIn(("seed", "REQ-001"), kinds)
        self.assertIn(("unmapped_change", "app/orphan.py"), kinds)
        self.assertIn(("test_to_run", "file:tests/test_pantry.py"), kinds)

    def test_bounded_response(self):
        response = query._response(query.Index(self.snapshot), {"kind": "x"}, [{"n": i} for i in range(150)])
        self.assertEqual(response["returned_count"], 100)
        self.assertFalse(response["complete"])
        self.assertTrue(response["omissions"])

    def test_gaps_name_their_gate(self):
        response, _ = self.ask("gaps")
        gaps = {(i["gate"], i["subject"]) for i in response["items"]}
        self.assertIn(("G06", "REQ-001"), gaps)
        self.assertIn(("docs", "app/util.py"), gaps)


class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = pantry_project()
        cls.snapshot = graph.snapshot(cls.project.root, cls.project.root / "knowledge/spec/spec.json")

    @classmethod
    def tearDownClass(cls):
        cls.project.close()

    def ids(self, packet):
        return {item["id"] for part in packet["parts"] for item in part["items"]}

    def test_closure_follows_ax_k_010(self):
        packet = query.packet(self.snapshot, [], ["app/pantry.py"])
        self.assertEqual(packet["status"], "complete")
        self.assertEqual(packet["seeds"], ["REQ-001"])
        # depends_on is expanded in both directions, governing decisions and bindings come along.
        self.assertTrue({"REQ-001", "REQ-002", "GOAL-001", "DEC-001", "TEST-001", "COMP-001", "BIND-001",
                         "ACTOR-001", "SRC-001"} <= self.ids(packet))

    def test_budget_splits_never_drops(self):
        whole = query.packet(self.snapshot, ["REQ-001"], [])
        split = query.packet(self.snapshot, ["REQ-001"], [], budget_bytes=600)
        self.assertGreater(len(split["parts"]), 1)
        self.assertEqual(self.ids(whole), self.ids(split))
        self.assertEqual(whole["closure_sha256"], split["closure_sha256"])

    def test_unmapped_change_makes_packet_incomplete(self):
        packet = query.packet(self.snapshot, ["REQ-777"], ["app/orphan.py"])
        self.assertEqual(packet["status"], "incomplete")
        self.assertEqual(packet["unmapped_changes"], ["app/orphan.py"])
        self.assertEqual(packet["unknown_ids"], ["REQ-777"])
        self.assertIn("Incomplete", query.packet_markdown(packet))


if __name__ == "__main__":
    unittest.main()
