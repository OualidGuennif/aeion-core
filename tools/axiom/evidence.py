# Spec: knowledge/components/axiom-toolkit.md
"""Test evidence (AX-G-010, AX-G-011, AX-T-005): run the unittest tests bound to each TestCase and
keep a receipt tied to the spec digest and the source tree; check receipts against current inputs.

The runner is fixed code (this file's adapter mode): no shell, no command text from the spec.
Receipts are local and untrusted: consistency is checked, never the producer's honesty."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import EVIDENCE_DIR, SPEC_PATH, TOOL_VERSION, canonical_digest, confined, pretty, sha256, write_atomic

ADAPTER = f"unittest/{TOOL_VERSION}"
ADAPTER_SCRIPT = Path(__file__).resolve().with_name("unittest_adapter.py")
TIMEOUT = 900


def source_tree(root):
    """AX-G-008: sorted (path, sha256) of code, test and config files; generated views and evidence excluded."""
    import graph
    files = [rel for rel in graph._files(Path(root)) if graph._role(rel) in ("code", "test", "config")
             and not rel.startswith(("docs/generated/", str(EVIDENCE_DIR) + "/"))]
    return canonical_digest([[rel, sha256((Path(root) / rel).read_bytes())] for rel in files])


def adapter_command(path, symbol):
    """The runner for one bound test. -P keeps the toolkit's own folder off sys.path, so no toolkit module
    shadows what the test imports, while PYTHONPATH and user site-packages still apply as under
    `python -m unittest`; -B writes no bytecode into the project."""
    return [sys.executable, "-P", "-B", str(ADAPTER_SCRIPT), path, symbol]

def run(root, model, ids):
    """Execute the bound tests of the selected active TestCases; one receipt each. Exit 0 all pass, 2 otherwise."""
    root = Path(root)
    tests = [n for n in model.active("TestCase") if not ids or n["id"] in ids]
    unknown = sorted(set(ids) - {n["id"] for n in tests})
    for test_id in unknown:
        print(f"evidence: {test_id} is not an active TestCase")
    tree = source_tree(root)
    worst = 2 if unknown else 0
    for test in tests:
        bindings = [b for b in model.spec["bindings"] if b["node_id"] == test["id"] and b["kind"] == "test"]
        if not bindings:
            print(f"  {test['id']}: no test binding; not executed (G10 stays unknown)")
            worst = max(worst, 3)
            continue
        receipt = _execute(root, test, bindings, model.digest, tree)
        write_atomic(root / EVIDENCE_DIR / f"{test['id']}.json", pretty(receipt))
        counts = receipt["counts"]
        print(f"  {test['id']}: {receipt['status']} ({counts['passed']}/{counts['collected']} passed"
              + (f", {counts['failed']} failed, {counts['errors']} errors, {counts['skipped']} skipped" if
                 receipt["status"] != "pass" else "") + ")")
        worst = max(worst, 0 if receipt["status"] == "pass" else 2)
    return worst


def _execute(root, test, bindings, spec_digest, tree):
    results, raw, problems = {}, [], []
    for binding in bindings:
        path = binding["path"]
        if binding["language"] != "python" or not path.endswith(".py"):
            problems.append(f"{binding['id']}: no adapter for {binding['language']} ({path})")
            continue
        if confined(root, path) is None or not (root / path).is_file():
            problems.append(f"{binding['id']}: {path} is missing or escapes the project")
            continue
        if not binding["symbol"]:
            problems.append(f"{binding['id']}: a test binding names a test (Class.test_method); this one names none")
            continue
        command = adapter_command(path, binding["symbol"])
        try:
            done = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=TIMEOUT,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        except subprocess.TimeoutExpired:
            problems.append(f"{binding['id']}: timed out after {TIMEOUT}s")
            continue
        raw.append(done.stdout + done.stderr)
        try:
            report = json.loads(done.stdout.strip().split("\n")[-1])
        except (ValueError, IndexError):
            problems.append(f"{binding['id']}: the adapter returned no report (exit {done.returncode})")
            continue
        if not report["results"]:
            problems.append(f"{binding['id']}: {report.get('error') or 'zero tests collected'}")
        for name, outcome in report["results"].items():
            key = f"{path}::{name}"
            if key in results:
                problems.append(f"{binding['id']}: {key} collected twice")
            results[key] = outcome
    counts = {"collected": len(results), "passed": sum(1 for v in results.values() if v == "pass"),
              "failed": sum(1 for v in results.values() if v == "fail"),
              "errors": sum(1 for v in results.values() if v == "error"),
              "skipped": sum(1 for v in results.values() if v == "skip")}
    passed = counts["collected"] > 0 and counts["passed"] == counts["collected"] and not problems
    files = sorted({b["path"] for b in bindings if (root / b["path"]).is_file()})
    return {"format": "aeion-test-receipt/0.1", "test_id": test["id"], "level": test["data"]["level"],
            "adapter": ADAPTER, "python": sys.version.split()[0], "trust": "untrusted_local",
            "bindings": [{"id": b["id"], "path": b["path"], "symbol": b["symbol"]} for b in bindings],
            "bound_files": {f: sha256((root / f).read_bytes()) for f in files},
            "results": dict(sorted(results.items())), "counts": counts, "problems": problems,
            "status": "pass" if passed else "fail", "spec_sha256": spec_digest, "source_tree_sha256": tree,
            "raw_output_sha256": sha256("".join(raw).encode("utf-8")),
            "executed_at": datetime.now(timezone.utc).isoformat()}


def receipts_state(root, model):
    """{TestCase ID: (state, detail)} with state current, failed, stale or missing (AX-G-010/011)."""
    root = Path(root)
    tree = source_tree(root)
    states = {}
    for test in model.active("TestCase"):
        path = root / EVIDENCE_DIR / f"{test['id']}.json"
        if not path.is_file():
            states[test["id"]] = ("missing", "planned or implemented, never executed through the adapter")
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            states[test["id"]] = ("failed", "receipt unreadable")
            continue
        if not isinstance(receipt, dict) or receipt.get("test_id") != test["id"]:
            states[test["id"]] = ("failed", "the receipt is not this test's (test_id differs or is missing)")
            continue
        counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
        if receipt.get("spec_sha256") != model.digest:
            states[test["id"]] = ("stale", "spec changed since the run")
        elif receipt.get("source_tree_sha256") != tree:
            states[test["id"]] = ("stale", "code, tests or configuration changed since the run")
        elif (receipt.get("status") != "pass" or not counts.get("collected") or counts.get("skipped")
              or counts.get("failed") or counts.get("errors")):
            states[test["id"]] = ("failed", f"status {receipt.get('status')}, counts {counts}")
        else:
            states[test["id"]] = ("current", f"{counts['passed']} test(s) passed at {receipt.get('executed_at', '?')}")
    return states


def check(root, model):
    states = receipts_state(root, model)
    for test_id, (state, detail) in sorted(states.items()):
        print(f"  {test_id:<10} {state:<8} {detail}")
    values = {state for state, _ in states.values()}
    code = 2 if values & {"failed", "stale"} else 3 if "missing" in values else 0
    print(f"evidence: {'current' if code == 0 else 'not current'} ({len(states)} active test case(s))")
    return code


def implementation_gates(root, model, result, spec_path=None):
    """G08-G12 for the implementation phase; what needs trusted adapters stays unknown."""
    import graph
    snapshot = graph.snapshot(root, Path(spec_path) if spec_path else Path(root) / SPEC_PATH)
    nodes = {n["id"]: n for n in snapshot["nodes"]}
    result.add("G08", "unknown", "NO_CONTEXT_ADMISSION", "context rights and delivery need a trusted principal "
               "and policy adapter, which this toolkit does not provide")
    for binding in model.spec["bindings"]:
        resolution = nodes.get(binding["id"], {}).get("resolution", {})
        if resolution.get("status") != "resolved":
            status = "fail" if binding["expected_resolution"] == "must_resolve" else "unknown"
            result.add("G09", status, "UNRESOLVED_BINDING", f"{binding['path']} {binding['symbol']}: "
                       f"{resolution.get('detail', resolution.get('status', 'not resolved'))}", binding["id"])
    for test_id, (state, detail) in sorted(receipts_state(root, model).items()):
        if state == "missing":
            result.add("G10", "unknown", "NOT_EXECUTED", detail, test_id)
        elif state == "failed":
            result.add("G10", "fail", "TEST_FAILED", detail, test_id)
        elif state == "stale":
            result.add("G11", "fail", "STALE_EVIDENCE", detail, test_id)
    result.add("G12", "unknown", "NO_AUTHORITY_ADAPTER", "actors are asserted, not authenticated; acceptance "
               "authority needs a trusted adapter (AX-P-008)")
