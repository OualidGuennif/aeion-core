# Spec: knowledge/components/goldfish.md
"""The three sections with scripted agents: what each sends (once), what it accepts, and what it refuses."""
import json
import unittest

from support import Workspace, events
from aeion import brainstorm, design, docshub, goldfish, specstudio
from aeion.store import StoreError

FRAGMENT = {
    "title": "Saved searches",
    "goal": {"title": "Members find new posts on saved topics", "description": "Members save up to 20 searches and "
             "receive a weekly digest of new matching posts.", "success_measure": "30% of members with saved searches "
             "open a digest each month."},
    "terms": [{"key": "x1", "title": "Saved search", "definition": "A query a member stored to replay later.", "unit": None}],
    "requirements": [
        {"key": "r1", "title": "Save a search", "category": "functional", "priority": "must", "risk": "high",
         "verification_mode": "executable", "pattern": "event", "conditions": [], "trigger": "A member saves a search.",
         "feature": None, "subject": "the search store", "response": "Store it and list it on the member's page.",
         "terms": ["x1"], "depends_on": []},
        {"key": "r2", "title": "Refuse a 21st search", "category": "functional", "priority": "must", "risk": "medium",
         "verification_mode": "executable", "pattern": "unwanted", "conditions": [],
         "trigger": "a member who has 20 saved searches saves another", "feature": None, "subject": "search store",
         "response": "refuse it and change nothing", "terms": ["x1"], "depends_on": ["r1"]}],
    "decisions": [{"key": "d1", "title": "Digest unit", "question": "One email per member or one per search?",
                   "options": ["One per member", "One per search"], "recommendation": "One per member", "blocking": True,
                   "governs": ["r1"], "rationale": "Changes the send volume by up to 20 times."}],
    "assumptions": [{"key": "a1", "title": "Search replay cost", "claim": "Postgres full-text replays 600k queries in six hours.",
                     "validation_method": "Load test on a production copy.", "blocking": False, "assumed_by": ["r1"]}],
    "tests": [
        {"key": "t1", "title": "Saving works", "level": "integration", "negative": False,
         "oracle": "After saving, the search is listed once.", "verifies": ["r1"]},
        {"key": "t2", "title": "Bad search refused", "level": "unit", "negative": True,
         "oracle": "An empty query is refused and nothing is stored.", "verifies": ["r1"]},
        {"key": "t3", "title": "Cap enforced", "level": "unit", "negative": True,
         "oracle": "The 21st save is refused and the 20 stay unchanged.", "verifies": ["r2"]}],
    "components": [{"key": "c1", "title": "Search store", "responsibility": "Keep each member's saved searches.",
                    "boundary": "Only the member's own searches.", "implements": ["r1", "r2"]}],
    "export": {"delivery": ["Add the saved-search table and its 20-per-member cap.", "Add the save and list endpoints with tests."],
               "out_of_scope": ["Per-match alerts."], "test_scenario": "A member saves 20 searches; the 21st is refused.",
               "area": "forum", "size": "M", "phase": "P3"},
}


def submit(name, value):
    return {"calls": [(name, value)], "text": ""}


class BrainstormTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def tearDown(self):
        self.ws.close()

    def test_first_turn_sends_the_idea_once_and_the_tool_anchors_the_hypothesis(self):
        session = brainstorm.create(self.ws.store, "Digest", "Members miss replies.", "owner")
        self.ws.agents.script("elephant", {"text": "Who misses them?", "calls": []})
        brainstorm.turn(self.ws.store, self.ws.agents, session["id"], "")
        call = self.ws.agents.calls[-1]
        self.assertEqual(call["message"], "Members miss replies.")
        self.assertEqual(call["blocks"], [])
        self.ws.agents.script("elephant", {"text": "Clear enough.", "calls": [("anchor_hypothesis", {"hypothesis": "A weekly digest for members who follow threads."})]})
        stored = brainstorm.turn(self.ws.store, self.ws.agents, session["id"], "Members who follow threads.")
        call = self.ws.agents.calls[-1]
        self.assertEqual(call["message"], "Members who follow threads.")
        self.assertNotIn("Members who follow threads.", json.dumps(call["blocks"]))
        self.assertEqual(stored["hypothesis"], "A weekly digest for members who follow threads.")

    def test_review_needs_a_hypothesis(self):
        session = brainstorm.create(self.ws.store, "Digest", "Idea.", "owner")
        with self.assertRaises(StoreError):
            brainstorm.review(self.ws.store, self.ws.agents, session["id"])

    def test_review_runs_seven_fresh_goldfish_then_the_brief(self):
        session = brainstorm.create(self.ws.store, "Digest", "Idea.", "owner")
        stored = self.ws.store.session(session["id"])
        stored["hypothesis"] = "A digest."
        self.ws.store.save_session(stored)
        self.ws.agents.script("synthesizer", {"text": "# Digest\n\n## Overview\n\nA brief."})
        seen, emit = events()
        result = brainstorm.review(self.ws.store, self.ws.agents, session["id"], emit)
        fish = [c for c in self.ws.agents.calls if c["agent"] == "goldfish"]
        self.assertEqual(len(fish), 7)
        self.assertTrue(all(c["blocks"][-1] == {"tag": "feature_concept", "body": "A digest."} for c in fish))
        self.assertTrue(all("conversation" not in json.dumps(c["blocks"]) for c in fish))
        self.assertEqual(result["briefs"][-1]["markdown"], "# Digest\n\n## Overview\n\nA brief.")


