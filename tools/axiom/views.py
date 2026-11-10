# Spec: knowledge/components/axiom-toolkit.md
"""Diagram views rendered to SVG with the standard library (AX-M-015, playbook sections 12-18).

Sources are structured JSON (aeion-view/0.1), never diagram text: labels are data and are escaped,
so a requirement title cannot become markup. Layout is deterministic: the same source gives the
same bytes. Families: flow (system context, components, process), sequence, usecase, state."""
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from common import GENERATED, VIEW_CATALOG, write_atomic
from schema import Validator
from strict import InputError, load

FORMAT = "aeion-view/0.1"
RENDERER = "aeion-svg/1"
# Every rendered SVG carries this on its root element: what the generator wrote, it may replace or delete.
MARK = 'data-generator="tools/axiom"'
FONT = 13
LINE = 17
_id = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"}
_text = {"type": "string", "minLength": 1, "maxLength": 200}
_label = {"type": "string", "maxLength": 200}
SOURCE_SCHEMA = {
    "type": "object", "required": ["format", "kind"], "additionalProperties": False,
    "properties": {
        "format": {"const": FORMAT}, "kind": {"enum": ["flow", "sequence", "usecase", "state"]},
        "direction": {"enum": ["LR", "TB"]}, "model_id": {"type": "string"},
        "nodes": {"type": "array", "maxItems": 40, "items": {
            "type": "object", "required": ["id", "label"], "additionalProperties": False,
            "properties": {"id": _id, "label": _text, "shape": {"enum": ["box", "round", "decision", "store",
                                                                          "actor", "external", "start", "end"]},
                           "group": _id, "ids": {"type": "array", "items": {"type": "string"}}}}},
        "groups": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "required": ["id", "label"], "additionalProperties": False,
            "properties": {"id": _id, "label": _text}}},
        "edges": {"type": "array", "maxItems": 80, "items": {
            "type": "object", "required": ["from", "to"], "additionalProperties": False,
            "properties": {"from": _id, "to": _id, "label": _label, "style": {"enum": ["solid", "dashed"]}}}},
        "participants": {"type": "array", "maxItems": 10, "items": {
            "type": "object", "required": ["id", "label"], "additionalProperties": False,
            "properties": {"id": _id, "label": _text, "type": {"enum": ["actor", "participant", "store"]}}}},
        "steps": {"type": "array", "maxItems": 60, "items": {"type": "object"}},
        "system": _text,
        "actors": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "required": ["id", "label"], "additionalProperties": False,
            "properties": {"id": _id, "label": _text, "side": {"enum": ["left", "right"]}}}},
        "usecases": {"type": "array", "maxItems": 14, "items": {
            "type": "object", "required": ["id", "label"], "additionalProperties": False,
            "properties": {"id": _id, "label": _text, "ids": {"type": "array", "items": {"type": "string"}}}}},
        "links": {"type": "array", "maxItems": 60, "items": {
            "type": "object", "required": ["actor", "usecase"], "additionalProperties": False,
            "properties": {"actor": _id, "usecase": _id}}},
        "relations": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "required": ["from", "to", "kind"], "additionalProperties": False,
            "properties": {"from": _id, "to": _id, "kind": {"enum": ["include", "extend"]}}}},
        "states": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
        "initial": {"type": "string"}, "final": {"type": "array", "items": {"type": "string"}},
        "transitions": {"type": "array", "maxItems": 60, "items": {
            "type": "object", "required": ["from", "to"], "additionalProperties": False,
            "properties": {"from": {"type": "string"}, "to": {"type": "string"}, "label": _label}}}}}
STEP_KINDS = {"sync", "async", "reply", "self"}
STYLE = """
.v{--bg:#ffffff;--fg:#0f172a;--muted:#475569;--line:#64748b;--node:#ffffff;--soft:#f8fafc;--group:#94a3b8;
--accent:#2563eb;--decision:#fef3c7;--store:#ecfeff;--note:#fefce8}
@media (prefers-color-scheme:dark){.v{--bg:#0b1120;--fg:#e2e8f0;--muted:#94a3b8;--line:#94a3b8;--node:#1e293b;
--soft:#0b1120;--group:#475569;--accent:#60a5fa;--decision:#3b2f0b;--store:#083344;--note:#2a2a12}}
.v .bg{fill:var(--bg)}
.v text{font:13px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--fg)}
.v .muted{fill:var(--muted);font-size:12px}.v .title{font-weight:600}
.v .n{fill:var(--node);stroke:var(--line);stroke-width:1.3}.v .d{fill:var(--decision);stroke:var(--line);stroke-width:1.3}
.v .s{fill:var(--store);stroke:var(--line);stroke-width:1.3}.v .x{fill:var(--node);stroke:var(--line);stroke-dasharray:5 3}
.v .g{fill:none;stroke:var(--group);stroke-dasharray:6 4;stroke-width:1.2}.v .e{fill:none;stroke:var(--line);stroke-width:1.3}
.v .dash{stroke-dasharray:5 4}.v .a{fill:var(--line)}.v .lab{fill:var(--soft);opacity:.92}
.v .act{fill:none;stroke:var(--accent);stroke-width:1.6}.v .life{stroke:var(--group);stroke-dasharray:4 4}
.v .frag{fill:none;stroke:var(--group);stroke-width:1.2}.v .note{fill:var(--note);stroke:var(--group)}
.v .solid{fill:var(--fg)}.v .ring{fill:none;stroke:var(--fg);stroke-width:1.5}
"""


