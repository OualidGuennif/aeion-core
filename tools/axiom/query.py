# Spec: knowledge/components/axiom-toolkit.md
"""Bounded queries over a graph snapshot (AX-K-003..007, AX-K-010) and the context packet of a change.

A name matches exactly or not at all. Every response states what it omitted and the analysis limits;
required context is never dropped for budget: the packet splits instead."""
import json
from collections import deque

from common import canonical_digest
from spec import render_requirement

MAX_ITEMS, MAX_BYTES = 100, 32768
CODE_ROLES = ("code", "test")


class Index:
    """In-memory adjacency over one snapshot; built per command, never persisted."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.nodes = {n["id"]: n for n in snapshot["nodes"]}
        self.out, self.into = {}, {}
        for edge in snapshot["edges"]:
            self.out.setdefault(edge["from"], []).append(edge)
            self.into.setdefault(edge["to"], []).append(edge)
        self.symbols = snapshot["symbols"]
        self.limits = snapshot["manifest"]["analysis_limits"]

    def targets(self, node_id, relation):
        return [e["to"] for e in self.out.get(node_id, []) if e["relation"] == relation]

    def sources(self, node_id, relation):
        return [e["from"] for e in self.into.get(node_id, []) if e["relation"] == relation]

    def label(self, node_id):
        node = self.nodes.get(node_id, {})
        return node.get("path") or node.get("label") or node_id

    def resolve(self, name):
        """Exact matches for a name: a node ID, a path, a canonical title or a symbol (with or without ())."""
        if name in self.nodes:
            return [name]
        if "file:" + name in self.nodes:
            return ["file:" + name]
        bare = name[:-2] if name.endswith("()") else name
        found = {n["id"] for n in self.nodes.values() if n.get("label") == name or n.get("title") == name}
        found |= {"file:" + rel for rel, items in self.symbols.items() for item in items
                  if item["name"] == bare or item["name"].split(".")[-1] == bare and "." not in bare}
        return sorted(found)


def run(snapshot, kind, args, depth=1, top=15):
    """(response, exit code): 0 an answer, 3 ambiguous, 4 nothing matches, 2 usage."""
    index = Index(snapshot)
    query = {"kind": kind, "args": args, "depth": depth, "top": top}
    handler = HANDLERS[kind]
    needs = {"node": 1, "requirement": 1, "find": 1, "deps": 1, "rdeps": 1, "tests": 1, "spec": 1, "files": 1,
             "path": 2, "search": 1, "impact": 1}.get(kind, 0)
    if len(args) < needs:
        return _response(index, query, [], error=f"{kind} needs {needs} argument(s)"), 2
    if kind in ("node", "requirement", "deps", "rdeps", "tests", "spec", "files"):
        matches = index.resolve(args[0])
        if len(matches) != 1:
            items = [{"id": m, "label": index.label(m), "type": index.nodes[m]["type"]} for m in matches]
            reason = "ambiguous name, candidates listed" if matches else f"nothing matches {args[0]!r}"
            return _response(index, query, items, error=reason), 3 if matches else 4
        args = [matches[0], *args[1:]]
    items, extra = handler(index, args, depth=depth, top=top)
    return _response(index, query, items, **extra), 0


def _response(index, query, items, error=None, notes=(), limits=None):
    """AX-K-006: bounded items with honest counts, omissions and limits."""
    kept, size = [], 0
    for item in items:
        encoded = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if len(kept) >= MAX_ITEMS or size + encoded > MAX_BYTES - 2048:
            break
        kept.append(item)
        size += encoded
    omitted = len(items) - len(kept)
    return {"snapshot_id": index.snapshot["manifest"]["snapshot_id"], "query": query,
            "query_digest": canonical_digest(query), "items": kept, "returned_count": len(kept),
            "total_visible_count": len(items), "complete": omitted == 0 and error is None, "next_cursor": None,
            "omissions": [f"{omitted} item(s) over the {MAX_ITEMS}-item / {MAX_BYTES}-byte bound"] if omitted else [],
            "error": error, "notes": list(notes),
            "analysis_limits": index.limits if limits is None else limits}


def _node(index, args, **_):
    node_id = args[0]
    node = index.nodes[node_id]
    item = {"id": node_id, "type": node["type"], "label": index.label(node_id)}
    record = node.get("record")
    if record:
        item["record"] = record
        if node["type"] == "Requirement":
            item["sentence"] = render_requirement(record["data"])
    if node["type"] == "Binding":
        item["resolution"] = node.get("resolution")
    relations = [{"direction": "out", "relation": e["relation"], "other": e["to"], "other_label": index.label(e["to"]),
                  "origin": e["origin"], "line": e.get("line")} for e in index.out.get(node_id, [])]
    relations += [{"direction": "in", "relation": e["relation"], "other": e["from"],
                   "other_label": index.label(e["from"]), "origin": e["origin"], "line": e.get("line")}
                  for e in index.into.get(node_id, [])]
    return [item, *sorted(relations, key=lambda r: (r["direction"], r["relation"], r["other"]))], {}


def _requirement(index, args, **_):
    node_id = args[0]
    node = index.nodes[node_id]
    if node["type"] != "Requirement":
        return [{"id": node_id, "type": node["type"], "label": index.label(node_id)}], {
            "notes": [f"{node_id} is a {node['type']}; showing its node only"]}
    record = node["record"]
    items = [{"id": node_id, "type": "Requirement", "label": record["title"], "status": record["status"],
              "sentence": render_requirement(record["data"]), "priority": record["data"]["priority"],
              "risk": record["data"]["risk"], "verification_mode": record["data"]["verification_mode"]}]
    neighbours = [(e["to"], e["relation"]) for e in index.out.get(node_id, [])]
    neighbours += [(e["from"], e["relation"]) for e in index.into.get(node_id, [])]
    for other, relation in sorted(set(neighbours)):
        items.append(_brief(index, other, relation))
    # Where it lives: its own bindings, then those of the components and tests linked to it.
    owners = [node_id] + sorted(o for o, relation in set(neighbours) if relation in ("implements", "verifies"))
    for owner in owners:
        for binding in sorted(index.targets(owner, "has_binding")):
            items.append(_brief(index, binding, "has_binding" if owner == node_id else f"binding of {owner}"))
    return items, {}


def _brief(index, node_id, relation):
    node = index.nodes.get(node_id, {"type": "Unknown"})
    item = {"relation": relation, "id": node_id, "type": node["type"], "label": index.label(node_id)}
    data = node.get("record", {}).get("data", {})
    if node["type"] == "TestCase":
        item.update(level=data["level"], negative=data["negative"], state=data["state"], oracle=data["oracle"])
    elif node["type"] == "Constraint":
        item.update(role=data["predicate_role"], strength=data["classification"]["strength"], scope=data["scope"])
    elif node["type"] == "Decision":
        item.update(question=data["question"], answer=data["answer"], blocking=data["blocking"])
    elif node["type"] == "Binding":
        record = node["record"]
        item.update(path=record["path"], symbol=record["symbol"], resolution=node.get("resolution"))
    elif node["type"] == "Requirement":
        item["sentence"] = render_requirement(data)
    return item


def _find(index, args, **_):
    name = args[0]
    items = []
    for match in index.resolve(name):
        node = index.nodes[match]
        item = {"id": match, "type": node["type"], "label": index.label(match)}
        if node["type"] == "File":
            bare = name[:-2] if name.endswith("()") else name
            lines = [s for s in index.symbols.get(node["path"], []) if s["name"] == bare
                     or s["name"].split(".")[-1] == bare]
            item["definitions"] = [{"name": s["name"], "line": s["line"], "kind": s["kind"]} for s in lines]
        items.append(item)
    return items, {}


def _search(index, args, **_):
    needle = " ".join(args).lower()
    items = [{"id": n["id"], "type": n["type"], "label": index.label(n["id"])} for n in index.nodes.values()
             if needle in index.label(n["id"]).lower() or needle in n["id"].lower()]
    return sorted(items, key=lambda i: (i["type"], i["id"])), {"notes": ["substring search, case-insensitive"]}


def _deps(index, args, **_):
    node_id = args[0]
    return [{"id": e["to"], "path": index.label(e["to"]), "relation": e["relation"], "line": e.get("line"),
             "origin": e["origin"]} for e in sorted(index.out.get(node_id, []), key=lambda e: (e["to"], e.get("line", 0)))
            if e["relation"] in ("imports", "names_file")], {}


def _rdeps(index, args, depth=1, **_):
    seen, frontier, items = {args[0]}, [args[0]], []
    for hop in range(1, max(depth, 1) + 1):
        following = []
        for current in frontier:
            for edge in index.into.get(current, []):
                if edge["relation"] == "imports" and edge["from"] not in seen:
                    seen.add(edge["from"])
                    following.append(edge["from"])
                    items.append({"id": edge["from"], "path": index.label(edge["from"]), "hop": hop,
                                  "via": index.label(current), "line": edge.get("line")})
        frontier = following
    return sorted(items, key=lambda i: (i["hop"], i["path"])), {}


def _path(index, args, **_):
    starts, ends = index.resolve(args[0]), index.resolve(args[1])
    if len(starts) != 1 or len(ends) != 1:
        return [], {"notes": [f"{args[0]!r} -> {len(starts)} matches, {args[1]!r} -> {len(ends)} matches; "
                              "both must match exactly once"]}
    start, end = starts[0], ends[0]
    for relations in (("imports",), ("imports", "names_file"), None):
        hops = _bfs(index, start, end, relations)
        if hops is not None:
            break
    if hops is None:
        return [], {"notes": [f"no edge path from {index.label(start)} to {index.label(end)}; a call through an object "
                              "or configuration is not an edge here: read the code"]}
    return [{"hop": i + 1, "from": index.label(e["from"]), "relation": e["relation"], "to": index.label(e["to"]),
             "line": e.get("line"), "origin": e["origin"]} for i, e in enumerate(hops)], {}


def _bfs(index, start, end, relations):
    previous = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == end:
            hops = []
            while previous[current] is not None:
                hops.append(previous[current])
                current = previous[current]["from"]
            return list(reversed(hops))
        for edge in sorted(index.out.get(current, []), key=lambda e: (e["relation"], e["to"])):
            if (relations is None or edge["relation"] in relations) and edge["to"] not in previous:
                previous[edge["to"]] = edge
                queue.append(edge["to"])
    return None


def _reaching_tests(index, target):
    """Tests that import target directly, reach it through imports, or name its path."""
    found = {}
    reached = {target: [target]}
    queue = deque([target])
    while queue:
        current = queue.popleft()
        for edge in index.into.get(current, []):
            if edge["relation"] == "imports" and edge["from"] not in reached:
                reached[edge["from"]] = [edge["from"], *reached[current]]
                queue.append(edge["from"])
    for node_id, chain in reached.items():
        if node_id != target and index.nodes[node_id].get("role") == "test":
            found[node_id] = ("imports" if len(chain) == 2 else "reaches", [index.label(c) for c in chain])
    for edge in index.into.get(target, []):
        if edge["relation"] == "names_file" and edge["from"] not in found:
            found[edge["from"]] = ("names", [index.label(edge["from"]), index.label(target)])
    return found


def _tests(index, args, **_):
    found = _reaching_tests(index, args[0])
    order = {"imports": 0, "names": 1, "reaches": 2}
    return sorted(({"test": index.label(t), "how": how, "chain": chain} for t, (how, chain) in found.items()),
                  key=lambda i: (order[i["how"]], i["test"])), {}


def _untested(index, args, **_):
    reached = set()
    for node in index.nodes.values():
        if node.get("role") == "test":
            stack, seen = [node["id"]], {node["id"]}
            while stack:
                current = stack.pop()
                for edge in index.out.get(current, []):
                    if edge["relation"] in ("imports", "names_file") and edge["to"] not in seen:
                        seen.add(edge["to"])
                        stack.append(edge["to"])
            reached |= seen
    items = [{"path": n["path"], "language": n["language"] or "script"} for n in index.nodes.values()
             if n.get("role") == "code" and n["id"] not in reached]
    return sorted(items, key=lambda i: i["path"]), {"notes": ["reach = imports or a literal path in a test"]}


def _spec(index, args, **_):
    node_id = args[0]
    items = []
    for doc in sorted(set(index.sources(node_id, "specifies"))):
        items.append({"doc": index.label(doc), "how": "frontmatter sources"})
    headers = sorted(set(index.targets(node_id, "specified_by")))
    for doc in headers:
        lists = node_id in index.targets(doc, "specifies")
        items.append({"doc": index.label(doc), "how": "Spec: header" + ("" if lists else
                      " (GAP: that doc's sources omit this file)")})
    for binding in sorted(set(index.sources(node_id, "resolves_to"))):
        record = index.nodes[binding]["record"]
        owner = record["node_id"]
        items.append({"canonical": owner, "label": index.label(owner), "how": f"binding {binding} "
                      f"({record['kind']}, symbol {record['symbol']})"})
    notes = []
    if index.nodes[node_id].get("role") in CODE_ROLES and not headers:
        notes.append("GAP: no `Spec:` header line in this file")
    if not items:
        notes.append("no document or canonical node covers this file")
    return items, {"notes": notes}


def _files(index, args, **_):
    node_id = args[0]
    items = [{"path": index.label(t), "how": "frontmatter sources"} for t in sorted(set(index.targets(node_id, "specifies")))]
    items += [{"path": index.label(f), "how": "Spec: header"} for f in sorted(set(index.sources(node_id, "specified_by")))]
    items += [{"id": n, "label": index.label(n), "how": "mentioned"} for n in sorted(set(index.targets(node_id, "mentions")))]
    return items, {}


def _hubs(index, args, top=15, **_):
    counts = {}
    for edge in index.snapshot["edges"]:
        target = index.nodes.get(edge["to"], {})
        source = index.nodes.get(edge["from"], {})
        if edge["relation"] == "imports" and target.get("role") == "code" and source.get("role") == "code":
            counts[edge["to"]] = counts.get(edge["to"], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return [{"path": index.label(n), "imported_by": c} for n, c in ranked], {"notes": ["tests and documents excluded"]}


def _status(index, args, **_):
    manifest = index.snapshot["manifest"]
    types = {}
    for node in index.nodes.values():
        types[node["type"]] = types.get(node["type"], 0) + 1
    return [{"snapshot_id": manifest["snapshot_id"], "rebuilt": index.snapshot.get("rebuilt", False),
             "spec": {k: v for k, v in manifest["spec"].items() if k != "dangling_mentions"},
             "counts": manifest["counts"], "types": dict(sorted(types.items())),
             "extractors": manifest["extractors"]}], {}


def _gaps(index, args, **_):
    """AX-K-005: hard gaps with their gate; never a compensating score."""
    items = []
    for node in sorted(index.nodes.values(), key=lambda n: n["id"]):
        record = node.get("record", {})
        data = record.get("data", {})
        if node["type"] == "Decision" and record.get("status") == "active" and data.get("blocking") and data.get("answer") is None:
            items.append({"gate": "G04", "subject": node["id"], "gap": "open blocking decision", "detail": data["question"]})
        if node["type"] == "Assumption" and record.get("status") == "active" and data.get("blocking") and data.get("state") != "validated":
            items.append({"gate": "G04", "subject": node["id"], "gap": f"blocking assumption {data['state']}",
                          "detail": data["claim"]})
        if node["type"] == "Requirement" and record.get("status") == "active":
            tests = index.sources(node["id"], "verifies")
            if data.get("priority") == "must" and not tests:
                items.append({"gate": "G07", "subject": node["id"], "gap": "no test verifies this must requirement",
                              "detail": record["title"]})
            if not index.sources(node["id"], "illustrates"):
                items.append({"gate": "G06", "subject": node["id"], "gap": "no scenario illustrates it",
                              "detail": record["title"]})
            if not index.sources(node["id"], "implements"):
                items.append({"gate": "G09", "subject": node["id"], "gap": "no component implements it",
                              "detail": record["title"]})
        if node["type"] == "Binding":
            resolution = node.get("resolution", {})
            if resolution.get("status") != "resolved":
                expected = record.get("expected_resolution")
                items.append({"gate": "G09", "subject": node["id"], "gap": f"binding {resolution.get('status')} "
                              f"({expected})", "detail": resolution.get("detail", "")})
    for rel, ids in sorted(index.snapshot["manifest"]["spec"].get("dangling_mentions", {}).items()):
        items.append({"gate": "G02", "subject": rel, "gap": "mentions unknown IDs", "detail": ", ".join(ids)})
    for node in sorted(index.nodes.values(), key=lambda n: n["id"]):
        if node.get("role") == "code" and not index.targets(node["id"], "specified_by") \
                and not index.sources(node["id"], "specifies"):
            items.append({"gate": "docs", "subject": node["path"], "gap": "no doc covers this file", "detail": ""})
    return items, {}


def _impact(index, args, **_):
    """AX-K-004: known, declared and unmapped impacts of changed IDs or files, reported separately."""
    ids = [a for a in args if a in index.nodes and not a.startswith("file:")]
    files = [a for a in args if a not in ids]
    closure = closure_of(index, ids, files)
    items = [{"kind": "seed", "id": s, "label": index.label(s)} for s in closure["seeds"]]
    items += [{"kind": "declared_impact", "id": n, "type": index.nodes[n]["type"], "label": index.label(n)}
              for n in closure["mandatory"] if index.nodes[n]["type"] in ("Requirement", "Constraint", "TestCase",
                                                                          "Component", "StateModel", "Control")]
    for rel in files:
        node_id = "file:" + rel
        if node_id not in index.nodes:
            continue
        items += [{"kind": "code_impact", "id": i["id"], "label": i["path"], "hop": i["hop"]}
                  for i in _rdeps(index, [node_id], depth=3)[0]]
        items += [{"kind": "test_to_run", "id": t, "label": index.label(t), "how": how}
                  for t, (how, _) in sorted(_reaching_tests(index, node_id).items())]
    items += [{"kind": "unmapped_change", "id": u, "label": u} for u in closure["unmapped"]]
    notes = ["Empty known impacts with unmapped changes does not establish no impact."] if closure["unmapped"] else []
    return items, {"notes": notes}


def closure_of(index, ids, files):
    """AX-K-010 steps 1-6 on active canonical nodes of the snapshot; deterministic and conservative."""
    active = {n["id"]: n for n in index.nodes.values() if n.get("record", {}).get("status") == "active"}
    kind = {nid: n["type"] for nid, n in active.items()}
    seeds, unmapped, unknown = set(), [], []
    # Step 1: seed requirements from declared IDs and from bindings that resolve to changed files.
    changed = [i for i in ids if i in active]
    unknown += [i for i in ids if i not in active]
    for rel in files:
        bindings = index.sources("file:" + rel, "resolves_to")
        owners = [index.nodes[b]["record"]["node_id"] for b in bindings]
        if not owners:
            unmapped.append(rel)
        changed += [o for o in owners if o in active]
    for node_id in changed:
        seeds |= _requirements_of(index, node_id, kind)
        if not _requirements_of(index, node_id, kind) and kind.get(node_id) != "Requirement":
            unmapped.append(node_id)
    # Step 2: add requirements formalized by hard project rules, then depends_on both ways to a fixed point.
    hard_rules = sorted(nid for nid, n in active.items() if n["type"] == "Constraint"
                        and n["record"]["data"]["scope"] == "project"
                        and n["record"]["data"]["classification"]["strength"] == "hard")
    requirements = set(seeds) | {r for rule in hard_rules for r in index.targets(rule, "formalizes") if r in active}
    frontier = list(requirements)
    while frontier:
        current = frontier.pop()
        for other in index.targets(current, "depends_on") + index.sources(current, "depends_on"):
            if other in active and other not in requirements:
                requirements.add(other)
                frontier.append(other)
    selected = set(requirements) | set(hard_rules)
    # Step 3: endpoints incident to the selected requirements.
    for requirement in requirements:
        for edge in index.out.get(requirement, []) + index.into.get(requirement, []):
            other = edge["to"] if edge["from"] == requirement else edge["from"]
            if other in active and edge["relation"] in RELATION_NAMES:
                selected.add(other)
    # Steps 4-5: technical dependencies of constraints, tests and models, to a fixed point.
    frontier = sorted(selected)
    while frontier:
        current = frontier.pop()
        record = active.get(current, {}).get("record", {})
        found = set()
        if kind.get(current) == "Constraint":
            found |= set(index.targets(current, "uses_term")) | set(index.targets(current, "assumes"))
            found |= set(index.sources(current, "governs"))
        if kind.get(current) == "TestCase":
            found |= set(record["data"]["witness_scenario_ids"])
        if kind.get(current) == "StateModel":
            found |= {t["guard_id"] for t in record["data"]["transitions"] if t["guard_id"]}
        if kind.get(current) in ("Constraint", "StateModel", "Scenario") and record["data"].get("environment_id"):
            found.add(record["data"]["environment_id"])
        for other in sorted(found - selected):
            if other in active or index.nodes.get(other, {}).get("type") == "Environment":
                selected.add(other)
                frontier.append(other)
    # Step 6: actors, sources, bindings and assets the selection refers to.
    metadata = set()
    for node_id in list(selected):
        record = index.nodes.get(node_id, {}).get("record", {})
        metadata |= {record.get("owner"), record.get("created_by")} | set(record.get("source_ids", []))
        metadata |= set(index.targets(node_id, "has_binding"))
    for node in index.nodes.values():
        if node["type"] == "Asset" and set(node["record"]["supports"]) & selected:
            metadata.add(node["id"])
            metadata |= set(node["record"]["source_ids"])
    selected |= {m for m in metadata if m and m in index.nodes}
    return {"seeds": sorted(seeds), "hard_rules": hard_rules, "mandatory": sorted(selected),
            "unmapped": sorted(set(unmapped)), "unknown": sorted(set(unknown))}


RELATION_NAMES = {"satisfies", "uses_term", "formalizes", "models", "illustrates", "verifies", "implements",
                  "depends_on", "assumes", "governs", "threatens", "realizes"}


def _requirements_of(index, node_id, kind):
    """The requirements a changed node maps to through its typed links (step 1)."""
    node_kind = kind.get(node_id)
    if node_kind == "Requirement":
        return {node_id}
    linked = set(index.targets(node_id, "implements") + index.targets(node_id, "formalizes")
                 + index.targets(node_id, "verifies") + index.targets(node_id, "models")
                 + index.targets(node_id, "illustrates") + index.targets(node_id, "threatens")
                 + index.targets(node_id, "governs") + index.sources(node_id, "satisfies")
                 + index.sources(node_id, "uses_term") + index.sources(node_id, "assumes")
                 + index.sources(node_id, "realizes"))
    if node_kind == "Control":
        risks = index.targets(node_id, "mitigates")
        linked |= {r for risk in risks for r in index.targets(risk, "threatens")}
    return {n for n in linked if kind.get(n) == "Requirement"}


def packet(snapshot, ids, files, budget_bytes=MAX_BYTES):
    """AX-D-001/AX-K-007: the mandatory closure, rendered, split into parts under the budget; never truncated."""
    index = Index(snapshot)
    closure = closure_of(index, ids, files)
    records = [_packet_item(index, node_id, closure) for node_id in closure["mandatory"]]
    records.sort(key=lambda r: (ORDER.get(r["type"], 99), r["id"]))
    docs = sorted({e["from"][5:] for n in closure["mandatory"] for e in index.into.get(n, [])
                   if e["relation"] == "mentions"} | {e["from"][5:] for f in files
                                                      for e in index.into.get("file:" + f, []) if e["relation"] == "specifies"})
    parts, current, size = [], [], 0
    for record in records:
        encoded = len(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        if current and size + encoded > budget_bytes:
            parts.append(current)
            current, size = [], 0
        current.append(record)
        size += encoded
    if current:
        parts.append(current)
    status = "complete" if not closure["unmapped"] and not closure["unknown"] else "incomplete"
    return {"format": "aeion-packet/0.1", "snapshot_id": snapshot["manifest"]["snapshot_id"],
            "spec_sha256": snapshot["manifest"]["spec"].get("sha256"), "change": {"ids": ids, "files": files},
            "seeds": closure["seeds"], "hard_rules": closure["hard_rules"], "unmapped_changes": closure["unmapped"],
            "unknown_ids": closure["unknown"], "closure_sha256": canonical_digest(closure["mandatory"]),
            "status": status, "budget_bytes": budget_bytes,
            "parts": [{"index": i + 1, "of": len(parts), "items": part} for i, part in enumerate(parts)],
            "optional_documents": docs,
            "limits": ["Selection follows declared relations, not learned relevance (AX-K-007).",
                       "A delivery receipt does not prove the reader understood or obeyed it.",
                       *index.limits]}


ORDER = {"Constraint": 0, "Requirement": 1, "Goal": 2, "Decision": 3, "Assumption": 4, "Term": 5, "StateModel": 6,
         "Scenario": 7, "TestCase": 8, "Component": 9, "Risk": 10, "Control": 11, "Environment": 12, "Binding": 13,
         "Asset": 14, "Source": 15, "Actor": 16}


def _packet_item(index, node_id, closure):
    node = index.nodes[node_id]
    record = node.get("record", {})
    item = {"id": node_id, "type": node["type"], "label": index.label(node_id)}
    if node["type"] == "Requirement":
        item["sentence"] = render_requirement(record["data"])
    if node_id in closure["hard_rules"]:
        item["hard_project_rule"] = True
    if node["type"] == "Binding":
        item["resolution"] = node.get("resolution")
    item["record"] = record
    return item


def packet_markdown(value):
    """The packet as a coding agent reads it: hard rules first, then obligations, then their evidence plan."""
    lines = [f"# Context packet ({value['status']})", "",
             f"Snapshot `{value['snapshot_id'][:16]}` · spec `{(value['spec_sha256'] or 'none')[:16]}` · "
             f"closure `{value['closure_sha256'][:16]}` · {len(value['parts'])} part(s)", "",
             f"Change: ids {value['change']['ids'] or '-'}; files {value['change']['files'] or '-'}"]
    if value["unmapped_changes"] or value["unknown_ids"]:
        lines += ["", "**Incomplete:** unmapped " + ", ".join(value["unmapped_changes"] or ["-"])
                  + "; unknown " + ", ".join(value["unknown_ids"] or ["-"]) + ". Investigate before claiming impact."]
    for part in value["parts"]:
        lines += ["", f"## Part {part['index']} of {part['of']}"]
        for item in part["items"]:
            lines.append(_markdown_item(item))
    if value["optional_documents"]:
        lines += ["", "## Documents to read (optional context)", *[f"- `{d}`" for d in value["optional_documents"]]]
    lines += ["", "## Limits", *[f"- {limit}" for limit in value["limits"]]]
    return "\n".join(lines)


def _markdown_item(item):
    record, kind = item["record"], item["type"]
    data = record.get("data", {})
    head = f"- **{item['id']}** {kind}{' · HARD PROJECT RULE' if item.get('hard_project_rule') else ''}: {item['label']}"
    if kind == "Requirement":
        return head + f"\n  - {item['sentence']} (priority {data['priority']}, risk {data['risk']})"
    if kind == "Constraint":
        body = (f"BCIR in {data['environment_id']}: `{json.dumps(data['expression'], separators=(',', ':'))}`"
                if data["expression"] else f"review protocol: {data['review_protocol']}")
        return head + f"\n  - {data['predicate_role']}, {data['classification']['strength']}, {data['scope']}; {body}"
    if kind == "Decision":
        return head + f"\n  - Q: {data['question']} A: {data['answer'] if data['answer'] is not None else 'OPEN'}"
    if kind == "TestCase":
        return head + f"\n  - {data['level']}, {'negative' if data['negative'] else 'normal'}, {data['state']}: {data['oracle']}"
    if kind == "Scenario":
        return head + f"\n  - {data['intent']} on `{data['event']}`: {data['expected']}"
    if kind == "Binding":
        resolution = item.get("resolution") or {}
        where = f"line {resolution['line']}" if resolution.get("line") else resolution.get("status", "unknown")
        return head + f"\n  - `{record['path']}` `{record['symbol']}` ({record['expected_resolution']}): {where}"
    if kind == "Term":
        return head + f"\n  - {data['definition']}" + (f" Unit: {data['unit']}." if data.get("unit") else "")
    if kind == "Goal":
        return head + f"\n  - {data['description']} Success: {data['success_measure']}"
    return head


def text(response, cap=40):
    """Compact lines for an agent; the header always states counts, completeness and the snapshot."""
    kind = response["query"]["kind"]
    head = (f"{kind} {' '.join(response['query']['args'])}: {response['returned_count']} of "
            f"{response['total_visible_count']} (snapshot {response['snapshot_id'][:12]}"
            f"{'' if response['complete'] else ', incomplete'})")
    lines = [head]
    if response.get("error"):
        lines.append(f"  {response['error']}")
    formatter = LINES.get(kind, _generic)
    for item in response["items"]:
        lines.append("  " + (_generic(item) if response.get("error") else formatter(item)))
    if cap is not None and len(lines) > cap + 1:
        hidden = len(lines) - cap - 1
        lines = lines[:cap + 1] + [f"  ... {hidden} more line(s); --all or --json shows them"]
    lines += [f"  note: {n}" for n in response.get("notes", [])]
    lines += [f"  omitted: {o}" for o in response["omissions"]]
    return "\n".join(lines)


def _at(path, line):
    return f"{path}:{line}" if line else path


def _generic(item):
    return ", ".join(f"{k}={v}" for k, v in item.items() if v not in (None, "", []))


def _node_line(item):
    if "direction" in item:
        arrow = "->" if item["direction"] == "out" else "<-"
        return f"{arrow} {item['relation']:<14} {_at(item['other_label'], item.get('line'))} [{item['origin']}]"
    sentence = f": {item['sentence']}" if item.get("sentence") else ""
    status = item.get("record", {}).get("status")
    return f"{item['id']} {item['type']}{' ' + status if status else ''} '{item['label']}'{sentence}"


def _brief_line(item):
    if "relation" not in item:
        return _node_line(item)
    extra = {k: v for k, v in item.items() if k not in ("relation", "id", "type", "label")}
    details = "; ".join(f"{k}={v}" for k, v in extra.items() if v not in (None, "", []))
    return f"{item['relation']:<12} {item['id']} {item['type']} '{item['label']}'" + (f" ({details})" if details else "")


LINES = {
    "node": _node_line,
    "requirement": _brief_line,
    "find": lambda i: (f"{i['label']}: " + ", ".join(f"{d['kind']} {d['name']} line {d['line']}" for d in i["definitions"])
                       if i.get("definitions") else f"{i['id']} {i['type']} '{i['label']}'"),
    "search": lambda i: f"{i['id']} {i['type']} '{i['label']}'",
    "deps": lambda i: f"{i['relation']:<10} {_at(i['path'], i.get('line'))} [{i['origin']}]",
    "rdeps": lambda i: f"hop {i['hop']}  {_at(i['path'], i.get('line'))}  (imports {i['via']})",
    "path": lambda i: f"{i['hop']}. {_at(i['from'], i.get('line'))} -{i['relation']}-> {i['to']} [{i['origin']}]",
    "tests": lambda i: f"{i['how']:<8} {i['test']}" + (f"  via {' -> '.join(i['chain'][1:-1])}" if len(i['chain']) > 2 else ""),
    "untested": lambda i: f"{i['path']} ({i['language']})",
    "spec": lambda i: (f"{i['doc']}  ({i['how']})" if "doc" in i else f"{i['canonical']} '{i['label']}'  ({i['how']})"),
    "files": lambda i: f"{i.get('path') or i['id'] + ' ' + repr(i['label'])}  ({i['how']})",
    "hubs": lambda i: f"{i['imported_by']:>3}  {i['path']}",
    "gaps": lambda i: f"{i['gate']:<5} {i['subject']}: {i['gap']}" + (f" -- {i['detail']}" if i['detail'] else ""),
    "impact": lambda i: f"{i['kind']:<16} {i['id']}" + (f" '{i['label']}'" if i['label'] != i['id'] else "")
                        + (f" (hop {i['hop']})" if "hop" in i else "") + (f" ({i['how']})" if "how" in i else ""),
}


HANDLERS = {"node": _node, "requirement": _requirement, "find": _find, "search": _search, "deps": _deps,
            "rdeps": _rdeps, "path": _path, "tests": _tests, "untested": _untested, "spec": _spec, "files": _files,
            "hubs": _hubs, "status": _status, "gaps": _gaps, "impact": _impact}
