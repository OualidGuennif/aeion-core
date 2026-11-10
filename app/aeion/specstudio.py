# Spec: knowledge/components/spec-studio.md
"""Section 2, the spec studio: a saved feature document becomes one goal of a product's canonical
AxiomSpec specification, checked by the template's own gates, completed through an interview with the
owner, then exported as the eight-section Markdown that aeion-observability builds.

The analyst agent drafts a fragment with local keys; code assigns IDs and edges. Every submission is
merged into a scratch copy and checked by the same gates before it is accepted, so the agent fixes what
it can before the owner sees it; a patch that still fails is not applied, and nothing `axiom check`
would refuse is ever saved. No agent answers a decision, approves, or writes a file: decisions,
approval and export are the owner's acts."""
import copy
import functools
import hashlib
import json
import re
from datetime import date
from pathlib import Path

import docs as axdocs
import spec as axspec
import strict as axstrict
import views as axviews
from schema import Validator
from .agents import Submit, ToolRefused, streaming
from .store import StoreError, now

PROFILES = Path(__file__).resolve().parent / "profiles"
ASSISTANT = "aeion-core assistant"
_text = {"type": "string", "minLength": 1, "maxLength": 600}
_long = {"type": "string", "minLength": 1, "maxLength": 2000}
_keys = {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 20}}
# Hard bounds stop runaway values; the 12,000-byte export check is what keeps the feature short, with
# feedback per section, so a long sentence never forces the analyst to regenerate a whole fragment.
_clause = {"type": "string", "minLength": 1, "maxLength": 500}
_short = {"type": "string", "minLength": 1, "maxLength": 800}
_requirement = {"type": "object", "additionalProperties": False,
                "required": ["key", "title", "category", "priority", "risk", "verification_mode", "pattern", "conditions",
                             "trigger", "feature", "subject", "response", "terms", "depends_on"],
                "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                               "category": {"enum": ["functional", "quality", "security", "privacy", "data"]},
                               "priority": {"enum": ["must", "should", "could"]}, "risk": {"enum": ["low", "medium", "high", "critical"]},
                               "verification_mode": {"enum": ["executable", "manual", "mixed"]},
                               "pattern": {"enum": ["ubiquitous", "event", "state", "unwanted", "optional", "composite"]},
                               "conditions": {"type": "array", "maxItems": 3, "items": _clause},
                               "trigger": {"anyOf": [_clause, {"type": "null"}]}, "feature": {"anyOf": [_clause, {"type": "null"}]},
                               "subject": {"type": "string", "minLength": 1, "maxLength": 120}, "response": _short,
                               "terms": _keys, "depends_on": _keys}}
_test = {"type": "object", "additionalProperties": False, "required": ["key", "title", "level", "negative", "oracle", "verifies"],
         "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                        "level": {"enum": ["unit", "property", "integration", "contract", "e2e", "model", "manual"]},
                        "negative": {"type": "boolean"}, "oracle": _short, "verifies": _keys}}
_term = {"type": "object", "additionalProperties": False, "required": ["key", "title", "definition", "unit"],
         "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                        "definition": _short, "unit": {"anyOf": [{"type": "string", "maxLength": 40}, {"type": "null"}]}}}
_decision = {"type": "object", "additionalProperties": False,
             "required": ["key", "title", "question", "options", "recommendation", "blocking", "governs", "rationale"],
             "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                            "question": _clause, "options": {"type": "array", "minItems": 2, "maxItems": 4, "items": _clause},
                            "recommendation": {"anyOf": [_text, {"type": "null"}]}, "blocking": {"type": "boolean"},
                            "governs": _keys, "rationale": _long}}
_assumption = {"type": "object", "additionalProperties": False, "required": ["key", "title", "claim", "validation_method", "blocking", "assumed_by"],
               "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                              "claim": _short, "validation_method": _text, "blocking": {"type": "boolean"}, "assumed_by": _keys}}
_component = {"type": "object", "additionalProperties": False, "required": ["key", "title", "responsibility", "boundary", "implements"],
              "properties": {"key": {"type": "string", "maxLength": 20}, "title": {"type": "string", "minLength": 1, "maxLength": 120},
                             "responsibility": _clause, "boundary": _text, "implements": _keys}}
_export = {"type": "object", "additionalProperties": False, "required": ["delivery", "out_of_scope", "test_scenario"],
           "properties": {"delivery": {"type": "array", "minItems": 1, "maxItems": 6, "items": _text},
                          "out_of_scope": {"type": "array", "minItems": 1, "maxItems": 8, "items": _text},
                          "test_scenario": {"type": "string", "maxLength": 800}, "area": {"type": "string", "maxLength": 40},
                          "size": {"enum": ["S", "M", "L"]}, "phase": {"type": "string", "maxLength": 4}}}
FRAGMENT = {"type": "object", "additionalProperties": False,
            "required": ["title", "goal", "terms", "requirements", "decisions", "assumptions", "tests", "components", "export"],
            "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 120},
                           "goal": {"type": "object", "additionalProperties": False, "required": ["title", "description", "success_measure"],
                                    "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 120},
                                                   "description": _long, "success_measure": _text}},
                           "terms": {"type": "array", "maxItems": 10, "items": _term},
                           "requirements": {"type": "array", "minItems": 1, "maxItems": 10, "items": _requirement},
                           "decisions": {"type": "array", "maxItems": 6, "items": _decision},
                           "assumptions": {"type": "array", "maxItems": 6, "items": _assumption},
                           "tests": {"type": "array", "minItems": 1, "maxItems": 16, "items": _test},
                           "components": {"type": "array", "maxItems": 5, "items": _component}, "export": _export}}
AMEND = {"type": "object", "additionalProperties": False,
         "properties": {**{k: v for k, v in FRAGMENT["properties"].items()},
                        "remove": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 20}}}}
AMEND["properties"]["requirements"] = {"type": "array", "maxItems": 10, "items": _requirement}
AMEND["properties"]["tests"] = {"type": "array", "maxItems": 16, "items": _test}
LISTS = ("terms", "requirements", "decisions", "assumptions", "tests", "components")