class ViewError(ValueError):
    pass


def text_width(text):
    """An estimate for 13px sans-serif: enough to size boxes without a font engine."""
    total = 0.0
    for char in text:
        if char in "iljt.,:;'|!()[] ":
            total += 3.9
        elif char in "mwMW@%":
            total += 10.5
        elif char.isupper() or char.isdigit():
            total += 8.2
        else:
            total += 7.0
    return total


def wrap(text, limit=22):
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return lines + ([current] if current else []) or [""]


class Canvas:
    """SVG fragments with escaping in one place."""

    def __init__(self):
        self.parts = []
        self.low = (math.inf, math.inf)

    def reach(self, x, y):
        """Record a point drawn outside the node grid (a label corner, a loop's far side)."""
        self.low = (min(self.low[0], x), min(self.low[1], y))

    def add(self, fragment):
        self.parts.append(fragment)

    def text(self, x, y, value, anchor="middle", css=""):
        cls = f' class="{css}"' if css else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{cls}>{escape(value)}</text>')

    def lines(self, x, y, values, anchor="middle", css=""):
        top = y - (len(values) - 1) * LINE / 2
        for index, value in enumerate(values):
            self.text(x, top + index * LINE + 4.5, value, anchor, css)

    def label(self, x, y, value, limit=18):
        if not value:
            return
        rows = wrap(value, limit)
        width = max(text_width(r) for r in rows) + 10
        height = len(rows) * LINE + 4
        self.reach(x - width / 2, y - height / 2)
        self.add(f'<rect class="lab" x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" '
                 f'height="{height:.1f}" rx="4"/>')
        self.lines(x, y, rows, css="muted")

    def svg(self, width, height, title, description, margin=0):
        body = "\n".join(self.parts)
        # Shift everything right or down when a label or a loop reached past the left or top margin.
        dx, dy = (max(0.0, margin - self.low[0]) if margin else 0.0), (max(0.0, margin - self.low[1]) if margin else 0.0)
        if dx or dy:
            body = f'<g transform="translate({dx:.1f},{dy:.1f})">\n{body}\n</g>'
            width, height = width + dx, height + dy
        return (f'<svg xmlns="http://www.w3.org/2000/svg" class="v" {MARK} width="{math.ceil(width)}" '
                f'height="{math.ceil(height)}" viewBox="0 0 {math.ceil(width)} {math.ceil(height)}" role="img" '
                f'aria-labelledby="t d">\n<title id="t">{escape(title)}</title>\n<desc id="d">{escape(description)}</desc>\n'
                f"<style>{STYLE}</style>\n<defs><marker id=\"arrow\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" "
                f"markerWidth=\"8\" markerHeight=\"8\" orient=\"auto-start-reverse\"><path class=\"a\" "
                f"d=\"M0,0 L10,5 L0,10 z\"/></marker><marker id=\"open\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" "
                f"markerWidth=\"8\" markerHeight=\"8\" orient=\"auto\"><path class=\"e\" d=\"M0,0 L10,5 L0,10\"/>"
                f"</marker></defs>\n<rect class=\"bg\" width=\"100%\" height=\"100%\" rx=\"10\"/>\n{body}\n</svg>\n")


def render(source, title, question, model=None):
    """SVG text for one validated view source; a state view may derive from a canonical StateModel."""
    problems = Validator(SOURCE_SCHEMA).errors(source)
    if problems:
        pointer, message = problems[0]
        raise ViewError(f"view source invalid at {pointer or '/'}: {message}")
    kind = source["kind"]
    if kind == "state" and source.get("model_id"):
        source = _state_from_model(source, model)
    if kind == "flow":
        return _flow(source, title, question)
    if kind == "state":
        return _flow(_state_as_flow(source), title, question)
    if kind == "sequence":
        return _sequence(source, title, question)
    return _usecase(source, title, question)


def _state_from_model(source, model):
    record = (model.nodes.get(source["model_id"]) if model else None)
    if record is None or record["kind"] != "StateModel":
        raise ViewError(f"{source['model_id']} is not a StateModel in the spec")
    data = record["data"]
    names = {t["guard_id"]: (model.nodes[t["guard_id"]]["title"] if t["guard_id"] in model.nodes else t["guard_id"])
             for t in data["transitions"] if t["guard_id"]}
    return {"format": FORMAT, "kind": "state", "direction": source.get("direction", "LR"),
            "states": [s["name"] for s in data["states"]], "initial": data["initial"],
            "final": [s["name"] for s in data["states"] if s["terminal"]],
            "transitions": [{"from": t["from"], "to": t["to"],
                             "label": t["event"] + (f" [{names[t['guard_id']]}]" if t["guard_id"] else "")}
                            for t in data["transitions"]]}


