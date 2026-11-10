# Spec: knowledge/components/goldfish.md
"""Section 1, design documents: draft section by section with approval gates (egm-draft), review in five
Goldfish stages (egm-review) and resolve the findings with the Elephant (egm-resolve). An edit is
applied only when its exact text occurs once in the document, so a fix can never land in the wrong place."""
import re
from datetime import date

from . import goldfish
from .agents import Submit, streaming
from .store import StoreError, now

SECTIONS = [
    ("Overview & Goals", "## Overview, ## The Problem, ## Goals, ## Non-Goals, ## Open Questions and "
                         "## Critical User Journeys (CUJs) with Given/When/Then for each journey"),
    ("Technical Plan", "## Technical Plan (Architecture) with the components, data flow and interfaces, an "
                       "ASCII or Mermaid block diagram, then ## Non-Functional Requirements (security and privacy, "
                       "performance, rollout and rollback) or 'None' when nothing is critical"),
    ("Alternatives Considered", "## Alternatives Considered: each alternative with Pros, Cons and 'Reason for "
                                "Rejection' written as 'Rejected by author: <technical rationale>'"),
    ("Detailed Implementation Plan", "## Detailed Implementation Plan: ### Target Files to Create/Modify, every "
                                     "file with Type/Scope and Proposed Changes (no code, signatures and schemas "
                                     "allowed), then ### Verification Plan (build, unit, lint, coverage, E2E)"),
]
RECONCILE = {"type": "object", "required": ["contradictions", "additions"], "additionalProperties": False,
             "properties": {key: {"type": "array", "maxItems": 30, "items": {
                 "type": "object", "required": ["brief", "draft", "question"], "additionalProperties": False,
                 "properties": {"brief": {"type": "string", "maxLength": 1000}, "draft": {"type": "string", "maxLength": 1000},
                                "question": {"type": "string", "maxLength": 600}}}} for key in ("contradictions", "additions")}}


def create_draft(store, source_feature=None, title=None, notes=""):
    """A draft session from a saved brief (preferred), or from the owner's notes."""
    context, origin = notes.strip(), "notes"
    if source_feature:
        meta, context = store.feature(source_feature)
        title, origin = title or meta["title"], f"feature:{source_feature}"
    if not context:
        raise StoreError("give a saved brief or some notes to draft from")
    name = store.new_name("sessions", title or "design")
    session = {"id": name, "kind": "draft", "title": title or "Design", "author": "owner", "state": "drafting",
               "context": context, "origin": origin, "current": 0, "messages": [], "feature": None, "created": now(),
               "sections": [{"name": n, "status": "pending", "markdown": "", "question": None} for n, _ in SECTIONS]}
    return store.save_session(session)


def _ask_owner(data, run):
    run.state["question"] = data["question"].strip()
    return "Question recorded for the owner. Stop now.", True


def draft_section(store, client, name, instruction="", emit=lambda e: None):
    """Draft (or redraft with the owner's instruction) the current section, or ask the owner one question."""
    session = store.session(name)
    index = session["current"]
    if index >= len(SECTIONS):
        raise StoreError("every section is approved: save the design")
    section = session["sections"][index]
    approved = "\n\n".join(s["markdown"] for s in session["sections"][:index])
    blocks = [{"tag": "predecessor", "body": session["context"]}]
    if approved:
        blocks.append({"tag": "approved_sections", "body": approved})
    if section["markdown"]:
        blocks.append({"tag": "current_draft", "body": section["markdown"]})
    if section["question"] and instruction.strip():
        blocks.append({"tag": "your_question", "body": section["question"]})
    message = f"Write the section '{SECTIONS[index][0]}': {SECTIONS[index][1]}."
    if instruction.strip():
        session["messages"].append({"role": "user", "content": instruction.strip(), "at": now(), "section": index})
        message += f"\n\nThe owner's instruction or answer: {instruction.strip()}"
    result = client.run("drafter", message, blocks=blocks, tools={"ask_owner": _ask_owner}, session=name, **streaming(emit))
    question = result.state.get("question")
    if question:
        section["question"], section["status"] = question, "question"
    elif result.text.strip():
        section["markdown"], section["question"], section["status"] = result.text.strip(), None, "drafted"
    else:
        raise StoreError("the Elephant returned neither a section nor a question; try again")
    session["messages"].append({"role": "assistant", "content": section["question"] or f"Drafted {section['name']}.",
                                "at": now(), "section": index})
    store.save_session(session)
    emit({"type": "section", "index": index, "section": section})
    return session


def approve_section(store, name):
    session = store.session(name)
    section = session["sections"][session["current"]]
    if section["status"] != "drafted":
        raise StoreError("draft the section (or answer its question) before approving it")
    section["status"] = "approved"
    session["current"] += 1
    if session["current"] == len(SECTIONS):
        session["state"] = "complete"
    return store.save_session(session)