def amend(current, change):
    """A fragment with an amendment folded in: items replace those with the same key, new keys are added,
    `remove` drops keys; title, goal and export are replaced whole when given."""
    value = copy.deepcopy(current)
    for key in ("title", "goal", "export"):
        if key in change:
            value[key] = change[key]
    gone = set(change.get("remove") or ())
    for key in LISTS:
        items = [item for item in value.get(key, []) if item["key"] not in gone]
        for item in change.get(key) or []:
            index = next((i for i, old in enumerate(items) if old["key"] == item["key"]), None)
            if index is None:
                items.append(item)
            else:
                items[index] = item
        value[key] = items
    return value


PATCH = {"type": "object", "additionalProperties": False, "required": ["note", "update", "add", "drop"],
         "properties": {"note": {"type": "string", "maxLength": 600},
                        "update": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False,
                                   "required": ["id", "fields"], "properties": {"id": {"type": "string", "maxLength": 20},
                                                                                "fields": {"type": "object"}}}},
                        "add": {"type": "object", "additionalProperties": False,
                                "properties": {"terms": FRAGMENT["properties"]["terms"],
                                               "requirements": {"type": "array", "maxItems": 6, "items": _requirement},
                                               "decisions": FRAGMENT["properties"]["decisions"],
                                               "assumptions": FRAGMENT["properties"]["assumptions"],
                                               "tests": {"type": "array", "maxItems": 10, "items": _test},
                                               "components": FRAGMENT["properties"]["components"]}},
                        "drop": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 20}},
                        "export": {"type": "object", "additionalProperties": False,
                                   "properties": {k: v for k, v in _export["properties"].items()}}}}
EDITABLE = {"Goal": {"title", "description", "success_measure"},
            "Requirement": {"title", "category", "priority", "risk", "verification_mode", "pattern", "conditions", "trigger",
                            "feature", "subject", "response"},
            "TestCase": {"title", "level", "negative", "oracle"}, "Term": {"title", "definition", "unit"},
            "Component": {"title", "responsibility", "boundary"},
            "Decision": {"title", "question", "options", "rationale"}, "Assumption": {"title", "claim", "validation_method"}}
def target():
    """The build factory's rules (aeion-observability), read from the profile shipped with aeion-core."""
    return json.loads((PROFILES / "aeion-observability-target.json").read_text(encoding="utf-8"))


def profile():
    return json.loads((PROFILES / "aeion-observability.json").read_text(encoding="utf-8"))