def _state_as_flow(source):
    nodes = [{"id": "__start", "label": "start", "shape": "start"}]
    index = {}
    for position, name in enumerate(source["states"]):
        index[name] = f"s{position}"
        nodes.append({"id": f"s{position}", "label": name, "shape": "round"})
    edges = [{"from": "__start", "to": index[source["initial"]]}] if source.get("initial") in index else []
    for transition in source["transitions"]:
        if transition["from"] not in index or transition["to"] not in index:
            raise ViewError(f"transition {transition['from']} -> {transition['to']} names an undeclared state")
        edges.append({"from": index[transition["from"]], "to": index[transition["to"]],
                      "label": transition.get("label", "")})
    for position, name in enumerate(source.get("final", [])):
        if name in index:
            nodes.append({"id": f"__end{position}", "label": "end", "shape": "end"})
            edges.append({"from": index[name], "to": f"__end{position}"})
    return {"format": FORMAT, "kind": "flow", "direction": source.get("direction", "LR"), "nodes": nodes,
            "edges": edges}


def _flow(source, title, question):
    """Layered layout: ranks by longest path, waypoints for long edges, barycenter ordering, groups contiguous."""
    nodes = {n["id"]: dict(n) for n in source.get("nodes", [])}
    if not nodes:
        raise ViewError("a flow view needs nodes")
    order = [n["id"] for n in source["nodes"]]
    edges = source.get("edges", [])
    for edge in edges:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            raise ViewError(f"edge {edge['from']} -> {edge['to']} names an undeclared node")
    groups = {g["id"]: g["label"] for g in source.get("groups", [])}
    for node in nodes.values():
        if node.get("group") and node["group"] not in groups:
            raise ViewError(f"node {node['id']} names undeclared group {node['group']}")
    vertical = source.get("direction", "LR") == "TB"
    forward = _acyclic(order, edges)
    rank = {n: 0 for n in order}
    for _ in order:
        for a, b in forward:
            rank[b] = max(rank[b], rank[a] + 1)
    # A forward edge spanning several ranks gets one waypoint per crossed rank, ordered like a node.
    sizes = {n: _node_size(nodes[n]) for n in order}
    chains, segments = {}, []
    for index, edge in enumerate(edges):
        a, b = edge["from"], edge["to"]
        if a == b or rank[b] <= rank[a]:
            continue
        chain = [a]
        for r in range(rank[a] + 1, rank[b]):
            waypoint = f"\0w{index}.{r}"
            rank[waypoint], sizes[waypoint] = r, (14, 14)
            nodes[waypoint] = {"id": waypoint, "label": "", "shape": "waypoint", "group": None}
            chain.append(waypoint)
        chain.append(b)
        chains[index] = chain
        segments += list(zip(chain, chain[1:]))
    members = order + [n for chain in chains.values() for n in chain[1:-1]]
    layers = {}
    for node_id in members:
        layers.setdefault(rank[node_id], []).append(node_id)
    group_key = {g: i for i, g in enumerate(groups)}
    position = {n: i for i, n in enumerate(members)}
    for sweep in range(8):
        ranks = sorted(layers) if sweep % 2 == 0 else sorted(layers, reverse=True)
        for r in ranks:
            neighbours = {n: [position[a if b == n else b] for a, b in segments if n in (a, b)] for n in layers[r]}
            key = {n: (sum(v) / len(v) if v else position[n]) for n, v in neighbours.items()}
            layers[r].sort(key=lambda n: (group_key.get(nodes[n].get("group"), -1), key[n], position[n]))
            for i, n in enumerate(layers[r]):
                position[n] = i + r * 0.001
    gap_rank, gap_order, margin = (70, 34, 28) if vertical else (78, 26, 28)
    # A gap between two ranks is wide enough for the labels of the edges that cross it.
    needed = {}
    for edge in edges:
        if edge.get("label") and rank[edge["to"]] > rank[edge["from"]]:
            rows = wrap(edge["label"], 18 if vertical else 30)
            extent = len(rows) * LINE + 44 if vertical else max(text_width(r) for r in rows) + 52
            low = rank[edge["from"]] if rank[edge["to"]] - rank[edge["from"]] == 1 else rank[edge["from"]] + 1
            needed[low] = max(needed.get(low, 0), extent)
    rank_extent = {r: max((sizes[n][1] if vertical else sizes[n][0]) for n in layers[r]) for r in layers}
    span = {r: sum((sizes[n][0] if vertical else sizes[n][1]) for n in layers[r]) + gap_order * (len(layers[r]) - 1)
            for r in layers}
    widest = max(span.values())
    centers, cursor = {}, margin + 22
    group_pad = 30 if groups else 0
    for r in sorted(layers):
        along = cursor + rank_extent[r] / 2
        offset = margin + group_pad + (widest - span[r]) / 2
        for n in layers[r]:
            extent = sizes[n][0] if vertical else sizes[n][1]
            centers[n] = (offset + extent / 2, along) if vertical else (along, offset + extent / 2)
            offset += extent + gap_order
        cursor += rank_extent[r] + max(gap_rank, needed.get(r, 0))
    real = {n: centers[n] for n in order}
    canvas = Canvas()
    group_boxes = _group_boxes(nodes, real, sizes, groups, vertical)
    for x, y, w, h, _ in group_boxes:
        canvas.add(f'<rect class="g" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10"/>')
    labels = []
    for index, edge in enumerate(edges):
        labels.append(_flow_edge(canvas, edge, chains.get(index), centers, sizes, rank, layers, vertical, nodes))
    for node_id in order:
        _shape(canvas, nodes[node_id], centers[node_id], sizes[node_id])
    for x, y, value in labels:
        canvas.label(x, y, value, 18 if vertical else 30)
    for x, y, w, h, label in group_boxes:
        width_label = text_width(label) + 14
        top = y + h - 24 if vertical else y + 4
        canvas.add(f'<rect class="lab" x="{x + 6:.1f}" y="{top:.1f}" width="{width_label:.1f}" height="18" rx="4"/>')
        canvas.text(x + 13, top + 13, label, "start", "muted title")
    width = max(c[0] + sizes[n][0] / 2 for n, c in real.items()) + margin + group_pad
    height = max(c[1] + sizes[n][1] / 2 for n, c in real.items()) + margin + group_pad
    for x, y, w, h, _ in group_boxes:
        width, height = max(width, x + w + margin), max(height, y + h + margin)
    if any(rank[e["to"]] <= rank[e["from"]] for e in edges):
        # Return edges loop beyond the last row or column; their labels sit on that loop.
        width, height = (width + 70, height) if vertical else (width, height + 56)
    return canvas.svg(width, height, title, question, margin=12)