def document(session):
    header = (f"# {session['title']}\n\n*   **Author:** {session['author']}\n*   **Status:** Draft\n"
              f"*   **Date:** {date.today().isoformat()}\n\n---\n\n")
    return header + "\n\n".join(s["markdown"] for s in session["sections"] if s["markdown"]) + "\n\n*Drafted with EGM in aeion-core*\n"


def reconcile(store, client, name):
    """Step 6.1: contradictions between the brief and the draft, for the owner to decide; nothing is changed."""
    session = store.session(name)
    if session["origin"] == "notes":
        return {"contradictions": [], "additions": []}
    result = client.run("reconciler", "Compare the attached brief with the attached design draft.",
                        blocks=[{"tag": "brief", "body": session["context"]}, {"tag": "design_draft", "body": document(session)}],
                        submits=[Submit("submit_reconciliation", RECONCILE)], require="submit_reconciliation", session=name)
    value = result.submissions["submit_reconciliation"]
    session["reconcile"] = value
    store.save_session(session)
    return value


def save_draft(store, name):
    session = store.session(name)
    if session["state"] != "complete":
        raise StoreError("approve every section first")
    meta = store.save_feature(session["title"], document(session), "design", f"draft:{name}", name=session.get("feature"))
    session["feature"], session["state"] = meta["id"], "final"
    store.save_session(session)
    return meta


def create_review(store, feature, preset="interactive"):
    """A review of a saved document; the semantic split separates the feature spec from the implementation plan."""
    if preset not in goldfish.PRESETS:
        raise StoreError(f"unknown preset {preset!r}")
    meta, text = store.feature(feature)
    feature_range, detailed_range = goldfish.split(text)
    stages = [s for s in goldfish.STAGES if s["number"] in goldfish.PRESETS[preset]]
    if preset == "feature_spec":
        feature_range, detailed_range = (1, text.count("\n") + 1), None
    name = store.new_name("sessions", f"review {meta['title']}")
    session = {"id": name, "kind": "review", "title": f"Review: {meta['title']}", "feature": feature, "preset": preset,
               "state": "ready", "document": text, "ranges": {"feature": feature_range, "detailed": detailed_range},
               "stages": [{"number": s["number"], "name": s["name"], "status": "pending", "audits": 0} for s in stages],
               "current": 0, "created": now()}
    return store.save_session(session)


def _range(session, kind):
    total = session["document"].count("\n") + 1
    if kind == "full":
        return (1, total)
    return tuple(session["ranges"][kind]) if session["ranges"][kind] else None


def run_stage(store, client, name, emit=lambda e: None):
    """Run the current stage's reviewers in parallel and write its report; consolidated runs them all."""
    session = store.session(name)
    while session["current"] < len(session["stages"]):
        entry = session["stages"][session["current"]]
        stage = next(s for s in goldfish.STAGES if s["number"] == entry["number"])
        line_range = _range(session, stage["range"])
        emit({"type": "stage", "number": stage["number"], "name": stage["name"]})
        if line_range is None:
            entry.update(status="skipped", report="No implementation plan was found: this stage reviews nothing.",
                         findings=[], results=[])
        else:
            results = goldfish.run_all(client, stage["reviewers"], "REVIEW", session["document"], line_range=line_range,
                                       standards=stage["standards"], on_event=emit, session=name)
            for r in results:
                r["raw"] = bool(stage.get("raw"))
            items = goldfish.findings(client, session["feature"], line_range, results, session=name)
            entry.update(status="done", results=results, findings=items, audits=entry["audits"] + 1,
                         report=goldfish.report_markdown(session["feature"], line_range, stage["name"], results, items))
        emit({"type": "stage_done", "number": stage["number"], "report": entry["report"]})
        if session["preset"] != "consolidated":
            session["state"] = "gate"
            break
        session["current"] += 1
    else:
        session["state"] = "complete"
        session["consolidated"] = consolidated(session)
    store.save_session(session)
    return session


def consolidated(session):
    """All stage findings by priority with a traceability table (the uninterrupted flow's report)."""
    rows, items = [], []
    for stage in session["stages"]:
        for finding in stage.get("findings", []):
            items.append((stage, finding))
    order = {"Blocker": 0, "Major": 1, "Nit": 2}
    items.sort(key=lambda pair: order[pair[1]["severity"]])
    lines = [f"# Consolidated review: {session['title']}", "", "## Action items", ""]
    for index, (stage, finding) in enumerate(items, 1):
        lines.append(f"{index}. **{finding['severity']}**: {finding['title']} ({finding['scope']}): {finding['recommendation']}")
        rows.append(f"| {index} | {stage['number']} {stage['name']} | `{finding['reviewer']}` | {finding['title']} |")
    if not items:
        lines.append("No finding across the stages.")
    lines += ["", "## Traceability", "", "| Item | Stage | Reviewer | Raw finding |", "| --- | --- | --- | --- |", *rows]
    return "\n".join(lines) + "\n"


