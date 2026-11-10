---
name: aeion-views
description: How to choose and write the diagrams of a feature - system, process, sequence and use case - in the aeion-view/0.1 source format that the template renders to SVG. Use before proposing diagrams.
---

# Propose feature diagrams

Choose one to three diagrams that help a reader understand the feature, only those it needs:

- **system**: context or components, and what talks to what (a `flow` source).
- **process**: decisions and refusals in order (a `flow` source with `decision` nodes).
- **sequence**: who calls whom, in which order, with `alt` branches for refusals.
- **usecase**: actors and the goals they reach through the system.

## Source format (aeion-view/0.1)

Flow:
```json
{"kind": "flow", "direction": "LR", "nodes": [{"id": "sender", "label": "Digest sender", "shape": "box"}],
 "edges": [{"from": "sender", "to": "provider", "label": "send"}]}
```
Shapes: `box`, `round`, `decision`, `store`, `actor`, `external`, `start`, `end`. Direction `LR` or `TB`.

Sequence:
```json
{"kind": "sequence", "participants": [{"id": "member", "label": "Member", "type": "actor"}],
 "steps": [{"from": "member", "to": "api", "label": "unsubscribe", "kind": "sync"},
           {"note": "token checked", "over": ["api"]},
           {"fragment": "alt", "branches": [{"label": "valid token", "steps": []}, {"label": "invalid", "steps": []}]}]}
```
Participant types: `actor`, `participant`, `store`. Step kinds: `sync`, `async`, `reply`.

Use case:
```json
{"kind": "usecase", "system": "Forum", "actors": [{"id": "member", "label": "Member", "side": "left"}],
 "usecases": [{"id": "read", "label": "Read the digest"}], "links": [{"actor": "member", "usecase": "read"}]}
```

Rules: IDs are short lowercase words; at most 10 boxes per diagram; labels say what the reader needs,
not internal names. Each diagram answers one question, stated in its `question` field. The server renders
every proposal; a refusal names the problem, fix it and submit again.