def _acyclic(order, edges):
    """Edges with back edges (found by DFS in declared order) reversed, so ranking always terminates."""
    adjacency = {n: [] for n in order}
    for edge in edges:
        adjacency[edge["from"]].append(edge["to"])
    state, back = {}, set()
    for root in order:
        if root in state:
            continue
        stack = [(root, iter(adjacency[root]))]
        state[root] = "open"
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[node] = "done"
                stack.pop()
            elif state.get(child) == "open":
                back.add((node, child))
            elif child not in state:
                state[child] = "open"
                stack.append((child, iter(adjacency[child])))
    return [(b, a) if (a, b) in back else (a, b) for a, b in ((e["from"], e["to"]) for e in edges) if a != b]


def _wrap_of(node):
    return node.get("wrap") or (18 if node.get("shape") == "decision" else 22)


def _node_size(node):
    shape = node.get("shape", "box")
    if shape in ("start", "end"):
        return (22, 22)
    rows = wrap(node["label"], _wrap_of(node))
    width = max(text_width(r) for r in rows) + 28
    height = len(rows) * LINE + 18
    if shape == "decision":
        return (max(width * 1.45, 110), max(height * 1.5, 64))
    if shape == "actor":
        return (max(width, 70), height + 34)
    if shape == "store":
        return (max(width, 96), height + 14)
    return (max(width, 96), max(height, 40))


def _shape(canvas, node, center, size):
    x, y = center
    w, h = size
    shape = node.get("shape", "box")
    rows = wrap(node["label"], _wrap_of(node))
    if shape == "start":
        canvas.add(f'<circle class="solid" cx="{x:.1f}" cy="{y:.1f}" r="9"/>')
        return
    if shape == "end":
        canvas.add(f'<circle class="ring" cx="{x:.1f}" cy="{y:.1f}" r="10"/><circle class="solid" cx="{x:.1f}" '
                   f'cy="{y:.1f}" r="6"/>')
        return
    if shape == "decision":
        canvas.add(f'<polygon class="d" points="{x:.1f},{y - h / 2:.1f} {x + w / 2:.1f},{y:.1f} {x:.1f},'
                   f'{y + h / 2:.1f} {x - w / 2:.1f},{y:.1f}"/>')
    elif shape == "store":
        top, rx = y - h / 2, w / 2
        canvas.add(f'<path class="s" d="M{x - rx:.1f},{top + 7:.1f} v{h - 14:.1f} a{rx:.1f},7 0 0 0 {w:.1f},0 '
                   f'v{-(h - 14):.1f} a{rx:.1f},7 0 0 0 {-w:.1f},0 a{rx:.1f},7 0 0 0 {w:.1f},0"/>')
        y += 4
    elif shape == "actor":
        head = y - h / 2 + 9
        canvas.add(f'<g class="act"><circle cx="{x:.1f}" cy="{head:.1f}" r="7"/><path d="M{x:.1f},{head + 7:.1f} '
                   f'v14 M{x - 10:.1f},{head + 12:.1f} h20 M{x:.1f},{head + 21:.1f} l-8,10 M{x:.1f},'
                   f'{head + 21:.1f} l8,10"/></g>')
        canvas.lines(x, y + 17, rows)
        return
    else:
        css = "x" if shape == "external" else "n"
        radius = 16 if shape == "round" else 6
        canvas.add(f'<rect class="{css}" x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" '
                   f'rx="{radius}"/>')
    canvas.lines(x, y, rows)