def catalog(settings):
    """The observability catalog, read-only: its features, the next free ID and the architecture digest."""
    rules, result = target(), {"available": False, "features": [], "architecture_digest": profile()["frontmatter"]["architecture_digest"]}
    manifest = settings.observability / rules["manifest"]
    architecture = settings.observability / rules["architecture"]
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        result["features"] = [{k: f.get(k) for k in ("id", "title", "phase", "area", "sequence")} for f in raw["features"]]
        result["available"] = True
        result["architecture_digest"] = hashlib.sha256(architecture.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return result


def create(store, feature, product, title=None):
    meta, text = store.feature(feature)
    product = product or "aeion-autonomous-forum"
    store.product(product, product)
    name = store.new_name("studio", title or meta["title"])
    session = {"id": name, "kind": "studio", "title": title or meta["title"], "feature": feature, "product": product,
               "state": "new", "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "nodes": [],
               "goal": None, "entry": {}, "messages": [], "answered": [], "checks": None, "export": None, "created": now()}
    return store.save_session(session, "studio")


def _spec_path(store, session):
    return store.product(session["product"]) / "knowledge/spec/spec.json"


def _load(store, session):
    return json.loads(_spec_path(store, session).read_text(encoding="utf-8"))


def _commit_blockers(raw):
    """What `axiom check` refuses a commit for (strict JSON, schema, references, BCIR), keyed so two versions compare."""
    result = axspec.Result()
    try:
        value = axstrict.loads(raw)
    except axstrict.InputError as error:
        return {("G01", error.code, None, ""): error.message}
    for pointer, message in axspec.schema_validator().errors(value)[:50]:
        result.add("G01", "error", "SCHEMA", message, pointer=pointer)
    if not result.diagnostics:
        axspec.validate(value, result=result)
    return {(d["gate"], d["code"], d["subject_id"], d["pointer"] if d["gate"] == "G01" else ""): d["message"]
            for d in result.diagnostics if d["gate"] in ("G01", "G02", "G03") and d["status"] == "error"
            or d["gate"] == "G02" and d["status"] == "fail" and d["code"] != "EMPTY_BASELINE"}


def _save_spec(store, session, spec):
    """Writes the product specification only when it adds nothing `axiom check` would refuse; else nothing is written."""
    path = _spec_path(store, session)
    try:
        raw = (json.dumps(spec, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    except UnicodeEncodeError:
        raise StoreError("refused: the specification holds text that is not valid Unicode; nothing was saved") from None
    added = _commit_blockers(raw)
    for key in (_commit_blockers(path.read_bytes()) if path.is_file() else {}):
        added.pop(key, None)
    if added:
        (gate, code, subject, pointer), message = sorted(added.items(), key=str)[0]
        where = f" on {subject}" if subject else f" at {pointer}" if pointer else ""
        raise StoreError(f"refused: saving would break the product specification ({gate} {code}{where}: {message}); "
                         "nothing was saved")
    store.write(path, raw.decode("utf-8"))


def _next(spec, prefix):
    numbers = [int(i.split("-")[1]) for i in _all_ids(spec) if i.startswith(prefix + "-")]
    return f"{prefix}-{(max(numbers) + 1) if numbers else 1:03d}"


def _all_ids(spec):
    ids = [spec["project"]["id"]]
    for section in ("actors", "sources", "environments", "nodes", "edges", "bindings", "context_assets"):
        ids += [r["id"] for r in spec[section]]
    return ids


def _assistant(spec, model):
    for actor in spec["actors"]:
        if actor["name"].startswith(ASSISTANT):
            return actor["id"]
    actor = {"id": _next(spec, "ACTOR"), "name": f"{ASSISTANT} ({model})", "type": "ai", "binding_status": "asserted"}
    spec["actors"].append(actor)
    return actor["id"]


def _source(spec, kind, locator, digest=None, review="unreviewed"):
    source = {"id": _next(spec, "SRC"), "type": kind, "locator": locator[:2000], "capture_sha256": digest, "review_state": review}
    spec["sources"].append(source)
    return source["id"]


def _edge(spec, a, relation, b, why):
    spec["edges"].append({"id": _next(spec, "EDGE"), "from": a, "relation": relation, "to": b, "origin": "declared",
                          "rationale": why[:1000]})


def _owner(spec):
    return spec["project"]["owner"]


CLAUSES = ("trigger", "feature", "subject", "response")


def clause(text):
    """A sentence part as EARS joins it: no final period, lowercase first letter unless a word like 'API' starts it."""
    if not isinstance(text, str):
        return text
    text = text.strip().rstrip(".").rstrip()
    word = re.match(r"[A-Za-z]+", text)
    if word and (word.group() == "A" or (len(word.group()) > 1 and word.group()[0].isupper() and word.group()[1:].islower())):
        text = text[0].lower() + text[1:]
    return text


def requirement_data(item):
    """A requirement's data with its sentence parts normalized, so the rendered EARS sentence reads correctly."""
    data = {k: item[k] for k in ("category", "priority", "risk", "verification_mode", "pattern", "conditions", "trigger",
                                 "feature", "subject", "response")}
    for key in CLAUSES:
        data[key] = clause(data[key])
    data["conditions"] = [clause(c) for c in data["conditions"]]
    data["subject"] = data["subject"].removeprefix("the ")
    return data


def merge(spec, session, fragment, model, keys=None, source=None):
    """Turn a fragment (local keys) into canonical draft nodes and typed edges; returns the key -> ID map."""
    keys = dict(keys or {})
    author, owner = _assistant(spec, model), _owner(spec)
    source = source or session.get("source_id")
    why = f"declared by the spec studio from '{session['title']}'"

    def add(kind, prefix, item, data):
        node_id = _next(spec, prefix)
        spec["nodes"].append({"id": node_id, "kind": kind, "revision": 1, "status": "draft", "title": item["title"][:256],
                              "owner": owner, "created_by": author, "source_ids": [source], "data": data})
        session["nodes"].append(node_id)
        if "key" in item:
            keys[item["key"]] = node_id
        return node_id

    def ref(key):
        target_id = keys.get(key, key if key in {n["id"] for n in spec["nodes"]} else None)
        return target_id
    if "goal" in fragment:
        session["goal"] = add("Goal", "GOAL", fragment["goal"], {"description": fragment["goal"]["description"],
                                                                  "success_measure": fragment["goal"]["success_measure"]})
    for term in fragment.get("terms", []):
        add("Term", "TERM", term, {"definition": term["definition"], "aliases": [], "unit": term["unit"],
                                   "context": spec["project"]["name"]})
    for r in fragment.get("requirements", []):
        rid = add("Requirement", "REQ", r, requirement_data(r))
        _edge(spec, rid, "satisfies", session["goal"], why)
    for r in fragment.get("requirements", []):
        for t in r["terms"]:
            if ref(t):
                _edge(spec, keys[r["key"]], "uses_term", ref(t), why)
        for d in r["depends_on"]:
            if ref(d) and ref(d) != keys[r["key"]]:
                _edge(spec, keys[r["key"]], "depends_on", ref(d), why)
    for d in fragment.get("decisions", []):
        rationale = d["rationale"] + (f" Assistant's recommendation: {d['recommendation']}." if d["recommendation"] else "")
        did = add("Decision", "DEC", d, {"question": d["question"], "options": d["options"], "answer": None,
                                         "blocking": d["blocking"], "rationale": rationale[:16000]})
        for g in d["governs"] or ["goal"]:
            target_id = session["goal"] if g == "goal" else ref(g)
            if target_id:
                _edge(spec, did, "governs", target_id, why)
    for a in fragment.get("assumptions", []):
        aid = add("Assumption", "ASM", a, {"claim": a["claim"], "validation_method": a["validation_method"],
                                           "state": "unverified", "blocking": a["blocking"]})
        for r in a["assumed_by"]:
            if ref(r) and ref(r).startswith("REQ-"):
                _edge(spec, ref(r), "assumes", aid, why)
    for t in fragment.get("tests", []):
        tid = add("TestCase", "TEST", t, {"level": t["level"], "oracle": t["oracle"], "state": "planned", "runner": None,
                                          "negative": t["negative"], "witness_scenario_ids": []})
        for r in t["verifies"]:
            if ref(r) and ref(r).startswith("REQ-"):
                _edge(spec, tid, "verifies", ref(r), why)
    for c in fragment.get("components", []):
        cid = add("Component", "COMP", c, {"responsibility": c["responsibility"], "boundary": c["boundary"]})
        for r in c["implements"]:
            if ref(r) and ref(r).startswith("REQ-"):
                _edge(spec, cid, "implements", ref(r), why)
    return keys


def _drop(spec, session, ids):
    ids = set(ids) & set(session["nodes"])
    spec["nodes"] = [n for n in spec["nodes"] if n["id"] not in ids]
    spec["edges"] = [e for e in spec["edges"] if e["from"] not in ids and e["to"] not in ids]
    session["nodes"] = [n for n in session["nodes"] if n not in ids]


OWNER_ONLY = {"OPEN_BLOCKING_DECISION", "UNVALIDATED_ASSUMPTION"}


def _entry(fragment, rules):
    export = fragment["export"]
    return {"title": fragment["title"], "delivery": export["delivery"][:4], "out_of_scope": export["out_of_scope"],
            "test_scenario": export["test_scenario"],
            "area": export.get("area") if export.get("area") in rules["areas"] else None,
            "size": export.get("size") or "M",
            "phase": export.get("phase") if export.get("phase") in rules["phases"] else None,
            "write_paths": list(rules["default_write_paths"]), "depends_on": []}


def fixable(checks, keys=None):
    """The failed checks an agent can fix, named by its local keys when it has them; the owner's are left out."""
    names = {v: k for k, v in (keys or {}).items()}
    problems = []
    for d in checks["diagnostics"]:
        if d["status"] in ("pass", "info") or d["code"] in OWNER_ONLY:
            continue
        subject = d["subject_id"]
        where = f" on {names[subject]} ({subject})" if subject in names else f" on {subject}" if subject else ""
        problems.append(f"{d['gate']} {d['code']}{where}: {d['message']}")
    for issue in checks["export"]:
        if issue["field"] in ("write_paths", "depends_on"):
            continue
        hint = " " + size_hint(checks["preview"]) if issue["code"] == "TOO_LARGE" else ""
        problems.append(f"export {issue['field']} {issue['code']}: {issue['message']}{hint}")
    return problems


def _catalog_tool(settings):
    def run(data, current):
        if current.state.get("list_catalog:calls", 0) > 3:
            raise ToolRefused("the catalog was listed three times already: choose dependencies from those results")
        words = [w for w in re.findall(r"[a-z0-9]+", (data.get("query") or "").lower()) if len(w) > 2]
        found = [f for f in catalog(settings)["features"]
                 if not words or any(w in f"{f['title']} {f['area']}".lower() for w in words)]
        return [{k: f[k] for k in ("id", "title", "phase", "area")} for f in found[-80:]] or "no matching feature"
    return run


def draft(store, client, settings, name, emit=lambda e: None):
    """The analyst agent's fragment for the feature document, merged as draft nodes; then the checks run."""
    session = store.session(name, "studio")
    meta, text = store.feature(session["feature"])
    rules = target()
    spec = _load(store, session)
    _drop(spec, session, list(session["nodes"]))

    def trial(fragment):
        # The same merge and checks as below, on scratch copies: what fails goes back to the analyst.
        trial_spec, trial_session = copy.deepcopy(spec), copy.deepcopy(session)
        trial_session["source_id"] = _source(trial_spec, "document", "trial", None, "reviewed")
        keys = merge(trial_spec, trial_session, fragment, settings.model)
        trial_session["entry"] = _entry(fragment, rules)
        return fixable(evaluate(settings, trial_session, trial_spec), keys)
    blocks = [{"tag": "feature_document", "body": f"{meta['title']} ({meta['kind']})\n\n{text[:30000]}"},
              {"tag": "export_values", "body": json.dumps({k: rules[k] for k in ("areas", "sizes", "phases")}), "trust": "owner"}]
    emit({"type": "phase", "phase": "drafting"})
    result = client.run("analyst", f"Specify the attached feature document '{meta['title']}' as AxiomSpec obligations.",
                        blocks=blocks, tools={"list_catalog": _catalog_tool(settings)},
                        submits=[Submit("submit_fragment", FRAGMENT, check=trial, attempts=5),
                                 Submit("amend_fragment", AMEND, target="submit_fragment", combine=amend)],
                        require="submit_fragment", session=name, max_output=65536, timeout=2400, **streaming(emit))
    fragment = result.submissions["submit_fragment"]
    session["source_id"] = _source(spec, "document", f"aeion-core workspace/features/{session['feature']}.md",
                                   session["source_sha256"], "reviewed")
    session["keys"] = merge(spec, session, fragment, settings.model)
    session["entry"] = _entry(fragment, rules)
    session["state"] = "interview"
    _save_spec(store, session, spec)
    store.save_session(session, "studio")
    return check(store, settings, name)


def candidate(spec, session):
    """The spec as if this feature were approved: its draft nodes active, so every gate applies to them."""
    value = copy.deepcopy(spec)
    for node in value["nodes"]:
        if node["id"] in session["nodes"]:
            node["status"] = "active"
    return value


def evaluate(settings, session, spec):
    """Gates on the candidate, scoped to this feature, plus the build factory's export rules. Saves nothing."""
    value = candidate(spec, session)
    result = axspec.Result()
    for pointer, message in axspec.schema_validator().errors(value)[:20]:
        result.add("G01", "error", "SCHEMA", message, pointer=pointer)
    model = None
    # The other gates run only on a schema-valid spec; when G01 fails they did not run, so they are unknown.
    schema_failed = bool(result.diagnostics)
    if not schema_failed:
        model, _ = axspec.validate(value, result=result)
    mine = set(session["nodes"])
    scoped = [d for d in result.diagnostics if d["gate"] == "G01" or d["subject_id"] in mine
              or (d["subject_id"] is None and d["code"] != "EMPTY_BASELINE")]
    gates = {g: max([d["status"] for d in scoped if d["gate"] == g], key=axspec.SEVERITY.get,
                    default="unknown" if schema_failed and g != "G01" else "pass")
             for g in axspec.DESIGN_GATES}
    issues, preview = export_issues(settings, session, model)
    return {"at": now(), "gates": gates, "diagnostics": scoped, "export": issues,
            "design_ready": all(v == "pass" for v in gates.values()), "preview": preview,
            "bytes": len(preview.encode("utf-8")) if preview else 0}


def check(store, settings, name):
    """The checks for this feature as stored, the interview's open questions, and the session state."""
    session = store.session(name, "studio")
    spec = _load(store, session)
    session["checks"] = evaluate(settings, session, spec)
    session["questions"] = questions(candidate(spec, session), session)
    session["state"] = ("ready" if session["checks"]["design_ready"] and not session["checks"]["export"]
                        and not _blocking(session) else "interview")
    if session.get("export") and session["state"] != "exported":
        session["state"] = "exported" if session["export"].get("sha256") == _sha(session["checks"]["preview"]) else session["state"]
    store.save_session(session, "studio")
    return session


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _blocking(session):
    return [q for q in session["questions"] if q["required"]]


def number(settings, store, session):
    """The feature's ID in the build factory: kept once assigned, else the next free after the catalog and exports."""
    if session["entry"].get("number"):
        return session["entry"]["number"]
    taken = [int(f["id"]) for f in catalog(settings)["features"] if str(f.get("id", "")).isdigit()]
    exports = store.product(session["product"]) / "exports"
    taken += [int(p.name[:3]) for p in exports.glob("[0-9][0-9][0-9]-*.md")] if exports.is_dir() else []
    for other in store.sessions("studio"):
        value = store.session(other["id"], "studio").get("entry", {}).get("number")
        if value and other["id"] != session["id"]:
            taken.append(int(value))
    return f"{max(taken + [100]) + 1:03d}"


def export_issues(settings, session, model):
    """(issues, Markdown preview) for the build factory's rules; each issue names the field to fix."""
    rules, entry, issues = target(), session["entry"], []
    known = catalog(settings)
    phases = {f["id"]: f["phase"] for f in known["features"]}
    if entry.get("area") not in rules["areas"]:
        issues.append({"field": "area", "code": "AREA", "message": f"choose an area: {', '.join(rules['areas'])}"})
    if entry.get("phase") not in rules["phases"]:
        issues.append({"field": "phase", "code": "PHASE", "message": f"choose a phase: {', '.join(rules['phases'])}"})
    if entry.get("size") not in rules["sizes"]:
        issues.append({"field": "size", "code": "SIZE", "message": "choose a size: S, M or L"})
    paths = entry.get("write_paths") or []
    # The build factory's own scope rules: literal paths under its product roots, no hidden or parent component.
    if not paths or len(paths) != len(set(paths)) or any(
            not p.startswith(tuple(rules["write_prefixes"])) or not re.fullmatch(r"[A-Za-z0-9_./-]+", p) or "//" in p
            or any(part in ("", ".", "..") or part.startswith(".") for part in p.rstrip("/").split("/")) for p in paths):
        issues.append({"field": "write_paths", "code": "WRITE_PATHS",
                       "message": f"write paths must start with {', '.join(rules['write_prefixes'])}"})
    for dependency in entry.get("depends_on") or []:
        if known["available"] and dependency not in phases:
            issues.append({"field": "depends_on", "code": "UNKNOWN_DEPENDENCY", "message": f"{dependency} is not in the catalog"})
        elif entry.get("phase") in rules["phases"] and phases.get(dependency) in rules["phases"] and \
                rules["phases"].index(phases[dependency]) > rules["phases"].index(entry["phase"]):
            issues.append({"field": "depends_on", "code": "LATER_PHASE",
                           "message": f"{dependency} is in {phases[dependency]}, later than {entry['phase']}"})
    low, high = rules["delivery_steps"]
    steps = entry.get("delivery") or []
    if not low <= len(steps) <= high or any(len(s) > rules["delivery_max_chars"] for s in steps):
        issues.append({"field": "delivery", "code": "DELIVERY",
                       "message": f"{low}-{high} delivery steps of at most {rules['delivery_max_chars']} characters"})
    if not entry.get("out_of_scope"):
        issues.append({"field": "out_of_scope", "code": "OUT_OF_SCOPE", "message": "name at least one exclusion"})
    if model is None or not session.get("goal"):
        return issues + [{"field": "spec", "code": "SPEC", "message": "the specification does not validate yet"}], ""
    text = markdown(settings, session, model, known)
    if len(text.encode("utf-8")) > profile()["max_bytes"]:
        issues.append({"field": "spec", "code": "TOO_LARGE", "message": f"{len(text.encode('utf-8'))} bytes; the build "
                       f"factory reads at most {profile()['max_bytes']}: merge or drop requirements and tests"})
    if re.search(rules["superseded_stack"], text, re.IGNORECASE):
        issues.append({"field": "spec", "code": "SUPERSEDED_STACK", "message": "the text names a stack the build factory "
                       "superseded (FastAPI, pytest, no client framework...): describe behaviour, not that stack"})
    if "- [ ] " not in text:
        issues.append({"field": "spec", "code": "NO_ACCEPTANCE", "message": "no test verifies this feature's requirements"})
    issues += [{"field": "spec", "code": "STRUCTURE", "message": p} for p in axdocs.structure_problems(text)]
    return issues, text


def markdown(settings, session, model, known=None):
    known = known or catalog(settings)
    entry, prof = dict(session["entry"]), profile()
    prof["frontmatter"] = dict(prof["frontmatter"], architecture_digest=known["architecture_digest"])
    entry.update(goal_id=session["goal"], number=entry.get("number") or "000",
                 slug=re.sub(r"[^a-z0-9]+", "-", (entry.get("title") or session["title"]).lower()).strip("-")[:60] or "feature",
                 sequence=entry.get("sequence") or 1, parallel=False)
    text, _ = axdocs.feature_markdown(model, session["goal"], entry, {session["goal"]: entry}, prof)
    return text


def questions(spec, session):
    """One interview item per open matter, required ones first; the owner answers them one at a time."""
    nodes = {n["id"]: n for n in spec["nodes"]}
    found = []
    for node_id in session["nodes"]:
        node = nodes.get(node_id)
        if node and node["kind"] == "Decision" and node["data"]["answer"] is None:
            found.append({"id": f"decision:{node_id}", "kind": "decision", "subject": node_id, "required": node["data"]["blocking"],
                          "title": node["data"]["question"], "detail": node["data"]["rationale"],
                          "options": node["data"]["options"], "free_text": True})
        if node and node["kind"] == "Assumption" and node["data"]["state"] != "validated" and node["data"]["blocking"]:
            found.append({"id": f"assumption:{node_id}", "kind": "assumption", "subject": node_id, "required": True,
                          "title": f"Is this true? {node['data']['claim']}", "detail": node["data"]["validation_method"],
                          "options": ["Validated", "Rejected", "Unverified, not blocking"], "free_text": True})
    for d in (session.get("checks") or {}).get("diagnostics", []):
        if d["code"] == "OPEN_BLOCKING_DECISION" or d["code"] == "UNVALIDATED_ASSUMPTION":
            continue
        found.append({"id": f"gate:{d['gate']}:{d['code']}:{d['subject_id']}", "kind": "gate", "subject": d["subject_id"],
                      "required": True, "title": f"{d['gate']} {d['code']}: {d['message']}",
                      "detail": "A deterministic check failed. Describe the fix, or let the assistant propose one for you to review.",
                      "options": ["Let the assistant fix it"], "free_text": True})
    for issue in (session.get("checks") or {}).get("export", []):
        found.append({"id": f"export:{issue['field']}:{issue['code']}", "kind": "export", "subject": issue["field"],
                      "required": True, "title": issue["message"], "detail": f"Build-factory rule on {issue['field']}.",
                      "options": ["Let the assistant shorten it"] if issue["code"] == "TOO_LARGE" else [], "free_text": True})
    return sorted(found, key=lambda q: (not q["required"], ["decision", "assumption", "gate", "export"].index(q["kind"])))


def answer(store, client, settings, name, question_id, choice=None, text="", emit=lambda e: None):
    """Apply the owner's answer: a decision or assumption directly, a failed check through a reviewed patch."""
    session = store.session(name, "studio")
    question = next((q for q in session.get("questions", []) if q["id"] == question_id), None)
    if question is None:
        raise StoreError("that question is no longer open")
    spec = _load(store, session)
    nodes = {n["id"]: n for n in spec["nodes"]}
    stamp = f"{date.today().isoformat()}, studio {name}"
    if question["kind"] == "decision":
        value = (text or "").strip() or choice
        if not value:
            raise StoreError("choose an option or write the answer")
        node = nodes[question["subject"]]
        source = _source(spec, "user_input", f"owner answer to {node['id']} ({stamp}): {value}", review="reviewed")
        node["data"]["answer"], node["revision"] = value[:16000], node["revision"] + 1
        node["source_ids"] = sorted(set(node["source_ids"]) | {source})
    elif question["kind"] == "assumption":
        node = nodes[question["subject"]]
        state = {"Validated": "validated", "Rejected": "rejected"}.get(choice)
        if choice == "Unverified, not blocking":
            node["data"]["blocking"] = False
        elif state:
            node["data"]["state"] = state
        else:
            raise StoreError("choose one of the options")
        source = _source(spec, "user_input", f"owner on {node['id']} ({stamp}): {choice}. {text}".strip(), review="reviewed")
        node["revision"] += 1
        node["source_ids"] = sorted(set(node["source_ids"]) | {source})
    elif question["kind"] == "export" and question["subject"] in ("area", "phase", "size", "write_paths", "depends_on",
                                                                     "delivery", "out_of_scope") and (choice or text):
        _set_entry(session, question["subject"], choice if choice is not None else text)
    else:
        session["messages"].append({"role": "user", "content": f"[{question['title']}] {text or choice}", "at": now()})
        _save_spec(store, session, spec)
        store.save_session(session, "studio")
        instruction = f"Fix this check: {question['title']}\nOwner's guidance: {text or 'none, propose the smallest correct fix'}"
        if question["id"] == "export:spec:TOO_LARGE":
            instruction += ("\nShorten the export without changing what it means: reword long responses, oracles, "
                            "definitions and decision questions through update; merge tests that check the same behaviour; "
                            "drop only should or could items. " + size_hint((session.get("checks") or {}).get("preview", "")))
        kind, _, rest = question["id"].partition(":")
        aimed = (rest.split(":")[1], rest.split(":")[2] if rest.count(":") >= 2 else None) if kind == "gate" else \
            (rest.split(":")[1], None) if kind == "export" else None
        return change(store, client, settings, name, instruction, emit, target=aimed)
    session["answered"].append({"question": question_id, "choice": choice, "text": text, "at": now()})
    _save_spec(store, session, spec)
    store.save_session(session, "studio")
    return check(store, settings, name)


def size_hint(preview):
    """Bytes per section of the export preview, so a shortening patch knows where the bulk is."""
    parts = re.split(r"(?m)^(## .*)$", preview or "")
    sizes = [f"{parts[i][3:]} {len((parts[i] + parts[i + 1]).encode('utf-8'))}" for i in range(1, len(parts) - 1, 2)]
    return "Bytes per section: " + ", ".join(sizes) + "." if sizes else ""


def _set_entry(session, field, value):
    if field in ("write_paths", "depends_on", "delivery", "out_of_scope"):
        items = value if isinstance(value, list) else [v.strip() for v in re.split(r"[\n,]" if field != "delivery" and
                                                                                     field != "out_of_scope" else r"\n", value) if v.strip()]
        session["entry"][field] = items[:12]
    else:
        session["entry"][field] = str(value).strip()


def set_entry(store, settings, name, fields):
    session = store.session(name, "studio")
    for field, value in fields.items():
        if field in ("title", "area", "phase", "size", "write_paths", "depends_on", "delivery", "out_of_scope", "test_scenario"):
            _set_entry(session, field, value)
    store.save_session(session, "studio")
    return check(store, settings, name)


def closure(spec, session):
    """This feature's canonical records, compact, for the model's context."""
    mine = set(session["nodes"])
    nodes = [{k: n[k] for k in ("id", "kind", "status", "title", "data")} for n in spec["nodes"] if n["id"] in mine]
    edges = [f"{e['from']} {e['relation']} {e['to']}" for e in spec["edges"] if e["from"] in mine or e["to"] in mine]
    return json.dumps({"nodes": nodes, "edges": edges, "export": session["entry"]}, ensure_ascii=False)[:60000]


def _record_tool(spec):
    nodes = {n["id"]: n for n in spec["nodes"]}

    def run(data, _run):
        node = nodes.get(data["id"])
        if node is None:
            return f"no record {data['id']} in this specification"
        links = [f"{e['from']} {e['relation']} {e['to']}" for e in spec["edges"] if node["id"] in (e["from"], e["to"])]
        return {k: node[k] for k in ("id", "kind", "status", "revision", "title", "data")} | {"links": links[:60]}
    return run


def _checks_tool(settings, session, spec):
    def run(_data, _run):
        checks = evaluate(settings, session, spec)
        return {"gates": checks["gates"], "failing": fixable(checks), "bytes": checks["bytes"],
                "owner_questions": [q["title"] for q in questions(candidate(spec, session), session) if q["required"]][:12]}
    return run


def _context(session, spec):
    checks = session.get("checks") or {}
    blocks = [{"tag": "feature_records", "body": closure(spec, session)},
              {"tag": "open_checks", "body": json.dumps({"failing": fixable(checks) if checks else [],
                                                         "owner_questions": [q["title"] for q in session.get("questions", [])
                                                                             if q["required"]][:12]}, ensure_ascii=False)}]
    return blocks


def discuss(store, client, settings, name, text, emit=lambda e: None):
    """Talk the specification through with the discussant agent; changes happen only through change()."""
    session = store.session(name, "studio")
    spec = _load(store, session)
    blocks = _context(session, spec)
    if session["messages"]:
        lines = [f"{'Owner' if m['role'] == 'user' else 'Analyst'}: {m['content']}" for m in session["messages"][-20:]]
        blocks.append({"tag": "conversation", "body": "\n\n".join(lines)})
    session["messages"].append({"role": "user", "content": text.strip(), "at": now()})
    result = client.run("discussant", text.strip(), blocks=blocks,
                        tools={"read_record": _record_tool(spec), "run_checks": _checks_tool(settings, session, spec)},
                        session=name, **streaming(emit))
    session["messages"].append({"role": "assistant", "content": result.text, "at": now()})
    store.save_session(session, "studio")
    emit({"type": "message", "content": result.text})
    return session


def change(store, client, settings, name, instruction="", emit=lambda e: None, target=None):
    """A patch the patcher agent proposes from the conversation or a failed check, dry-run checked, then applied."""
    session = store.session(name, "studio")
    spec = _load(store, session)
    before = fixable(evaluate(settings, session, spec))

    def trial(patch):
        # Apply to scratch copies and report what still fails, so the agent repairs its own patch.
        trial_spec, trial_session = copy.deepcopy(spec), copy.deepcopy(session)
        applied = apply_patch(trial_spec, trial_session, patch, settings.model)
        invalid = [f"{item}: the value does not fit the AxiomSpec schema for this field" for item in applied["invalid"]]
        if not (applied["updated"] + applied["added"] + applied["dropped"] + applied["export"]):
            return invalid or [f"the patch changes nothing the studio can edit ({', '.join(applied['ignored'][:6]) or 'empty'})"]
        after = fixable(evaluate(settings, trial_session, trial_spec), trial_session.get("keys"))
        # New failures, plus the targeted check when it still fails (its code and subject in the message).
        aimed = [p for p in after if target and target[0] in p and (not target[1] or target[1] in p)]
        return invalid + [p for p in after if p not in before] + [p for p in aimed if p in before]
    blocks = _context(session, spec)
    if session["messages"]:
        lines = [f"{'Owner' if m['role'] == 'user' else 'Analyst'}: {m['content']}" for m in session["messages"][-12:]]
        blocks.append({"tag": "conversation", "body": "\n\n".join(lines)})
    emit({"type": "phase", "phase": "patching"})
    result = client.run("patcher", instruction or "Apply what the owner asked for in the attached conversation.",
                        blocks=blocks, tools={"read_record": _record_tool(spec)},
                        submits=[Submit("submit_patch", PATCH, check=trial)], require="submit_patch",
                        session=name, **streaming(emit))
    value = result.submissions["submit_patch"]
    # A patch that still fails its checks when its attempts run out is not applied: the specification stays as it was.
    still = result.state.get("submit_patch:problems") or []
    if still:
        content = (f"No change was applied: the proposal still failed {len(still)} check(s) when its attempts ran out, "
                   f"so the specification is unchanged. First: {still[0]} Its note was: {value['note']}")
        session["messages"].append({"role": "assistant", "content": content, "at": now()})
        store.save_session(session, "studio")
        emit({"type": "message", "content": content})
        return check(store, settings, name)
    applied = apply_patch(spec, session, value, settings.model)
    counts = f"{applied['updated']} updated, {applied['added']} added, {applied['dropped']} dropped"
    if applied["updated"] + applied["added"] + applied["dropped"] + applied["export"]:
        content = f"Change applied ({counts}): {value['note']}"
    else:
        content = (f"No change was applied: the proposal touched nothing the studio can edit"
                   f"{' (' + ', '.join(applied['ignored'][:6]) + ')' if applied['ignored'] else ''}. Its note was: {value['note']}")
    session["messages"].append({"role": "assistant", "content": content, "at": now()})
    _save_spec(store, session, spec)
    store.save_session(session, "studio")
    emit({"type": "message", "content": content})
    return check(store, settings, name)


# Link fields a patch may set on an existing record: (relation, direction, target ID prefix or None for any).
LINKS = {("TestCase", "verifies"): ("verifies", "out", "REQ-"), ("Component", "implements"): ("implements", "out", "REQ-"),
         ("Requirement", "terms"): ("uses_term", "out", "TERM-"), ("Requirement", "depends_on"): ("depends_on", "out", "REQ-"),
         ("Decision", "governs"): ("governs", "out", None), ("Assumption", "assumed_by"): ("assumes", "in", "REQ-")}


def apply_patch(spec, session, patch, model):
    """Add new records, then update editable fields and links of this feature's records, then drop listed ones.
    Returns what actually changed, so the page never reports a change that did not happen."""
    before = set(session["nodes"])
    keys = merge(spec, session, patch["add"], model, keys=session.get("keys"))
    session["keys"] = keys
    nodes = {n["id"]: n for n in spec["nodes"]}
    updated, ignored, invalid = 0, [], []
    why = f"changed in the spec studio for '{session['title']}'"

    def resolve(value):
        value = str(value)
        return session["goal"] if value == "goal" else keys.get(value, value if value in nodes else None)
    for item in patch["update"]:
        node = nodes.get(item["id"])
        if node is None or node["id"] not in session["nodes"]:
            ignored.append(item["id"])
            continue
        changed = False
        for field, value in item["fields"].items():
            link = LINKS.get((node["kind"], field))
            if link and isinstance(value, list):
                relation, direction, prefix = link
                targets = sorted({t for t in map(resolve, value) if t and t != node["id"] and (prefix is None or t.startswith(prefix))})
                end = "from" if direction == "out" else "to"
                spec["edges"] = [e for e in spec["edges"] if not (e[end] == node["id"] and e["relation"] == relation)]
                for t in targets:
                    if direction == "out":
                        _edge(spec, node["id"], relation, t, why)
                    else:
                        _edge(spec, t, relation, node["id"], why)
                changed = True
            elif field in EDITABLE.get(node["kind"], set()):
                if node["kind"] == "Requirement" and field in CLAUSES:
                    value = clause(value)
                elif node["kind"] == "Requirement" and field == "conditions" and isinstance(value, list):
                    value = [clause(v) for v in value]
                elif field == "title" and isinstance(value, str):
                    value = value[:256]
                # A value the AxiomSpec schema refuses is never stored; the patcher is told which field.
                if _field_validator(node["kind"], field).errors(value):
                    invalid.append(f"{node['id']}.{field}")
                    continue
                if field == "title":
                    node["title"] = value
                else:
                    node["data"][field] = value
                changed = True
            else:
                ignored.append(f"{node['id']}.{field}")
        if changed:
            node["revision"] += 1
            updated += 1
    dropped = [i for i in patch["drop"] if i in session["nodes"]]
    _drop(spec, session, dropped)
    for field, value in (patch.get("export") or {}).items():
        _set_entry(session, field, value)
    added = len(set(session["nodes"]) - before)
    return {"updated": updated, "added": added, "dropped": len(dropped), "export": len(patch.get("export") or {}),
            "ignored": ignored, "invalid": invalid}


@functools.lru_cache(maxsize=None)
def _field_validator(kind, field):
    """The AxiomSpec schema of one editable field of a record kind, so a patched value is checked before it is stored."""
    whole = axspec.schema_validator().root
    branch = next(b for b in whole["properties"]["nodes"]["items"]["oneOf"] if b["properties"]["kind"].get("const") == kind)
    schema = branch["properties"]["title"] if field == "title" else branch["properties"]["data"]["properties"][field]
    return Validator({**schema, "$defs": whole.get("$defs", {})})


def approve(store, client, settings, name, emit=lambda e: None):
    """The owner's approval: nodes become active, the export is written, the product's docs regenerate."""
    session = check(store, settings, name)
    if session["state"] not in ("ready", "exported"):
        raise StoreError("the feature is not ready: answer the open questions first")
    # The ID, the dependencies and the architecture digest come from the build factory's catalog: without it, no export.
    if not catalog(settings)["available"]:
        raise StoreError(f"approval refused: the aeion-observability catalog under {settings.observability} cannot be read, "
                         "so the feature's ID, dependencies and architecture digest cannot be checked; set AEION_OBSERVABILITY")
    spec = _load(store, session)
    approval = _source(spec, "user_input", f"approved by the owner in aeion-core studio {name} on {date.today().isoformat()}",
                       review="reviewed")
    for node in spec["nodes"]:
        if node["id"] in session["nodes"]:
            node["status"] = "active"
            node["source_ids"] = sorted(set(node["source_ids"]) | {approval})
    session["entry"]["number"] = number(settings, store, session)
    known = catalog(settings)
    sequences = [int(f["sequence"]) for f in known["features"] if isinstance(f.get("sequence"), int)]
    session["entry"].setdefault("sequence", max(sequences + [100]) + 1)
    _save_spec(store, session, spec)
    model = axspec.Model(spec)
    text = markdown(settings, session, model, known)
    problems = axdocs.structure_problems(text)
    if problems or len(text.encode("utf-8")) > profile()["max_bytes"]:
        raise StoreError(f"export refused: {problems[0] if problems else 'over the byte limit'}")
    slug = re.sub(r"[^a-z0-9]+", "-", session["entry"]["title"].lower()).strip("-")[:60] or "feature"
    filename = f"{session['entry']['number']}-{slug}.md"
    folder = store.product(session["product"])
    store.write(folder / "exports" / filename, text)
    row = {"id": session["entry"]["number"], "sequence": session["entry"]["sequence"], "title": session["entry"]["title"],
           "area": session["entry"]["area"], "size": session["entry"]["size"], "parallel": False,
           "phase": session["entry"]["phase"], "tier": 3, "write_paths": session["entry"]["write_paths"],
           "depends_on": session["entry"]["depends_on"], "file": filename,
           "architecture": profile()["frontmatter"]["architecture"], "architecture_digest": known["architecture_digest"]}
    store.write(folder / "exports" / f"{filename[:-3]}.manifest-row.json", row)
    session["export"] = {"file": filename, "bytes": len(text.encode("utf-8")), "sha256": _sha(text), "row": row, "at": now()}
    session["state"] = "exported"
    store.save_session(session, "studio")
    emit({"type": "phase", "phase": "documenting"})
    propose_views(store, client, settings, name)
    regenerate(store, session)
    return store.session(name, "studio")


VIEW_PLAN = {"type": "object", "required": ["views"], "additionalProperties": False, "properties": {"views": {
    "type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False,
        "required": ["family", "title", "question", "source"],
        "properties": {"family": {"enum": ["system", "process", "sequence", "usecase"]},
                       "title": {"type": "string", "minLength": 1, "maxLength": 120},
                       "question": {"type": "string", "minLength": 1, "maxLength": 200}, "source": {"type": "object"}}}}}}
def propose_views(store, client, settings, name):
    """Diagrams the illustrator agent proposes for the approved feature; each is rendered here or refused."""
    session = store.session(name, "studio")
    folder = store.product(session["product"])
    spec = _load(store, session)

    def renders(plan):
        problems = []
        for index, view in enumerate(plan["views"], 1):
            try:
                axviews.render(dict(view["source"], format="aeion-view/0.1"), view["title"], view["question"])
            except axviews.ViewError as error:
                problems.append(f"view {index} ({view['title']}): {error}")
        return problems
    try:
        result = client.run("illustrator", "Propose the diagrams of the attached feature.",
                            blocks=[{"tag": "feature_records", "body": closure(spec, session)}],
                            submits=[Submit("submit_views", VIEW_PLAN, check=renders, attempts=3)], require="submit_views",
                            session=name)
        plan = result.submissions["submit_views"]
    except Exception as error:  # a diagram is documentation; its failure never blocks the export
        session["views_error"] = str(error)[:300]
        store.save_session(session, "studio")
        return []
    catalog_path = folder / "docs/view-catalog.json"
    view_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    added = []
    for index, view in enumerate(plan["views"], 1):
        source = dict(view["source"], format="aeion-view/0.1")
        try:
            axviews.render(source, view["title"], view["question"])
        except axviews.ViewError as error:
            session.setdefault("views_dropped", []).append(f"{view['title']}: {error}")
            continue
        stem = f"{session['entry']['number']}-{view['family']}-{index}"
        view_id = f"VIEW-{stem.upper()}"
        store.write(folder / f"docs/views/{stem}.json", source)
        view_catalog["views"] = [v for v in view_catalog["views"] if v["id"] != view_id]
        view_catalog["views"].append({"id": view_id, "kind": view["family"], "title": view["title"][:200],
                                      "question": view["question"][:200], "audience": "the team building the feature",
                                      "claim": "proposed", "canonical_ids": [session["goal"]], "scope": session["title"][:900],
                                      "source_path": f"docs/views/{stem}.json", "review": "drafted by the assistant; not reviewed"})
        added.append(view_id)
    store.write(catalog_path, view_catalog)
    session["views"] = added
    store.save_session(session, "studio")
    return added


def regenerate(store, session):
    """The product cockpit, pages and diagrams, as the template's toolkit builds them."""
    folder = store.product(session["product"])
    result = axspec.Result()
    spec = axspec.load_spec(folder / "knowledge/spec/spec.json", result)
    if spec is None:
        return [d["message"] for d in result.diagnostics]
    model, _ = axspec.validate(spec, result=result)
    return axdocs.generate(folder, spec, model, result)
