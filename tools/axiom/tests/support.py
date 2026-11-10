"""Shared fixtures for the axiom tests: the vendored ledger, a deep copy of it, and a temporary project."""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
FACTORY = HERE.parents[2]
PACKAGE = FACTORY / "knowledge/axiomspec/AxiomSpec"
LEDGER = PACKAGE / "examples/refund-ledger"
_ledger = json.loads((LEDGER / "spec.json").read_text(encoding="utf-8"))


def ledger():
    return copy.deepcopy(_ledger)


def mutate(document, mutation):
    """Apply one conformance-vector mutation (add, replace, remove, append) to a copy."""
    result = copy.deepcopy(document)
    parts = [p.replace("~1", "/").replace("~0", "~") for p in mutation["path"].split("/")[1:]]
    target = result
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = parts[-1]
    if mutation["op"] == "append":
        target[last].append(copy.deepcopy(mutation["value"]))
    elif mutation["op"] == "remove":
        del target[int(last) if isinstance(target, list) else last]
    else:
        target[int(last) if isinstance(target, list) else last] = copy.deepcopy(mutation["value"])
    return result


class Project:
    """A throwaway project folder with the factory's tools/axiom and schemas, for end-to-end commands."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="axiom-test-"))
        for rel in ("tools/axiom", ".claude/hooks", "knowledge/axiomspec/AxiomSpec/schemas"):
            shutil.copytree(FACTORY / rel, self.root / rel, ignore=shutil.ignore_patterns("tests", "__pycache__"))

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if isinstance(text, str) else json.dumps(text, indent=2), encoding="utf-8")
        return path

    def run(self, *args):
        import subprocess
        return subprocess.run([sys.executable, str(self.root / "tools/axiom/axiom"), "--root", str(self.root), *args],
                              capture_output=True, text=True)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def node(node_id, kind, title, data, status="active"):
    return {"id": node_id, "kind": kind, "revision": 1, "status": status, "title": title, "owner": "ACTOR-001",
            "created_by": "ACTOR-002", "source_ids": ["SRC-001"], "data": data}


def edge(number, source, relation, target):
    return {"id": f"EDGE-{number:03d}", "from": source, "relation": relation, "to": target, "origin": "declared",
            "rationale": "fixture"}


def pantry_spec():
    """A small product spec whose bindings point at the pantry fixture files."""
    requirement = {"category": "functional", "priority": "must", "risk": "medium", "verification_mode": "executable",
                   "pattern": "unwanted", "conditions": [], "trigger": "a take exceeds the stock", "feature": None,
                   "subject": "pantry", "response": "refuse the take without changing the stock"}
    return {
        "format": "axiomspec/0.1", "profile": "AX-CORE-0.1",
        "project": {"id": "PROJECT-001", "name": "Pantry", "description": "Fixture product.", "owner": "ACTOR-001",
                    "mode": "product"},
        "actors": [{"id": "ACTOR-001", "name": "Owner", "type": "human_role", "binding_status": "asserted"},
                   {"id": "ACTOR-002", "name": "Agent", "type": "ai", "binding_status": "asserted"}],
        "sources": [{"id": "SRC-001", "type": "user_input", "locator": "docs/authored/brief.md",
                     "capture_sha256": None, "review_state": "reviewed"}],
        "environments": [],
        "nodes": [
            node("GOAL-001", "Goal", "Never overdraw stock", {"description": "Stock stays non-negative.",
                                                              "success_measure": "No take below zero."}),
            node("REQ-001", "Requirement", "Refuse overdraw", requirement),
            node("REQ-002", "Requirement", "Record additions", dict(requirement, pattern="event",
                 trigger="an item is added", response="increase its stock", priority="should")),
            node("COMP-001", "Component", "Pantry store", {"responsibility": "Holds stock.", "boundary": "process"}),
            node("TEST-001", "TestCase", "Overdraw refused", {"level": "unit", "oracle": "Stock unchanged after refusal.",
                 "state": "implemented", "runner": "unittest", "negative": True, "witness_scenario_ids": []}),
            node("DEC-001", "Decision", "Units", {"question": "Count or weight?", "options": ["count", "weight"],
                 "answer": "count", "blocking": True, "rationale": "Simplest."})],
        "edges": [edge(1, "REQ-001", "satisfies", "GOAL-001"), edge(2, "REQ-002", "satisfies", "GOAL-001"),
                  edge(3, "COMP-001", "implements", "REQ-001"), edge(4, "TEST-001", "verifies", "REQ-001"),
                  edge(5, "DEC-001", "governs", "REQ-001"), edge(6, "REQ-002", "depends_on", "REQ-001")],
        "bindings": [{"id": "BIND-001", "kind": "code", "node_id": "COMP-001", "path": "app/pantry.py",
                      "symbol": "Pantry.take", "language": "python", "expected_resolution": "must_resolve"},
                     {"id": "BIND-002", "kind": "test", "node_id": "TEST-001", "path": "tests/test_pantry.py",
                      "symbol": "PantryTests.test_overdraw_refused", "language": "python",
                      "expected_resolution": "must_resolve"}],
        "context_assets": []}


PANTRY = {
    "app/pantry.py": '# Spec: knowledge/components/pantry.md\n"""Stock of items."""\nfrom util import positive\n\n\n'
                     'class Pantry:\n    def __init__(self):\n        self.stock = {}\n\n    def add(self, item, count):\n'
                     '        self.stock[item] = self.stock.get(item, 0) + positive(count)\n\n    def take(self, item, count):\n'
                     '        if self.stock.get(item, 0) < count:\n            raise ValueError("overdraw")\n'
                     '        self.stock[item] -= count\n',
    "app/util.py": "def positive(value):\n    if value <= 0:\n        raise ValueError('positive')\n    return value\n",
    "app/orphan.py": "VALUE = 1\n",
    "tests/test_pantry.py": "import sys\nimport unittest\nfrom pathlib import Path\n"
                            "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))\nfrom pantry import Pantry\n\n\n"
                            "class PantryTests(unittest.TestCase):\n    def test_overdraw_refused(self):\n        p = Pantry()\n"
                            "        p.add('rice', 1)\n        with self.assertRaises(ValueError):\n            p.take('rice', 2)\n"
                            "        self.assertEqual(p.stock['rice'], 1)\n",
    "knowledge/index.md": "---\ntype: Reference\ntitle: Index\ndescription: x\nstatus: stable\n---\n# Index\n\n"
                          "[Pantry](components/pantry.md)\n",
    "knowledge/components/pantry.md": "---\ntype: Component\ntitle: \"Pantry\"\ndescription: x\nstatus: draft\n"
                                      "sources:\n  - resource: ../../app/pantry.py\nspec_ids: [REQ-001]\n---\n# Pantry\n\n"
                                      "Implements REQ-001; see also `REQ-999` as an example.\n",
}


def pantry_project():
    project = Project()
    for rel, text in PANTRY.items():
        project.write(rel, text)
    project.write("knowledge/spec/spec.json", pantry_spec())
    return project