def _group_boxes(nodes, centers, sizes, groups, vertical=False):
    boxes = []
    for group_id, label in groups.items():
        members = [n for n in centers if nodes[n].get("group") == group_id]
        if not members:
            continue
        left = min(centers[n][0] - sizes[n][0] / 2 for n in members) - 16
        top = min(centers[n][1] - sizes[n][1] / 2 for n in members) - (16 if vertical else 34)
        right = max(max(centers[n][0] + sizes[n][0] / 2 for n in members) + 16, left + text_width(label) + 30)
        bottom = max(centers[n][1] + sizes[n][1] / 2 for n in members) + (34 if vertical else 14)
        boxes.append((left, top, right - left, bottom - top, label))
    return boxes


def _border(center, size, toward, shape):
    """The point where the segment from center toward a target leaves the node's outline."""
    x, y = center
    dx, dy = toward[0] - x, toward[1] - y
    if dx == 0 and dy == 0:
        return center
    w, h = size[0] / 2, size[1] / 2
    if shape in ("start", "end"):
        scale = 11 / math.hypot(dx, dy)
    elif shape == "decision":
        scale = 1 / (abs(dx) / w + abs(dy) / h)
    else:
        scale = min(w / abs(dx) if dx else math.inf, h / abs(dy) if dy else math.inf)
    return (x + dx * scale, y + dy * scale)