class GoldfishTests(unittest.TestCase):
    def test_review_input_numbers_the_range_and_names_the_standard_once(self):
        message, blocks = goldfish.review_input("REVIEW", "a\nb\nc", (2, 3), "zoom-out-standard")
        self.assertIn("target_standard", message)
        self.assertEqual([b["tag"] for b in blocks], ["mode", "target_standard", "target_file"])
        self.assertIn("   2  b", blocks[-1]["body"])
        self.assertNotIn("   1  a", blocks[-1]["body"])

    def test_a_reviewer_that_fails_twice_is_not_run(self):
        from aeion.llm import LLMError
        ws = Workspace()
        ws.agents.script("goldfish", LLMError("network", "down"), LLMError("network", "down"))
        result = goldfish.run(ws.agents, "egm-design", "BRAINSTORM", "A concept.")
        ws.close()
        self.assertEqual((result["status"], result["report"]), ("not run", ""))

    def test_split_finds_the_implementation_plan(self):
        doc = "# T\n## Overview\ntext\n## Detailed Implementation Plan\nsteps"
        self.assertEqual(goldfish.split(doc), ((1, 3), (4, 5)))


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.feature = self.ws.store.save_feature("Digest", "# Digest\n\nThe brief.", "brief", "test")

    def tearDown(self):
        self.ws.close()

    def test_ask_owner_turns_the_section_into_a_question(self):
        draft = design.create_draft(self.ws.store, self.feature["id"])
        self.ws.agents.script("drafter", {"calls": [("ask_owner", {"question": "Store digests in Postgres or a queue?"})]})
        session = design.draft_section(self.ws.store, self.ws.agents, draft["id"])
        self.assertEqual(session["sections"][0]["status"], "question")
        with self.assertRaises(StoreError):
            design.approve_section(self.ws.store, draft["id"])

    def test_resolution_refuses_an_edit_that_does_not_apply_once(self):
        review = design.create_review(self.ws.store, self.feature["id"])
        stored = self.ws.store.session(review["id"])
        stored["stages"][0]["findings"] = [{"title": "Vague", "severity": "Major", "reviewer": "egm-zoom-out", "scope": "l3",
                                            "description": "d", "recommendation": "r"}]
        self.ws.store.save_session(stored)
        bad = {"items": [{"index": 1, "category": "PROPOSE FIX", "justification": "j", "find": "missing text", "replace": "x"}]}
        good = {"items": [{"index": 1, "category": "PROPOSE FIX", "justification": "j", "find": "The brief.", "replace": "A brief."}]}
        self.ws.agents.script("resolver", {"calls": [("submit_resolution", bad), ("submit_resolution", good)]})
        items = design.resolve(self.ws.store, self.ws.agents, review["id"], 5)
        self.assertIn("occurs 0 times", self.ws.agents.last_outputs[0])
        self.assertTrue(items[0]["applicable"])
        result = design.apply(self.ws.store, review["id"], 5, [1])
        self.assertEqual(result["applied"], [1])
        self.assertIn("A brief.", self.ws.store.feature(self.feature["id"])[1])


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.feature = self.ws.store.save_feature("Saved searches", "# Saved searches\n\nMembers save searches.", "brief", "test")

    def tearDown(self):
        self.ws.close()

    def draft(self, fragment):
        session = specstudio.create(self.ws.store, self.feature["id"], "demo-product")
        self.ws.agents.script("analyst", submit("submit_fragment", fragment))
        return specstudio.draft(self.ws.store, self.ws.agents, self.ws.settings, session["id"])

    def test_draft_merges_normalized_requirements_and_leaves_decisions_to_the_owner(self):
        session = self.draft(FRAGMENT)
        spec = json.loads((self.ws.store.product("demo-product") / "knowledge/spec/spec.json").read_text())
        requirement = next(n for n in spec["nodes"] if n["kind"] == "Requirement" and n["title"] == "Save a search")
        self.assertEqual(requirement["data"]["trigger"], "a member saves a search")
        self.assertEqual(requirement["data"]["subject"], "search store")
        self.assertEqual(requirement["data"]["response"], "store it and list it on the member's page")
        decision = next(n for n in spec["nodes"] if n["kind"] == "Decision")
        self.assertIsNone(decision["data"]["answer"])
        self.assertEqual(session["state"], "interview")
        self.assertEqual(session["questions"][0]["kind"], "decision")

    def test_failed_gates_go_back_to_the_analyst_by_local_key(self):
        broken = json.loads(json.dumps(FRAGMENT))
        broken["requirements"][0]["pattern"] = "state"  # state needs conditions: G04 PATTERN_FIELDS
        session = specstudio.create(self.ws.store, self.feature["id"], "demo-product")
        self.ws.agents.script("analyst", {"calls": [("submit_fragment", broken), ("submit_fragment", FRAGMENT)]})
        specstudio.draft(self.ws.store, self.ws.agents, self.ws.settings, session["id"])
        outputs = self.ws.agents.last_outputs
        self.assertIn("PATTERN_FIELDS on r1", outputs[0])
        self.assertEqual(outputs[1], "Accepted.")

    def test_an_amendment_fixes_one_item_and_is_checked_as_a_whole(self):
        broken = json.loads(json.dumps(FRAGMENT))
        broken["requirements"][0]["pattern"] = "state"
        fixed = json.loads(json.dumps(FRAGMENT["requirements"][0]))
        session = specstudio.create(self.ws.store, self.feature["id"], "demo-product")
        self.ws.agents.script("analyst", {"calls": [("amend_fragment", {"requirements": [fixed]}),
                                                    ("submit_fragment", broken),
                                                    ("amend_fragment", {"requirements": [fixed]})]})
        specstudio.draft(self.ws.store, self.ws.agents, self.ws.settings, session["id"])
        outputs = self.ws.agents.last_outputs
        self.assertIn("nothing to amend yet", outputs[0])
        self.assertIn("amend_fragment", outputs[1])
        self.assertEqual(outputs[2], "Accepted.")
        spec = json.loads((self.ws.store.product("demo-product") / "knowledge/spec/spec.json").read_text())
        self.assertEqual(sum(1 for n in spec["nodes"] if n["kind"] == "Requirement"), 2)

    def test_answers_then_approval_write_an_export_the_build_factory_accepts(self):
        session = self.draft(FRAGMENT)
        decision = session["questions"][0]
        session = specstudio.answer(self.ws.store, self.ws.agents, self.ws.settings, session["id"], decision["id"], "One per member")
        self.assertEqual(session["state"], "ready", session["checks"])
        approved = specstudio.approve(self.ws.store, self.ws.agents, self.ws.settings, session["id"])
        export = approved["export"]
        text = (self.ws.store.product("demo-product") / "exports" / export["file"]).read_text()
        self.assertTrue(export["file"].startswith("101-"))
        self.assertLessEqual(len(text.encode()), 12000)
        self.assertIn("## Acceptance checks", text)
        self.assertIn("- [ ] ", text)
        self.assertTrue(text.startswith("---\nid: 101\n"))
        self.assertEqual(export["row"]["tier"], 3)

    def test_approval_is_refused_while_a_blocking_decision_is_open(self):
        session = self.draft(FRAGMENT)
        with self.assertRaises(StoreError):
            specstudio.approve(self.ws.store, self.ws.agents, self.ws.settings, session["id"])

    def test_patch_may_relink_a_test_but_never_answer_a_decision(self):
        session = self.draft(FRAGMENT)
        spec = json.loads((self.ws.store.product("demo-product") / "knowledge/spec/spec.json").read_text())
        tests = {n["title"]: n["id"] for n in spec["nodes"] if n["kind"] == "TestCase"}
        reqs = {n["title"]: n["id"] for n in spec["nodes"] if n["kind"] == "Requirement"}
        dec = next(n["id"] for n in spec["nodes"] if n["kind"] == "Decision")
        patch = {"note": "relink", "update": [{"id": tests["Cap enforced"], "fields": {"verifies": [reqs["Save a search"], reqs["Refuse a 21st search"]]}},
                                              {"id": dec, "fields": {"answer": "One per member"}}], "add": {}, "drop": []}
        self.ws.agents.script("patcher", submit("submit_patch", patch))
        specstudio.change(self.ws.store, self.ws.agents, self.ws.settings, session["id"], "relink")
        spec = json.loads((self.ws.store.product("demo-product") / "knowledge/spec/spec.json").read_text())
        links = {e["to"] for e in spec["edges"] if e["from"] == tests["Cap enforced"] and e["relation"] == "verifies"}
        self.assertEqual(links, {reqs["Save a search"], reqs["Refuse a 21st search"]})
        self.assertIsNone(next(n for n in spec["nodes"] if n["id"] == dec)["data"]["answer"])

    def test_write_paths_follow_the_build_factory_scope_rules(self):
        session = self.draft(FRAGMENT)
        for bad in ("demo/forum-app/.git/", "demo/forum-app//x", "other/path/", "demo/forum-app/../x"):
            checked = specstudio.set_entry(self.ws.store, self.ws.settings, session["id"], {"write_paths": bad})
            self.assertIn("WRITE_PATHS", [i["code"] for i in checked["checks"]["export"]], bad)


class DocsTests(unittest.TestCase):
    def test_section_text_stops_at_the_next_heading_of_the_same_level(self):
        text = "# Page\n\nintro\n\n## One\n\nfirst\n\n### Deeper\n\nmore\n\n## Two\n\nsecond\n"
        title, body = docshub.section_text(text, "one")
        self.assertEqual(title, "One")
        self.assertIn("more", body)
        self.assertNotIn("second", body)
        self.assertEqual(docshub.section_text(text, "absent"), (None, None))

    def test_the_answer_cites_only_numbered_evidence(self):
        ws = Workspace()
        try:
            ws.store.save_feature("Saved searches", "# Saved searches\n\n## Cap\n\nTwenty searches per member.", "brief", "test")
            corpus = docshub.Corpus(ws.settings, ws.store)
            assistant = docshub.Assistant(corpus, ws.agents, ws.settings, ws.store)
            ws.agents.script("librarian", {"calls": [("search_docs", {"query": "searches per member"})],
                                           "text": "Twenty per member [1]. Also [7]."})
            result = assistant.ask("How many saved searches?", session="t")
        finally:
            ws.close()
        self.assertEqual([s["number"] for s in result["sources"]], [1])


if __name__ == "__main__":
    unittest.main()