def gate(store, name, action):
    """After an interactive stage: proceed, rerun once after edits, or pause."""
    session = store.session(name)
    if action == "proceed":
        session["current"] += 1
        session["state"] = "complete" if session["current"] >= len(session["stages"]) else "ready"
    elif action == "rerun":
        entry = session["stages"][session["current"]]
        if entry["audits"] >= 2:
            raise StoreError("this stage was re-audited once already; residual findings are accepted trade-offs")
        _, session["document"] = store.feature(session["feature"])
        session["ranges"]["feature"], session["ranges"]["detailed"] = goldfish.split(session["document"])
        session["state"] = "ready"
    elif action == "pause":
        session["state"] = "paused"
    else:
        raise StoreError(f"unknown action {action!r}")
    return store.save_session(session)


RESOLUTION = {"type": "object", "required": ["items"], "additionalProperties": False, "properties": {"items": {
    "type": "array", "maxItems": 40, "items": {
        "type": "object", "required": ["index", "category", "justification", "find", "replace"], "additionalProperties": False,
        "properties": {"index": {"type": "integer", "minimum": 1, "maximum": 40},
                       "category": {"enum": ["CONTEST", "ESCALATE", "PROPOSE FIX", "DECLINE"]},
                       "justification": {"type": "string", "minLength": 1, "maxLength": 2000},
                       "find": {"type": "string", "maxLength": 4000}, "replace": {"type": "string", "maxLength": 6000}}}}}}
def resolve(store, client, name, stage_number):
    """The resolver agent categorizes every finding; an edit is applicable only when its text occurs once."""
    session = store.session(name)
    entry = next(s for s in session["stages"] if s["number"] == stage_number)
    findings = entry.get("findings") or []
    if not findings:
        raise StoreError("this stage has no finding to resolve")
    listing = "\n\n".join(f"{i}. [{f['severity']}] {f['title']} ({f['reviewer']}, {f['scope']}): {f['description']} "
                           f"Recommendation: {f['recommendation']}" for i, f in enumerate(findings, 1))

    def check(value):
        # Every finding answered once; every proposed edit lands in exactly one place.
        problems, seen = [], [item["index"] for item in value["items"]]
        missing = sorted(set(range(1, len(findings) + 1)) - set(seen))
        if missing:
            problems.append(f"no item for finding(s) {missing}")
        for item in value["items"]:
            if item["index"] > len(findings):
                problems.append(f"finding {item['index']} does not exist")
            if item["category"] == "PROPOSE FIX" and session["document"].count(item["find"]) != 1:
                problems.append(f"finding {item['index']}: the find text occurs {session['document'].count(item['find'])} "
                                "times; copy a longer passage that occurs exactly once")
        return problems
    result = client.run("resolver", "Resolve every attached finding.",
                        blocks=[{"tag": "document", "body": session["document"]}, {"tag": "findings", "body": listing}],
                        submits=[Submit("submit_resolution", RESOLUTION, check=check)], require="submit_resolution",
                        session=name)
    items = []
    for item in result.submissions["submit_resolution"]["items"]:
        if not 1 <= item["index"] <= len(findings):
            continue
        count = session["document"].count(item["find"]) if item["find"] else 0
        item["applicable"] = item["category"] == "PROPOSE FIX" and count == 1
        item["finding"] = findings[item["index"] - 1]
        items.append(item)
    entry["resolution"] = sorted(items, key=lambda i: i["index"])
    store.save_session(session)
    return entry["resolution"]


def apply(store, name, stage_number, accepted):
    """Apply the accepted PROPOSE FIX edits in order; save the document as a new version of the feature."""
    session = store.session(name)
    entry = next(s for s in session["stages"] if s["number"] == stage_number)
    text, applied, refused = session["document"], [], []
    for item in entry.get("resolution", []):
        if item["index"] not in accepted:
            continue
        if item["category"] != "PROPOSE FIX" or text.count(item["find"]) != 1:
            refused.append(item["index"])
            continue
        text = text.replace(item["find"], item["replace"], 1)
        applied.append(item["index"])
    if applied:
        meta, _ = store.feature(session["feature"])
        store.save_feature(meta["title"], text, meta["kind"], meta["origin"], name=session["feature"])
        session["document"] = text
        session["ranges"]["feature"], session["ranges"]["detailed"] = goldfish.split(text)
    entry["applied"] = applied
    store.save_session(session)
    return {"applied": applied, "refused": refused}