def _flow_edge(canvas, edge, chain, centers, sizes, rank, layers, vertical, nodes):
    a, b = edge["from"], edge["to"]
    style = " dash" if edge.get("style") == "dashed" else ""
    (ax, ay), (bx, by) = centers[a], centers[b]
    if a == b:
        x, y = ax + sizes[a][0] / 2, ay
        canvas.add(f'<path class="e{style}" d="M{x:.1f},{y - 8:.1f} c34,-26 34,42 0,16" marker-end="url(#arrow)"/>')
        return (x + 30, y, edge.get("label", ""))
    if rank[b] <= rank[a]:
        # A return edge loops outside every node of the ranks it spans, so it crosses none of them.
        spanned = [n for r in range(rank[b], rank[a] + 1) for n in layers.get(r, [])]
        across = 0 if vertical else 1
        # Leave on the free side: toward the start (left or top) when the node is first in its rank.
        first = all(centers[n][across] >= centers[a][across] for n in layers[rank[a]])
        last = all(centers[n][across] <= centers[a][across] for n in layers[rank[a]])
        sign = -1 if first and not last else 1
        if vertical:
            edge_of = lambda n: centers[n][0] + sign * sizes[n][0] / 2  # noqa: E731
            side = (max if sign > 0 else min)(edge_of(n) for n in spanned) + sign * 30
            start, end = (edge_of(a), ay), (edge_of(b), by)
            path = f"M{start[0]:.1f},{start[1]:.1f} C{side:.1f},{start[1]:.1f} {side:.1f},{end[1]:.1f} {end[0]:.1f},{end[1]:.1f}"
            middle = (side - sign * 8, (start[1] + end[1]) / 2)
        else:
            edge_of = lambda n: centers[n][1] + sign * sizes[n][1] / 2  # noqa: E731
            low = (max if sign > 0 else min)(edge_of(n) for n in spanned) + sign * 30
            start, end = (ax, edge_of(a)), (bx, edge_of(b))
            path = f"M{start[0]:.1f},{start[1]:.1f} C{start[0]:.1f},{low:.1f} {end[0]:.1f},{low:.1f} {end[0]:.1f},{end[1]:.1f}"
            middle = ((start[0] + end[0]) / 2, low - sign * 8)
        canvas.add(f'<path class="e{style}" d="{path}" marker-end="url(#arrow)"/>')
        canvas.reach(side if vertical else min(start[0], end[0]), min(start[1], end[1]) if vertical else low)
        return (*middle, edge.get("label", ""))
    points = [centers[n] for n in chain]
    points[0] = _border(centers[a], sizes[a], points[1], nodes[a].get("shape", "box"))
    points[-1] = _border(centers[b], sizes[b], points[-2], nodes[b].get("shape", "box"))
    commands, label_at = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"], None
    for index, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        if vertical:
            bend = (y1 - y0) / 2
            c1, c2 = (x0, y0 + bend), (x1, y1 - bend)
        else:
            bend = (x1 - x0) / 2
            c1, c2 = (x0 + bend, y0), (x1 - bend, y1)
        commands.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x1:.1f},{y1:.1f}")
        if len(points) == 2:
            t = 0.62
            weights = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3)
            segment = ((x0, y0), c1, c2, (x1, y1))
            label_at = tuple(sum(w * p[axis] for w, p in zip(weights, segment)) for axis in (0, 1))
        else:
            # A long edge's label sits on its middle waypoint, which ordering placed in free space.
            label_at = points[len(points) // 2]
    canvas.add(f'<path class="e{style}" d="{" ".join(commands)}" marker-end="url(#arrow)"/>')
    return (*label_at, edge.get("label", ""))


def _sequence(source, title, question):
    participants = source.get("participants", [])
    if len(participants) < 2:
        raise ViewError("a sequence view needs at least two participants")
    ids = [p["id"] for p in participants]
    widths = [max(text_width(r) for r in wrap(p["label"], 18)) + 30 for p in participants]
    heights = [len(wrap(p["label"], 18)) * LINE + 22 for p in participants]
    column = max(max(widths) + 50, 150)
    x = {pid: 40 + column / 2 + i * column for i, pid in enumerate(ids)}
    rows = _sequence_rows(source.get("steps", []), set(ids), 0)
    head_h, top = max(max(heights), 44), 30
    y = top + head_h + 26
    canvas = Canvas()
    body = Canvas()
    y = _sequence_draw(body, rows, x, y, column, 0)
    bottom = y + 16
    for participant, width in zip(participants, widths):
        cx = x[participant["id"]]
        canvas.add(f'<line class="life" x1="{cx:.1f}" y1="{top + head_h:.1f}" x2="{cx:.1f}" y2="{bottom:.1f}"/>')
    for participant, width in zip(participants, widths):
        cx = x[participant["id"]]
        node = {"id": participant["id"], "label": participant["label"], "wrap": 18,
                "shape": {"actor": "actor", "store": "store"}.get(participant.get("type"), "box")}
        size = (width, head_h) if node["shape"] != "actor" else (width, head_h + 8)
        _shape(canvas, node, (cx, top + head_h / 2), size)
    canvas.parts += body.parts
    width = 40 * 2 + column * len(ids)
    return canvas.svg(width, bottom + 30, title, question)


def _sequence_rows(steps, ids, depth):
    rows = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ViewError(f"step {index} must be an object")
        if "note" in step:
            over = step.get("over", [])
            if not isinstance(step["note"], str) or len(step["note"]) > 200:
                raise ViewError(f"note {index} is a string of at most 200 characters")
            if not isinstance(over, list) or not over or not all(isinstance(o, str) for o in over) or not set(over) <= ids:
                raise ViewError(f"note {index} must name declared participants in 'over'")
            rows.append(("note", step["note"], over))
        elif "fragment" in step:
            if step["fragment"] not in ("alt", "opt", "loop", "par") or depth > 3:
                raise ViewError(f"fragment {index}: alt, opt, loop or par, at most 4 deep")
            listed = step.get("branches", [])
            if not isinstance(listed, list) or not all(isinstance(b, dict) and isinstance(b.get("label", ""), str)
                                                       and isinstance(b.get("steps", []), list) for b in listed):
                raise ViewError(f"fragment {index}: branches are objects with a label and a list of steps")
            branches = [(b.get("label", ""), _sequence_rows(b.get("steps", []), ids, depth + 1)) for b in listed]
            if not branches:
                raise ViewError(f"fragment {index} needs branches")
            rows.append(("fragment", step["fragment"], branches))
        else:
            kind = step.get("kind", "sync")
            ends = (step.get("from"), step.get("to"))
            if not all(isinstance(e, str) and e in ids for e in ends) or not isinstance(kind, str) or kind not in STEP_KINDS:
                raise ViewError(f"step {index}: from/to must be declared participants and kind one of {sorted(STEP_KINDS)}")
            if not isinstance(step.get("label", ""), str) or len(step.get("label", "")) > 200:
                raise ViewError(f"step {index}: label is a string of at most 200 characters")
            rows.append(("message", step, None))
    return rows


def _sequence_draw(canvas, rows, x, y, column, depth):
    for kind, value, extra in rows:
        if kind == "note":
            xs = [x[p] for p in extra]
            left, right = min(xs) - column * 0.4, max(xs) + column * 0.4
            texts = wrap(value, max(int((right - left) / 7.2), 16))
            height = len(texts) * LINE + 12
            canvas.add(f'<rect class="note" x="{left:.1f}" y="{y:.1f}" width="{right - left:.1f}" height="{height:.1f}" rx="4"/>')
            canvas.lines((left + right) / 2, y + height / 2, texts)
            y += height + 14
        elif kind == "fragment":
            name, branches = value, extra
            start, left, right = y, min(x.values()) - column * 0.45 + depth * 8, max(x.values()) + column * 0.45 - depth * 8
            y += 44
            separators = []
            for number, (label, inner) in enumerate(branches):
                if number:
                    separators.append((y, label))
                    y += 40
                elif label:
                    canvas.text(left + 58, start + 17, f"[{label}]", "start", "muted")
                y = _sequence_draw(canvas, inner, x, y, column, depth + 1)
            canvas.add(f'<rect class="frag" x="{left:.1f}" y="{start:.1f}" width="{right - left:.1f}" '
                       f'height="{y - start:.1f}" rx="4"/>')
            canvas.add(f'<path class="frag" d="M{left:.1f},{start + 22:.1f} h44 l8,-8 v-14"/>')
            canvas.text(left + 6, start + 16, name, "start", "title")
            for line_y, label in separators:
                canvas.add(f'<line class="frag dash" x1="{left:.1f}" y1="{line_y:.1f}" x2="{right:.1f}" y2="{line_y:.1f}"/>')
                canvas.text(left + 10, line_y + 15, f"[{label}]", "start", "muted")
            y += 12
        else:
            step = value
            a, b = x[step["from"]], x[step["to"]]
            label = step.get("label", "")
            style = " dash" if step.get("kind") == "reply" else ""
            marker = "url(#open)" if step.get("kind") == "async" else "url(#arrow)"
            if a == b or step.get("kind") == "self":
                canvas.add(f'<path class="e{style}" d="M{a:.1f},{y:.1f} h34 v18 h-30" marker-end="{marker}"/>')
                canvas.text(a + 42, y + 13, label, "start", "muted")
                y += 40
                continue
            rows_text = wrap(label, max(int(abs(b - a) / 7.6) - 2, 14))
            # Reserve the label's height first, so a wrapped label never climbs into the row above.
            y += (len(rows_text) - 1) * LINE
            for index, row in enumerate(rows_text):
                canvas.text((a + b) / 2, y - 6 - (len(rows_text) - 1 - index) * LINE, row)
            end = b - 2 if b > a else b + 2
            canvas.add(f'<line class="e{style}" x1="{a:.1f}" y1="{y:.1f}" x2="{end:.1f}" y2="{y:.1f}" marker-end="{marker}"/>')
            y += 34
    return y


def _usecase(source, title, question):
    actors, usecases = source.get("actors", []), source.get("usecases", [])
    if not actors or not usecases:
        raise ViewError("a use-case view needs actors and use cases")
    known_actors, known_cases = {a["id"] for a in actors}, {u["id"] for u in usecases}
    for link in source.get("links", []):
        if link["actor"] not in known_actors or link["usecase"] not in known_cases:
            raise ViewError(f"link {link['actor']} -> {link['usecase']} names an undeclared actor or use case")
    for relation in source.get("relations", []):
        if relation["from"] not in known_cases or relation["to"] not in known_cases:
            raise ViewError(f"{relation['kind']} {relation['from']} -> {relation['to']} names an undeclared use case")
    sizes = {u["id"]: (max(max(text_width(r) for r in wrap(u["label"], 24)) + 56, 150),
                       len(wrap(u["label"], 24)) * LINE + 26) for u in usecases}
    ellipse_w = max(s[0] for s in sizes.values())
    left_actors = [a for a in actors if a.get("side", "left") == "left"]
    right_actors = [a for a in actors if a.get("side") == "right"]
    actor_w = 120
    box_left = 30 + (actor_w if left_actors else 0) + 40
    box_w = ellipse_w + 80
    centers, y = {}, 76
    for usecase in usecases:
        centers[usecase["id"]] = (box_left + box_w / 2, y + sizes[usecase["id"]][1] / 2)
        y += sizes[usecase["id"]][1] + 22
    box_h = y - 40
    canvas = Canvas()
    canvas.add(f'<rect class="g" x="{box_left:.1f}" y="30" width="{box_w:.1f}" height="{box_h:.1f}" rx="12"/>')
    canvas.text(box_left + box_w / 2, 52, source.get("system", "System"), "middle", "title")
    actor_pos = {}
    for side, group in (("left", left_actors), ("right", right_actors)):
        ax = 30 + actor_w / 2 if side == "left" else box_left + box_w + 40 + actor_w / 2
        floor = 40
        for actor in group:
            # Level with the use cases the actor pursues, never closer than one actor height to the last.
            linked = [centers[l["usecase"]][1] for l in source.get("links", []) if l["actor"] == actor["id"]]
            wanted = sum(linked) / len(linked) - 12 if linked else floor
            actor_pos[actor["id"]] = (ax, max(wanted, floor))
            floor = actor_pos[actor["id"]][1] + 96
    for link in source.get("links", []):
        (ax, ay), (ux, uy) = actor_pos[link["actor"]], centers[link["usecase"]]
        rx = sizes[link["usecase"]][0] / 2
        edge_x = ux - rx if ax < ux else ux + rx
        start_x = ax + 26 if ax < ux else ax - 26
        canvas.add(f'<line class="e" x1="{start_x:.1f}" y1="{ay:.1f}" x2="{edge_x:.1f}" y2="{uy:.1f}"/>')
    for relation in source.get("relations", []):
        (fx, fy), (tx, ty) = centers[relation["from"]], centers[relation["to"]]
        side = box_left + box_w - 18
        start = (fx + sizes[relation["from"]][0] / 2 - 6, fy)
        end = (tx + sizes[relation["to"]][0] / 2 - 6, ty)
        canvas.add(f'<path class="e dash" d="M{start[0]:.1f},{start[1]:.1f} C{side + 24:.1f},{fy:.1f} {side + 24:.1f},'
                   f'{ty:.1f} {end[0]:.1f},{end[1]:.1f}" marker-end="url(#open)"/>')
        canvas.label(side + 10, (fy + ty) / 2, f"«{relation['kind']}»")
    for usecase in usecases:
        cx, cy = centers[usecase["id"]]
        w, h = sizes[usecase["id"]]
        canvas.add(f'<ellipse class="n" cx="{cx:.1f}" cy="{cy:.1f}" rx="{w / 2:.1f}" ry="{h / 2:.1f}"/>')
        canvas.lines(cx, cy, wrap(usecase["label"], 24))
    for actor in actors:
        ax, ay = actor_pos[actor["id"]]
        _shape(canvas, {"id": actor["id"], "label": actor["label"], "shape": "actor"}, (ax, ay),
               (actor_w, LINE * len(wrap(actor["label"])) + 52))
    width = box_left + box_w + (40 + actor_w if right_actors else 0) + 30
    lowest = max(y for _, y in actor_pos.values()) + LINE * 3 + 40
    return canvas.svg(width, max(box_h + 60, lowest), title, question)


CATALOG_FORMAT = "project-doc-views/0.1"
CATALOG_SCHEMA = {
    "type": "object", "required": ["format", "views"], "additionalProperties": False,
    "properties": {"format": {"const": CATALOG_FORMAT}, "views": {"type": "array", "maxItems": 200, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "kind", "title", "question", "claim", "canonical_ids", "source_path", "scope"],
        "properties": {"id": {"type": "string", "pattern": "^VIEW-[A-Z0-9-]{1,40}$"},
                       "kind": {"enum": ["system", "process", "sequence", "usecase", "state", "domain"]},
                       "title": _text, "question": _text, "audience": _label,
                       "claim": {"enum": ["proposed", "intended", "observed"]},
                       "canonical_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                       "source_path": {"type": "string", "pattern": "^docs/views/[a-z0-9-]+\\.json$"},
                       "scope": {"type": "string", "maxLength": 1000}, "review": _label}}}}}


def catalog(root):
    """The validated view catalog, or an empty one when the project has none yet."""
    path = Path(root) / VIEW_CATALOG
    if not path.is_file():
        return {"format": CATALOG_FORMAT, "views": []}
    value = load(path)
    problems = Validator(CATALOG_SCHEMA).errors(value)
    if problems:
        raise ViewError(f"{VIEW_CATALOG} invalid at {problems[0][0] or '/'}: {problems[0][1]}")
    ids = [v["id"] for v in value["views"]]
    if len(ids) != len(set(ids)):
        raise ViewError(f"{VIEW_CATALOG}: view IDs repeat")
    return value


def rendered(root, model=None):
    """{relative output path: SVG text} for every catalogued view, or a ViewError naming the first bad one."""
    outputs = {}
    for view in catalog(root)["views"]:
        try:
            source = load(Path(root) / view["source_path"])
            svg = render(source, view["title"], view["question"], model)
        except (InputError, ViewError) as error:
            raise ViewError(f"{view['id']} ({view['source_path']}): {error}") from None
        outputs[f"{GENERATED.as_posix()}/diagrams/{view['id']}.svg"] = svg
    return outputs


def listed_outputs(root):
    """The paths the docs manifest says the generator wrote, or None when there is no valid manifest."""
    try:
        manifest = json.loads((Path(root) / GENERATED / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("format") != "aeion-docs-manifest/0.1":
        return None
    outputs = manifest.get("outputs")
    return {rel for rel in outputs if isinstance(rel, str)} if isinstance(outputs, (dict, list)) else set()


def generator_owns(root, rel, listed):
    """Whether a file under docs/generated/ is the generator's: the manifest lists it, or it is an SVG with
    the mark. A project's own file there is never overwritten, deleted or reported as stale."""
    if rel in (listed or ()) or (listed is not None and rel == f"{GENERATED.as_posix()}/manifest.json"):
        return True
    if not rel.endswith(".svg"):
        return False
    try:
        with open(Path(root) / rel, encoding="utf-8", errors="replace") as handle:
            return MARK in handle.read(400)
    except OSError:
        return False


def render_all(root, check=False, model=None):
    """Write (or, with check, compare) every view's SVG; returns problems, empty when all is current."""
    if model is None:
        model = _model(root)
    try:
        outputs = rendered(root, model)
    except (InputError, ViewError) as error:
        return [f"views: {error}"]
    problems = []
    folder = Path(root) / GENERATED / "diagrams"
    existing = {p.relative_to(root).as_posix() for p in folder.glob("*.svg")} if folder.is_dir() else set()
    listed = listed_outputs(root)
    for rel, svg in sorted(outputs.items()):
        path = Path(root) / rel
        current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
        if current == svg:
            continue
        if current is not None and not generator_owns(root, rel, listed):
            problems.append(f"views: {rel} exists and was not generated; move it before its view is rendered there")
            continue
        if check:
            problems.append(f"views: {rel} is {'missing' if current is None else 'stale'} (run tools/axiom/axiom views)")
        else:
            write_atomic(path, svg)
    for rel in sorted(existing - set(outputs)):
        if not generator_owns(root, rel, listed):
            continue
        if check:
            problems.append(f"views: {rel} has no catalogued view (run tools/axiom/axiom views)")
        else:
            (Path(root) / rel).unlink()
    return problems


def _model(root):
    import spec as specs
    from common import SPEC_PATH
    path = Path(root) / SPEC_PATH
    if not path.is_file():
        return None
    result = specs.Result()
    loaded = specs.load_spec(path, result)
    return specs.Model(loaded) if loaded else None


def svg_of(source_text, title="View", question=""):
    """Render a JSON source given as text (used by tools that preview a proposed view)."""
    return render(json.loads(source_text), title, question)
